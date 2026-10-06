import pytest
from PyQt6.QtCore import QDateTime, Qt, QThreadPool
from PyQt6.QtWidgets import QApplication, QWidget

import src.profile as profile_module
from src.desktop.activities import VIDEO, BreakActivity
from src.desktop.kwin_rules import EYE_GROUP
from src.domain.eye_rest import CLOSE, GAZE, LOOK, OPEN, SQUEEZE, length_ms, look_away
from src.gui.components.eye_veil import DONE, GAZE_NOTE, REST_TITLE, VEIL_CAPTION
from src.gui.views.pomodoro_view import BLINK_SET_EVENT, PomodoroView, read_spent_today

pytestmark = [pytest.mark.gui, pytest.mark.exact]

NO_INPUT = (Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowStaysOnTopHint)


@pytest.fixture
def eyes_rested(strict_timer):
    written = strict_timer.read_text(encoding="utf-8")
    assert "[eye_rest]\nenabled = false" in written, "the [eye_rest] template no longer says this"
    assert written.count("\nsound = true") == 1
    written = written.replace("[eye_rest]\nenabled = false", "[eye_rest]\nenabled = true")
    strict_timer.write_text(written.replace("\nsound = true", "\nsound = false"),
                            encoding="utf-8")
    profile_module.reload_profile()
    return strict_timer


class Clock:
    def __init__(self):
        self.ms = 1_000_000

    def __call__(self):
        return self.ms


class Tones:
    def __init__(self):
        self.played = []

    def play(self, name):
        self.played.append(name)


class FilmPane(QWidget):
    def __init__(self, activity, start_at=0, parent=None):
        super().__init__(parent)
        self.held = []

    def open(self, path, start_at=0):
        pass

    def still(self, held):
        self.held.append(held)

    def position(self):
        return 0

    def duration(self):
        return 0

    def stop(self):
        pass


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def timer(qapp, eyes_rested, recording_db, clock):
    view = PomodoroView(recording_db, tray_icon=None)
    view.refresh_timer.stop()
    view.stress_calendar.anim_timer.stop()
    view._idle_watch.stop()
    view.eye_rest.now = clock
    view.eye_rest.tones = Tones()
    yield view
    view.shutdown()
    QThreadPool.globalInstance().waitForDone(2000)
    view.deleteLater()


def gather_screen_time(view):
    view.eye_rest.advance(view.eye_rest.screen_time.every_ms, 0)


def at(view, clock, ms):
    clock.ms = view.eye_rest._began_ms + ms
    view.eye_rest.pace()


def enter_break(view):
    view._skip_phase()
    assert view.holds_the_screens()


def look_now(view, idle):
    view.idle_source = lambda: idle
    view._screen_seen_ms = QDateTime.currentMSecsSinceEpoch() - 1000
    view._watch_for_the_member()


