import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QAbstractItemView

from src.gui.components.vim_table_view import VimTableView
from src.gui.models.log_table import LogTableModel

pytestmark = [pytest.mark.gui, pytest.mark.accessibility]

HEADERS = ["Alpha", "Beta", "Gamma"]
MAPPING = {"Alpha": "alpha", "Beta": "beta", "Gamma": "gamma"}

ROWS = [(row_id, f"r{row_id}c0", f"r{row_id}c1", f"r{row_id}c2") for row_id in range(3)]


def press(widget, key):
    widget.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def build_table(headers=HEADERS, mapping=None, rows=ROWS):
    widget = VimTableView(0)
    model = LogTableModel(headers, MAPPING if mapping is None else mapping, 0, parent=widget)
    model.set_rows(rows)
    widget.setModel(model)
    return widget, model


def at(table):
    index = table.currentIndex()
    return index.row(), index.column()


def go(table, row, column):
    table.setCurrentIndex(table.model().index(row, column))


@pytest.fixture
def table(qapp, profile_path):
    widget, _model = build_table()
    go(widget, 1, 1)
    yield widget
    widget.deleteLater()


class TestMovement:
    def test_j_moves_down_and_k_moves_up(self, table):
        press(table, Qt.Key.Key_J)
        assert at(table)[0] == 2

        press(table, Qt.Key.Key_K)
        assert at(table)[0] == 1

    def test_l_moves_right_and_h_moves_left(self, table):
        press(table, Qt.Key.Key_L)
        assert at(table)[1] == 2

        press(table, Qt.Key.Key_H)
        assert at(table)[1] == 1

    def test_moving_never_changes_the_other_axis(self, table):
        press(table, Qt.Key.Key_J)
        assert at(table)[1] == 1

        press(table, Qt.Key.Key_L)
        assert at(table)[0] == 2

    @pytest.mark.parametrize(
        "start, key, stays",
        [((0, 1), Qt.Key.Key_K, (0, 1)),
         ((2, 1), Qt.Key.Key_J, (2, 1)),
         ((1, 0), Qt.Key.Key_H, (1, 0)),
         ((1, 2), Qt.Key.Key_L, (1, 2))],
    )
    def test_movement_stops_at_the_edges(self, table, start, key, stays):
        go(table, *start)

        press(table, key)

        assert at(table) == stays

    def test_every_cell_is_reachable_with_the_four_keys(self, table):
        go(table, 0, 0)
        visited = set()

        for _ in range(3):
            for _ in range(3):
                visited.add(at(table))
                press(table, Qt.Key.Key_L)
            for _ in range(3):
                press(table, Qt.Key.Key_H)
            press(table, Qt.Key.Key_J)

        assert len(visited) == 9

    def test_moving_in_an_empty_table_does_not_raise(self, qapp, profile_path):
        widget, _model = build_table(rows=[])
        try:
            for key in (Qt.Key.Key_J, Qt.Key.Key_K, Qt.Key.Key_H, Qt.Key.Key_L,
                        Qt.Key.Key_E):
                press(widget, key)
        finally:
            widget.deleteLater()


class TestEditing:
    def test_e_opens_an_editable_cell(self, table):
        press(table, Qt.Key.Key_E)

        assert table.state() == QAbstractItemView.State.EditingState

    def test_e_does_nothing_on_a_read_only_cell(self, qapp, profile_path):
        widget, model = build_table(mapping={"Alpha": "alpha", "Gamma": "gamma"})
        try:
            go(widget, 1, HEADERS.index("Beta"))

            press(widget, Qt.Key.Key_E)

            assert widget.state() != QAbstractItemView.State.EditingState
        finally:
            widget.deleteLater()

    def test_navigation_keys_are_typed_into_an_open_editor(self, table):
        press(table, Qt.Key.Key_E)
        assert table.state() == QAbstractItemView.State.EditingState

        press(table, Qt.Key.Key_J)

        assert at(table)[0] == 1, "j must insert a letter, not move, while editing"


class TestModeSignals:
    def test_escape_leaves_the_sheet_and_drops_the_selection(self, table):
        modes = []
        table.mode_requested.connect(modes.append)

        press(table, Qt.Key.Key_Escape)

        assert modes == ["NORMAL"]
        assert table.selectionModel().selectedIndexes() == []

    def test_taking_focus_announces_sheet_mode(self, table, qapp):
        modes = []
        table.mode_requested.connect(modes.append)

        table.show()
        table.activateWindow()
        table.setFocus()
        qapp.processEvents()

        assert "SHEET" in modes


