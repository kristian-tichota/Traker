import pytest

from src.gui.commands import COMMANDS
from src.gui.models.log_table import PENDING_TEXT
from src.gui.views.beverage_view import BeveragesView
from src.gui.views.exercise_view import ExerciseView
from src.gui.views.food_views import FoodView
from src.gui.views.mobility_view import MobilityView
from src.gui.views.supplement_view import SupplementsView

LOG_VIEWS = {"food": FoodView, "beverages": BeveragesView,
             "exercise": ExerciseView, "supplements": SupplementsView,
             "mobility": MobilityView}

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qapp, profile_path, recording_db):
    from src.gui.main_window import MainWindow

    built = MainWindow(recording_db)
    yield built
    built.close()
    built.deleteLater()


def submit(window, text, settled):
    window.command_line.setText(text)
    window.execute_command()
    settled()


class TestEveryLogCommandDeclaresItsRow:
    @pytest.mark.parametrize("name", ["log", "bevlog", "exlog", "supplog", "moblog"])
    def test_a_logging_command_can_show_its_row_at_once(self, name):
        assert COMMANDS[name].optimistic is not None

    @pytest.mark.parametrize("name", ["define", "bevdefine", "exdefine",
                                      "suppdefine", "mobdefine", "rm",
                                      "track", "graphlayout", "setdsi"])
    def test_a_command_that_writes_no_log_row_declares_none(self, name):
        assert COMMANDS[name].optimistic is None
        assert COMMANDS[name].pending_row({}) is None

    def test_the_row_starts_with_no_id(self):
        command = COMMANDS["log"]
        row = command.pending_row(command.parse("1 b Rolled Oats"))

        assert row[0] is None

    LOGGERS = {"log": "food", "bevlog": "beverages", "exlog": "exercise",
               "supplog": "supplements", "moblog": "mobility"}

    LINES = {"log": ["2 l Rolled Oats", "100g l Rolled Oats", "l Rolled Oats"],
             "bevlog": ["1 08:30 Black Coffee", "Black Coffee"],
             "exlog": ["7,7,7 30 8 Overhead Press"],
             "supplog": ["1 Morning Stack", "Morning Stack"],
             "moblog": ["20 Hip Opener"]}

    @pytest.mark.parametrize("name", list(LOGGERS))
    def test_the_row_is_no_wider_than_the_ledger_it_lands_in(
            self, qapp, profile_path, recording_db, name):
        view = LOG_VIEWS[self.LOGGERS[name]](recording_db)
        try:
            assert len(COMMANDS[name].optimistic.fields) <= len(view.headers[0])
        finally:
            view.shutdown()
            view.deleteLater()

    @pytest.mark.parametrize("name", list(LOGGERS))
    def test_every_declared_field_is_one_the_command_can_produce(self, name):
        command = COMMANDS[name]
        produced = set(dict(command.optimistic.fixed))
        for line in self.LINES[name]:
            produced |= set(command.parse(line))

        unfillable = set(command.optimistic.fields) - produced
        assert unfillable <= {"estimated", "meal_set", "drink_set", "stack",
                              "routine_set", "workout"}, (name, unfillable)


