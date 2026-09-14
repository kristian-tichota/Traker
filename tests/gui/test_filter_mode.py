import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

pytestmark = [pytest.mark.gui, pytest.mark.accessibility]


def press(widget, key):
    widget.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key,
                                   Qt.KeyboardModifier.NoModifier))


@pytest.fixture
def window(qapp, profile_path, recording_db, settled):
    from src.database.rows import FoodLogRow
    from src.gui.main_window import MainWindow

    recording_db.food_logs = [
        FoodLogRow.from_server([1, 0, "2026-09-05", "Breakfast", "Rolled Oats",
                                1.0, 50.0, None,
                                312.4, 20.0, 40.0, 2.0, 5.0, 1.0, 0.5, 8.0]),
        FoodLogRow.from_server([2, 0, "2026-09-05", "Lunch", "Grilled Salmon",
                                2.0, 300.0, None,
                                9.0, 30.0, 0.0, 0.0, 12.0, 2.0, 1.0, 0.0]),
    ]
    built = MainWindow(recording_db)
    built.tabs.setCurrentIndex(built.tab_indices["food"])
    settled()
    yield built
    built.close()
    built.deleteLater()


def go_to(window, key):
    window.tabs.setCurrentIndex(window.tab_indices[key])


class TestOpeningTheBar:
    def test_the_filter_bar_starts_hidden(self, window):
        assert not window.filter_line.isVisibleTo(window)

    def test_slash_opens_it_from_normal(self, window):
        window.set_mode("NORMAL")

        press(window, Qt.Key.Key_Slash)

        assert window.filter_line.isVisibleTo(window)

    def test_opening_it_enters_filter_mode(self, window):
        window.open_filter()
        window.filter_line.setFocus()

        assert window.current_mode == "FILTER"

    def test_the_mode_readout_names_the_mode(self, window):
        window.set_mode("FILTER")

        assert "FILTER" in window.mode_label.text()

    def test_it_is_told_the_columns_of_the_table_it_points_at(self, window):
        window.open_filter()

        assert window.filter_line.headers == window.views["food"].headers[0]

    def test_the_sheet_can_open_it_without_leaving(self, window):
        from src.gui.components.vim_table_view import VimTableView

        table = window.views["food"].findChildren(VimTableView)[0]

        press(table, Qt.Key.Key_Slash)

        assert window.filter_line.isVisibleTo(window)

    def test_a_chart_tab_says_there_is_nothing_to_filter(self, window):
        go_to(window, "food_graphs")

        window.open_filter()

        assert "Nothing to filter" in window.status_bar.text()
        assert not window.filter_line.isVisibleTo(window)

    def test_the_filterable_view_is_none_on_a_chart_tab(self, window):
        go_to(window, "food_graphs")

        assert window.filterable_view() is None


class TestTheFoldIsWarmedWhenTheBarOpens:
    def test_opening_the_bar_warms_the_fold(self, window, settled):
        window.open_filter()
        settled()

        assert window.views["food"].fold_is_warm(0)

    def test_a_refresh_alone_does_not_warm_it(self, window, settled):
        view = window.views["food"]
        view.set_rows(0, list(view.model_for(0).rows))
        settled()

        assert not view.fold_is_warm(0)

    def test_a_refresh_keeps_a_filtered_table_warm(self, window, settled):
        window.open_filter()
        settled()
        view = window.views["food"]
        assert view.fold_is_warm(0)

        view.set_rows(0, list(view.model_for(0).rows))
        settled()

        assert view.fold_is_warm(0)

    def test_the_warm_runs_off_the_interface_thread(self, window):
        view = window.views["food"]
        view.set_rows(0, list(view.model_for(0).rows))

        view.warm_fold(0)

        assert not view.fold_is_warm(0), "nothing should have landed yet"

    def test_a_fold_for_rows_that_have_been_replaced_is_discarded(self, window):
        from src.database.rows import FoodLogRow

        view = window.views["food"]
        model = view.model_for(0)
        stale_rows = list(model.rows)
        prebuilt = model.fold_all()

        model.set_rows([FoodLogRow.from_server(
            [9, 0, "2026-09-06", "Dinner", "Something Else", 1.0, 1.0, None,
             1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])])

        assert model.adopt_fold(prebuilt, stale_rows) is False

    def test_a_fold_for_the_rows_still_held_is_adopted(self, window):
        view = window.views["food"]
        model = view.model_for(0)

        assert model.adopt_fold(model.fold_all(), model.rows) is True
        assert view.fold_is_warm(0)

    def test_a_refresh_landing_mid_fold_does_not_raise(self, window):
        from src.database.rows import FoodLogRow

        view = window.views["food"]
        model = view.model_for(0)
        rows = list(model.rows) * 20
        model.set_rows(rows)
        held = model.rows

        original = model._fold_row

        def refresh_midway(row_index, source=None):
            if row_index == 3:
                model.set_rows([FoodLogRow.from_server(
                    [9, 0, "2026-09-06", "Dinner", "Only Row", 1.0, 1.0, None,
                     1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])])
            return original(row_index, source)

        model._fold_row = refresh_midway
        prebuilt = model.fold_all(held)

        assert len(prebuilt) == len(held)
        assert model.adopt_fold(prebuilt, held) is False, "and it is discarded"

    def test_matching_still_works_without_a_warm_fold(self, window):
        view = window.views["food"]
        view.set_rows(0, list(view.model_for(0).rows))
        assert not view.fold_is_warm(0)

        window.open_filter()
        window.filter_line.setText("oats")

        assert view.proxy_for(0).rowCount() == 1


