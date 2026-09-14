import pytest
from PyQt6.QtCore import Qt

from src.database.rows import DailyTotals, FoodLogRow, MatchedTotals
from src.gui.filtering import parse
from src.gui.views.base import summary_line
from src.gui.views.food_views import FoodView

pytestmark = pytest.mark.gui


def food(row_id, date, meal, name, servings, kcal, protein=10.0, meal_set=None,
         grams=None, estimated=0):
    return FoodLogRow.from_server(
        [row_id, estimated, date, meal, name, servings,
         grams if grams is not None else (servings or 0) * 50.0, meal_set,
         kcal, protein, 40.0, 2.0, 5.0, 1.0, 0.5, 8.0])

LEDGER = [
    food(1, "2026-09-05", "Breakfast", "Rolled Oats", 1.0, 312.4),
    food(2, "2026-09-05", "Lunch", "Grilled Salmon", 2.0, 9.0),
    food(3, "2026-08-01", "Breakfast", "Rolled Oats", 1.5, 500.0),
    food(4, "2026-03-14", "Dinner", "Řízek s bramborem", 1.0, 800.0),
    food(5, "2026-09-06", "Breakfast", None, 1.0, None),
]


@pytest.fixture
def view(qapp, profile_path, recording_db):
    built = FoodView(recording_db)
    built.set_rows(0, LEDGER)
    yield built
    built.shutdown()
    built.deleteLater()


def visible_names(view):
    proxy = view.proxy_for(0)
    column = view.headers[0].index("Food Name")
    return [proxy.index(row, column).data() for row in range(proxy.rowCount())]


def apply(view, text):
    view.apply_filter(parse(text, view.headers[0]))


class TestFilteringTheTable:
    def test_no_filter_shows_every_row(self, view):
        assert view.proxy_for(0).rowCount() == len(LEDGER)

    def test_a_bare_word_narrows_the_table(self, view):
        apply(view, "oats")

        assert visible_names(view) == ["Rolled Oats", "Rolled Oats"]

    def test_accents_are_folded(self, view):
        apply(view, "rizek")

        assert visible_names(view) == ["Řízek s bramborem"]

    def test_a_field_term_narrows_to_one_column(self, view):
        apply(view, "meal:l")

        assert visible_names(view) == ["Grilled Salmon"]

    def test_a_numeric_comparison_uses_the_stored_value(self, view):
        apply(view, "kcal>300")

        assert "Grilled Salmon" not in visible_names(view)
        assert set(visible_names(view)) == {"Rolled Oats", "Řízek s bramborem"}

    def test_terms_and_together(self, view):
        apply(view, "oats meal:b")

        assert len(visible_names(view)) == 2

    def test_a_date_comparison_reads_the_czech_spelling(self, view):
        apply(view, "date>01.09.2026")

        assert "Řízek s bramborem" not in visible_names(view)

    def test_clearing_restores_every_row(self, view):
        apply(view, "oats")
        view.clear_filter()

        assert view.proxy_for(0).rowCount() == len(LEDGER)

    def test_a_filter_matching_nothing_shows_nothing(self, view):
        apply(view, "kangaroo")

        assert view.proxy_for(0).rowCount() == 0

    def test_the_source_model_keeps_every_row(self, view):
        apply(view, "kangaroo")

        assert view.model_for(0).rowCount() == len(LEDGER)

    def test_a_refresh_re_evaluates_the_filter(self, view):
        apply(view, "oats")
        assert len(visible_names(view)) == 2

        view.set_rows(0, [LEDGER[0]])

        assert len(visible_names(view)) == 1


class TestAPendingRowIsNeverHidden:
    def test_it_shows_through_a_filter_it_does_not_match(self, view):
        apply(view, "kangaroo")
        assert view.proxy_for(0).rowCount() == 0

        view.model_for(0).insert_pending_row(
            (None, "2026-09-06", "Lunch", "Rolled Oats", 1.0))
        view.proxy_for(0).invalidateFilter()

        assert view.proxy_for(0).rowCount() == 1

    def test_the_refresh_that_replaces_it_is_filtered_normally(self, view):
        apply(view, "kangaroo")
        view.model_for(0).insert_pending_row(
            (None, "2026-09-06", "Lunch", "Rolled Oats", 1.0))
        view.proxy_for(0).invalidateFilter()

        view.set_rows(0, LEDGER)

        assert view.proxy_for(0).rowCount() == 0


class TestDeletingUnderAFilter:
    def test_the_row_deleted_is_the_row_clicked(self, view, recording_db, settled):
        from PyQt6.QtWidgets import QMenu

        apply(view, "meal:l")
        table = view._table_widgets[0]
        table.show()
        table.resizeColumnsToContents()
        point = table.visualRect(view.proxy_for(0).index(0, 0)).center()

        original = QMenu.exec
        QMenu.exec = lambda self, *args: self.actions()[0]
        try:
            view.show_context_menu(table, 0, point)
            settled()
        finally:
            QMenu.exec = original

        assert recording_db.last("delete_record") == ("food_logs", 2)


