import pytest
from PyQt6.QtCore import QDateTime, QThreadPool

from src.gui.views.pomodoro_view import HOLD_STOP, PomodoroView
from tests.gui.conftest import advance

pytestmark = [pytest.mark.gui, pytest.mark.exact]


def built(recording_db):
    view = PomodoroView(recording_db, tray_icon=None)
    view.refresh_timer.stop()
    view.stress_calendar.anim_timer.stop()
    view.last_logged_minute = -1
    return view


@pytest.fixture
def timer(qapp, profile_path, recording_db):
    view = built(recording_db)
    yield view
    QThreadPool.globalInstance().waitForDone(2000)
    view.deleteLater()


@pytest.fixture
def strict(qapp, strict_timer, recording_db):
    view = built(recording_db)
    assert view.strict_mode is True
    yield view
    view.shutdown()
    QThreadPool.globalInstance().waitForDone(2000)
    view.deleteLater()


def stop_by_hand(view, seconds=None):
    """The stop held for as long as it asks, the way the button drives it."""
    view._begin_stop_hold()
    paid = view.stop_hold_secs if seconds is None else seconds
    view._hold_started_ms = QDateTime.currentMSecsSinceEpoch() - int(paid * 1000)
    view._hold_tick()


class Away:
    """What the session answers for how long the member has been idle."""

    def __init__(self, ms=0):
        self.ms = ms

    def __call__(self):
        return self.ms


def start_recording(recording_db):
    QThreadPool.globalInstance().waitForDone(2000)
    recording_db.calls.clear()


class TestStateRouting:
    def test_running_focus_accrues_to_focus(self, timer):
        timer._toggle_timer()

        assert timer.is_running is True
        assert timer._get_current_state() == "focus"

    def test_a_running_break_accrues_to_rest(self, timer):
        timer._toggle_timer()
        timer._skip_phase()

        assert timer.current_phase == "break"
        assert timer._get_current_state() == "rest"

    def test_waiting_to_start_focus_accrues_to_rest_overtime(self, timer):
        assert timer.waiting_for_work_start is True
        assert timer._get_current_state() == "rest_overtime"

    def test_waiting_to_start_a_break_accrues_to_focus_overtime(self, timer):
        timer._toggle_timer()
        timer.time_left_ms = 5
        advance(timer, 50)

        assert timer.waiting_for_break_start is True
        assert timer._get_current_state() == "focus_overtime"

    def test_stopping_focus_by_hand_accrues_to_focus_overtime(self, timer):
        timer._toggle_timer()

        stop_by_hand(timer)

        assert timer.is_running is False
        assert timer._get_current_state() == "focus_overtime"

    def test_an_interval_the_member_walked_away_from_accrues_to_rest_overtime(self, timer):
        timer._toggle_timer()
        timer.idle_source = Away(timer.idle_pause_ms)

        timer._watch_for_the_member()

        assert timer.is_running is False
        assert timer._get_current_state() == "rest_overtime"

    def test_pausing_a_break_accrues_to_focus_overtime(self, timer):
        timer._toggle_timer()
        timer._skip_phase()

        timer._toggle_timer()

        assert timer.current_phase == "break"
        assert timer._get_current_state() == "focus_overtime"

    def test_the_engine_accumulates_into_the_counter_for_the_current_state(self, timer):
        timer._toggle_timer()

        advance(timer, 250)

        assert timer.intra_minute_focus_ms == pytest.approx(250, abs=50)
        assert timer.intra_minute_rest_ms == 0


class TestFreshTimer:
    def test_a_fresh_timer_waits_in_rest_overtime_with_a_full_clock(self, timer):
        assert timer.current_phase == "work"
        assert timer.time_left_ms == timer.work_ms
        assert timer.is_running is False
        assert timer._get_current_state() == "rest_overtime"

    def test_it_says_it_is_waiting_for_the_user(self, timer):
        assert "PRESS PLAY" in timer.lbl_phase.text()

    def test_the_clock_shows_minutes_seconds_and_hundredths(self, timer):
        assert timer.lbl_timer.text() == "30:00.00"

    @pytest.mark.parametrize(
        "milliseconds, rendered",
        [(0, "00:00.00"), (65432, "01:05.43"), (1_800_000, "30:00.00"), (-5, "00:00.00")],
    )
    def test_the_clock_format(self, timer, milliseconds, rendered):
        assert timer._format_high_precision(milliseconds) == rendered


