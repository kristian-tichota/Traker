import threading

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QAbstractAnimation, QEvent, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QKeyEvent
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

import src.profile as profile_module
from src.desktop import rest_positions, rest_queue
from src.desktop.activities import (ANY_DECK, BOOK, DECK, DOCUMENT, PAGE, SHELF, VIDEO,
                                    BreakActivity)
from src.domain.media import Place
from src.gui.commands import COMMANDS
from src.gui.views import pomodoro_view
from src.config import PALETTE
from src.gui.components.book_pane import BookPane
from src.gui.components.media_surface import DeckPane, LibraryPane
from src.gui.components.upcoming_panel import UpcomingPanel
from src.gui.views.pomodoro_view import RELEASE_KEY, PomodoroView, StrictOverlay
from tests.anki_double import FakeAnki
from tests.gui.conftest import advance

pytestmark = [pytest.mark.gui, pytest.mark.exact, pytest.mark.accessibility]

ACTIVITIES_TOML = """
[[strict_break.activities]]
name = "Reading"
path = "/x/reading.pdf"

[[strict_break.activities]]
name = "Something to watch"
path = "/x/rest.mp4"
"""

DECK_TOML = """
[[strict_break.activities]]
name = "Japanese"
deck = "Japanese"

[[strict_break.activities]]
name = "Anki"
deck = "*"
"""

PAGE_URL = "http://127.0.0.1:9743/?via=break"

PAGE_TOML = f"""
[[strict_break.activities]]
name = "Tutor"
url = "{PAGE_URL}"
"""


class FakePane(QWidget):
    def __init__(self, activity, start_at=0, parent=None):
        super().__init__(parent)
        self.activity = activity
        self.start_at = start_at
        self.calls = []
        self.opens = []
        self.at = start_at
        self.of = 0

    def open(self, path, start_at=0):
        self.opens.append((path, start_at))
        self.start_at = start_at
        self.at = start_at

    def toggle(self):
        self.calls.append("toggle")

    def step(self, direction):
        self.calls.append(("step", direction))

    def nudge(self, direction):
        self.calls.append(("nudge", direction))

    def position(self):
        return self.at

    def duration(self):
        return self.of

    def stop(self):
        self.calls.append("stop")


class FakeDeckPane(FakePane):
    changed = pyqtSignal()

    def __init__(self, activity, start_at=0, parent=None):
        super().__init__(activity, start_at, parent)
        self.choosing = self.from_list = activity.path == ANY_DECK
        self.deck = ""

    def open(self, path, start_at=0):
        super().open(path, start_at)
        self.choosing = self.from_list = path == ANY_DECK

    def undo(self):
        self.calls.append("undo")

    def back(self):
        self.calls.append("back")
        if not self.from_list or self.choosing:
            return False
        self.choosing = True
        return True

    def title(self):
        return self.deck


class FakeBookPane(FakePane):
    rtl = False

    def turn(self, direction):
        self.calls.append(("turn", direction))

    def undo(self):
        self.calls.append("undo")


class Panes:
    def __init__(self):
        self.built = []

    def __call__(self, activity, start_at=0, parent=None):
        if activity.kind == SHELF:
            pane = LibraryPane(activity.path, start_at, parent)
        else:
            kind = {DECK: FakeDeckPane, BOOK: FakeBookPane}.get(activity.kind, FakePane)
            pane = kind(activity, start_at, parent)
        self.built.append(pane)
        return pane

    @property
    def last(self):
        return self.built[-1]


def web_pane(activity, start_at=0, parent=None):
    if activity.kind == DECK:
        return DeckPane(activity.path, start_at, parent, client=FakeAnki())
    return BookPane(activity.path, start_at, parent)


