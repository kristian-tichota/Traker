import pytest
from PyQt6.QtCore import QAbstractAnimation, Qt

from src.gui.views.base import BaseManagedView

pytestmark = pytest.mark.gui

HEADERS = ["Date", "Meal Type", "Food Name", "Servings", "Calories"]
MAPPING = {"Date": "date", "Meal Type": "meal_type",
           "Food Name": "food_item_id", "Servings": "servings"}

ROW = (7, "2026-09-05", "Breakfast", "Rolled Oats", 2.0, 380.0)
ORPHANED = (7, "2026-09-05", "Breakfast", None, 1.0, None)


class StubWindow:
    class _StatusBar:
        def __init__(self):
            self.message = ""

        def setText(self, value):
            self.message = value

    def __init__(self, tab_count=4, current_index=2):
        self.status_bar = self._StatusBar()
        self.tab_count = tab_count
        self.current_index = current_index
        self.dirty_tabs = set()
        self.refreshed = None

    def connect(self, view):
        view.data_changed.connect(self.mark_all_tabs_stale)
        view.status_message.connect(self.status_bar.setText)

    def mark_all_tabs_stale(self):
        self.dirty_tabs = set(range(self.tab_count))
        self.refreshed = self.current_index


class LogView(BaseManagedView):
    def __init__(self, db):
        super().__init__(db, ["food_logs"], [HEADERS], [MAPPING])
        layout, self.table = self.build_table_layout(None, HEADERS, 0)
        self.setLayout(layout)


@pytest.fixture
def view(qapp, profile_path, recording_db):
    window = StubWindow()
    widget = LogView(recording_db)
    window.connect(widget)
    widget.stub_window = window
    yield widget
    widget.shutdown()
    widget.deleteLater()


@pytest.fixture
def model(view):
    return view.model_for(0)


def cell(model, row, column):
    return model.index(row, column).data(Qt.ItemDataRole.DisplayRole)


def type_into(model, row, column, text):
    return model.setData(model.index(row, column), text, Qt.ItemDataRole.EditRole)


