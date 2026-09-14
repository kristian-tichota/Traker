import pytest
from PyQt6.QtCore import Qt

from src.database import rows
from src.domain import plans
from src.gui.views.plan_view import MOVEMENT_HEADERS, PlanCalendar, PlanView

pytestmark = pytest.mark.gui

TODAY = plans.today_iso()
START = "2026-09-14"


def plan_row(session_count=2):
    return rows.TrainingPlanRow.from_server(
        [1, "Cycle 1", START, 4, "Rebuild", session_count])


def session(date, week=1, name="Upper A", block="re-entry", movements=2):
    return rows.PlanSessionRow.from_server(
        [hash(date) % 1000, date, week, name, block, "Keep it light", movements])


def movement(date, name="Overhead Press", position=0, sets=3, low=8, high=12,
             weight=16.5, ident=1):
    return rows.PlanMovementRow.from_server(
        [ident, date, "Upper A", position, name, sets, low, high, weight, 7.0,
         "3/3", None, None, "Reps"])


def exercise_log(date, name="Overhead Press", reps=(8, 8, 8), weight=16.5):
    padded = list(reps) + [0] * (5 - len(reps))
    return rows.ExerciseLogRow.from_server(
        [1, date, name, None, *padded, weight, 7.0, "Shoulders", "Reps"])


@pytest.fixture
def seeded(recording_db):
    recording_db.training_plans = [plan_row()]
    recording_db.plan_sessions = [session("2026-09-14"),
                                  session("2026-09-15", name="Lower A")]
    recording_db.plan_movements = [
        movement("2026-09-14", "Overhead Press", 0, ident=1),
        movement("2026-09-14", "Plank", 1, ident=2),
        movement("2026-09-15", "Overhead Press", 0, ident=3),
    ]
    recording_db.exercise_logs = [exercise_log("2026-09-14")]
    return recording_db


@pytest.fixture
def view(qapp, seeded, settled):
    built = PlanView(seeded)
    built.refresh()
    settled()
    yield built
    built.shutdown()
    built.deleteLater()
    qapp.processEvents()


class TestWhatItReads:
    def test_it_shows_the_cycle_that_has_started(self, view):
        assert view.plan.name == "Cycle 1"

    def test_the_ledger_read_is_bounded_at_the_cycles_own_start(self, view, seeded):
        assert ("exercise_logs", START) in seeded.since_asked

    def test_it_reads_once_for_the_whole_tab(self, view, seeded):
        assert len(seeded.since_asked) == 1

    def test_a_household_with_no_plan_says_so_rather_than_drawing_one(
        self, qapp, recording_db, settled
    ):
        built = PlanView(recording_db)
        built.refresh()
        settled()
        assert built.plan is None
        assert not built.model_for(0).rows
        built.shutdown()
        built.deleteLater()


class TestTheDayItShows:
    def test_it_opens_on_a_session_rather_than_a_rest_day(self, view):
        assert view.selected_date in {"2026-09-14", "2026-09-15"}

    def test_the_movements_are_the_selected_days_only(self, view):
        view.on_day_selected("2026-09-14")
        assert [row.name for row in view.model_for(0).rows] == [
            "Overhead Press", "Plank"]

    def test_moving_to_another_day_regroups_without_reading_again(
        self, view, seeded
    ):
        before = len(seeded.since_asked)
        view.on_day_selected("2026-09-15")
        assert [row.name for row in view.model_for(0).rows] == ["Overhead Press"]
        assert len(seeded.since_asked) == before

    def test_a_rest_day_empties_the_table_rather_than_keeping_the_last_one(
        self, view
    ):
        view.on_day_selected("2026-09-16")
        assert not view.model_for(0).rows

    def test_the_heading_names_the_session_and_its_state(self, view):
        view.on_day_selected("2026-09-14")
        assert "Upper A" in view.session_label.text()
        assert plans.DONE in view.session_label.text()

    def test_a_refresh_keeps_the_day_the_member_chose(self, view, settled):
        view.on_day_selected("2026-09-15")
        view.refresh()
        settled()
        assert view.selected_date == "2026-09-15"