class TestFocusingTheFirstCell:
    def test_focusing_an_unvisited_table_lands_on_the_first_cell(self, qapp, profile_path):
        widget, _model = build_table()
        try:
            widget.focus_first_cell()

            assert at(widget) == (0, 0)
        finally:
            widget.deleteLater()

    def test_focusing_again_keeps_the_cursor_where_it_was(self, table):
        go(table, 2, 1)

        table.focus_first_cell()

        assert at(table) == (2, 1)

    def test_focusing_an_empty_table_does_not_raise(self, qapp, profile_path):
        widget, _model = build_table(rows=[])
        try:
            widget.focus_first_cell()

            assert at(widget) == (-1, -1)
        finally:
            widget.deleteLater()


class TestConfiguredKeys:
    def test_the_bindings_come_from_the_profile(self, table):
        assert (table.key_up, table.key_down, table.key_left,
                table.key_right, table.key_edit) == (
            Qt.Key.Key_K, Qt.Key.Key_J, Qt.Key.Key_H, Qt.Key.Key_L, Qt.Key.Key_E,
        )

    def test_a_rebound_key_moves_instead_of_the_default(self, table):
        table.key_down = Qt.Key.Key_S
        go(table, 0, 0)

        press(table, Qt.Key.Key_S)

        assert at(table)[0] == 1


class TestSelectionModel:
    def test_one_cell_at_a_time_is_selected(self, table):
        assert table.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectItems
        assert table.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection

    def test_a_single_click_does_not_start_an_edit(self, table):
        assert table.editTriggers() == QAbstractItemView.EditTrigger.DoubleClicked


class TestColumnWidthsAreMeasuredOnce:
    def test_the_columns_are_interactive_rather_than_recomputed(self, table):
        from PyQt6.QtWidgets import QHeaderView

        mode = table.horizontalHeader().sectionResizeMode(0)
        assert mode == QHeaderView.ResizeMode.Interactive
        assert mode != QHeaderView.ResizeMode.ResizeToContents

    def test_an_empty_load_does_not_count_as_the_measurement(self, qapp, profile_path):
        widget, model = build_table(rows=[])
        try:
            widget.measure_columns_once()
            assert not widget._measured

            model.set_rows(ROWS)
            widget.measure_columns_once()
            assert widget._measured
        finally:
            widget.deleteLater()

    def test_a_member_resize_survives_the_next_refresh(self, qapp, profile_path):
        widget, model = build_table()
        try:
            widget.measure_columns_once()
            widget.setColumnWidth(0, 321)

            model.set_rows(ROWS)
            widget.measure_columns_once()

            assert widget.columnWidth(0) == 321
        finally:
            widget.deleteLater()


class TestBindingsAreReadWhenTheTableIsBuilt:
    def test_a_rebound_key_from_the_profile_takes_effect(self, qapp, write_profile):
        write_profile('[keybinds]\ndown = "s"\nup = "w"\n')

        table, _model = build_table()
        go(table, 0, 0)

        try:
            assert table.key_down == Qt.Key.Key_S
            assert table.key_up == Qt.Key.Key_W

            press(table, Qt.Key.Key_S)
            assert at(table)[0] == 1
        finally:
            table.deleteLater()

    def test_bindings_the_profile_leaves_out_keep_their_defaults(self, qapp, write_profile):
        write_profile('[keybinds]\ndown = "s"\n')

        table, _model = build_table()
        try:
            assert table.key_down == Qt.Key.Key_S
            assert table.key_up == Qt.Key.Key_K
            assert table.key_edit == Qt.Key.Key_E
        finally:
            table.deleteLater()


class TestTabShortcutsAvoidTheReservedKeys:
    def test_the_nutrient_window_keys_never_address_a_tab(self):
        from src.gui.main_window import tab_shortcut_keys

        keys = tab_shortcut_keys("is")

        assert "D" not in keys
        assert "W" not in keys

    def test_the_members_own_mode_keys_never_address_a_tab(self):
        from src.gui.main_window import tab_shortcut_keys

        assert "I" not in tab_shortcut_keys("is")
        assert "S" not in tab_shortcut_keys("is")

    def test_a_rebound_mode_key_is_reserved_too(self):
        from src.gui.main_window import tab_shortcut_keys

        keys = tab_shortcut_keys("aj")

        assert "A" not in keys and "J" not in keys
        assert keys[10] == "B", "the eleventh tab moves on rather than being shadowed"

    def test_the_digits_still_address_the_first_ten_tabs(self):
        from src.gui.main_window import tab_shortcut_keys

        assert tab_shortcut_keys("is")[:10] == "0123456789"

    def test_the_sequence_has_no_gaps(self):
        from src.gui.main_window import tab_shortcut_keys

        keys = tab_shortcut_keys("is")

        assert len(keys) == len(set(keys))
        assert all(character.isalnum() for character in keys)