class TestOnlyOnePromptIsOnScreen:
    def test_the_command_bar_is_hidden_while_filtering(self, window):
        window.open_filter()

        assert not window.command_line.isVisibleTo(window)
        assert not window.command_prefix.isVisibleTo(window)

    def test_it_comes_back_on_escape(self, window):
        window.open_filter()

        press(window.filter_line, Qt.Key.Key_Escape)

        assert window.command_line.isVisibleTo(window)
        assert window.command_prefix.isVisibleTo(window)

    def test_it_comes_back_when_the_tab_changes(self, window):
        window.open_filter()

        go_to(window, "supplements")

        assert window.command_line.isVisibleTo(window)


class TestTheEmptyBarDoesNotOverprintItsPlaceholder:
    def test_an_empty_bar_hints_nothing(self, window):
        window.open_filter()

        assert window.filter_line.hint_text == ""

    def test_the_placeholder_is_what_says_what_to_type(self, window):
        placeholder = window.filter_line.placeholderText()

        assert "oats" in placeholder
        assert "meal:b" in placeholder
        assert "kcal>300" in placeholder

    def test_deleting_back_to_nothing_drops_the_hint_again(self, window):
        window.open_filter()
        window.filter_line.setText("Rolled")
        assert window.filter_line.hint_text

        window.filter_line.setText("")

        assert window.filter_line.hint_text == ""

    def test_the_paint_refuses_a_hint_over_the_placeholder(self, qapp):
        from PyQt6.QtGui import QPixmap

        from src.gui.components.filter_line import FilterLineEdit

        bar = FilterLineEdit()
        bar.resize(600, 24)
        bar.show()
        bar.setFocus()
        qapp.processEvents()
        assert bar.hasFocus(), "the paint under test is guarded on focus"

        def rendered():
            pixmap = QPixmap(bar.size())
            bar.render(pixmap)
            return pixmap.toImage()

        untouched = rendered()
        assert rendered() == untouched, "two renders of one state must agree"

        bar.hint_text = "  1rm bev caffeine cal cals carb carbs date …"

        assert rendered() == untouched
        bar.deleteLater()


class TestTypingNarrowsTheTable:
    def test_the_table_narrows_as_the_member_types(self, window):
        window.open_filter()

        window.filter_line.setText("oats")

        assert window.views["food"].proxy_for(0).rowCount() == 1

    def test_the_status_bar_reports_how_many_matched(self, window):
        window.open_filter()

        window.filter_line.setText("oats")

        assert "1 of 2 rows" in window.status_bar.text()

    def test_deleting_back_to_nothing_shows_everything(self, window):
        window.open_filter()
        window.filter_line.setText("oats")

        window.filter_line.setText("")

        assert window.views["food"].proxy_for(0).rowCount() == 2

    def test_a_bad_term_is_reported_and_does_not_narrow(self, window):
        window.open_filter()
        window.filter_line.setText("oats")
        assert window.views["food"].proxy_for(0).rowCount() == 1

        window.filter_line.setText("oats nonsense:x")

        assert "No column called" in window.status_bar.text()
        assert window.views["food"].proxy_for(0).rowCount() == 1, \
            "the previous filter stays in force rather than silently widening"