class TestALookAway:
    def test_screen_time_brings_a_veil_over_every_screen_that_takes_no_input(self, timer):
        gather_screen_time(timer)

        veils = timer.eye_rest.windows
        assert len(veils) == len(QApplication.screens())
        for veil in veils:
            assert veil.isVisible()
            assert veil.windowFlags() & NO_INPUT == NO_INPUT
            assert veil.windowTitle().startswith(VEIL_CAPTION)
            assert veil.lines == ("CLOSE GENTLY", "", REST_TITLE)

    def test_each_step_cues_its_motion_and_the_gaze_is_counted_down(self, timer, clock):
        gather_screen_time(timer)

        for ms in (2000, 3000, 5000, 7000, 8000):
            at(timer, clock, ms)
        veil = timer.eye_rest.windows[0]
        assert timer.eye_rest.tones.played == [CLOSE, OPEN, CLOSE, SQUEEZE, OPEN, LOOK]
        assert veil.lines == (GAZE, "20", GAZE_NOTE)
        at(timer, clock, 27_500)
        assert veil.lines == (GAZE, "1", GAZE_NOTE)

    def test_the_end_chimes_lifts_the_veil_and_counts_from_zero(self, timer, clock):
        gather_screen_time(timer)
        veils = list(timer.eye_rest.windows)

        at(timer, clock, length_ms(look_away(timer.eye_rest.gaze_ms)))

        assert timer.eye_rest.running is False
        assert timer.eye_rest.tones.played[-1] == DONE
        assert all(veil.raised is False for veil in veils)
        assert timer.eye_rest.screen_time.screen_ms == 0

    def test_an_absence_as_long_as_the_timer_pause_is_a_rest(self, timer):
        timer.eye_rest.screen_time.screen_ms = timer.eye_rest.screen_time.every_ms - 1

        look_now(timer, timer.idle_pause_ms)

        assert timer.eye_rest.running is False
        assert timer.eye_rest.screen_time.screen_ms == 0

    def test_reading_without_input_is_still_screen_time(self, timer):
        timer.eye_rest.screen_time.screen_ms = timer.eye_rest.screen_time.every_ms - 1

        look_now(timer, timer.idle_pause_ms - 1)

        assert timer.eye_rest.running is True

    def test_the_veils_rule_is_held_until_the_timer_shuts_down(self, timer, desktop_session):
        with open(desktop_session.rules_path, encoding="utf-8") as rules:
            assert f"[{EYE_GROUP}]" in rules.read()

        timer.shutdown()

        with open(desktop_session.rules_path, encoding="utf-8") as rules:
            assert f"[{EYE_GROUP}]" not in rules.read()


class TestOnABreak:
    def test_the_days_first_break_opens_with_a_blink_set_on_every_wall(self, timer):
        enter_break(timer)

        assert timer.eye_rest.repetitions == 15
        assert timer.eye_rest.windows == []
        for wall in timer.overlays:
            assert wall.veil.raised is True
            assert wall.veil.lines == ("CLOSE", "1 / 15", "BLINK SET 1 OF 3")

    def test_a_finished_set_is_recorded(self, timer, clock, recording_db):
        enter_break(timer)

        at(timer, clock, 75_000)

        QThreadPool.globalInstance().waitForDone(2000)
        assert recording_db.last("log_pomodoro_event")["event_type"] == BLINK_SET_EVENT
        assert timer.blink_sets_left() == 2

    def test_the_fourth_break_of_the_day_has_none(self, timer):
        timer._blink_sets_done = 3

        enter_break(timer)

        assert timer.eye_rest.running is False

    def test_a_restart_does_not_hand_the_days_sets_out_again(self):
        class Day:
            def get_pomodoro_events_for_day(self, date):
                return [("t", BLINK_SET_EVENT, 0), ("t", "long_break_started", 0),
                        ("t", BLINK_SET_EVENT, 0)]

        assert read_spent_today(Day())[1:] == (1, 2)

    def test_walls_showing_nothing_rest_the_eyes(self, timer):
        timer.blink_sets_per_day = 0
        enter_break(timer)
        timer.eye_rest.screen_time.screen_ms = timer.eye_rest.screen_time.every_ms - 1
        timer._dark_since_ms = QDateTime.currentMSecsSinceEpoch() - 60_000

        look_now(timer, None)

        assert timer.eye_rest.running is False
        assert timer.eye_rest.screen_time.screen_ms == 0

    def test_a_rest_on_the_walls_holds_the_film_still(self, timer, clock):
        timer.blink_sets_per_day = 0
        timer.away_secs = 0
        timer.media_pane_factory = FilmPane
        enter_break(timer)
        timer._show_activity(BreakActivity("Film", "/x/film.mkv", VIDEO))
        pane = timer.media_surface.pane

        gather_screen_time(timer)
        at(timer, clock, length_ms(look_away(timer.eye_rest.gaze_ms)))

        assert pane.held == [True, False]
        assert timer._media_host.veil.raised is False