class TestFocusEnding:
    def test_without_strict_mode_the_clock_holds_at_zero(self, timer):
        timer._toggle_timer()
        timer.time_left_ms = 5

        advance(timer, 50)

        assert timer.time_left_ms == 0
        assert timer.is_running is False
        assert timer.current_phase == "work"
        assert "FOCUS OVER" in timer.lbl_phase.text()

    def test_strict_mode_starts_the_break_immediately(self, strict):
        strict._toggle_timer()
        strict.time_left_ms = 5

        advance(strict, 50)

        assert strict.current_phase == "break"
        assert strict.is_running is True

    def test_starting_the_break_by_hand_records_a_resumed_break_event(self, timer, recording_db):
        timer._toggle_timer()
        timer.time_left_ms = 5
        advance(timer, 50)
        start_recording(recording_db)

        timer._toggle_timer()

        assert timer.current_phase == "break"
        assert timer.is_running is True
        QThreadPool.globalInstance().waitForDone(2000)
        assert recording_db.last("log_pomodoro_event")["event_type"] == "resumed_break"


class TestBreakEnding:
    def test_a_break_never_resumes_focus_automatically(self, timer):
        timer._toggle_timer()
        timer._skip_phase()
        timer.time_left_ms = 5

        advance(timer, 50)

        assert timer.current_phase == "work"
        assert timer.time_left_ms == timer.work_ms
        assert timer.is_running is False
        assert timer.waiting_for_work_start is True
        assert "REST OVER" in timer.lbl_phase.text()

    def test_the_wait_after_a_break_accrues_to_rest_overtime(self, timer):
        timer._toggle_timer()
        timer._skip_phase()
        timer.time_left_ms = 5
        advance(timer, 50)

        assert timer._get_current_state() == "rest_overtime"

    def test_starting_focus_by_hand_records_a_resumed_focus_event(self, timer, recording_db):
        start_recording(recording_db)

        timer._toggle_timer()

        assert timer.is_running is True
        assert "FOCUS INTERVAL" in timer.lbl_phase.text()
        QThreadPool.globalInstance().waitForDone(2000)
        assert recording_db.last("log_pomodoro_event")["event_type"] == "resumed_focus"

    def test_strict_mode_also_waits_at_the_end_of_a_break(self, strict):
        timer = strict
        timer._toggle_timer()
        timer._skip_phase()
        timer.time_left_ms = 5

        advance(timer, 50)

        assert timer.current_phase == "work"
        assert timer.is_running is False


class TestTheLongBreak:
    def test_the_ordinary_break_is_what_follows_focus(self, timer):
        timer._toggle_timer()

        timer._skip_phase()

        assert timer.current_phase == "break"
        assert timer.time_left_ms == timer.break_ms

    def test_a_queued_one_is_what_follows_the_next_focus(self, timer):
        timer.set_long_break_queued(True)
        timer._toggle_timer()

        timer._skip_phase()

        assert timer.current_phase == "long_break"
        assert timer.time_left_ms == timer.long_break_ms

    def test_queuing_it_does_not_lengthen_the_break_already_running(self, timer):
        timer._toggle_timer()
        timer._skip_phase()

        timer.set_long_break_queued(True)

        assert timer.time_left_ms == timer.break_ms
        assert timer.current_phase == "break"

    def test_it_is_spent_when_it_begins(self, timer, recording_db):
        timer.set_long_break_queued(True)
        assert timer.long_breaks_left() == 2
        timer._toggle_timer()
        start_recording(recording_db)

        timer._skip_phase()

        assert timer.long_breaks_left() == 1
        QThreadPool.globalInstance().waitForDone(2000)
        assert recording_db.last("log_pomodoro_event")["event_type"] == "long_break_started"

    def test_queuing_and_changing_your_mind_costs_nothing(self, timer):
        timer.set_long_break_queued(True)

        timer.set_long_break_queued(False)

        assert timer.long_breaks_left() == 2
        assert timer._long_break_queued is False

    def test_one_queued_break_is_one_break(self, timer):
        timer.set_long_break_queued(True)
        timer._toggle_timer()
        timer._skip_phase()
        timer._skip_phase()
        timer._toggle_timer()

        timer._skip_phase()

        assert timer.current_phase == "break"

    def test_the_third_one_of_a_day_is_refused_in_words(self, timer):
        for _ in range(2):
            timer.set_long_break_queued(True)
            timer._toggle_timer()
            timer._skip_phase()
            timer._skip_phase()

        said = timer.set_long_break_queued(True)

        assert timer._long_break_queued is False
        assert "spent" in said

    def test_and_the_button_says_so(self, timer):
        for _ in range(2):
            timer.set_long_break_queued(True)
            timer._toggle_timer()
            timer._skip_phase()
            timer._skip_phase()

        assert timer.btn_long.isEnabled() is False

    def test_the_dots_count_what_the_day_has_spent(self, timer):
        timer.set_long_break_queued(True)
        timer._toggle_timer()
        timer._skip_phase()

        assert (timer.progress_dots.spent, timer.progress_dots.available) == (1, 2)

    def test_midnight_gives_them_back(self, timer):
        timer.set_long_break_queued(True)
        timer._toggle_timer()
        timer._skip_phase()
        assert timer.long_breaks_left() == 1

        timer._long_break_day = "2026-09-09"

        assert timer.long_breaks_left() == 2

    def test_a_restart_does_not_hand_the_afternoon_two_more(self, qapp, profile_path,
                                                            recording_db, settled):
        import datetime

        from src.gui.views.pomodoro_view import LONG_BREAK_EVENT

        today = datetime.date.today().isoformat()
        recording_db.pomodoro_events = [
            (f"{today}T09:00:00", LONG_BREAK_EVENT, 0)]
        recording_db.get_pomodoro_events_for_day = (
            lambda date: list(recording_db.pomodoro_events))

        view = built(recording_db)
        settled()

        assert view.long_breaks_left() == 1

        QThreadPool.globalInstance().waitForDone(2000)
        view.deleteLater()

    def test_a_toggle_is_the_other_state_from_the_one_it_is_in(self, timer):
        timer.toggle_long_break()
        assert timer._long_break_queued is True

        timer.toggle_long_break()
        assert timer._long_break_queued is False