class FakeShell(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Traker")


@pytest.fixture
def app_id(qapp):
    previous = QGuiApplication.desktopFileName()
    QGuiApplication.setDesktopFileName("Traker.desktop")
    yield "traker"
    QGuiApplication.setDesktopFileName(previous)


@pytest.fixture
def queue_path(tmp_path):
    return str(tmp_path / "rest-queue.m3u")


@pytest.fixture
def with_activities(strict_timer, queue_path):
    written = strict_timer.read_text()
    assert '[strict_break.queue]\npath = ""' in written, \
        "the [strict_break.queue] template no longer says this"
    written = written.replace('[strict_break.queue]\npath = ""',
                              f'[strict_break.queue]\npath = "{queue_path}"')
    strict_timer.write_text(written + ACTIVITIES_TOML, encoding="utf-8")
    profile_module.reload_profile()
    return strict_timer


@pytest.fixture
def with_no_wait(with_activities):
    written = with_activities.read_text(encoding="utf-8")
    assert "away_secs = 300" in written, \
        "the [strict_break] template no longer says this"
    with_activities.write_text(written.replace("away_secs = 300", "away_secs = 0"),
                               encoding="utf-8")
    profile_module.reload_profile()
    return with_activities


def a_view(db):
    shell = FakeShell()
    view = PomodoroView(db, tray_icon=None)
    view.setParent(shell)
    view.refresh_timer.stop()
    view.stress_calendar.anim_timer.stop()
    view.last_logged_minute = -1
    view.media_pane_factory = Panes()
    yield view
    view.shutdown()
    QThreadPool.globalInstance().waitForDone(2000)
    shell.deleteLater()


@pytest.fixture
def with_a_deck(with_no_wait):
    with_no_wait.write_text(with_no_wait.read_text(encoding="utf-8") + DECK_TOML,
                            encoding="utf-8")
    profile_module.reload_profile()
    return with_no_wait


@pytest.fixture
def with_a_page(with_no_wait):
    with_no_wait.write_text(with_no_wait.read_text(encoding="utf-8") + PAGE_TOML,
                            encoding="utf-8")
    profile_module.reload_profile()
    return with_no_wait


@pytest.fixture
def media(tmp_path):
    folder = tmp_path / "Media"
    for name in ("Books/a.epub", "Books/b.epub", "Videos/e1.mkv", "Videos/e2.mkv"):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(b"")
    return folder


@pytest.fixture
def with_library(with_activities, media):
    written = with_activities.read_text(encoding="utf-8")
    assert '[strict_break.library]\npath = ""' in written, \
        "the [strict_break.library] template no longer says this"
    with_activities.write_text(written.replace(
        '[strict_break.library]\npath = ""', f'[strict_break.library]\npath = "{media}"'),
        encoding="utf-8")
    profile_module.reload_profile()
    return with_activities


@pytest.fixture
def timer(qapp, app_id, with_activities, recording_db):
    yield from a_view(recording_db)


@pytest.fixture
def library_timer(qapp, app_id, with_library, recording_db):
    yield from a_view(recording_db)


@pytest.fixture
def deck_timer(qapp, app_id, with_a_deck, recording_db):
    yield from a_view(recording_db)


@pytest.fixture
def page_timer(qapp, app_id, with_a_page, recording_db):
    yield from a_view(recording_db)


@pytest.fixture
def timer_that_never_waits(qapp, app_id, with_no_wait, recording_db):
    yield from a_view(recording_db)


@pytest.fixture
def said(monkeypatch, desktop_session):
    desktop_session.inhibit_cookie = None
    posted = []
    monkeypatch.setattr(pomodoro_view.notify_service, "notify",
                        lambda summary, body, **kw: posted.append((summary, body)))
    return posted


def enter_strict_break(view, past_the_wait=True):
    view._skip_phase()
    if past_the_wait:
        view.time_left_ms -= view.away_ms()
        view._say_when_the_offers_open()
    assert view.holds_the_screens()


def enter_with_the_shelves(view):
    enter_strict_break(view)
    QThreadPool.globalInstance().waitForDone(2000)
    QApplication.processEvents()


def send_key(target, key):
    QApplication.sendEvent(target, QKeyEvent(
        QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def covered_screen(view):
    overlay = StrictOverlay(view, QApplication.primaryScreen())
    view.overlays.append(overlay)
    return overlay


def two_screens(view):
    screen = QApplication.primaryScreen()
    view.screens_to_cover = lambda: [screen, screen]


def corner_colour(widget) -> str:
    QApplication.processEvents()
    return widget.grab().toImage().pixelColor(2, 2).name()


def showing_pane(view):
    return view.media_surface.pane if view.media_surface is not None else None


class TestNothingIsShownUnasked:
    def test_a_break_beginning_shows_nothing(self, timer):
        enter_strict_break(timer)

        assert timer._showing is None
        assert timer.media_pane_factory.built == []
        assert timer._media_host.is_showing_media() is False

    def test_only_what_the_profile_names_can_be_shown(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_3)

        assert timer._showing is None
        assert timer.media_pane_factory.built == []

    def test_a_profile_naming_none_offers_none(self, qapp, app_id, profile_path,
                                               recording_db):
        view = PomodoroView(recording_db, tray_icon=None)
        view.refresh_timer.stop()
        view.stress_calendar.anim_timer.stop()

        assert view.activities == []
        assert view.take_offers() == []
        assert view.offer_section() == []
        assert view._offer_index(Qt.Key.Key_Return) is None

        view.shutdown()
        QThreadPool.globalInstance().waitForDone(2000)
        view.deleteLater()

    def test_a_key_with_no_activity_behind_it_is_not_swallowed(self, timer):
        enter_strict_break(timer)

        assert timer._offer_index(Qt.Key.Key_9) is None
        assert timer._offer_index(Qt.Key.Key_A) is None

    def test_the_keys_do_nothing_outside_a_held_break(self, timer):
        send_key(timer, Qt.Key.Key_Return)

        assert timer._showing is None
        assert timer.media_surface is None

    @pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_2,
                                     Qt.Key.Key_Space, Qt.Key.Key_Right])
    def test_a_key_delivered_to_a_text_field_is_left_to_it(self, timer, key):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        typing = QLineEdit(timer.window())
        typing.setText(":log 2 Rolled Oats")
        before = list(timer.media_pane_factory.last.calls)

        taken = timer.eventFilter(typing, QKeyEvent(
            QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

        assert taken is False
        assert timer.media_pane_factory.last.calls == before

    def test_the_exit_is_taken_from_a_text_field_all_the_same(self, timer):
        enter_strict_break(timer)
        typing = QLineEdit(timer.window())

        taken = timer.eventFilter(typing, QKeyEvent(
            QEvent.Type.KeyPress, RELEASE_KEY, Qt.KeyboardModifier.NoModifier))

        assert taken is True
        assert timer._hold_timer.isActive() is True


class TestTheFirstMinutesAreAwayFromTheScreen:
    @pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_2])
    def test_an_offers_key_does_nothing_until_the_wait_is_up(self, timer, key):
        enter_strict_break(timer, past_the_wait=False)

        send_key(timer, key)

        assert timer._showing is None
        assert timer.media_pane_factory.built == []
        assert timer._media_host.is_showing_media() is False

    def test_a_queued_path_is_held_back_the_same_way(self, timer, queue_path):
        rest_queue.append("/x/queued.mp4", queue_path)
        enter_strict_break(timer, past_the_wait=False)

        send_key(timer, Qt.Key.Key_Return)

        assert timer._showing is None

    def test_the_wait_is_five_minutes_of_an_ordinary_break(self, timer):
        enter_strict_break(timer, past_the_wait=False)

        assert timer.away_ms() == 300_000
        assert timer.opens_in_ms() == 300_000

    def test_a_second_short_of_it_is_still_held(self, timer, said):
        enter_strict_break(timer, past_the_wait=False)
        advance(timer, timer.away_ms() - 1_000)

        send_key(timer, Qt.Key.Key_Return)

        assert timer._showing is None
        assert timer.opens_in_ms() == 1_000

    def test_and_the_moment_it_is_up_the_key_works(self, timer, said):
        enter_strict_break(timer, past_the_wait=False)
        advance(timer, timer.away_ms())

        send_key(timer, Qt.Key.Key_Return)

        assert timer._showing is timer._offers[0]
        assert timer.opens_in_ms() == 0

    def test_a_long_break_is_longer_away_from_the_screen(self, timer):
        timer.set_long_break_queued(True)
        enter_strict_break(timer, past_the_wait=False)

        assert timer.current_phase == "long_break"
        assert timer.away_ms() == 600_000

        advance(timer, 300_000)
        send_key(timer, Qt.Key.Key_Return)

        assert timer._showing is None

    def test_a_profile_that_waits_for_nothing_opens_at_once(
            self, timer_that_never_waits):
        timer = timer_that_never_waits
        enter_strict_break(timer, past_the_wait=False)

        send_key(timer, Qt.Key.Key_Return)

        assert timer.away_ms() == 0
        assert timer._showing is timer._offers[0]

    def test_the_exit_still_costs_the_same_ten_seconds(self, timer):
        enter_strict_break(timer, past_the_wait=False)

        timer.begin_hold()

        assert timer._hold_timer.isActive()

    def test_nothing_of_the_break_is_given_away_by_it(self, timer):
        enter_strict_break(timer, past_the_wait=False)

        send_key(timer, Qt.Key.Key_Return)

        assert timer.holds_the_screens()
        assert timer.btn_play.isEnabled() is False
        assert timer.btn_skip.isEnabled() is False


class TestTheOffersSayWhenTheyOpen:
    def test_the_title_counts_the_wait_down(self, timer, settled):
        enter_strict_break(timer, past_the_wait=False)
        settled()

        assert timer.upcoming.lines()[0] == f"{timer.OFFERS_TITLE}   (OPENS IN 5:00)"

    def test_the_offers_themselves_are_named_throughout(self, timer, settled):
        enter_strict_break(timer, past_the_wait=False)
        settled()

        assert "ENTER  Reading" in timer.upcoming.lines()

    def test_it_goes_on_counting_down_as_the_break_runs(self, timer, settled):
        enter_strict_break(timer, past_the_wait=False)
        settled()

        advance(timer, 29_000)

        assert timer.upcoming.lines()[0] == f"{timer.OFFERS_TITLE}   (OPENS IN 4:31)"

    def test_every_wall_says_the_same_thing(self, timer, settled):
        two_screens(timer)
        enter_strict_break(timer, past_the_wait=False)
        settled()

        for wall in timer.overlays:
            assert wall.upcoming.lines() == timer.upcoming.lines()

    def test_and_the_title_is_bare_once_they_open(self, timer, settled, said):
        enter_strict_break(timer, past_the_wait=False)
        settled()

        advance(timer, timer.away_ms())

        assert timer.upcoming.lines()[0] == timer.OFFERS_TITLE

    def test_a_break_that_waits_for_nothing_never_says_it(
            self, timer_that_never_waits, settled):
        enter_strict_break(timer_that_never_waits, past_the_wait=False)
        settled()

        assert timer_that_never_waits.upcoming.lines()[0] == \
            timer_that_never_waits.OFFERS_TITLE

    def test_a_chore_ticked_during_the_wait_does_not_take_it_off(
            self, timer, settled):
        enter_strict_break(timer, past_the_wait=False)
        settled()

        timer._show_upcoming()

        assert "OPENS IN" in timer.upcoming.lines()[0]


class TestHearingThatTheWaitIsUp:
    def test_it_is_said_when_the_wait_runs_out(self, timer, said):
        enter_strict_break(timer, past_the_wait=False)

        advance(timer, timer.away_ms())

        assert len(said) == 1

    def test_it_names_the_key_and_what_is_behind_it(self, timer, said):
        enter_strict_break(timer, past_the_wait=False)

        advance(timer, timer.away_ms())

        (_, body), = said
        assert "ENTER" in body and "Reading" in body and "5:00" in body

    def test_a_break_holding_notifications_back_leaves_it_to_the_walls(
            self, timer, said, desktop_session):
        desktop_session.inhibit_cookie = 7
        enter_strict_break(timer, past_the_wait=False)

        advance(timer, timer.away_ms())

        assert said == []
        assert timer.offers_note() == ""

    def test_nothing_is_said_while_the_wait_runs(self, timer, said):
        enter_strict_break(timer, past_the_wait=False)

        advance(timer, timer.away_ms() - 1_000)

        assert said == []

    def test_it_is_said_once_a_break_and_not_once_a_frame(self, timer, said):
        enter_strict_break(timer, past_the_wait=False)

        advance(timer, timer.away_ms())
        for _ in range(5):
            advance(timer, 1_000)

        assert len(said) == 1

    def test_a_break_with_nothing_written_down_says_nothing_at_all(
            self, timer, said):
        timer.activities = []
        enter_strict_break(timer, past_the_wait=False)

        advance(timer, timer.away_ms() + 1_000)

        assert timer._offers == []
        assert said == []

    def test_a_break_that_waits_for_nothing_says_nothing_either(
            self, timer_that_never_waits, said):
        enter_strict_break(timer_that_never_waits, past_the_wait=False)

        advance(timer_that_never_waits, 60_000)

        assert said == []

    def test_the_next_break_says_it_again(self, timer, said):
        enter_strict_break(timer, past_the_wait=False)
        advance(timer, timer.away_ms())
        advance(timer, timer.break_ms)
        timer._toggle_timer()

        enter_strict_break(timer, past_the_wait=False)
        advance(timer, timer.away_ms())

        assert len(said) == 2


class TestShowingOne:
    def test_enter_shows_the_first_one_written_down(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert timer._showing.name == "Reading"
        assert timer.media_pane_factory.last.activity.path == "/x/reading.pdf"

    def test_the_rest_are_on_their_own_digits(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_2)

        assert timer._showing.name == "Something to watch"

    def test_a_pdf_is_read_and_anything_else_is_played(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)
        assert timer.media_pane_factory.last.activity.kind == DOCUMENT

        send_key(timer, Qt.Key.Key_2)
        assert timer.media_pane_factory.last.activity.kind == VIDEO

    def test_it_is_shown_inside_the_wall_that_covers_the_primary_screen(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        host = timer._media_host
        assert host in timer.overlays
        assert host.screen_covered is QApplication.primaryScreen()
        assert host.media is timer.media_surface
        assert host.is_showing_media() is True
        assert timer.media_surface.window() is host

    def test_the_application_window_is_not_what_shows_it(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert timer.media_surface.window() is not timer.window()

    def test_the_wall_is_not_given_back(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert timer.overlays
        assert timer._media_host.media is timer.media_surface
        assert timer._strict_engaged is True
        assert timer.holds_the_screens() is True

    def test_pause_and_skip_stay_refused(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert timer.btn_play.isEnabled() is False
        assert timer.btn_skip.isEnabled() is False

    def test_the_covered_screens_go_on_being_covered(self, timer, settled):
        enter_strict_break(timer)
        overlay = covered_screen(timer)
        settled()

        send_key(timer, Qt.Key.Key_Return)

        assert overlay.isVisible() or overlay in timer.overlays
        assert timer.upcoming.lines() == [
            timer.OFFERS_TITLE, "ENTER  Reading", "2  Something to watch"]

    def test_a_second_offer_replaces_the_first(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)
        first = timer.media_pane_factory.last

        send_key(timer, Qt.Key.Key_2)

        assert "stop" in first.calls
        assert timer._showing.name == "Something to watch"
        assert len(timer.media_pane_factory.built) == 2
        assert timer._media_host.is_showing_media() is True

    def test_a_second_offer_of_the_same_kind_re_opens_the_one_pane(self, timer,
                                                                   queue_path):
        rest_queue.append("/tmp/a.mkv", queue_path)
        rest_queue.append("/tmp/b.mkv", queue_path)
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)
        send_key(timer, Qt.Key.Key_2)

        assert len(timer.media_pane_factory.built) == 1
        assert timer.media_pane_factory.last.opens == [("/tmp/b.mkv", 0)]

    def test_a_break_that_covers_no_screen_shows_nothing(self, timer):
        timer.screens_to_cover = lambda: []
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert timer._showing is None
        assert timer.media_surface is None
        assert timer.media_pane_factory.built == []


class TestTheFiveKeys:
    @pytest.fixture
    def showing(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        return timer

    def test_space_pauses_a_video_or_turns_a_page(self, showing):
        send_key(showing, Qt.Key.Key_Space)

        assert showing_pane(showing).calls == ["toggle"]

    @pytest.mark.parametrize("key", [Qt.Key.Key_Right, Qt.Key.Key_PageDown])
    def test_forward_seeks_or_turns_the_page(self, showing, key):
        send_key(showing, key)

        assert showing_pane(showing).calls == [("step", 1)]

    @pytest.mark.parametrize("key", [Qt.Key.Key_Left, Qt.Key.Key_PageUp])
    def test_back_seeks_or_turns_it_back(self, showing, key):
        send_key(showing, key)

        assert showing_pane(showing).calls == [("step", -1)]

    def test_up_and_down_are_volume_or_scroll(self, showing):
        send_key(showing, Qt.Key.Key_Up)
        send_key(showing, Qt.Key.Key_Down)

        assert showing_pane(showing).calls == [("nudge", 1), ("nudge", -1)]

    def test_zero_puts_the_wall_back(self, showing):
        pane = showing_pane(showing)

        send_key(showing, Qt.Key.Key_0)

        assert showing._showing is None
        assert "stop" in pane.calls
        assert showing._media_host.is_showing_media() is False
        assert showing.holds_the_screens() is True

    def test_pressing_its_key_again_while_it_shows_does_nothing(self, showing):
        pane = showing_pane(showing)
        before = list(pane.opens)

        send_key(showing, Qt.Key.Key_Return)

        assert showing_pane(showing) is pane
        assert pane.opens == before
        assert "stop" not in pane.calls
        assert showing._media_host.is_showing_media() is True

    def test_and_its_key_opens_it_again(self, showing):
        pane = showing_pane(showing)
        send_key(showing, Qt.Key.Key_0)

        send_key(showing, Qt.Key.Key_Return)

        assert showing_pane(showing) is pane
        assert showing.media_pane_factory.built == [pane]
        assert showing._media_host.is_showing_media() is True
        assert showing.holds_the_screens() is True
        assert showing.kwin_pin.engaged is True

    def test_closing_it_and_opening_it_again_carries_on_where_it_was(self, showing):
        pane = showing_pane(showing)
        pane.at = 8

        send_key(showing, Qt.Key.Key_0)
        send_key(showing, Qt.Key.Key_Return)

        assert pane.opens == [("/x/reading.pdf", 8)]

    def test_another_offer_can_still_be_opened_while_one_is_showing(self, showing):
        send_key(showing, Qt.Key.Key_2)

        assert showing._showing.name == "Something to watch"

    def test_the_chore_letters_are_still_the_chores(self, showing):
        assert showing._offer_index(Qt.Key.Key_N) is None
        assert showing._drive_media(Qt.Key.Key_N) is False
        assert showing._drive_media(Qt.Key.Key_P) is False

    def test_the_keys_do_nothing_when_nothing_is_showing(self, timer):
        enter_strict_break(timer)

        for key in (Qt.Key.Key_Space, Qt.Key.Key_Right, Qt.Key.Key_0):
            assert timer._drive_media(key) is False

    def test_and_they_do_nothing_again_once_it_is_closed(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)

        send_key(timer, Qt.Key.Key_0)

        for key in (Qt.Key.Key_Space, Qt.Key.Key_Right, Qt.Key.Key_0):
            assert timer._drive_media(key) is False


class TestTheExitStillCostsTheSameSeconds:
    def test_the_hold_starts_while_something_is_showing(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)

        taken = timer.eventFilter(timer.media_surface, QKeyEvent(
            QEvent.Type.KeyPress, RELEASE_KEY, Qt.KeyboardModifier.NoModifier))

        assert taken is True
        assert timer._hold_timer.isActive() is True

    def test_paying_it_gives_the_screens_back_and_stops_what_was_on(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        pane = timer.media_pane_factory.last

        timer._release_strict_break()

        assert "stop" in pane.calls
        assert timer.media_surface is None
        assert timer.overlays == []
        assert timer._strict_engaged is False


class TestTheBreakGoesOnBeingABreak:
    def test_the_time_still_accrues_to_rest(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)

        assert timer._get_current_state() == "rest"

    def test_the_break_still_ends_on_its_own(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)

        advance(timer, timer.break_ms + 1000)

        assert timer.waiting_for_work_start is True

    def test_and_what_was_on_for_it_goes_on_playing(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        pane = timer.media_pane_factory.last

        advance(timer, timer.break_ms + 1000)

        assert "stop" not in pane.calls
        assert timer._showing is not None
        assert timer._media_host.is_showing_media() is True
        assert timer._strict_engaged is True

    def test_its_keys_go_on_driving_it(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        pane = timer.media_pane_factory.last
        advance(timer, timer.break_ms + 1000)

        send_key(timer, Qt.Key.Key_Space)

        assert "toggle" in pane.calls

    def test_starting_focus_takes_it_away_and_keeps_the_place(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)
        pane = timer.media_pane_factory.last
        pane.at = 754_000
        advance(timer, timer.break_ms + 1000)

        send_key(timer, RELEASE_KEY)

        assert "stop" in pane.calls
        assert timer.overlays == []
        assert rest_positions.read(timer._positions_path) == {
            "/x/rest.mp4": Place(754_000, 0)}

    @pytest.mark.parametrize("kind", [DECK, BOOK])
    @pytest.mark.parametrize("ended", [True, False], ids=["run-out", "held"])
    def test_leaving_destroys_a_web_view_before_its_wall_is_hidden(
            self, timer, epub, settled, kind, ended):
        timer.media_pane_factory = web_pane
        enter_strict_break(timer)
        timer._show_activity(BreakActivity(
            "Web", "Japanese" if kind == DECK else epub("<p>一</p>"), kind))
        settled()
        wall, standing = timer._media_host, []
        showing_pane(timer).view.destroyed.connect(
            lambda: standing.append(not sip.isdeleted(wall) and wall.isVisible()))

        if ended:
            advance(timer, timer.break_ms + 1000)
            send_key(timer, RELEASE_KEY)
        else:
            timer._release_strict_break()
        settled()

        assert standing == [True]

    def test_the_engine_slows_down_while_the_walls_are_up(self, timer, qapp):
        timer.parent().show()
        qapp.processEvents()

        enter_strict_break(timer)

        assert timer.refresh_timer.interval() == timer.COVERED_INTERVAL_MS

    def test_and_speeds_up_again_when_the_screens_are_given_back(self, timer, qapp):
        timer.parent().show()
        qapp.processEvents()
        enter_strict_break(timer)
        advance(timer, timer.break_ms + 1000)

        timer._toggle_timer()

        assert timer.refresh_timer.interval() == timer.visible_interval_ms()

    def test_starting_focus_takes_the_wall_away_too(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        advance(timer, timer.break_ms + 1000)

        timer._toggle_timer()

        assert timer.media_surface is None
        assert timer.overlays == []
        assert timer.kwin_pin.engaged is False


class TestWhereItStopped:
    def positions(self, timer):
        return rest_positions.read(timer._positions_path)

    def test_the_walls_going_remembers_it(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)
        timer.media_pane_factory.last.at = 754_000

        advance(timer, timer.break_ms + 1000)
        timer._clear_overlays()

        assert self.positions(timer) == {"/x/rest.mp4": Place(754_000, 0)}

    def test_so_does_asking_for_the_wall_back(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)
        timer.media_pane_factory.last.at = 12_000

        send_key(timer, Qt.Key.Key_0)

        assert self.positions(timer) == {"/x/rest.mp4": Place(12_000, 0)}

    def test_how_long_the_file_is_is_kept_with_it(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)
        pane = timer.media_pane_factory.last
        pane.at, pane.of = 754_000, 2_400_000

        send_key(timer, Qt.Key.Key_0)

        assert self.positions(timer) == {"/x/rest.mp4": Place(754_000, 2_400_000)}

    def test_a_file_that_would_not_open_keeps_the_length_it_had(self, timer):
        rest_positions.remember("/x/rest.mp4", 754_000, timer._positions_path, 2_400_000)
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)
        assert timer.media_pane_factory.last.duration() == 0

        send_key(timer, Qt.Key.Key_0)

        assert self.positions(timer) == {"/x/rest.mp4": Place(754_000, 2_400_000)}

    def test_the_next_break_carries_on_from_there(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)
        timer.media_pane_factory.last.at = 300_000
        timer._release_strict_break()
        timer._toggle_timer()

        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)

        assert timer.media_pane_factory.last.start_at == 300_000

    def test_the_monitor_it_was_on_going_dark_carries_on_from_there(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)
        gone = timer._media_host.screen_covered
        timer.media_pane_factory.last.at = 300_000

        timer._an_output_went(gone)
        timer.screens_to_cover = lambda: [QApplication.primaryScreen()]
        timer._rewall_for_the_outputs()

        assert timer.media_pane_factory.last.start_at == 300_000
        assert timer._showing.path == "/x/rest.mp4"
        assert timer._media_host.is_showing_media() is True

    def test_a_page_is_remembered_the_same_way(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        timer.media_pane_factory.last.at = 9

        send_key(timer, Qt.Key.Key_0)

        assert self.positions(timer) == {"/x/reading.pdf": Place(9, 0)}

    def test_one_left_at_the_start_is_not_remembered(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)

        send_key(timer, Qt.Key.Key_0)

        assert self.positions(timer) == {}

    def test_it_is_kept_beside_the_queue(self, timer, queue_path):
        import os

        assert os.path.dirname(timer._positions_path) == os.path.dirname(queue_path)


class TestWhatTheScreenShows:
    def test_nothing_of_the_breaks_own_readouts_is_on_it(self, timer, settled):
        two_screens(timer)
        enter_strict_break(timer)
        settled()

        send_key(timer, Qt.Key.Key_Return)

        assert len(timer.overlays) == 2
        assert timer.media_surface.strip is None

    def test_a_break_with_no_other_screen_keeps_one_line(self, timer):
        enter_strict_break(timer)
        timer.time_left_ms = 125_000

        send_key(timer, Qt.Key.Key_Return)

        assert timer.media_surface.strip is not None
        assert "REST 02:05" in timer.media_surface.strip.text()
        assert timer.release_hint() in timer.media_surface.strip.text()

    def test_that_line_is_driven_by_the_engine(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        timer.time_left_ms = 61_000

        advance(timer, 1000)

        assert "REST 01:00" in timer.media_surface.strip.text()

    def test_and_shows_the_hold_being_paid(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)

        timer._show_hold(0.5, True)

        assert "5s" in timer.media_surface.strip.text()

    def test_letting_go_puts_the_exit_back(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        timer._show_hold(0.5, True)

        timer._show_hold(0.0, False)

        assert timer.release_hint() in timer.media_surface.strip.text()

    def test_a_break_that_has_run_out_says_so_there(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        surface = timer.media_surface

        advance(timer, timer.break_ms + 1000)

        assert timer._showing is not None
        assert "BREAK OVER +0:00" in surface.strip.text()

    def test_the_frame_is_only_on_the_walls_showing_no_file(self, timer):
        two_screens(timer)
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        host = timer._media_host
        other, = [wall for wall in timer.overlays if wall is not host]

        advance(timer, timer.break_ms + 1000)

        assert corner_colour(host) != PALETTE["blue"]
        assert corner_colour(other) == PALETTE["blue"]

        send_key(timer, Qt.Key.Key_0)

        assert corner_colour(host) == PALETTE["blue"]


class TestTheQueue:
    def test_a_queued_path_is_offered_ahead_of_the_standing_entries(
            self, timer, queue_path, settled):
        rest_queue.append("/tmp/talk.mkv", queue_path)

        enter_strict_break(timer)
        settled()

        assert [offer.name for offer in timer._offers] == [
            "talk.mkv", "Reading", "Something to watch"]

    def test_enter_shows_the_queued_one(self, timer, queue_path):
        rest_queue.append("/tmp/talk.mkv", queue_path)
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert timer.media_pane_factory.last.activity.path == "/tmp/talk.mkv"

    def test_a_queued_pdf_needs_nothing_declared_for_it(self, timer, queue_path):
        rest_queue.append("/tmp/paper.pdf", queue_path)
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert timer.media_pane_factory.last.activity.kind == DOCUMENT

    def test_the_standing_entries_move_along_one(self, timer, queue_path):
        rest_queue.append("/tmp/talk.mkv", queue_path)
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_2)

        assert timer._showing.name == "Reading"

    def test_an_empty_queue_leaves_the_keys_where_they_were(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert timer._showing.name == "Reading"

    def test_the_surface_numbers_what_the_keys_answer(self, timer, queue_path,
                                                      settled):
        rest_queue.append("/tmp/talk.mkv", queue_path)
        rest_queue.append("/tmp/b.mkv", queue_path)

        enter_strict_break(timer)
        settled()

        assert timer.upcoming.lines() == [
            timer.OFFERS_TITLE, "ENTER  talk.mkv", "2  b.mkv",
            "3  Reading", "4  Something to watch"]

    def test_it_is_read_again_at_the_next_break(self, timer, queue_path):
        enter_strict_break(timer)
        rest_queue.append("/tmp/talk.mkv", queue_path)
        timer._release_strict_break()
        timer._toggle_timer()

        enter_strict_break(timer)

        assert timer._offers[0].name == "talk.mkv"

    def test_it_is_not_re_read_under_the_members_own_fingers(self, timer, queue_path):
        enter_strict_break(timer)
        rest_queue.append("/tmp/talk.mkv", queue_path)

        send_key(timer, Qt.Key.Key_Return)

        assert timer._showing.name == "Reading"

    def test_an_item_stays_queued_after_it_is_shown(self, timer, queue_path):
        rest_queue.append("/tmp/talk.mkv", queue_path)
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert rest_queue.read(queue_path) == ["/tmp/talk.mkv"]


class TestTheCommandThatQueues:
    def submit(self, window, text, settled):
        window.command_line.setText(text)
        window.execute_command()
        settled()
        return window.status_bar.text()

    @pytest.fixture
    def window_queue(self, window, profile_path, queue_path, monkeypatch):
        monkeypatch.setattr(rest_queue, "DEFAULT_PATH", queue_path)
        return queue_path

    def test_a_path_is_queued(self, window, window_queue, settled):
        line = self.submit(window, "rest /tmp/talk.mkv", settled)

        assert rest_queue.read(window_queue) == ["/tmp/talk.mkv"]
        assert "talk.mkv" in line

    def test_a_path_with_spaces_stays_one_path(self, window, window_queue, settled):
        self.submit(window, "rest /tmp/a talk.mkv", settled)

        assert rest_queue.read(window_queue) == ["/tmp/a talk.mkv"]

    def test_rest_alone_reads_the_queue_back(self, window, window_queue, settled):
        rest_queue.append("/tmp/talk.mkv", window_queue)

        line = self.submit(window, "rest", settled)

        assert "1 talk.mkv" in line

    def test_an_empty_queue_says_so(self, window, window_queue, settled):
        assert "empty" in self.submit(window, "rest", settled)

    def test_one_is_dropped_by_its_number(self, window, window_queue, settled):
        rest_queue.append("/tmp/a.mkv", window_queue)
        rest_queue.append("/tmp/b.mkv", window_queue)

        self.submit(window, "rest rm 1", settled)

        assert rest_queue.read(window_queue) == ["/tmp/b.mkv"]

    def test_dropping_without_a_number_is_refused_and_left_to_correct(
            self, window, window_queue, settled):
        rest_queue.append("/tmp/a.mkv", window_queue)

        line = self.submit(window, "rest rm", settled)

        assert "which one" in line
        assert rest_queue.read(window_queue) == ["/tmp/a.mkv"]
        assert window.command_line.text() == "rest rm"

    def test_a_number_that_is_not_in_the_queue_is_refused(self, window,
                                                          window_queue, settled):
        line = self.submit(window, "rest rm 4", settled)

        assert "no 4" in line
        assert window.command_line.text() == "rest rm 4"

    def test_the_queue_can_be_emptied(self, window, window_queue, settled):
        rest_queue.append("/tmp/a.mkv", window_queue)

        self.submit(window, "rest clear", settled)

        assert rest_queue.read(window_queue) == []

    def test_it_writes_no_household_data(self, window, window_queue, settled):
        self.submit(window, "rest /tmp/talk.mkv", settled)

        assert COMMANDS["rest"].domains == ()
        assert not window.db.called("log_pomodoro_event")


class TestHowFarIntoEachOneIAm:
    def remembered(self, timer, path, at, of):
        rest_positions.remember(path, at, timer._positions_path, of)

    def test_the_wall_says_how_far_into_each_offer_i_am(self, timer, settled):
        self.remembered(timer, "/x/rest.mp4", 1_593_000, 5_195_000)

        enter_strict_break(timer)
        settled()

        assert timer.upcoming.lines() == [
            timer.OFFERS_TITLE,
            'ENTER  Reading                           —',
            '    2  Something to watch  26:33 / 1:26:35']

    def test_a_document_is_said_in_pages(self, timer, settled):
        self.remembered(timer, "/x/reading.pdf", 41, 310)

        enter_strict_break(timer)
        settled()

        assert 'ENTER  Reading             42 / 310' in timer.upcoming.lines()

    def test_a_break_with_nothing_opened_yet_keeps_the_names_alone(self, timer,
                                                                   settled):
        enter_strict_break(timer)
        settled()

        assert timer.upcoming.lines() == [
            timer.OFFERS_TITLE, "ENTER  Reading", "2  Something to watch"]

    def test_an_entry_from_before_the_length_was_kept_says_nothing(self, timer,
                                                                   settled):
        self.remembered(timer, "/x/rest.mp4", 754_000, 0)
        self.remembered(timer, "/x/reading.pdf", 41, 310)

        enter_strict_break(timer)
        settled()

        assert '    2  Something to watch         —' in timer.upcoming.lines()

    def test_closing_a_video_leaves_the_wall_saying_where_i_stopped(self, timer,
                                                                    settled):
        enter_strict_break(timer)
        settled()
        send_key(timer, Qt.Key.Key_2)
        pane = timer.media_pane_factory.last
        pane.at, pane.of = 1_593_000, 5_195_000

        send_key(timer, Qt.Key.Key_0)

        assert '    2  Something to watch  26:33 / 1:26:35' in timer.upcoming.lines()

    def test_and_so_does_the_wall_on_the_screen_beside_it(self, timer, settled):
        two_screens(timer)
        enter_strict_break(timer)
        settled()
        send_key(timer, Qt.Key.Key_2)
        pane = timer.media_pane_factory.last
        pane.at, pane.of = 1_593_000, 5_195_000

        send_key(timer, Qt.Key.Key_0)

        for wall in timer.overlays:
            assert wall.upcoming.lines() == timer.upcoming.lines()


class TestTheExitAndTheOfferAreBothNamed:
    def test_the_timer_view_names_every_offer_and_its_key(self, timer, settled):
        enter_strict_break(timer)
        settled()

        assert timer.upcoming.lines() == [
            timer.OFFERS_TITLE, "ENTER  Reading", "2  Something to watch"]

    def test_a_covered_screen_names_them_too(self, timer, settled):
        enter_strict_break(timer)
        overlay = covered_screen(timer)
        settled()

        assert overlay.upcoming.lines() == timer.upcoming.lines()

    def test_nothing_is_named_outside_a_break(self, timer, settled):
        settled()

        assert timer.upcoming.lines() == []

    def test_a_profile_naming_none_names_nothing(self, qapp, app_id,
                                                 strict_timer, recording_db,
                                                 settled):
        view = PomodoroView(recording_db, tray_icon=None)
        view.refresh_timer.stop()
        view.stress_calendar.anim_timer.stop()
        enter_strict_break(view)
        settled()

        assert view.upcoming.lines() == []

        view.shutdown()
        QThreadPool.globalInstance().waitForDone(2000)
        view.deleteLater()

CARD_KEYS = {
    "SPACE": Qt.Key.Key_Space,
    "← →": Qt.Key.Key_Left,
    "↑ ↓": Qt.Key.Key_Up,
    "0": Qt.Key.Key_0,
    "BACKSPACE": Qt.Key.Key_Backspace,
}


def key_named(label):
    if label.startswith("ESC"):
        return RELEASE_KEY
    if label.startswith("1-"):
        return Qt.Key.Key_1
    return CARD_KEYS.get(label)


class TestTheCardOfKeys:
    def test_the_screen_showing_something_carries_it(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert ("0", "back to Traker") in timer.media_surface.keys.hints

    def test_it_names_what_leaving_costs(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        said = dict(timer.media_surface.keys.hints)
        assert said["ESC 10s"] == "leave the break"

    def test_a_video_is_paused_and_a_document_is_turned(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_2)
        watching = dict(timer.media_surface.keys.hints)
        send_key(timer, Qt.Key.Key_1)
        reading = dict(timer.media_surface.keys.hints)

        assert timer.media_surface.activity.kind == DOCUMENT
        assert watching["SPACE"] == "pause"
        assert reading["SPACE"] == "turn the page"

    def test_the_arrows_say_what_they_do_to_this_kind(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_2)
        watching = dict(timer.media_surface.keys.hints)
        send_key(timer, Qt.Key.Key_1)
        reading = dict(timer.media_surface.keys.hints)

        assert watching["← →"] == "seek 30 s"
        assert watching["↑ ↓"] == "volume"
        assert reading["← →"] == "page"
        assert reading["↑ ↓"] == "scroll"

    def test_the_digits_are_named_only_where_there_is_a_choice(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert dict(timer.media_surface.keys.hints)["1-2"] == "another offer"

    def test_a_lone_offer_names_no_digit(self, timer, queue_path):
        timer.activities = timer.activities[:1]
        rest_queue.clear(queue_path)
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert not [key for key, _ in timer.media_surface.keys.hints
                    if key.startswith("1-")]

    def test_every_key_it_names_is_one_the_break_answers(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        named = timer.media_surface.keys.hints

        for label, _says in named:
            key = key_named(label)
            assert key is not None, f"the card names {label!r} and nothing presses it"
            pressed = QKeyEvent(QEvent.Type.KeyPress, key,
                                Qt.KeyboardModifier.NoModifier)
            assert timer.eventFilter(timer, pressed) is True, label


class TestADeck:
    @pytest.fixture
    def reviewing(self, deck_timer):
        enter_strict_break(deck_timer)
        send_key(deck_timer, Qt.Key.Key_3)
        return deck_timer

    def test_it_is_offered_by_its_name(self, deck_timer, settled):
        enter_strict_break(deck_timer)
        settled()

        assert "3  Japanese" in deck_timer.upcoming.lines()

    def test_its_key_reviews_the_deck_it_names(self, reviewing):
        assert showing_pane(reviewing).activity == \
            BreakActivity("Japanese", "Japanese", DECK)

    def test_backspace_takes_the_last_answer_back(self, reviewing):
        send_key(reviewing, Qt.Key.Key_Backspace)

        assert showing_pane(reviewing).calls == ["undo"]

    def test_backspace_is_left_alone_where_nothing_can_be_taken_back(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)

        assert timer._drive_media(Qt.Key.Key_Backspace) is False

    def test_the_card_names_what_each_key_does_to_a_card(self, reviewing):
        said = dict(reviewing.media_surface.keys.hints)

        assert said["SPACE"] == "show, then good"
        assert said["← →"] == "again, good"
        assert said["BACKSPACE"] == "undo"

    def test_every_key_it_names_is_one_the_break_answers(self, reviewing):
        for label, _says in reviewing.media_surface.keys.hints:
            key = key_named(label)
            assert key is not None, f"the card names {label!r} and nothing presses it"
            pressed = QKeyEvent(QEvent.Type.KeyPress, key,
                                Qt.KeyboardModifier.NoModifier)
            assert reviewing.eventFilter(reviewing, pressed) is True, label

    def test_it_leaves_no_place_behind_to_resume(self, reviewing):
        pane = showing_pane(reviewing)
        pane.at, pane.of = 12, 49

        send_key(reviewing, Qt.Key.Key_0)

        assert rest_positions.read(reviewing._positions_path) == {}


def press(view, key, modifiers=Qt.KeyboardModifier.NoModifier) -> bool:
    return view.eventFilter(view, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))


class TestAPage:
    @pytest.fixture
    def browsing(self, page_timer):
        enter_strict_break(page_timer)
        send_key(page_timer, Qt.Key.Key_3)
        return page_timer

    def test_its_key_opens_the_url_it_names(self, browsing):
        assert showing_pane(browsing).activity == BreakActivity("Tutor", PAGE_URL, PAGE)

    @pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_1, Qt.Key.Key_0,
                                     Qt.Key.Key_Space, Qt.Key.Key_Right, Qt.Key.Key_A,
                                     Qt.Key.Key_Backspace])
    def test_every_other_key_reaches_the_page(self, browsing, key):
        assert press(browsing, key) is False
        assert showing_pane(browsing).calls == []
        assert browsing._showing.kind == PAGE

    def test_ctrl_0_puts_the_wall_back(self, browsing):
        assert press(browsing, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier) is True

        assert browsing._showing is None

    def test_the_release_key_is_the_break_s_all_the_same(self, browsing):
        assert press(browsing, RELEASE_KEY) is True

        assert browsing._hold_timer.isActive() is True

    def test_the_strip_under_it_names_both_keys_in_place_of_the_card(self, browsing):
        surface = browsing.media_surface

        assert surface.keys.isVisible() is False
        assert surface.strip.text().endswith(
            "CTRL 0 BACK TO TRAKER · ESC 10s LEAVE THE BREAK")

    def test_it_leaves_no_place_behind_to_resume(self, browsing):
        press(browsing, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)

        assert rest_positions.read(browsing._positions_path) == {}

    def test_the_hook_hears_a_page(self, browsing, settled):
        browsing.hook = told = Told()
        browsing._follow_the_state()
        settled()

        assert told.states == ["page"]


class TestEveryDeck:
    @pytest.fixture
    def listing(self, deck_timer):
        enter_strict_break(deck_timer)
        send_key(deck_timer, Qt.Key.Key_4)
        return deck_timer

    def in_a_deck(self, view):
        pane = showing_pane(view)
        pane.choosing, pane.deck = False, "Japanese::Kanji"
        pane.changed.emit()
        return pane

    def test_the_card_names_the_keys_that_choose_a_deck(self, listing):
        said = dict(listing.media_surface.keys.hints)

        assert said["\u2191 \u2193"] == "choose a deck"
        assert said["SPACE"] == "review it"
        assert said["0"] == "back to Traker"

    def test_the_card_follows_the_list_into_a_deck(self, listing):
        self.in_a_deck(listing)

        assert dict(listing.media_surface.keys.hints)["0"] == "back to the decks"

    def test_0_in_a_deck_from_the_list_goes_back_to_the_list(self, listing):
        pane = self.in_a_deck(listing)

        send_key(listing, Qt.Key.Key_0)

        assert (pane.calls[-1], pane.choosing) == ("back", True)
        assert listing._showing is not None

    def test_0_on_the_list_puts_the_wall_back(self, listing):
        send_key(listing, Qt.Key.Key_0)

        assert listing._showing is None

    def test_the_wall_beside_names_the_deck_under_review(self, listing):
        self.in_a_deck(listing)

        assert listing._playing()[0] == "Japanese::Kanji"

    def test_every_key_it_names_is_one_the_break_answers(self, listing):
        for label, _says in listing.media_surface.keys.hints:
            key = key_named(label)
            assert key is not None, f"the card names {label!r} and nothing presses it"
            pressed = QKeyEvent(QEvent.Type.KeyPress, key,
                                Qt.KeyboardModifier.NoModifier)
            assert listing.eventFilter(listing, pressed) is True, label


class TestTheReadoutIsOnTheWallBesideTheFilm:
    @pytest.fixture
    def watching(self, timer):
        two_screens(timer)
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_2)
        pane = timer.media_pane_factory.last
        pane.at, pane.of = 1_593_000, 5_195_000
        timer._redraw_break_surfaces()
        return timer

    def test_the_wall_names_it_and_says_where_it_has_got_to(self, watching):
        for wall in watching.overlays:
            assert wall.playing.isVisibleTo(wall.readouts) is True
            assert "Something to watch" in wall.playing.lines()
            assert wall.progress.says == "26:33 / 1:26:35"

    def test_every_wall_says_the_same_thing(self, watching):
        said = {(tuple(wall.playing.lines()), wall.progress.says)
                for wall in watching.overlays}

        assert len(watching.overlays) == 2 and len(said) == 1

    def test_the_film_screen_carries_no_readout_at_all(self, watching):
        assert watching.media_surface.progress is None

    def test_a_document_says_its_page_there_instead(self, timer):
        two_screens(timer)
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        pane = timer.media_pane_factory.last
        pane.at, pane.of = 41, 310
        timer._redraw_break_surfaces()

        assert timer.overlays[0].progress.says == "42 / 310"

    def test_a_break_showing_nothing_has_no_block_on_its_walls(self, timer):
        enter_strict_break(timer)

        for wall in timer.overlays:
            assert wall.playing.isVisibleTo(wall.readouts) is False
            assert wall.progress.isVisibleTo(wall.readouts) is False

    def test_asking_for_the_wall_back_takes_it_off_too(self, watching):
        send_key(watching, Qt.Key.Key_0)

        for wall in watching.overlays:
            assert wall.playing.isVisibleTo(wall.readouts) is False

    def test_the_break_running_out_leaves_it_on(self, watching):
        advance(watching, watching.break_ms + 1000)

        for wall in watching.overlays:
            assert wall.playing.isVisibleTo(wall.readouts) is True

    def test_the_player_is_asked_once_a_frame_and_not_once_a_wall(self, watching):
        pane = watching.media_pane_factory.last
        asked = []
        real = pane.position
        pane.position = lambda: asked.append(1) or real()

        watching._redraw_break_surfaces()

        assert len(watching.overlays) == 2 and len(asked) == 1


class TestTheCardOnEveryWall:
    def test_a_covered_screen_names_the_same_keys(self, timer):
        enter_strict_break(timer)
        overlay = covered_screen(timer)

        send_key(timer, Qt.Key.Key_Return)

        assert overlay.keys.hints == timer.media_surface.keys.hints
        assert overlay.keys.isHidden() is False

    def test_a_monitor_arriving_mid_activity_is_walled_with_the_keys_named(self, timer):
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        two_screens(timer)

        timer._rewall_for_the_outputs()

        arrived, = [wall for wall in timer.overlays if wall is not timer._media_host]
        assert arrived.keys.hints == timer.media_surface.keys.hints
        assert arrived.keys.isHidden() is False

    def test_a_wall_with_nothing_showing_names_none_of_them(self, timer):
        enter_strict_break(timer)
        overlay = covered_screen(timer)

        assert overlay.keys.hints == ()
        assert overlay.keys.isHidden() is True

    def test_asking_for_the_wall_back_takes_the_keys_off_it(self, timer):
        enter_strict_break(timer)
        overlay = covered_screen(timer)
        send_key(timer, Qt.Key.Key_Return)

        send_key(timer, Qt.Key.Key_0)

        assert overlay.keys.hints == ()
        assert overlay.keys.isHidden() is True

    def test_the_break_running_out_renames_the_key_it_prices(self, timer):
        enter_strict_break(timer)
        overlay = covered_screen(timer)
        send_key(timer, Qt.Key.Key_Return)

        advance(timer, timer.break_ms + 1000)

        assert dict(overlay.keys.hints)[pomodoro_view.RELEASE_KEY_NAME] == "start focus"

    def test_a_second_offer_renames_them_everywhere(self, timer):
        enter_strict_break(timer)
        overlay = covered_screen(timer)
        send_key(timer, Qt.Key.Key_2)

        send_key(timer, Qt.Key.Key_1)

        assert dict(overlay.keys.hints)["SPACE"] == "turn the page"


class TestTheLibrary:
    def test_its_subfolders_are_offered_after_the_standing_entries(self, library_timer):
        enter_with_the_shelves(library_timer)

        assert [offer.name for offer in library_timer._offers] == [
            "Reading", "Something to watch", "Books", "Videos"]

    def test_the_library_is_walked_off_the_interface_thread(self, library_timer,
                                                            monkeypatch):
        walked = []
        shelves = pomodoro_view.break_activities.shelves

        def noting(folder):
            walked.append(threading.current_thread() is threading.main_thread())
            return shelves(folder)

        monkeypatch.setattr(pomodoro_view.break_activities, "shelves", noting)
        enter_with_the_shelves(library_timer)

        assert walked == [False]
        assert library_timer._offers[-1].name == "Videos"

    def test_each_names_its_subfolder_and_the_file_it_opens(self, library_timer, settled):
        enter_with_the_shelves(library_timer)
        settled()

        assert library_timer.upcoming.lines()[-2:] == [
            "3  Books   a.epub", "4  Videos  e1.mkv"]

    def test_its_key_lists_its_folder_with_the_file_it_reached_marked(self, library_timer,
                                                                      media):
        enter_with_the_shelves(library_timer)

        send_key(library_timer, Qt.Key.Key_3)

        assert marked(library_timer) == str(media / "Books" / "a.epub")
        assert library_timer.hook_state() == "break"

    def test_a_file_that_reached_its_end_hands_the_mark_to_the_next(self, library_timer,
                                                                    media):
        ended = str(media / "Videos" / "e1.mkv")
        rest_positions.remember(ended, 1_440_000, library_timer._positions_path, 1_440_000)
        enter_with_the_shelves(library_timer)

        send_key(library_timer, Qt.Key.Key_4)

        assert marked(library_timer) == str(media / "Videos" / "e2.mkv")

    def test_space_opens_the_marked_file_as_what_it_is(self, library_timer, media):
        enter_with_the_shelves(library_timer)
        send_key(library_timer, Qt.Key.Key_3)

        send_key(library_timer, Qt.Key.Key_Down)
        send_key(library_timer, Qt.Key.Key_Space)

        assert library_timer.media_pane_factory.last.activity == BreakActivity(
            "b.epub", str(media / "Books" / "b.epub"), BOOK)

    def test_0_in_that_file_brings_the_list_back_with_it_marked(self, library_timer,
                                                                 media):
        enter_with_the_shelves(library_timer)
        send_key(library_timer, Qt.Key.Key_3)
        send_key(library_timer, Qt.Key.Key_Down)
        send_key(library_timer, Qt.Key.Key_Space)

        send_key(library_timer, Qt.Key.Key_0)
        assert marked(library_timer) == str(media / "Books" / "b.epub")

        send_key(library_timer, Qt.Key.Key_0)
        assert library_timer._showing is None

    def test_left_climbs_to_the_media_folder_and_right_into_another(self, library_timer,
                                                                   media):
        enter_with_the_shelves(library_timer)
        send_key(library_timer, Qt.Key.Key_3)

        send_key(library_timer, Qt.Key.Key_Left)
        assert marked(library_timer) == str(media / "Books")

        send_key(library_timer, Qt.Key.Key_Down)
        send_key(library_timer, Qt.Key.Key_Right)
        assert marked(library_timer) == str(media / "Videos" / "e1.mkv")

    def test_every_key_its_card_names_is_one_the_break_answers(self, library_timer):
        enter_with_the_shelves(library_timer)
        send_key(library_timer, Qt.Key.Key_3)

        for label, _says in library_timer.media_surface.keys.hints:
            key = LIST_KEYS.get(label) or key_named(label)
            assert key is not None, f"the card names {label!r} and nothing presses it"
            pressed = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            assert library_timer.eventFilter(library_timer, pressed) is True, label

    def test_its_key_again_while_its_list_shows_does_nothing(self, library_timer):
        enter_with_the_shelves(library_timer)
        send_key(library_timer, Qt.Key.Key_3)
        send_key(library_timer, Qt.Key.Key_Down)
        built = len(library_timer.media_pane_factory.built)

        send_key(library_timer, Qt.Key.Key_3)

        assert len(library_timer.media_pane_factory.built) == built
        assert library_timer.media_surface.pane.marked == 1


def marked(view) -> str:
    pane = view.media_surface.pane
    return pane.entries[pane.marked].path


LIST_KEYS = {"\u2191 \u2193": Qt.Key.Key_Up, "SPACE \u2192": Qt.Key.Key_Space,
             "BACKSPACE \u2190": Qt.Key.Key_Backspace, "0": Qt.Key.Key_0}


BOOK_KEYS = {"SPACE →": Qt.Key.Key_Space, "SPACE ←": Qt.Key.Key_Space,
             "BACKSPACE ←": Qt.Key.Key_Backspace, "BACKSPACE →": Qt.Key.Key_Backspace,
             "↑ ↓": Qt.Key.Key_Up, "0": Qt.Key.Key_0}


class TestABook:
    @pytest.fixture
    def reading(self, library_timer):
        enter_with_the_shelves(library_timer)
        send_key(library_timer, Qt.Key.Key_3)
        send_key(library_timer, Qt.Key.Key_Space)
        return library_timer

    def test_the_card_names_the_keys_that_turn_its_pages(self, reading):
        said = dict(reading.media_surface.keys.hints)

        assert (said["SPACE →"], said["BACKSPACE ←"], said["↑ ↓"]) == (
            "next page", "page back", "chapter")

    def test_a_right_to_left_book_turns_on_to_the_left(self, reading):
        showing_pane(reading).rtl = True
        reading._say_which_keys_drive_it()

        assert dict(reading.media_surface.keys.hints)["SPACE ←"] == "next page"

    def test_page_down_turns_on_in_reading_order_whichever_way_it_runs(self, reading):
        pane = showing_pane(reading)
        pane.rtl = True

        send_key(reading, Qt.Key.Key_PageDown)
        send_key(reading, Qt.Key.Key_PageUp)

        assert pane.calls[-2:] == [("turn", 1), ("turn", -1)]

    def test_backspace_turns_back(self, reading):
        send_key(reading, Qt.Key.Key_Backspace)

        assert showing_pane(reading).calls[-1] == "undo"

    def test_every_key_it_names_is_one_the_break_answers(self, reading):
        for label, _says in reading.media_surface.keys.hints:
            key = BOOK_KEYS.get(label) or key_named(label)
            assert key is not None, f"the card names {label!r} and nothing presses it"
            pressed = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            assert reading.eventFilter(reading, pressed) is True, label

    def test_where_it_was_left_is_kept_like_any_file(self, reading):
        pane = showing_pane(reading)
        pane.at, pane.of = 1_660, 4_486

        send_key(reading, Qt.Key.Key_0)

        assert rest_positions.place_for(pane.activity.path, reading._positions_path) == (
            Place(1_660, 4_486))
        assert "    3  Books   a.epub      37%" in reading.upcoming.lines()


def glowing(label):
    """Return the colour a label glows from, or None where it rests."""
    animation = label.glowing.animation
    if animation.state() != QAbstractAnimation.State.Running:
        return None
    return animation.startValue().name()


class TestAPressIsAcknowledged:
    def offers(self, panel, title):
        return [glowing(line) for line in panel._lines[title]]

    def test_an_offer_pressed_while_they_wait_glows_yellow_with_its_title(self, timer):
        enter_strict_break(timer, past_the_wait=False)

        send_key(timer, Qt.Key.Key_2)

        panel = timer.overlays[0].upcoming
        assert self.offers(panel, timer.OFFERS_TITLE) == [None, PALETTE['yellow']]
        assert glowing(panel._titles[timer.OFFERS_TITLE]) == PALETTE['yellow']

    def test_one_pressed_once_they_open_glows_on_its_own(self, timer):
        enter_strict_break(timer)

        send_key(timer, Qt.Key.Key_2)

        panel = timer.upcoming
        assert self.offers(panel, timer.OFFERS_TITLE) == [None, PALETTE['base2']]
        assert glowing(panel._titles[timer.OFFERS_TITLE]) is None

    def test_the_line_that_changed_glows_as_the_wall_comes_back(self, timer, settled):
        enter_strict_break(timer)
        settled()
        send_key(timer, Qt.Key.Key_2)
        pane = timer.media_pane_factory.last
        pane.at, pane.of = 1_593_000, 5_195_000

        send_key(timer, Qt.Key.Key_0)

        assert self.offers(timer.upcoming, timer.OFFERS_TITLE) == [None, PALETTE['base2']]

    def test_a_line_only_aligned_anew_does_not_glow(self, qapp):
        panel = UpcomingPanel()
        panel.set_sections([("OFFERS", ["ENTER  a.mkv", "2  b.pdf"])])

        panel.set_sections([("OFFERS", ["ENTER  a.mkv       —", "    2  b.pdf  1 / 9"])])

        assert self.offers(panel, "OFFERS") == [None, PALETTE['base2']]

    def test_lines_drawn_twice_at_once_open_no_window_of_their_own(self, qapp):
        host = QWidget()
        panel = UpcomingPanel(host)
        host.show()
        panel.set_sections([("OFFERS", ["ENTER  a.mkv"])])
        qapp.processEvents()
        panel.set_sections([("OFFERS", ["ENTER  b.mkv"])])
        drawn = panel.findChildren(QLabel)

        panel.set_sections([("OFFERS", ["ENTER  c.mkv"])])
        qapp.processEvents()

        assert not any(label.isVisible() for label in drawn)
        host.close()


class Told:
    def __init__(self):
        self.told = None
        self.states = []

    def tell(self, state):
        if state != self.told:
            self.told = state
            self.states.append(state)

    def close(self):
        pass


@pytest.fixture
def with_a_hook(with_activities, tmp_path):
    heard = tmp_path / "heard"
    written = with_activities.read_text(encoding="utf-8")
    assert '[hooks]\nstate = ""' in written, "the [hooks] template no longer says this"
    with_activities.write_text(written.replace(
        '[hooks]\nstate = ""', f"[hooks]\nstate = \"printf '%s\\\\n' {{state}} >> {heard}\""),
        encoding="utf-8")
    profile_module.reload_profile()
    return heard


class TestTheHookFollowsTheBreak:
    def test_it_hears_each_thing_the_break_shows_in_turn(self, timer, settled):
        timer.hook = told = Told()

        enter_strict_break(timer)
        settled()
        send_key(timer, Qt.Key.Key_Return)
        settled()
        send_key(timer, Qt.Key.Key_0)
        settled()
        send_key(timer, Qt.Key.Key_2)
        settled()
        timer._release_strict_break()
        settled()

        assert told.states == ["break", "document", "break", "video", "focus"]

    def test_an_offer_in_place_of_another_is_heard_alone(self, timer, settled):
        timer.hook = told = Told()
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        settled()

        send_key(timer, Qt.Key.Key_2)
        settled()

        assert told.states == ["document", "video"]

    def test_a_shelf_s_list_is_the_break_and_its_file_what_it_is(self, library_timer,
                                                                 settled):
        library_timer.hook = told = Told()
        enter_with_the_shelves(library_timer)

        send_key(library_timer, Qt.Key.Key_3)
        settled()
        send_key(library_timer, Qt.Key.Key_Space)
        settled()

        assert told.states == ["break", "book"]

    def test_the_walls_standing_after_the_break_are_still_the_break(self, timer, settled):
        timer.hook = told = Told()
        enter_strict_break(timer)
        settled()

        advance(timer, timer.break_ms + 1000)
        settled()
        assert timer.overlays and told.states == ["break"]

        send_key(timer, RELEASE_KEY)
        settled()
        assert told.states == ["break", "focus"]

    def test_quitting_mid_break_tells_it_focus(self, timer, settled):
        timer.hook = told = Told()
        enter_strict_break(timer)
        send_key(timer, Qt.Key.Key_Return)
        settled()

        timer.shutdown()

        assert told.states == ["document", "focus"]

    def test_the_profile_names_the_command_the_shell_runs(
            self, qapp, app_id, with_a_hook, recording_db, settled):
        for view in a_view(recording_db):
            enter_strict_break(view)
            settled()
            view.shutdown()

        assert with_a_hook.read_text().splitlines()[-1] == "focus"
