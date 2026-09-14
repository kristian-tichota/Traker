import pytest
from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from src.desktop.activities import VIDEO, BreakActivity
from src.database import rows
from src.domain import plans
from src.gui.views.plan_view import PlanView
from src.gui.views.pomodoro_view import (PomodoroView, StrictOverlay,
                                         read_upcoming)
from tests.gui.conftest import advance

pytestmark = [pytest.mark.gui, pytest.mark.exact, pytest.mark.accessibility]

TODAY = plans.today_iso()


def plan_row(start=TODAY, weeks=4):
    return rows.TrainingPlanRow.from_server([1, "Cycle 1", start, weeks, "Rebuild", 1])


def session(date, name="Upper A", week=1):
    return rows.PlanSessionRow.from_server(
        [1, date, week, name, "re-entry", "Keep it light", 2])


def movement(date, name="Overhead Press", position=0, sets=3, low=8, high=12,
             weight=16.5, ident=1, metric="Reps"):
    return rows.PlanMovementRow.from_server(
        [ident, date, "Upper A", position, name, sets, low, high, weight, 7.0,
         "3/3", None, None, metric])


def count_plan_reads(db):
    db.plan_reads = []
    for name in ("get_training_plans", "get_plan_sessions", "get_plan_movements"):
        answer = getattr(db, name)

        def counted(*args, _name=name, _answer=answer):
            db.plan_reads.append(_name)
            return _answer(*args)

        setattr(db, name, counted)
    return db


class Offline:
    online = False
    reason = "household service is not running"


@pytest.fixture
def app_id(qapp):
    previous = QGuiApplication.desktopFileName()
    QGuiApplication.setDesktopFileName("Traker.desktop")
    yield "traker"
    QGuiApplication.setDesktopFileName(previous)


@pytest.fixture
def with_a_session_today(recording_db):
    recording_db.training_plans = [plan_row()]
    recording_db.plan_sessions = [session(TODAY), session("2000-01-01", "Old")]
    recording_db.plan_movements = [
        movement(TODAY, "Overhead Press", 0, ident=1),
        movement(TODAY, "Plank", 1, sets=3, low=30, high=45, weight=0,
                 ident=2, metric="Seconds"),
        movement("2000-01-01", "Row", 0, ident=3),
    ]
    return count_plan_reads(recording_db)


@pytest.fixture
def timer(qapp, app_id, strict_timer, with_a_session_today):
    view = PomodoroView(with_a_session_today, tray_icon=None)
    view.refresh_timer.stop()
    view.stress_calendar.anim_timer.stop()
    view.last_logged_minute = -1
    yield view
    view.shutdown()
    QThreadPool.globalInstance().waitForDone(2000)
    view.deleteLater()


def enter_strict_break(view):
    view._skip_phase()
    assert view._strict_break_is_holding()


class TestWhatItSays:
    def test_it_names_todays_session(self, timer, settled):
        enter_strict_break(timer)
        settled()

        assert "Upper A" in timer.upcoming.lines()[0]

    def test_it_lists_the_movements_of_that_session_only(self, timer, settled):
        enter_strict_break(timer)
        settled()

        said = timer.upcoming.lines()
        assert any("Overhead Press · 3x8-12 · 16.5 kg" == line for line in said)
        assert any("Plank · 3x30-45 s" == line for line in said)
        assert not any("Row" in line for line in said)

    def test_a_day_with_nothing_on_it_is_named_rather_than_called_rest(
            self, timer, settled, with_a_session_today):
        with_a_session_today.plan_sessions = [session("2000-01-01", "Old")]
        with_a_session_today.plan_movements = []

        enter_strict_break(timer)
        settled()

        assert timer.upcoming.lines()[-1] == "nothing planned"

    def test_a_member_with_no_cycle_is_told_nothing(self, timer, settled,
                                                    with_a_session_today):
        with_a_session_today.training_plans = []

        enter_strict_break(timer)
        settled()

        assert timer.upcoming.lines() == []
        assert timer.upcoming.isHidden() is True

    def test_it_says_nothing_outside_a_break(self, timer, settled):
        settled()

        assert timer.upcoming.lines() == []

    def test_the_break_running_out_takes_it_away(self, timer, settled):
        enter_strict_break(timer)
        settled()

        advance(timer, timer.break_ms + 1000)

        assert timer.overlays
        assert timer.upcoming.lines() == []

        timer._toggle_timer()

        assert timer.upcoming.lines() == []