class TestSkipping:
    def test_skipping_focus_records_the_phase_and_the_remaining_time(self, timer, recording_db):
        timer._toggle_timer()
        timer.time_left_ms = 420_000
        start_recording(recording_db)

        timer._skip_phase()

        QThreadPool.globalInstance().waitForDone(2000)
        event = recording_db.last("log_pomodoro_event")
        assert event["event_type"] == "skipped_focus"
        assert event["amount_ms"] == 420_000

    def test_skipping_a_break_is_recorded_as_such(self, timer, recording_db):
        timer._toggle_timer()
        timer._skip_phase()
        start_recording(recording_db)

        timer._skip_phase()

        QThreadPool.globalInstance().waitForDone(2000)
        assert recording_db.last("log_pomodoro_event")["event_type"] == "skipped_break"

    def test_skipping_moves_on_as_though_the_interval_had_elapsed(self, timer):
        timer._toggle_timer()

        timer._skip_phase()

        assert timer.current_phase == "break"
        assert timer.time_left_ms == timer.break_ms


class TestStoppingByHand:
    def test_a_click_leaves_a_running_interval_running(self, timer):
        timer._toggle_timer()

        timer.btn_play.click()

        assert timer.is_running is True
        assert timer._get_current_state() == "focus"

    def test_the_hold_stops_it(self, timer, recording_db):
        timer._toggle_timer()
        start_recording(recording_db)

        stop_by_hand(timer)

        QThreadPool.globalInstance().waitForDone(2000)
        assert timer.is_running is False
        assert recording_db.last("log_pomodoro_event")["event_type"] == "paused_focus"

    def test_letting_go_early_costs_nothing(self, timer, recording_db):
        timer._toggle_timer()
        start_recording(recording_db)

        stop_by_hand(timer, timer.stop_hold_secs - 2)
        timer.cancel_hold()

        QThreadPool.globalInstance().waitForDone(2000)
        assert timer.is_running is True
        assert not recording_db.called("log_pomodoro_event")

    def test_the_click_that_ends_the_hold_does_not_start_it_again(self, timer):
        timer._toggle_timer()

        stop_by_hand(timer)
        timer.cancel_hold()
        timer._toggle_timer()

        assert timer.is_running is False

    def test_starting_again_is_one_press(self, timer):
        timer._toggle_timer()
        stop_by_hand(timer)

        timer.btn_play.click()

        assert timer.is_running is True
        assert timer.current_phase == "work"

    def test_a_break_that_holds_no_screens_still_stops_on_the_click(self, timer):
        timer._toggle_timer()
        timer._skip_phase()

        timer.btn_play.click()

        assert timer.current_phase == "break"
        assert timer.is_running is False

    def test_the_ring_counts_down_what_a_stop_costs(self, timer):
        timer._toggle_timer()

        timer.begin_hold(HOLD_STOP)

        assert timer.hold_ring.hold_secs == timer.stop_hold_secs
        assert timer._hold_timer.isActive() is True

    def test_a_running_interval_says_what_a_stop_costs(self, timer):
        timer._toggle_timer()

        assert timer.lbl_release_hint.isHidden() is False
        assert f"{timer.stop_hold_secs:.0f}s" in timer.lbl_release_hint.text()


