import datetime

import pytest
from PyQt6.QtCore import QDateTime, QThreadPool

from src.gui.views.pomodoro_view import PomodoroView

pytestmark = [pytest.mark.gui, pytest.mark.exact]


@pytest.fixture
def make_timer(qapp, profile_path, recording_db):
    built = []

    def _make():
        view = PomodoroView(recording_db, tray_icon=None)
        view.refresh_timer.stop()
        view.stress_calendar.anim_timer.stop()
        built.append(view)
        return view

    yield _make

    QThreadPool.globalInstance().waitForDone(2000)
    for view in built:
        view.shutdown()
        view.deleteLater()


def frame(view, milliseconds):
    view.last_frame_timestamp = QDateTime.currentMSecsSinceEpoch() - milliseconds
    view._engine_loop()


def totals(view):
    return (
        view.live_focus_ms + view.intra_minute_focus_ms,
        view.live_rest_ms + view.intra_minute_rest_ms,
        view.live_focus_ot_ms + view.intra_minute_focus_ot_ms,
        view.live_rest_ot_ms + view.intra_minute_rest_ot_ms,
    )


def run_for(view, wall_ms, cadence_ms):
    frames = max(1, int(wall_ms // cadence_ms))
    for _ in range(frames):
        frame(view, cadence_ms)
    return frames


class TestTheEngineIsDrivenByTheWallClockNotByTicks:
    def test_one_long_frame_accrues_the_same_as_many_short_ones(self, make_timer):
        coarse, fine = make_timer(), make_timer()
        for view in (coarse, fine):
            view.last_logged_minute = 0
            view._toggle_timer()
            frame(view, 0)

        frame(coarse, 6000)
        run_for(fine, 6000, 5)

        assert coarse.intra_minute_focus_ms == pytest.approx(
            fine.intra_minute_focus_ms, abs=10)

    def test_a_frame_accrues_its_own_delta_and_nothing_else(self, make_timer):
        view = make_timer()
        view.last_logged_minute = 0
        view._toggle_timer()
        frame(view, 0)

        frame(view, 1500)

        assert view.intra_minute_focus_ms == pytest.approx(1500, abs=10)

    def test_the_time_left_falls_by_the_elapsed_wall_clock(self, make_timer):
        view = make_timer()
        view.last_logged_minute = 0
        view._toggle_timer()
        frame(view, 0)
        before = view.time_left_ms

        frame(view, 2500)

        assert before - view.time_left_ms == pytest.approx(2500, abs=10)

    def test_time_accrues_to_the_state_the_timer_is_actually_in(self, make_timer):
        view = make_timer()
        view.last_logged_minute = 0
        frame(view, 0)

        frame(view, 1000)
        assert view.intra_minute_rest_ot_ms == pytest.approx(1000, abs=10)

        view._toggle_timer()
        frame(view, 1000)
        assert view.intra_minute_focus_ms == pytest.approx(1000, abs=10)

        view._skip_phase()
        frame(view, 1000)
        assert view.intra_minute_rest_ms == pytest.approx(1000, abs=10)


class TestCrossingAWallClockMinute:
    def _park_just_before_a_rollover(self, view):
        now = datetime.datetime.now()
        current_minute = now.hour * 60 + now.minute
        view.last_logged_minute = (current_minute - 1) % 1440
        return current_minute

    def test_crossing_a_minute_stores_exactly_one_heartbeat(
            self, make_timer, recording_db):
        view = make_timer()
        view._toggle_timer()
        frame(view, 0)
        self._park_just_before_a_rollover(view)
        QThreadPool.globalInstance().waitForDone(2000)
        recording_db.calls.clear()

        frame(view, 20)
        QThreadPool.globalInstance().waitForDone(2000)

        beats = [args for name, args in recording_db.calls
                 if name == "log_pomodoro_heartbeat"]
        assert len(beats) == 1

    def test_the_heartbeat_holds_the_state_at_the_crossing(
            self, make_timer, recording_db):
        view = make_timer()
        view._toggle_timer()
        frame(view, 0)
        self._park_just_before_a_rollover(view)
        QThreadPool.globalInstance().waitForDone(2000)
        recording_db.calls.clear()

        frame(view, 20)
        QThreadPool.globalInstance().waitForDone(2000)

        payload = next(args[0] for name, args in recording_db.calls
                       if name == "log_pomodoro_heartbeat")
        assert payload["state"] == "focus"
        assert payload["date"] == datetime.date.today().isoformat()
        assert payload["second"] == 0

    def test_staying_inside_one_minute_writes_no_heartbeat(
            self, make_timer, recording_db):
        view = make_timer()
        view._toggle_timer()
        frame(view, 0)
        now = datetime.datetime.now()
        view.last_logged_minute = now.hour * 60 + now.minute
        QThreadPool.globalInstance().waitForDone(2000)
        recording_db.calls.clear()

        for _ in range(50):
            frame(view, 20)
        QThreadPool.globalInstance().waitForDone(2000)

        assert not any(name == "log_pomodoro_heartbeat"
                       for name, _args in recording_db.calls)

    def test_the_sub_minute_counters_reset_once_the_re_read_lands(
            self, make_timer, qapp):
        view = make_timer()
        view._toggle_timer()
        frame(view, 0)
        frame(view, 3000)
        assert view.intra_minute_focus_ms > 0
        self._park_just_before_a_rollover(view)

        frame(view, 20)
        QThreadPool.globalInstance().waitForDone(2000)
        qapp.processEvents()

        assert view.intra_minute_focus_ms == 0

    def test_the_counters_are_not_cleared_before_that_read_answers(self, make_timer):
        view = make_timer()
        view._toggle_timer()
        frame(view, 0)
        frame(view, 3000)
        self._park_just_before_a_rollover(view)

        frame(view, 20)

        assert view.intra_minute_focus_ms > 0


class TestTheHiddenCadence:
    def test_a_visible_tab_runs_at_the_screens_refresh_rate(self, make_timer):
        view = make_timer()
        view.show()

        assert view.engine_interval_ms() == view.visible_interval_ms()

    def test_a_hidden_tab_runs_about_once_a_second(self, make_timer):
        view = make_timer()
        view.show()
        view.hide()

        assert view.engine_interval_ms() == view.HIDDEN_INTERVAL_MS

    def test_the_hidden_cadence_is_slower_than_the_visible_one(self, make_timer):
        view = make_timer()

        assert view.HIDDEN_INTERVAL_MS > view.visible_interval_ms()

    def test_it_still_catches_every_minute_boundary(self, make_timer):
        view = make_timer()

        assert view.HIDDEN_INTERVAL_MS < 60_000

    def test_hiding_the_tab_slows_the_running_timer(self, make_timer):
        view = make_timer()
        view.show()
        view.refresh_timer.start(view.visible_interval_ms())

        view.hide()

        assert view.refresh_timer.interval() == view.HIDDEN_INTERVAL_MS
        assert view.refresh_timer.isActive()

    def test_showing_the_tab_restores_the_full_cadence(self, make_timer):
        view = make_timer()
        view.show()
        view.hide()
        assert view.refresh_timer.interval() == view.HIDDEN_INTERVAL_MS

        view.show()

        assert view.refresh_timer.interval() == view.visible_interval_ms()

    def test_the_engine_keeps_running_while_hidden(self, make_timer):
        view = make_timer()
        view.show()
        view.hide()

        assert view.refresh_timer.isActive()

    def test_shutdown_does_not_let_a_hide_show_restart_the_engine(self, make_timer):
        view = make_timer()

        view.shutdown()
        view.show()

        assert not view.refresh_timer.isActive()


class TestTheCadenceWhileABreakCoversIt:
    def test_a_covered_view_runs_ten_frames_a_second(self, make_timer):
        view = make_timer()
        view.show()
        view._strict_engaged = True

        assert view.engine_interval_ms() == view.COVERED_INTERVAL_MS

    def test_slower_than_the_screen_and_faster_than_a_hidden_tab(self, make_timer):
        view = make_timer()

        assert view.visible_interval_ms() < view.COVERED_INTERVAL_MS
        assert view.COVERED_INTERVAL_MS < view.HIDDEN_INTERVAL_MS

    def test_it_is_inside_the_second_every_covered_readout_counts_in(self, make_timer):
        view = make_timer()

        assert view.COVERED_INTERVAL_MS < 1000

    def test_a_minimised_window_is_still_the_hidden_cadence(self, make_timer):
        view = make_timer()
        view.show()
        view.hide()
        view._strict_engaged = True

        assert view.engine_interval_ms() == view.HIDDEN_INTERVAL_MS


class TestTheHiddenCadenceChangesNoStoredNumber:
    def _run(self, view, cadence_ms, wall_ms=6000):
        view.last_logged_minute = 0
        view._toggle_timer()
        frame(view, 0)
        run_for(view, wall_ms, cadence_ms)
        return totals(view)

    def test_the_four_totals_match_at_either_cadence(self, make_timer):
        at_full = self._run(make_timer(), cadence_ms=5)
        at_hidden = self._run(make_timer(), cadence_ms=PomodoroView.HIDDEN_INTERVAL_MS)

        for full, hidden in zip(at_full, at_hidden):
            assert full == pytest.approx(hidden, abs=20)

    def test_the_time_remaining_matches_at_either_cadence(self, make_timer):
        full_view, hidden_view = make_timer(), make_timer()
        self._run(full_view, cadence_ms=5)
        self._run(hidden_view, cadence_ms=PomodoroView.HIDDEN_INTERVAL_MS)

        assert full_view.time_left_ms == pytest.approx(hidden_view.time_left_ms, abs=20)

    def test_a_heartbeat_at_the_hidden_cadence_holds_the_same_state(
            self, make_timer, recording_db):
        view = make_timer()
        view.show()
        view.hide()
        view._toggle_timer()
        frame(view, 0)
        now = datetime.datetime.now()
        view.last_logged_minute = (now.hour * 60 + now.minute - 1) % 1440
        QThreadPool.globalInstance().waitForDone(2000)
        recording_db.calls.clear()

        frame(view, PomodoroView.HIDDEN_INTERVAL_MS)
        QThreadPool.globalInstance().waitForDone(2000)

        payload = next(args[0] for name, args in recording_db.calls
                       if name == "log_pomodoro_heartbeat")
        assert payload["state"] == "focus"
        assert payload["second"] == 0