class TestThePrescriptionAgainstTheLedger:
    def test_a_logged_movement_shows_what_was_done(self, view):
        view.on_day_selected("2026-09-14")
        press = view.model_for(0).rows[0]
        assert press.logged == "8/8/8 @ 16.5"

    def test_a_session_that_went_to_plan_reads_as_hit(self, view):
        view.on_day_selected("2026-09-14")
        assert view.model_for(0).rows[0].result == "hit"

    def test_an_unlogged_movement_of_a_trained_day_stays_blank(self, view):
        view.on_day_selected("2026-09-14")
        plank = view.model_for(0).rows[1]
        assert (plank.logged, plank.result) == ("", "")

    def test_the_columns_are_the_row_types_own_order(self, view):
        assert view.headers[0] == MOVEMENT_HEADERS

    def test_the_prescription_is_editable_and_the_ledgers_answer_is_not(self, view):
        editable = {MOVEMENT_HEADERS[index] for index in view.editable_columns(0)}
        assert "Load (kg)" in editable
        assert not ({"Logged", "Result"} & editable)


class TestEditingThePlan:
    def test_a_load_typed_into_the_table_reaches_the_service(
        self, view, seeded, settled
    ):
        view.on_day_selected("2026-09-14")
        model = view.model_for(0)
        column = MOVEMENT_HEADERS.index("Load (kg)")
        model.setData(model.index(0, column), "18.5", Qt.ItemDataRole.EditRole)
        settled()
        assert seeded.last("update_record")[0] == "plan_movements"


class TestTheTabNeverWrites:
    def test_enter_on_a_planned_day_offers_the_command(self, view):
        offered = []
        view.command_requested.connect(offered.append)
        view.on_log_requested("2026-09-14")
        assert offered == ["planlog 14.09.2026"]

    def test_offering_it_writes_nothing(self, view, seeded, settled):
        view.on_log_requested("2026-09-14")
        settled()
        assert not seeded.called("log_planned_session")


class TestTheCalendar:
    @pytest.fixture
    def calendar(self, qapp):
        built = PlanCalendar()
        built.resize(320, 260)
        built.show_plan(4, [session("2026-09-14"), session("2026-09-15",
                                                           name="Lower A")],
                        {"2026-09-14"}, "2026-09-15", "2026-09-15")
        yield built
        built.deleteLater()
        qapp.processEvents()

    def test_it_paints_without_raising(self, calendar, qapp):
        from PyQt6.QtGui import QPixmap

        pixmap = QPixmap(calendar.size())
        calendar.render(pixmap)
        assert not pixmap.isNull()

    def test_it_paints_an_empty_cycle_without_raising(self, qapp):
        from PyQt6.QtGui import QPixmap

        built = PlanCalendar()
        built.resize(320, 260)
        built.show_plan(1, [], set(), TODAY, "")
        pixmap = QPixmap(built.size())
        built.render(pixmap)
        assert not pixmap.isNull()
        built.deleteLater()

    def test_a_session_whose_date_will_not_parse_is_dropped_not_guessed_at(
        self, qapp
    ):
        built = PlanCalendar()
        built.show_plan(1, [session("not a date")], set(), TODAY, "")
        assert not built._cells
        built.deleteLater()

    def test_the_cursor_starts_on_the_selected_day(self, calendar):
        assert calendar._cells[calendar._cursor].date == "2026-09-15"

    def test_moving_left_announces_the_day_it_landed_on(self, calendar):
        seen = []
        calendar.day_selected.connect(seen.append)
        calendar.keyPressEvent(_key(Qt.Key.Key_H))
        assert seen == ["2026-09-14"]

    def test_moving_onto_a_rest_day_announces_an_empty_date(self, calendar):
        seen = []
        calendar.day_selected.connect(seen.append)
        calendar.keyPressEvent(_key(Qt.Key.Key_L))
        assert seen == [""]

    def test_the_cursor_does_not_leave_the_grid(self, calendar):
        for _ in range(10):
            calendar.keyPressEvent(_key(Qt.Key.Key_K))
        assert calendar._cursor[0] == 0

    def test_enter_on_a_rest_day_offers_nothing(self, calendar):
        asked = []
        calendar.log_requested.connect(asked.append)
        calendar.keyPressEvent(_key(Qt.Key.Key_L))
        calendar.keyPressEvent(_key(Qt.Key.Key_Return))
        assert asked == []

    def test_enter_on_a_planned_day_asks_for_that_day(self, calendar):
        asked = []
        calendar.log_requested.connect(asked.append)
        calendar.keyPressEvent(_key(Qt.Key.Key_Return))
        assert asked == ["2026-09-15"]


def _key(code):
    from PyQt6.QtGui import QKeyEvent

    return QKeyEvent(QKeyEvent.Type.KeyPress, code, Qt.KeyboardModifier.NoModifier)