class TestPopulation:
    def test_the_first_field_is_the_row_id_not_a_column(self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        assert model.columnCount() == len(HEADERS)
        assert model.row_id(model.index(0, 0)) == 7

    def test_the_row_id_is_still_reachable_where_UserRole_carried_it(
            self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        assert model.index(0, 3).data(Qt.ItemDataRole.UserRole) == 7

    def test_iso_dates_are_rendered_the_way_the_household_reads_them(
            self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        assert cell(model, 0, 0) == "05.09.2026"

    def test_an_unparseable_date_is_shown_as_it_arrived(self, view, model, settled):
        view.populate_table(view.table, [(7, "not-a-date", "Breakfast", "Oats", 1.0, 0.0)],
                            table_idx=0)

        assert cell(model, 0, 0) == "not-a-date"

    def test_numbers_are_shown_to_two_decimals_and_right_aligned(
            self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        assert cell(model, 0, 3) == "2.00"
        alignment = model.index(0, 3).data(Qt.ItemDataRole.TextAlignmentRole)
        assert alignment & Qt.AlignmentFlag.AlignRight

    def test_a_name_is_not_right_aligned(self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        alignment = model.index(0, 2).data(Qt.ItemDataRole.TextAlignmentRole)
        assert not alignment & Qt.AlignmentFlag.AlignRight

    def test_an_orphaned_row_keeps_its_date_and_quantity(self, view, model, settled):
        view.populate_table(view.table, [ORPHANED], table_idx=0)

        assert model.rowCount() == 1
        assert cell(model, 0, 0) == "05.09.2026"
        assert cell(model, 0, 3) == "1.00"

    def test_an_orphaned_row_loses_its_name_rather_than_reading_None(
            self, view, model, settled):
        view.populate_table(view.table, [ORPHANED], table_idx=0)

        assert cell(model, 0, 2) == "—"

    def test_an_orphaned_rows_derived_values_read_zero(self, view, model, settled):
        view.populate_table(view.table, [ORPHANED], table_idx=0)

        assert cell(model, 0, 4) == "0.00"

    def test_an_orphaned_derived_value_is_right_aligned_like_a_number(
            self, view, model, settled):
        view.populate_table(view.table, [ORPHANED], table_idx=0)

        alignment = model.index(0, 4).data(Qt.ItemDataRole.TextAlignmentRole)
        assert alignment & Qt.AlignmentFlag.AlignRight

    def test_only_the_declared_columns_are_editable(self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        assert model.flags(model.index(0, 0)) & Qt.ItemFlag.ItemIsEditable
        assert not model.flags(model.index(0, 4)) & Qt.ItemFlag.ItemIsEditable

    def test_repopulating_replaces_the_previous_rows(self, view, model, settled):
        view.populate_table(view.table, [ROW, ROW], table_idx=0)
        view.populate_table(view.table, [ROW], table_idx=0)

        assert model.rowCount() == 1

    def test_populating_does_not_fire_edit_signals(self, view, recording_db, settled):
        edits = []
        view.model_for(0).edit_requested.connect(lambda *args: edits.append(args))

        view.populate_table(view.table, [ROW], table_idx=0)
        settled()

        assert edits == []
        assert recording_db.calls == [], "filling the table must not look like an edit"

    def test_an_empty_response_renders_an_empty_table(self, view, model, settled):
        view.populate_table(view.table, [], table_idx=0)

        assert model.rowCount() == 0

    def test_a_row_shorter_than_the_headers_does_not_raise(self, view, model, settled):
        view.populate_table(view.table, [(7, "2026-09-05")], table_idx=0)

        assert model.rowCount() == 1
        assert cell(model, 0, 0) == "05.09.2026"
        assert cell(model, 0, 4) == "0.00"

    def test_the_headers_are_what_the_view_declared(self, view, model, settled):
        rendered = [model.headerData(column, Qt.Orientation.Horizontal,
                                     Qt.ItemDataRole.DisplayRole)
                    for column in range(model.columnCount())]

        assert rendered == HEADERS


class TestInlineEditing:
    def test_a_readable_date_is_sent_back_as_iso(self, view, model, recording_db, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        type_into(model, 0, 0, "06.09.2026")
        settled()

        table, row_id, column, value, mapping = recording_db.last("update_record")
        assert (table, row_id, column, value) == ("food_logs", 7, "Date", "2026-09-06")
        assert mapping is MAPPING

    def test_a_non_date_column_is_sent_verbatim(self, view, model, recording_db, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        type_into(model, 0, 1, "Dinner")
        settled()

        _, _, column, value, _ = recording_db.last("update_record")
        assert (column, value) == ("Meal Type", "Dinner")

    def test_surrounding_whitespace_is_trimmed(self, view, model, recording_db, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        type_into(model, 0, 1, "  Dinner  ")
        settled()

        assert recording_db.last("update_record")[3] == "Dinner"

    def test_a_date_the_user_typed_badly_is_sent_as_typed(
            self, view, model, recording_db, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        type_into(model, 0, 0, "tomorrow")
        settled()

        assert recording_db.last("update_record")[3] == "tomorrow"

    def test_a_derived_column_refuses_the_edit_rather_than_sending_it(
            self, view, model, recording_db, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        accepted = type_into(model, 0, 4, "999")
        settled()

        assert accepted is False
        assert recording_db.calls == []

    def test_the_editor_opens_on_what_the_member_was_reading(self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        assert model.index(0, 0).data(Qt.ItemDataRole.EditRole) == "05.09.2026"

    def test_an_edit_does_not_put_unconfirmed_text_on_screen(
            self, view, model, recording_db, settled):
        recording_db.result = (False, "Column 'id' is not permitted for modification")
        view.populate_table(view.table, [ROW], table_idx=0)

        type_into(model, 0, 1, "Dinner")
        settled()

        assert cell(model, 0, 1) == "Breakfast"

    def test_a_saved_edit_marks_every_tab_stale(self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        type_into(model, 0, 1, "Dinner")
        settled()

        assert view.stub_window.dirty_tabs == set(range(4))
        assert view.stub_window.refreshed == 2
        assert "Saved" in view.stub_window.status_bar.message

    def test_a_refused_edit_is_reported_and_puts_the_cell_back(
            self, view, model, recording_db, settled):
        recording_db.result = (False, "Column 'id' is not permitted for modification")
        view.populate_table(view.table, [ROW], table_idx=0)

        type_into(model, 0, 1, "Dinner")
        settled()

        assert "Edit refused" in view.stub_window.status_bar.message
        assert "not permitted" in view.stub_window.status_bar.message
        assert view.stub_window.dirty_tabs == set(range(4))


class TestDeletion:
    @pytest.fixture
    def choose_delete(self, monkeypatch):
        from PyQt6.QtWidgets import QMenu

        monkeypatch.setattr(QMenu, "exec", lambda self, *args: self.actions()[0])

    def _point_at(self, view, row, column):
        view.table.show()
        view.table.resizeColumnsToContents()
        return view.table.visualRect(view.model_for(0).index(row, column)).center()

    def test_deleting_a_row_targets_that_tables_name_and_row_id(
        self, view, recording_db, choose_delete, settled
    ):
        view.populate_table(view.table, [ROW], table_idx=0)

        view.show_context_menu(view.table, 0, self._point_at(view, 0, 0))
        settled()

        assert recording_db.last("delete_record") == ("food_logs", 7)

    def test_the_table_reports_which_of_the_views_tables_was_clicked(
        self, view, recording_db, choose_delete, settled
    ):
        view.populate_table(view.table, [ROW], table_idx=0)

        view.table.context_menu_requested.emit(0, self._point_at(view, 0, 0))
        settled()

        assert recording_db.last("delete_record") == ("food_logs", 7)

    def test_a_successful_deletion_marks_every_tab_stale(self, view, choose_delete, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        view.show_context_menu(view.table, 0, self._point_at(view, 0, 0))
        settled()

        assert view.stub_window.dirty_tabs == set(range(4))
        assert "Deleted one row" in view.stub_window.status_bar.message

    def test_a_refused_deletion_is_reported(self, view, recording_db, choose_delete, settled):
        recording_db.result = (False, "Unauthorized target table")
        view.populate_table(view.table, [ROW], table_idx=0)

        view.show_context_menu(view.table, 0, self._point_at(view, 0, 0))
        settled()

        assert "Deletion refused" in view.stub_window.status_bar.message
        assert view.stub_window.dirty_tabs == set()

    def test_right_clicking_empty_space_deletes_nothing(
            self, view, recording_db, choose_delete, settled):
        from PyQt6.QtCore import QPoint

        view.populate_table(view.table, [], table_idx=0)

        view.show_context_menu(view.table, 0, QPoint(5, 5))

        assert recording_db.calls == []

    def test_the_view_knows_which_table_each_of_its_tables_writes_to(self, view, settled):
        assert view.tables == ["food_logs"]
        assert view.headers == [HEADERS]
        assert view.mappings == [MAPPING]


class TestEditableColumnsComeFromTheMapping:
    def test_only_the_mapped_headers_are_writable(self, view, settled):
        assert view.editable_columns(0) == [0, 1, 2, 3]

    def test_the_model_and_the_view_agree_on_which_columns_those_are(self, view, model):
        assert model.editable_columns() == view.editable_columns(0)

    def test_a_derived_column_is_not_writable(self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        calories = model.index(0, HEADERS.index("Calories"))
        assert not (model.flags(calories) & Qt.ItemFlag.ItemIsEditable)

    def test_a_mapped_column_is_writable(self, view, model, settled):
        view.populate_table(view.table, [ROW], table_idx=0)

        servings = model.index(0, HEADERS.index("Servings"))
        assert model.flags(servings) & Qt.ItemFlag.ItemIsEditable

    def test_there_is_no_override_to_widen_them(self, view):
        import inspect

        parameters = inspect.signature(view.populate_table).parameters
        assert "editable_cols" not in parameters


class TestARefreshSaysWhichRowsChanged:
    ARRIVAL = (11, "2026-09-07", "Lunch", "Rye Bread", 1.0, 210.0)

    def test_a_refresh_that_brought_a_row_in_starts_the_glow(self, view, model):
        view.set_rows(0, [ROW])

        view.set_rows(0, [ROW, self.ARRIVAL])

        assert model.changed_rows() == frozenset({1})
        assert view.glow_for(0).anim.state() == QAbstractAnimation.State.Running

    def test_a_refresh_that_changed_nothing_starts_nothing(self, view, model):
        view.set_rows(0, [ROW])

        view.set_rows(0, [ROW])

        assert view.glow_for(0).anim.state() == QAbstractAnimation.State.Stopped

    def test_the_first_load_starts_nothing(self, view):
        view.set_rows(0, [ROW, self.ARRIVAL])

        assert view.glow_for(0).anim.state() == QAbstractAnimation.State.Stopped

    def test_an_optimistic_row_is_washed_as_it_lands(self, view, model):
        view.set_rows(0, [ROW])

        position = view.show_pending_row((None, "2026-09-07", "Lunch", "Rye"))

        assert position in model.changed_rows()
        assert view.glow_for(0).anim.state() == QAbstractAnimation.State.Running

    def test_shutdown_stops_the_glow(self, view, model):
        view.set_rows(0, [ROW])
        view.set_rows(0, [ROW, self.ARRIVAL])
        assert view.glow_for(0).anim.state() == QAbstractAnimation.State.Running

        view.shutdown()

        assert view.glow_for(0).anim.state() == QAbstractAnimation.State.Stopped
        assert model.changed_rows() == frozenset()


class TestARefreshKeepsTheMembersPlace:
    SECOND = (11, "2026-09-07", "Lunch", "Rye Bread", 1.0, 210.0)

    def selected(self, view):
        index = view.table.currentIndex()
        return (index.row(), index.column()) if index.isValid() else None

    def test_the_cursor_stays_on_the_row_it_was_on(self, view, model):
        view.set_rows(0, [ROW, self.SECOND])
        view.table.setCurrentIndex(view.table.model().index(1, 3))

        view.set_rows(0, [ROW, self.SECOND])

        assert self.selected(view) == (1, 3)

    def test_it_follows_the_row_rather_than_the_position(self, view, model):
        view.set_rows(0, [ROW, self.SECOND])
        view.table.setCurrentIndex(view.table.model().index(1, 2))

        view.set_rows(0, [self.SECOND, ROW])

        assert self.selected(view) == (0, 2)

    def test_a_table_the_member_never_entered_gains_no_cursor(self, view):
        view.set_rows(0, [ROW])

        view.set_rows(0, [ROW, self.SECOND])

        assert self.selected(view) is None

    def test_a_cursor_on_a_row_the_refresh_deleted_is_let_go(self, view):
        view.set_rows(0, [ROW, self.SECOND])
        view.table.setCurrentIndex(view.table.model().index(1, 0))

        view.set_rows(0, [ROW])

        assert self.selected(view) is None