class TestSorting:
    def _column(self, view, header):
        return view.headers[0].index(header)

    def test_sorting_compares_values_not_renderings(self, view):
        view.sort_by(self._column(view, "Calories"), Qt.SortOrder.AscendingOrder)

        proxy = view.proxy_for(0)
        column = self._column(view, "Calories")
        shown = [proxy.index(row, column).data() for row in range(proxy.rowCount())]
        assert shown[0] == "9.00"
        assert shown[1] == "312.40"

    def test_descending_reverses_it(self, view):
        column = self._column(view, "Calories")
        view.sort_by(column, Qt.SortOrder.DescendingOrder)

        proxy = view.proxy_for(0)
        assert proxy.index(0, column).data() == "800.00"

    def test_an_orphaned_row_sorts_last_ascending(self, view):
        column = self._column(view, "Calories")
        view.sort_by(column, Qt.SortOrder.AscendingOrder)

        proxy = view.proxy_for(0)
        last = proxy.rowCount() - 1
        assert proxy.index(last, self._column(view, "Food Name")).data() == "—"

    def test_an_orphaned_row_sorts_last_descending_too(self, view):
        column = self._column(view, "Calories")
        view.sort_by(column, Qt.SortOrder.DescendingOrder)

        proxy = view.proxy_for(0)
        last = proxy.rowCount() - 1
        assert proxy.index(last, self._column(view, "Food Name")).data() == "—"

    def test_sorting_by_text_orders_the_names(self, view):
        view.sort_by(self._column(view, "Food Name"), Qt.SortOrder.AscendingOrder)

        shown = visible_names(view)
        assert shown[0] == "Grilled Salmon"
        assert shown[:-1] == sorted(shown[:-1])
        assert shown[-1] == "—", "the orphan has no name to sort on, so it is last"

    def test_clearing_the_sort_restores_the_stored_order(self, view):
        view.sort_by(self._column(view, "Calories"), Qt.SortOrder.AscendingOrder)

        view.clear_sort()

        assert visible_names(view) == [row.name if row.name else "—" for row in LEDGER]

    def test_a_filter_and_a_sort_hold_together(self, view):
        apply(view, "oats")
        view.sort_by(self._column(view, "Calories"), Qt.SortOrder.DescendingOrder)

        proxy = view.proxy_for(0)
        column = self._column(view, "Calories")
        assert proxy.rowCount() == 2
        assert proxy.index(0, column).data() == "500.00"


class TestTheSummaryLine:
    def test_it_is_hidden_without_a_filter(self, view):
        assert not view.summary_label.isVisibleTo(view)

    def test_a_filter_shows_it(self, view):
        apply(view, "oats")

        assert view.summary_label.isVisibleTo(view)

    def test_it_counts_the_matched_rows(self, view):
        apply(view, "oats")

        assert "2 rows" in view.summary_label.text()

    def test_one_row_is_not_pluralised(self, view):
        apply(view, "salmon")

        assert "1 row ·" in view.summary_label.text()

    def test_it_totals_the_matched_set(self, view):
        apply(view, "oats")

        totals = view.matched_totals()
        assert totals.energy_kcal == pytest.approx(812.4)
        assert "812 kcal" in view.summary_label.text()

    def test_it_reports_the_span_in_czech_dates(self, view):
        apply(view, "oats")

        assert "01.08.2026 → 05.09.2026" in view.summary_label.text()

    def test_one_day_is_reported_once_rather_than_as_a_range(self, view):
        apply(view, "salmon")

        assert "05.09.2026" in view.summary_label.text()
        assert "→" not in view.summary_label.text()

    def test_clearing_hides_it_again(self, view):
        apply(view, "oats")
        view.clear_filter()

        assert not view.summary_label.isVisibleTo(view)

    def test_a_refresh_updates_it(self, view):
        apply(view, "oats")
        assert "2 rows" in view.summary_label.text()

        view.set_rows(0, [LEDGER[0]])

        assert "1 row" in view.summary_label.text()

    def test_a_table_without_nutrients_does_not_advertise_zeroes(self):
        totals = MatchedTotals.of([])
        line = summary_line(totals, ["Date", "Routine Name", "Duration (mins)"])

        assert "kcal" not in line
        assert "protein" not in line


class TestTheSummaryAndTheBarsShareOneSummation:
    def test_matched_totals_and_daily_totals_agree_on_the_same_rows(self):
        rows = [LEDGER[0], LEDGER[1]]

        matched = MatchedTotals.of(rows)
        daily = DailyTotals.of("2026-09-05", rows)

        assert matched.energy_kcal == daily.energy_kcal
        assert matched.protein_g == daily.protein_g
        assert matched.carbs_g == daily.carbs_g
        assert matched.fat_g == daily.fat_g
        assert matched.salt_g == daily.salt_g
        assert matched.fibre_g == daily.fibre_g
        assert matched.sugars_g == daily.sugars_g

    def test_they_agree_on_an_orphaned_row_too(self):
        rows = [LEDGER[4]]

        assert MatchedTotals.of(rows).energy_kcal == \
            DailyTotals.of("2026-09-06", rows).energy_kcal == 0.0

    def test_both_read_the_same_field_list(self):
        from src.database.rows import NUTRIENT_FIELDS

        assert set(NUTRIENT_FIELDS) <= set(MatchedTotals._fields)
        assert set(NUTRIENT_FIELDS) <= set(DailyTotals._fields)


class TestTheBarsKeepMeaningToday:
    def test_filtering_does_not_touch_the_bars(self, view):
        view.cal_bar.set_value(1234.0)

        apply(view, "kcal>10000")

        assert view.cal_bar.actual_value == pytest.approx(1234.0)

    def test_the_matched_totals_are_reported_separately(self, view):
        view.cal_bar.set_value(1234.0)
        apply(view, "oats")

        assert view.matched_totals().energy_kcal == pytest.approx(812.4)
        assert view.cal_bar.actual_value == pytest.approx(1234.0)