class TestEverySurfaceTheBreakCovers:
    def test_a_covered_screen_says_the_same_thing(self, timer, settled):
        enter_strict_break(timer)
        overlay = StrictOverlay(timer, QApplication.primaryScreen())
        timer.overlays.append(overlay)
        settled()

        assert overlay.upcoming.lines() == timer.upcoming.lines()

    def test_an_overlay_built_before_the_read_lands_still_gets_it(self, timer, settled):
        enter_strict_break(timer)
        overlay = StrictOverlay(timer, QApplication.primaryScreen())
        timer.overlays.append(overlay)

        settled()

        assert "Upper A" in overlay.upcoming.lines()[0]

    def test_every_surface_keeps_it_while_something_is_showing(
            self, timer, settled):
        enter_strict_break(timer)
        overlay = StrictOverlay(timer, QApplication.primaryScreen())
        timer.overlays.append(overlay)
        settled()

        timer._showing = (timer._offers[0] if timer._offers else
                          BreakActivity("Watching", "/x/talk.mkv", VIDEO))
        timer._show_upcoming()

        assert "Upper A" in timer.upcoming.lines()[0]
        assert "Upper A" in overlay.upcoming.lines()[0]


class TestReadOnceAndNotOncePerFrame:
    def test_a_break_beginning_reads_it_once(self, timer, settled,
                                             with_a_session_today):
        enter_strict_break(timer)
        settled()

        assert with_a_session_today.plan_reads.count("get_training_plans") == 1

    def test_nothing_is_read_before_a_break(self, timer, settled):
        settled()

        assert timer.db.plan_reads == []

    def test_many_frames_are_no_further_reads(self, timer, settled,
                                              with_a_session_today):
        enter_strict_break(timer)
        settled()
        timer.overlays.append(StrictOverlay(timer, QApplication.primaryScreen()))
        before = list(with_a_session_today.plan_reads)

        for _ in range(30):
            advance(timer, 16)
        settled()

        assert with_a_session_today.plan_reads == before

    def test_the_next_break_reads_it_again(self, timer, settled,
                                           with_a_session_today):
        enter_strict_break(timer)
        settled()
        timer._release_strict_break()
        timer._toggle_timer()
        with_a_session_today.plan_reads.clear()

        enter_strict_break(timer)
        settled()

        assert "get_training_plans" in with_a_session_today.plan_reads
        assert "Upper A" in timer.upcoming.lines()[0]


class TestAReadThatDidNotArrive:
    def test_nothing_is_shown_rather_than_another_days_plan(self, timer, settled,
                                                            with_a_session_today):
        enter_strict_break(timer)
        settled()
        assert timer.upcoming.lines() != []

        with_a_session_today.connection = Offline()
        timer._read_upcoming()
        settled()

        assert timer.upcoming.lines() == []


class TestTheTabAndTheSurfaceAgree:
    def test_the_same_targets_reach_both(self, qapp, settled, with_a_session_today):
        tab = PlanView(with_a_session_today)
        tab.refresh()
        settled()

        surface = read_upcoming(with_a_session_today)

        row = next(r for r in tab.model_for(0).rows if r.name == "Overhead Press")
        line = next(line for line in surface[0][1] if "Overhead Press" in line)
        assert plans.scheme_text(row.sets, row.target_low, row.target_high,
                                 "Reps") in line
        assert f"{row.weight_kg:g} kg" in line

        tab.shutdown()
        tab.deleteLater()
        qapp.processEvents()

    def test_both_read_the_same_day(self, qapp, settled, with_a_session_today):
        tab = PlanView(with_a_session_today)
        tab.refresh()
        settled()

        assert tab.selected_date == TODAY
        assert read_upcoming(with_a_session_today)[0][0].endswith("W1")

        tab.shutdown()
        tab.deleteLater()
        qapp.processEvents()
