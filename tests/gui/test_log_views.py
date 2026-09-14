import pytest

from src.gui.views.base import BaseManagedView
from src.gui.views.beverage_view import BeveragesView
from src.gui.views.exercise_view import ExerciseView
from src.gui.views.food_views import FoodView
from src.gui.views.mobility_view import MobilityView
from src.gui.views.supplement_view import SupplementsView

pytestmark = pytest.mark.gui

STOCK = {
    ExerciseView: (
        {"exercise_logs": [(1, "2026-09-05", "Overhead Press", 8, 8, 8, 0, 0, 40.0, 7.0)],
         "exercises": ["Overhead Press"]},
        {0, 1},
    ),
    MobilityView: (
        {"mobility_logs": [(1, "2026-09-05", "Hip Opener", 20.0, 3.0)],
         "mobility": ["Hip Opener"]},
        {0, 1},
    ),
    SupplementsView: (
        {"supplement_logs": [(1, "2026-09-05", "Morning Stack", 1.0, 500.0)],
         "supplements": ["Morning Stack"]},
        {0, 1},
    ),
    BeveragesView: (
        {"beverage_logs": [], "beverages": ["Black Coffee"]},
        {1},
    ),
    FoodView: (
        {"food_logs": [], "foods": ["Rolled Oats"]},
        {1},
    ),
}

TABLE_VIEWS = [ExerciseView, MobilityView, SupplementsView, BeveragesView, FoodView]


@pytest.fixture
def make_view(qapp, profile_path, recording_db):
    built = []

    def _make(view_class):
        stock, _expected = STOCK[view_class]
        for attribute, rows in stock.items():
            setattr(recording_db, attribute, list(rows))
        view = view_class(recording_db)
        built.append(view)
        return view

    yield _make

    from PyQt6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()
    for view in built:
        view.shutdown()
        view.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize("view_class", TABLE_VIEWS,
                         ids=lambda c: c.__name__)


class TestEveryLogTabRefreshes:
    def test_it_is_built_on_the_shared_table_view(self, make_view, view_class):
        assert isinstance(make_view(view_class), BaseManagedView)

    def test_every_table_it_hosts_is_registered_by_index(self, make_view, view_class):
        view = make_view(view_class)

        assert sorted(view._table_widgets) == list(range(len(view.tables)))

    def test_every_table_has_a_model_holding_its_rows(self, make_view, view_class):
        view = make_view(view_class)

        assert sorted(view._table_models) == list(range(len(view.tables)))
        assert sorted(view._table_proxies) == list(range(len(view.tables)))
        for index, widget in view._table_widgets.items():
            assert widget.model() is view.proxy_for(index)
            assert view.proxy_for(index).sourceModel() is view.model_for(index)

    def test_a_refresh_reaches_the_service_and_renders(self, make_view, view_class, settled):
        view = make_view(view_class)

        view.refresh()
        settled()

    def test_a_refresh_against_a_service_that_answers_nothing_renders_empty(
        self, make_view, view_class, recording_db, settled
    ):
        view = make_view(view_class)
        for attribute in STOCK[view_class][0]:
            setattr(recording_db, attribute, [])

        view.refresh()
        settled()

        for model in view._table_models.values():
            assert model.rowCount() == 0


@pytest.mark.parametrize("view_class", TABLE_VIEWS, ids=lambda c: c.__name__)
class TestARefreshFillsTheRightTable:
    def test_the_rows_land_in_the_table_the_view_asked_for(
        self, make_view, view_class, settled
    ):
        view = make_view(view_class)

        view.refresh()
        settled()

        filled = {index for index, model in view._table_models.items()
                  if model.rowCount() > 0}
        assert filled == STOCK[view_class][1]


class TestDeletingARow:
    def test_the_delete_reaches_the_service(self, make_view, recording_db, settled):
        view = make_view(ExerciseView)

        view.fetch(view._delete_row, view._on_delete_finished, "exercise_logs", 7)
        settled()

        assert recording_db.last("delete_record") == ("exercise_logs", 7)

    def test_the_confirmation_names_the_table(self, make_view, settled):
        view = make_view(ExerciseView)
        said = []
        view.status_message.connect(said.append)

        view.fetch(view._delete_row, view._on_delete_finished, "exercise_logs", 7)
        settled()

        assert "exercise_logs" in said[-1]

    def test_a_refused_delete_says_why_and_does_not_claim_success(
        self, make_view, recording_db, settled
    ):
        view = make_view(ExerciseView)
        recording_db.result = (False, "No row 7 of exercise_logs")
        said = []
        view.status_message.connect(said.append)

        view.fetch(view._delete_row, view._on_delete_finished, "exercise_logs", 7)
        settled()

        assert "No row 7" in said[-1]
        assert "Deleted" not in said[-1]

    def test_a_successful_delete_marks_every_tab_stale(self, make_view, settled):
        view = make_view(ExerciseView)
        changed = []
        view.data_changed.connect(lambda: changed.append(True))

        view.fetch(view._delete_row, view._on_delete_finished, "exercise_logs", 7)
        settled()

        assert changed == [True]