class TestWalkingAway:
    def test_the_absence_is_recorded_with_what_was_left(self, timer, recording_db):
        timer._toggle_timer()
        timer.time_left_ms = 300_000
        timer.idle_source = Away(timer.idle_pause_ms)
        start_recording(recording_db)

        timer._watch_for_the_member()

        QThreadPool.globalInstance().waitForDone(2000)
        event = recording_db.last("log_pomodoro_event")
        assert event["event_type"] == "idled_focus"
        assert event["amount_ms"] == 300_000

    def test_the_minutes_of_the_inactivity_are_stored_as_rest_overtime(self, timer, recording_db):
        timer._toggle_timer()
        timer.idle_source = Away(timer.idle_pause_ms)
        start_recording(recording_db)

        timer._watch_for_the_member()

        QThreadPool.globalInstance().waitForDone(2000)
        stored = [args[0] for name, args in recording_db.calls
                  if name == "log_pomodoro_heartbeat"]
        assert len(stored) == timer.idle_pause_ms // 60_000
        assert {row["state"] for row in stored} == {"rest_overtime"}
        assert {row["second"] for row in stored} == {0}

    def test_the_part_minute_since_the_last_one_moves_with_them(self, timer):
        timer._toggle_timer()
        timer.intra_minute_focus_ms = 20_000

        timer.idle_source = Away(timer.idle_pause_ms)
        timer._watch_for_the_member()

        assert timer.intra_minute_focus_ms == 0
        assert timer.intra_minute_rest_ot_ms == 20_000

    def test_the_live_totals_move_with_the_minutes(self, timer):
        timer._toggle_timer()
        timer.live_focus_ms = 10 * 60_000
        timer.live_rest_ot_ms = 0

        timer.idle_source = Away(timer.idle_pause_ms)
        timer._watch_for_the_member()

        moved = timer.idle_pause_ms
        assert timer.live_focus_ms == 10 * 60_000 - moved
        assert timer.live_rest_ot_ms == moved

    def test_a_rewrite_that_did_not_land_is_named_in_the_log(self, timer, recording_db,
                                                            settled, caplog):
        timer._toggle_timer()
        timer.idle_source = Away(timer.idle_pause_ms)
        recording_db.result = (False, "no service")

        with caplog.at_level("WARNING"):
            timer._watch_for_the_member()
            settled()

        assert "minute(s) of an absence as focus" in caplog.text

    def test_no_break_lands_while_the_member_is_away(self, timer):
        timer._toggle_timer()
        timer.time_left_ms = 5_000
        timer.idle_source = Away(timer.idle_pause_ms)
        timer._watch_for_the_member()

        advance(timer, 60_000)

        assert timer.current_phase == "work"
        assert timer.time_left_ms == 5_000

    def test_coming_back_carries_the_interval_on(self, timer, recording_db):
        timer._toggle_timer()
        timer.time_left_ms = 5_000
        timer.idle_source = Away(timer.idle_pause_ms)
        timer._watch_for_the_member()
        start_recording(recording_db)

        timer.idle_source = Away(0)
        timer._watch_for_the_member()

        QThreadPool.globalInstance().waitForDone(2000)
        assert timer._get_current_state() == "focus"
        assert timer.time_left_ms == 5_000
        assert recording_db.last("log_pomodoro_event")["event_type"] == "resumed_focus"

    def test_the_break_still_lands_after_what_was_left(self, timer):
        timer._toggle_timer()
        timer.time_left_ms = 5_000
        timer.idle_source = Away(timer.idle_pause_ms)
        timer._watch_for_the_member()

        timer.idle_source = Away(0)
        timer._watch_for_the_member()
        advance(timer, 6_000)

        assert timer.waiting_for_break_start is True

    def test_pressing_play_is_coming_back_too(self, timer):
        timer._toggle_timer()
        timer.idle_source = Away(timer.idle_pause_ms)
        timer._watch_for_the_member()

        timer.btn_play.click()

        assert timer._idled is False
        assert timer._get_current_state() == "focus"

    def test_a_threshold_of_zero_leaves_the_clock_running(self, timer):
        timer._toggle_timer()
        timer.idle_pause_ms = 0
        timer.idle_source = Away(3_600_000)

        timer._watch_for_the_member()

        assert timer.is_running is True

    def test_a_session_that_cannot_say_leaves_the_clock_running(self, timer):
        timer._toggle_timer()
        timer.idle_source = Away(None)

        timer._watch_for_the_member()

        assert timer.is_running is True

    def test_a_break_is_not_watched_for_absence(self, timer):
        timer._toggle_timer()
        timer._skip_phase()
        timer.idle_source = Away(timer.idle_pause_ms)

        timer._watch_for_the_member()

        assert timer.is_running is True
        assert timer._get_current_state() == "rest"

    def test_an_absence_gives_up_a_stop_hold_that_was_being_paid(self, timer):
        timer._toggle_timer()
        timer.begin_hold(HOLD_STOP)
        timer.idle_source = Away(timer.idle_pause_ms)

        timer._watch_for_the_member()

        assert timer._hold_timer.isActive() is False
        assert timer.hold_ring.isHidden() is True


