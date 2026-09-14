import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

from src.gui.components.vim_table_view import VimTableView

pytestmark = [pytest.mark.gui, pytest.mark.accessibility]


@pytest.fixture
def window(qapp, profile_path, recording_db, settled):
    from src.database.rows import FoodLogRow
    from src.gui.main_window import MainWindow

    recording_db.food_logs = [
        FoodLogRow.from_server([1, 0, "2026-09-05", "Breakfast", "Rolled Oats",
                                1.0, 50.0, None,
                                312.4, 20.0, 40.0, 2.0, 5.0, 1.0, 0.5, 8.0]),
    ]
    built = MainWindow(recording_db)
    built.tabs.setCurrentIndex(built.tab_indices["food"])
    settled()
    yield built
    built.close()
    built.deleteLater()


def press(widget, key):
    widget.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def go_to(window, key):
    window.tabs.setCurrentIndex(window.tab_indices[key])


def first_table(window, key):
    return window.views[key].findChildren(VimTableView)[0]


class TestTheModeIsNamedForAsLongAsItIsActive:
    def test_the_readout_names_the_starting_mode(self, window):
        assert "NORMAL" in window.mode_label.text()

    @pytest.mark.parametrize("mode", ["NORMAL", "COMMAND", "SHEET", "FILTER"])
    def test_every_mode_names_itself(self, window, mode):
        window.set_mode(mode)

        assert mode in window.mode_label.text()

    def test_a_message_does_not_take_the_mode_away(self, window):
        window.set_mode("NORMAL")

        window._set_nutrient_window(7, " Graphs: 7-Day Windowed Averages.")

        assert "NORMAL" in window.mode_label.text()
        assert "7-Day" in window.status_bar.text()

    def test_switching_tabs_does_not_take_the_mode_away(self, window, settled):
        target = window.tab_indices["food"]
        window.dirty_tabs = {target}

        window._on_tab_changed(target)
        settled()
        window._on_reveal_poll()

        assert window.status_bar.text() == ""
        assert "NORMAL" in window.mode_label.text()

    def test_a_refused_write_does_not_take_the_mode_away(self, window):
        window.set_mode("COMMAND")

        window._report_failure("the service said no")

        assert "COMMAND" in window.mode_label.text()
        assert "the service said no" in window.status_bar.text()

    def test_the_mode_is_coloured_as_well_as_named(self, window):
        from src.config import PALETTE

        window.set_mode("COMMAND")
        in_command = window.mode_label.styleSheet()
        window.set_mode("SHEET")

        assert PALETTE["green"] in in_command
        assert PALETTE["blue"] in window.mode_label.styleSheet()


class TestTheReadoutListsTheMembersOwnKeys:
    @pytest.mark.parametrize(
        "mode, expected",
        [("NORMAL", ["x->Enter Sheet", "z->Focus Command Bar"]),
         ("SHEET", ["a,s,w,d->Move", "r->Edit", "t->Sort"])],
    )
    def test_the_keys_it_lists_are_the_remapped_ones(
            self, qapp, write_profile, recording_db, mode, expected):
        from src.gui.main_window import MainWindow

        write_profile("""
[keybinds]
command_mode = "z"
sheet_mode = "x"
left = "a"
down = "s"
up = "w"
right = "d"
edit = "r"
sort = "t"
""")
        built = MainWindow(recording_db)
        try:
            built.set_mode(mode)

            for fragment in expected:
                assert fragment in built.mode_label.text()
        finally:
            built.close()
            built.deleteLater()


class TestOnlyTheFourModesExist:
    def test_a_name_that_is_not_a_mode_is_refused(self, window):
        window.set_mode("SHEET")

        window.set_mode("VISUAL")

        assert window.current_mode == "SHEET"
        assert "SHEET" in window.mode_label.text()


class TestEnteringAMode:
    def test_the_sheet_key_enters_sheet_mode(self, window):
        go_to(window, "food")

        press(window, window.key_sheet)

        assert window.current_mode == "SHEET"
        assert "SHEET" in window.mode_label.text()

    def test_the_sheet_key_puts_the_cursor_on_a_cell(self, window):
        go_to(window, "food")

        press(window, window.key_sheet)

        assert first_table(window, "food").currentIndex().isValid()

    def test_a_tab_with_no_table_stays_in_normal(self, window):
        go_to(window, "heatmap")

        press(window, window.key_sheet)

        assert window.current_mode == "NORMAL"

    def test_clicking_into_a_table_still_announces_sheet_mode(self, window):
        go_to(window, "food")

        first_table(window, "food").mode_requested.emit("SHEET")

        assert window.current_mode == "SHEET"

    def test_the_command_key_enters_command_mode(self, window):
        press(window, window.key_cmd)

        assert window.current_mode == "COMMAND"

    def test_the_filter_key_enters_filter_mode(self, window):
        go_to(window, "food")

        press(window, window.key_filter)

        assert window.current_mode == "FILTER"


class TestEscapeReturnsTheKeyboardAsWellAsTheMode:
    def test_escape_from_the_sheet(self, window):
        go_to(window, "food")
        press(window, window.key_sheet)

        press(first_table(window, "food"), Qt.Key.Key_Escape)

        assert window.current_mode == "NORMAL"
        assert window.focusWidget() is window

    def test_escape_from_the_filter_bar(self, window):
        go_to(window, "food")
        window.open_filter()

        press(window.filter_line, Qt.Key.Key_Escape)

        assert window.current_mode == "NORMAL"
        assert window.focusWidget() is window

    def test_escape_from_the_command_bar(self, window):
        window.command_line.setFocus()
        window.set_mode("COMMAND")

        press(window.command_line, Qt.Key.Key_Escape)

        assert window.current_mode == "NORMAL"
        assert window.focusWidget() is window

    def test_the_tab_keys_answer_again_afterwards(self, window):
        go_to(window, "food")
        press(window, window.key_sheet)
        press(first_table(window, "food"), Qt.Key.Key_Escape)

        press(window, Qt.Key.Key_0)

        assert window.tabs.currentIndex() == 0


class TestAModeBelongsToTheSurfaceItWasEnteredFrom:
    def test_leaving_the_sheet_by_switching_tabs(self, window):
        go_to(window, "food")
        press(window, window.key_sheet)
        assert window.current_mode == "SHEET"

        go_to(window, "heatmap")

        assert window.current_mode == "NORMAL"
        assert "NORMAL" in window.mode_label.text()

    def test_leaving_the_command_bar_by_switching_tabs(self, window):
        window.command_line.setFocus()
        window.set_mode("COMMAND")

        go_to(window, "heatmap")

        assert window.current_mode == "NORMAL"

    def test_half_typed_command_text_is_kept(self, window):
        window.command_line.setFocus()
        window.set_mode("COMMAND")
        window.command_line.setText("log 1 b Oat")

        go_to(window, "heatmap")

        assert window.command_line.text() == "log 1 b Oat"

    def test_leaving_the_filter_bar_by_switching_tabs(self, window):
        go_to(window, "food")
        window.open_filter()
        assert window.current_mode == "FILTER"

        go_to(window, "supplements")

        assert window.current_mode == "NORMAL"

    def test_the_tab_keys_answer_on_the_tab_arrived_at(self, window):
        go_to(window, "food")
        press(window, window.key_sheet)

        go_to(window, "heatmap")
        press(window, Qt.Key.Key_0)

        assert window.tabs.currentIndex() == 0