class TestLeavingTheMode:
    def test_escape_returns_to_normal(self, window):
        window.open_filter()
        window.filter_line.setFocus()

        press(window.filter_line, Qt.Key.Key_Escape)

        assert window.current_mode == "NORMAL"

    def test_escape_clears_the_filter(self, window):
        window.open_filter()
        window.filter_line.setText("oats")
        assert window.views["food"].proxy_for(0).rowCount() == 1

        press(window.filter_line, Qt.Key.Key_Escape)

        assert window.views["food"].proxy_for(0).rowCount() == 2

    def test_escape_hides_the_bar(self, window):
        window.open_filter()

        press(window.filter_line, Qt.Key.Key_Escape)

        assert not window.filter_line.isVisibleTo(window)

    def test_enter_keeps_the_filter_and_moves_to_the_rows(self, window):
        window.open_filter()
        window.filter_line.setText("oats")

        press(window.filter_line, Qt.Key.Key_Return)

        assert window.views["food"].proxy_for(0).rowCount() == 1
        assert window.current_mode == "SHEET"

    def test_switching_tabs_closes_the_filter(self, window):
        window.open_filter()
        window.filter_line.setText("oats")

        go_to(window, "supplements")

        assert not window.filter_line.isVisibleTo(window)
        assert window.views["food"].proxy_for(0).rowCount() == 2


class TestSortingFromTheSheet:
    def _table(self, window):
        from src.gui.components.vim_table_view import VimTableView

        return window.views["food"].findChildren(VimTableView)[0]

    def test_the_sort_key_sorts_by_the_column_under_the_cursor(self, window):
        table = self._table(window)
        column = window.views["food"].headers[0].index("Calories")
        table.setCurrentIndex(table.model().index(0, column))

        press(table, Qt.Key.Key_O)

        assert table.model().index(0, column).data() == "9.00"

    def test_the_status_bar_names_the_column_and_direction(self, window):
        table = self._table(window)
        column = window.views["food"].headers[0].index("Calories")
        table.setCurrentIndex(table.model().index(0, column))

        press(table, Qt.Key.Key_O)

        assert "Calories" in window.status_bar.text()
        assert "ascending" in window.status_bar.text()

    def test_pressing_it_again_reverses(self, window):
        table = self._table(window)
        column = window.views["food"].headers[0].index("Calories")
        table.setCurrentIndex(table.model().index(0, column))

        press(table, Qt.Key.Key_O)
        press(table, Qt.Key.Key_O)

        assert table.model().index(0, column).data() == "312.40"
        assert "descending" in window.status_bar.text()

    def test_a_third_press_restores_the_stored_order(self, window):
        table = self._table(window)
        column = window.views["food"].headers[0].index("Calories")
        table.setCurrentIndex(table.model().index(0, column))

        for _ in range(3):
            press(table, Qt.Key.Key_O)

        assert window.views["food"].proxy_for(0).sortColumn() == -1
        assert "stored in" in window.status_bar.text()

    def test_the_sheet_mode_line_advertises_the_sort_key(self, window):
        window.set_mode("SHEET")

        assert "Sort" in window.mode_label.text()


class TestTheKeybindsAreConfigurable:
    def test_the_generated_profile_declares_both(self, qapp, profile_path):
        from src.profile import UserProfile

        profile = UserProfile()

        assert profile.get_metric("keybinds", "filter", None) == "/"
        assert profile.get_metric("keybinds", "sort", None) == "o"

    def test_a_rebound_sort_key_takes_effect(self, qapp, write_profile):
        from src.gui.components.vim_table_view import VimTableView

        write_profile('[keybinds]\nsort = "z"\n')
        table = VimTableView(0)
        try:
            assert table.key_sort == Qt.Key.Key_Z
        finally:
            table.deleteLater()