class TestTheRowAppearsBeforeTheRefresh:
    def test_a_food_log_lands_in_the_food_table_at_once(
            self, window, recording_db, settled):
        model = window.views["food"].model_for(0)
        before = model.rowCount()

        submit(window, "log 1 b Rolled Oats", settled)

        assert model.rowCount() >= before + 1

    def test_what_the_member_typed_is_what_is_shown(
            self, window, recording_db, settled):
        import datetime

        model = window.views["food"].model_for(0)

        submit(window, "log 2 l Rolled Oats", settled)

        last = model.rowCount() - 1
        today = datetime.date.today().strftime("%d.%m.%Y")
        assert model.index(last, 0).data() == PENDING_TEXT
        assert model.index(last, 1).data() == today
        assert model.index(last, 2).data() == "Lunch"
        assert model.index(last, 3).data() == "Rolled Oats"
        assert model.index(last, 4).data() == "2.00", "the servings typed"
        assert model.index(last, 5).data() == PENDING_TEXT

    def test_the_derived_columns_read_pending_rather_than_a_guess(
            self, window, recording_db, settled):
        model = window.views["food"].model_for(0)

        submit(window, "log 1 b Rolled Oats", settled)

        last = model.rowCount() - 1
        calories = window.views["food"].headers[0].index("Calories")
        assert model.index(last, calories).data() == PENDING_TEXT

    def test_a_pending_row_cannot_be_edited(self, window, recording_db, settled):
        from PyQt6.QtCore import Qt

        model = window.views["food"].model_for(0)
        submit(window, "log 1 b Rolled Oats", settled)
        last = model.rowCount() - 1

        accepted = model.setData(model.index(last, 1), "Dinner",
                                 Qt.ItemDataRole.EditRole)

        assert accepted is False

    def test_an_exercise_log_shows_every_set_it_was_given(
            self, window, recording_db, settled):
        model = window.views["exercise"].model_for(0)

        submit(window, "exlog 7,6,5 40 8 Overhead Press", settled)

        last = model.rowCount() - 1
        assert model.index(last, 1).data() == "Overhead Press"
        assert model.index(last, 2).data() == "", (
            "the workout column is known to be empty, not pending: :exlog "
            "refuses a workout name outright")
        assert [model.index(last, column).data() for column in range(3, 8)] == \
            ["7.00", "6.00", "5.00", "0.00", "0.00"]

    def test_the_1RM_column_is_pending_not_computed(
            self, window, recording_db, settled):
        model = window.views["exercise"].model_for(0)

        submit(window, "exlog 7,7,7 40 8 Overhead Press", settled)

        last = model.rowCount() - 1
        one_rm = window.views["exercise"].headers[0].index("1RM")
        assert model.index(last, one_rm).data() == PENDING_TEXT

    def test_a_beverage_log_shows_its_time(self, window, recording_db, settled):
        model = window.views["beverages"].model_for(0)

        submit(window, "bevlog 1 08:30 Black Coffee", settled)

        last = model.rowCount() - 1
        assert model.index(last, 1).data() == "08:30"
        assert model.index(last, 2).data() == "Black Coffee"

    def test_a_definition_inserts_no_row(self, window, recording_db, settled):
        model = window.views["food"].model_for(0)
        before = model.rowCount()

        submit(window, "define Steel Oats;Carbs;380;7;1;60;1;10;13;0;50", settled)

        assert model.rowCount() == before


class TestTheRefreshReconciles:
    def test_the_pending_row_is_replaced_by_what_the_store_holds(
            self, window, recording_db, settled):
        from src.database.rows import FoodLogRow

        model = window.views["food"].model_for(0)
        submit(window, "log 1 b Rolled Oats", settled)
        assert model.has_pending_rows()

        recording_db.food_logs = [FoodLogRow.from_server(
            [42, 0, "2026-09-06", "Breakfast", "Rolled Oats", 1.0, 50.0, None,
             190.0, 6.5, 30.0, 0.5, 3.5, 0.6, 0.0, 5.0])]
        window.views["food"].refresh()
        settled()

        assert not model.has_pending_rows()
        assert model.rowCount() == 1
        assert model.row_id(model.index(0, 0)) == 42

    def test_a_pending_row_the_refresh_does_not_contain_disappears(
            self, window, recording_db, settled):
        model = window.views["food"].model_for(0)
        submit(window, "log 1 b Rolled Oats", settled)
        assert model.rowCount() >= 1

        recording_db.food_logs = []
        window.views["food"].refresh()
        settled()

        assert model.rowCount() == 0

    def test_the_confirmed_row_is_editable_where_the_pending_one_was_not(
            self, window, recording_db, settled):
        from PyQt6.QtCore import Qt

        from src.database.rows import FoodLogRow

        model = window.views["food"].model_for(0)
        submit(window, "log 1 b Rolled Oats", settled)
        recording_db.food_logs = [FoodLogRow.from_server(
            [42, 0, "2026-09-06", "Breakfast", "Rolled Oats", 1.0, 50.0, None,
             190.0, 6.5, 30.0, 0.5, 3.5, 0.6, 0.0, 5.0])]
        window.views["food"].refresh()
        settled()

        assert model.setData(model.index(0, 1), "Dinner",
                             Qt.ItemDataRole.EditRole) is True


class TestATabTheProfileSwitchedOff:
    def test_a_command_for_an_absent_view_does_not_raise(
            self, qapp, write_profile, recording_db, settled):
        from src.gui.main_window import MainWindow

        write_profile('[windows]\nfood = false\n')
        window = MainWindow(recording_db)
        try:
            assert "food" not in window.views

            submit(window, "log 1 b Rolled Oats", settled)

            assert "Logged" in window.status_bar.text()
        finally:
            window.close()
            window.deleteLater()
