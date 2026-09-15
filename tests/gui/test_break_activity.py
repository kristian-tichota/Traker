import pytest
from PyQt6.QtCore import QEvent, Qt, QThreadPool
from PyQt6.QtGui import QGuiApplication, QKeyEvent
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget

import src.profile as profile_module
from src.desktop import rest_positions, rest_queue
from src.desktop.activities import DOCUMENT, VIDEO
from src.domain.media import Place
from src.gui.commands import COMMANDS
from src.gui.views import pomodoro_view
from src.gui.views.pomodoro_view import RELEASE_KEY, PomodoroView, StrictOverlay
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


class Panes:
    def __init__(self):
        self.built = []

    def __call__(self, activity, start_at=0, parent=None):
        pane = FakePane(activity, start_at, parent)
        self.built.append(pane)
        return pane

    @property
    def last(self):
        return self.built[-1]


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
def timer(qapp, app_id, with_activities, recording_db):
    yield from a_view(recording_db)


@pytest.fixture
def timer_that_never_waits(qapp, app_id, with_no_wait, recording_db):
    yield from a_view(recording_db)


@pytest.fixture
def said(monkeypatch):
    posted = []
    monkeypatch.setattr(pomodoro_view.notify_service, "notify",
                        lambda summary, body, **kw: posted.append((summary, body)))
    return posted


def enter_strict_break(view, past_the_wait=True):
    view._skip_phase()
    if past_the_wait:
        view.time_left_ms -= view.away_ms()
        view._say_when_the_offers_open()
    assert view._strict_break_is_holding()


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
        assert view._activity_for(Qt.Key.Key_Return) is None

        view.shutdown()
        QThreadPool.globalInstance().waitForDone(2000)
        view.deleteLater()

    def test_a_key_with_no_activity_behind_it_is_not_swallowed(self, timer):
        enter_strict_break(timer)

        assert timer._activity_for(Qt.Key.Key_9) is None
        assert timer._activity_for(Qt.Key.Key_A) is None

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

        assert timer._strict_break_is_holding()
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
        assert timer._strict_break_is_holding() is True

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
        assert showing._strict_break_is_holding() is True

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
        assert showing._strict_break_is_holding() is True
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
        assert showing._activity_for(Qt.Key.Key_N) is None
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