class TestManualActionsAndHeartbeats:
    def test_pausing_records_an_event_but_no_heartbeat(self, timer, recording_db):
        timer._toggle_timer()
        start_recording(recording_db)

        stop_by_hand(timer)

        QThreadPool.globalInstance().waitForDone(2000)
        assert recording_db.called("log_pomodoro_event")
        assert not recording_db.called("log_pomodoro_heartbeat")

    def test_a_minute_rollover_stores_one_heartbeat_and_resets_the_sub_minute_counters(
        self, timer, recording_db, settled
    ):
        timer._toggle_timer()
        advance(timer, 500)
        assert timer.intra_minute_focus_ms > 0
        timer.last_logged_minute = (timer.last_logged_minute + 1) % 1440
        start_recording(recording_db)

        advance(timer, 50)

        settled()
        heartbeat = recording_db.last("log_pomodoro_heartbeat")
        assert heartbeat["state"] == "focus"
        assert heartbeat["second"] == 0
        assert "mode" not in heartbeat
        assert timer.intra_minute_focus_ms == 0, "the sub-minute counters hand over to the store"

    def test_the_live_totals_combine_stored_minutes_with_the_sub_minute_counters(self, timer):
        timer.live_focus_ms = 120_000
        timer._toggle_timer()

        advance(timer, 500)

        assert timer.lbl_timer.text() != ""
        assert timer.rows_val_labels[0].text().startswith("02:00.")


class TestTheSplitIsTheSchedule:
    def test_the_shipped_split_is_thirty_and_thirty(self, timer):
        assert (timer.work_ms, timer.break_ms) == (30 * 60000, 30 * 60000)

    def test_the_long_break_is_an_hour_twice_a_day(self, timer):
        assert timer.long_break_ms == 60 * 60000
        assert timer.long_breaks_per_day == 2

    def test_the_view_says_what_the_split_is(self, timer):
        assert "30 / 30" in timer.lbl_split.text()

    def test_a_member_may_write_their_own(self, qapp, write_profile, recording_db):
        write_profile("[timer]\nfocus_mins = 50\nbreak_mins = 10\n"
                      "long_break_mins = 25\nlong_breaks_per_day = 3\n")

        view = built(recording_db)

        assert (view.work_ms, view.break_ms) == (50 * 60000, 10 * 60000)
        assert (view.long_break_ms, view.long_breaks_per_day) == (25 * 60000, 3)

        QThreadPool.globalInstance().waitForDone(2000)
        view.deleteLater()


class TestTheCommandThatQueuesALongBreak:
    def submit(self, window, text, settled):
        window.command_line.setText(text)
        window.execute_command()
        settled()
        return window.status_bar.text()

    def test_it_queues_the_next_break(self, window, settled):
        line = self.submit(window, "break long", settled)

        assert window.views["pomodoro"]._long_break_queued is True
        assert "60 minutes" in line

    def test_it_takes_it_back(self, window, settled):
        self.submit(window, "break long", settled)

        line = self.submit(window, "break cancel", settled)

        assert window.views["pomodoro"]._long_break_queued is False
        assert "ordinary one" in line

    def test_asking_twice_is_not_two_long_breaks(self, window, settled):
        self.submit(window, "break long", settled)

        self.submit(window, "break long", settled)

        assert window.views["pomodoro"].long_breaks_left() == 2

    def test_break_alone_reports_rather_than_changes(self, window, settled):
        line = self.submit(window, "break", settled)

        assert "2 of 2 left today" in line
        assert window.views["pomodoro"]._long_break_queued is False

    def test_a_word_it_does_not_know_is_refused_and_left_to_correct(self, window, settled):
        line = self.submit(window, "break soon", settled)

        assert "Syntax" in line
        assert window.command_line.text() == "break soon"

    def test_it_writes_no_household_data(self, window, settled):
        from src.gui.commands import COMMANDS

        self.submit(window, "break long", settled)

        assert COMMANDS["break"].domains == ()