class TestTheFoodTabsBars:
    def test_todays_totals_come_from_the_shared_summation(
        self, make_view, recording_db, settled
    ):
        import datetime

        from src.database.rows import FoodLogRow

        today = datetime.date.today().isoformat()
        view = make_view(FoodView)
        recording_db.food_logs = [
            FoodLogRow.from_server([1, 0, today, "Breakfast", "Oats", 1.0, 50.0,
                                    None,
                                    300.0, 20.0, 40.0, 2.0, 5.0, 1.0, 1.5, 8.0]),
            FoodLogRow.from_server([2, 0, today, "Lunch", "Oats", 1.0, 50.0, None,
                                    450.0, 15.0, 50.0, 3.0, 8.0, 2.0, 0.5, 6.0]),
            FoodLogRow.from_server([3, 0, "2026-01-01", "Dinner", "Oats", 1.0,
                                    50.0, None,
                                    999.0, 99.0, 99.0, 9.0, 9.0, 9.0, 9.0, 9.0]),
        ]

        view.refresh()
        settled()

        assert view.cal_bar.actual_value == pytest.approx(750.0)
        assert view.prot_bar.actual_value == pytest.approx(35.0)
        assert view.salt_bar.actual_value == pytest.approx(2.0)

    def test_the_activity_read_asks_only_for_today(
        self, make_view, recording_db, settled
    ):
        import datetime

        view = make_view(FoodView)

        view.refresh()
        settled()

        assert ("heatmap_points", datetime.date.today().isoformat()) \
            in recording_db.since_asked


class TestTheDayReadsAsPoorlyLoggedWhenItWas:
    @staticmethod
    def food(row_id, kcal, protein, estimated=0):
        import datetime

        from src.database.rows import FoodLogRow

        return FoodLogRow.from_server(
            [row_id, estimated, datetime.date.today().isoformat(), "Dinner",
             "Something", 1.0, 100.0, None, kcal, protein, 0.0, 0.0, 0.0, 0.0,
             0.0, 0.0])

    def test_a_well_logged_day_says_nothing_at_all(
            self, make_view, recording_db, settled):
        view = make_view(FoodView)
        recording_db.food_logs = [self.food(1, 1550.0, 120.0)]

        view.refresh()
        settled()

        assert view.estimate_note.text() == ""
        assert not view.estimate_note.isVisible()

    def test_it_reports_how_much_of_the_day_was_guessed(
            self, make_view, recording_db, settled):
        view = make_view(FoodView)
        recording_db.food_logs = [self.food(1, 1550.0, 120.0),
                                  self.food(2, 550.0, 0.0, estimated=1)]

        view.refresh()
        settled()

        said = view.estimate_note.text()
        assert "550" in said and "2,100" in said
        assert "26%" in said
        assert "1 row" in said

    def test_the_bars_still_count_the_estimate_towards_the_day(
            self, make_view, recording_db, settled):
        view = make_view(FoodView)
        recording_db.food_logs = [self.food(1, 1550.0, 120.0),
                                  self.food(2, 550.0, 0.0, estimated=1)]

        view.refresh()
        settled()

        assert view.cal_bar.actual_value == pytest.approx(2100.0)
        assert view.prot_bar.actual_value == pytest.approx(120.0)

    def test_the_ledger_marks_the_row_itself(self, make_view, recording_db, settled):
        from src.gui.models.log_table import FLAG_CLEAR_TEXT, FLAG_SET_TEXT

        view = make_view(FoodView)
        recording_db.food_logs = [self.food(1, 1550.0, 120.0),
                                  self.food(2, 550.0, 0.0, estimated=1)]

        view.refresh()
        settled()

        model = view.model_for(0)
        marks = [model.index(row, 0).data() for row in range(model.rowCount())]
        assert sorted(marks) == sorted([FLAG_CLEAR_TEXT, FLAG_SET_TEXT])
