import pytest
from PyQt6.QtCore import QModelIndex, Qt

from src.database.rows import FoodLogRow
from src.gui.models.log_table import (
    ALIGN_CENTRE, CHANGE_ACCENT, FLAG_CLEAR_TEXT, FLAG_SET_TEXT,
    ORPHAN_NAME_TEXT, ORPHAN_VALUE_TEXT, PENDING_TEXT, ROW_GROUND,
    LogTableModel, boolean_fields, editable_columns, numeric_fields)

pytestmark = pytest.mark.gui

HEADERS = ["Date", "Meal Type", "Food Name", "Servings", "Calories"]
MAPPING = {"Date": "date", "Meal Type": "meal_type",
           "Food Name": "food_item_id", "Servings": "servings"}

ROW = (7, "2026-09-05", "Breakfast", "Rolled Oats", 2.0, 380.0)
ORPHANED = (9, "2026-09-05", "Breakfast", None, 1.0, None)


@pytest.fixture
def model(qapp):
    built = LogTableModel(HEADERS, MAPPING, table_idx=0)
    built.set_rows([ROW])
    return built


def shown(model, row, column):
    return model.index(row, column).data(Qt.ItemDataRole.DisplayRole)


class TestShape:
    def test_the_rows_are_what_it_was_given(self, model):
        assert model.rowCount() == 1
        assert model.columnCount() == len(HEADERS)

    def test_a_child_index_has_no_rows(self, model):
        assert model.rowCount(model.index(0, 0)) == 0
        assert model.columnCount(model.index(0, 0)) == 0

    def test_the_headers_are_the_ones_declared(self, model):
        rendered = [model.headerData(column, Qt.Orientation.Horizontal,
                                     Qt.ItemDataRole.DisplayRole)
                    for column in range(model.columnCount())]
        assert rendered == HEADERS

    def test_rows_are_held_as_handed_over_not_reshaped(self, model):
        assert model.rows == [ROW]
        assert model.row_at(model.index(0, 0)) == ROW

    def test_an_out_of_range_index_answers_nothing_rather_than_raising(self, model):
        assert model.data(QModelIndex()) is None
        assert model.row_id(QModelIndex()) is None
        assert model.row_at(QModelIndex()) is None


class TestWhatACellShows:
    def test_an_iso_date_is_rendered_the_way_the_household_reads_it(self, model):
        assert shown(model, 0, 0) == "05.09.2026"

    def test_an_unparseable_date_comes_back_as_it_arrived(self, model):
        model.set_rows([(7, "not-a-date", "Breakfast", "Oats", 1.0, 0.0)])

        assert shown(model, 0, 0) == "not-a-date"

    def test_a_float_is_shown_to_two_decimals(self, model):
        assert shown(model, 0, 3) == "2.00"
        assert shown(model, 0, 4) == "380.00"

    def test_a_whole_number_that_is_not_a_float_is_not_padded(self, model):
        model.set_rows([(7, "2026-09-05", "Breakfast", "Oats", 7, 380.0)])

        assert shown(model, 0, 3) == "7"

    def test_text_is_shown_as_it_is(self, model):
        assert shown(model, 0, 1) == "Breakfast"
        assert shown(model, 0, 2) == "Rolled Oats"

    def test_numbers_are_right_aligned_and_names_are_not(self, model):
        numeric = model.index(0, 3).data(Qt.ItemDataRole.TextAlignmentRole)
        textual = model.index(0, 2).data(Qt.ItemDataRole.TextAlignmentRole)

        assert numeric & Qt.AlignmentFlag.AlignRight
        assert not textual & Qt.AlignmentFlag.AlignRight

    def test_a_role_it_does_not_serve_answers_nothing(self, model):
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DecorationRole) is None


class TestAnOrphanedRow:
    @pytest.fixture
    def orphan(self, model):
        model.set_rows([ORPHANED])
        return model

    def test_it_keeps_its_date(self, orphan):
        assert shown(orphan, 0, 0) == "05.09.2026"

    def test_it_keeps_its_quantity(self, orphan):
        assert shown(orphan, 0, 3) == "1.00"

    def test_it_loses_its_name(self, orphan):
        assert shown(orphan, 0, 2) == ORPHAN_NAME_TEXT

    def test_its_derived_values_read_zero(self, orphan):
        assert shown(orphan, 0, 4) == ORPHAN_VALUE_TEXT

    def test_the_name_column_is_told_apart_by_the_mapping_not_by_position(self, qapp):
        headers = ["Calories", "Food Name"]
        mapping = {"Food Name": "food_item_id"}
        model = LogTableModel(headers, mapping)
        model.set_rows([(1, None, None)])

        assert model.index(0, 0).data() == ORPHAN_VALUE_TEXT
        assert model.index(0, 1).data() == ORPHAN_NAME_TEXT

    def test_a_zero_reads_as_zero_rather_than_as_an_orphan(self, model):
        model.set_rows([(7, "2026-09-05", "Breakfast", "Oats", 0.0, 0.0)])

        assert shown(model, 0, 3) == "0.00"
        assert shown(model, 0, 2) == "Oats"

    def test_a_catalogs_unfilled_text_column_is_blank_not_zero(self, qapp):
        from src.database.rows import ExerciseItemRow
        from src.gui.views.exercise_view import ITEM_COLUMNS, ITEM_HEADERS

        model = LogTableModel(ITEM_HEADERS, ITEM_COLUMNS)
        model.set_rows([ExerciseItemRow.from_server({
            "id": 1, "name": "Plank", "muscle_group": "Core",
            "movement_pattern": "Hold", "secondary_muscles": None,
            "plane_of_motion": None, "joint_mechanics": None,
            "equipment_type": None, "unilateral_bilateral": None,
            "metric_type": "Seconds"})])

        def cell(header):
            return shown(model, 0, ITEM_HEADERS.index(header))

        assert cell("Exercise") == "Plank"
        assert cell("Metric Type") == "Seconds"
        for header in ("Secondary Muscles", "Plane of Motion", "Joint Mechanics",
                       "Equipment Type", "Unilateral/Bilateral"):
            assert cell(header) == ORPHAN_NAME_TEXT, header


class TestEditability:
    def test_the_mapped_columns_are_the_writable_ones(self, model):
        assert model.editable_columns() == [0, 1, 2, 3]

    def test_a_column_the_mapping_omits_is_not_writable(self, model):
        assert not model.flags(model.index(0, 4)) & Qt.ItemFlag.ItemIsEditable

    def test_a_mapped_column_is_writable(self, model):
        assert model.flags(model.index(0, 3)) & Qt.ItemFlag.ItemIsEditable

    def test_every_cell_is_selectable_so_the_keyboard_can_reach_it(self, model):
        for column in range(model.columnCount()):
            flags = model.flags(model.index(0, column))
            assert flags & Qt.ItemFlag.ItemIsSelectable
            assert flags & Qt.ItemFlag.ItemIsEnabled

    def test_an_invalid_index_has_no_flags(self, model):
        assert model.flags(QModelIndex()) == Qt.ItemFlag.NoItemFlags

    def test_the_derivation_is_a_function_of_the_two_lists(self):
        assert editable_columns(HEADERS, MAPPING) == [0, 1, 2, 3]
        assert editable_columns(HEADERS, {}) == []


class TestEditsLeaveBySignal:
    @pytest.fixture
    def edits(self, model):
        recorded = []
        model.edit_requested.connect(lambda *args: recorded.append(args))
        return recorded

    def test_typing_into_a_cell_reports_the_table_row_header_and_text(self, model, edits):
        accepted = model.setData(model.index(0, 1), "Dinner", Qt.ItemDataRole.EditRole)

        assert accepted is True
        assert edits == [(0, 7, "Meal Type", "Dinner")]

    def test_the_table_index_it_reports_is_its_own(self, qapp):
        second = LogTableModel(HEADERS, MAPPING, table_idx=1)
        second.set_rows([ROW])
        recorded = []
        second.edit_requested.connect(lambda *args: recorded.append(args))

        second.setData(second.index(0, 1), "Dinner", Qt.ItemDataRole.EditRole)

        assert recorded[0][0] == 1

    def test_surrounding_whitespace_is_trimmed(self, model, edits):
        model.setData(model.index(0, 1), "  Dinner  ", Qt.ItemDataRole.EditRole)

        assert edits[0][3] == "Dinner"

    def test_an_unwritable_column_refuses_rather_than_reporting(self, model, edits):
        accepted = model.setData(model.index(0, 4), "999", Qt.ItemDataRole.EditRole)

        assert accepted is False
        assert edits == []

    def test_a_role_other_than_edit_is_refused(self, model, edits):
        accepted = model.setData(model.index(0, 1), "Dinner", Qt.ItemDataRole.DisplayRole)

        assert accepted is False
        assert edits == []

    def test_the_model_does_not_write_the_value_into_its_own_rows(self, model, edits):
        model.setData(model.index(0, 1), "Dinner", Qt.ItemDataRole.EditRole)

        assert shown(model, 0, 1) == "Breakfast"
        assert model.rows == [ROW]

    def test_the_editor_opens_on_the_displayed_text(self, model):
        assert model.index(0, 0).data(Qt.ItemDataRole.EditRole) == "05.09.2026"


class TestRowIdentity:
    def test_the_row_id_is_the_first_field(self, model):
        assert model.row_id(model.index(0, 0)) == 7

    def test_every_column_of_a_row_answers_the_same_id(self, model):
        ids = {model.row_id(model.index(0, column))
               for column in range(model.columnCount())}
        assert ids == {7}

    def test_the_id_is_reachable_where_UserRole_carried_it(self, model):
        assert model.index(0, 2).data(Qt.ItemDataRole.UserRole) == 7


class TestReplacingTheRows:
    def test_set_rows_replaces_rather_than_appends(self, model):
        model.set_rows([ROW, ORPHANED])
        model.set_rows([ROW])

        assert model.rowCount() == 1

    def test_set_rows_resets_the_model_so_the_view_redraws(self, model):
        resets = []
        model.modelAboutToBeReset.connect(lambda: resets.append("about"))
        model.modelReset.connect(lambda: resets.append("done"))

        model.set_rows([ROW])

        assert resets == ["about", "done"]

    def test_an_empty_answer_empties_the_table(self, model):
        model.set_rows([])

        assert model.rowCount() == 0

    def test_a_row_shorter_than_the_headers_does_not_read_off_the_end(self, model):
        model.set_rows([(7, "2026-09-05")])

        assert shown(model, 0, 0) == "05.09.2026"
        assert shown(model, 0, 4) == ORPHAN_VALUE_TEXT

    def test_a_row_longer_than_the_headers_renders_only_the_headers(self, model):
        model.set_rows([ROW + ("Reps",)])

        assert model.columnCount() == len(HEADERS)
        assert shown(model, 0, 4) == "380.00"


class TestAPendingRow:
    def test_the_row_appears_at_once(self, model):
        model.insert_pending_row((99, "2026-09-06", "Lunch", "Rolled Oats", 1.0, None))

        assert model.rowCount() == 2
        assert model.row_id(model.index(1, 0)) == 99

    def test_what_was_written_is_shown(self, model):
        model.insert_pending_row((99, "2026-09-06", "Lunch", "Rolled Oats", 1.0, None))

        assert shown(model, 1, 0) == "06.09.2026"
        assert shown(model, 1, 2) == "Rolled Oats"
        assert shown(model, 1, 3) == "1.00"

    def test_a_derived_column_reads_pending_rather_than_zero(self, model):
        model.insert_pending_row((99, "2026-09-06", "Lunch", "Rolled Oats", 1.0, None))

        assert shown(model, 1, 4) == PENDING_TEXT
        assert shown(model, 1, 4) != ORPHAN_VALUE_TEXT

    def test_an_orphan_in_the_same_table_still_reads_as_an_orphan(self, model):
        model.set_rows([ORPHANED])
        model.insert_pending_row((99, "2026-09-06", "Lunch", "Rolled Oats", 1.0, None))

        assert shown(model, 0, 4) == ORPHAN_VALUE_TEXT
        assert shown(model, 1, 4) == PENDING_TEXT

    def test_it_inserts_rather_than_resetting_so_the_cursor_survives(self, model):
        events = []
        model.rowsAboutToBeInserted.connect(lambda *a: events.append("about"))
        model.rowsInserted.connect(lambda *a: events.append("done"))
        model.modelReset.connect(lambda: events.append("reset"))

        model.insert_pending_row((99, "2026-09-06", "Lunch", "Oats", 1.0, None))

        assert events == ["about", "done"]

    def test_the_next_refresh_clears_the_pending_state(self, model):
        model.insert_pending_row((99, "2026-09-06", "Lunch", "Oats", 1.0, None))
        assert model.has_pending_rows()

        model.set_rows([ROW])

        assert not model.has_pending_rows()

    def test_a_pending_row_the_refresh_does_not_contain_simply_goes(self, model):
        model.insert_pending_row((99, "2026-09-06", "Lunch", "Oats", 1.0, None))

        model.set_rows([ROW])

        assert model.rowCount() == 1
        assert model.row_id(model.index(0, 0)) == 7


class TestWhichRowsARefreshChanged:
    def test_the_first_population_changed_nothing(self, qapp):
        fresh = LogTableModel(HEADERS, MAPPING)

        fresh.set_rows([ROW, ORPHANED])

        assert fresh.changed_rows() == frozenset()

    def test_an_appended_row_is_the_one_that_changed(self, model):
        arrival = (11, "2026-09-07", "Lunch", "Rye Bread", 1.0, 210.0)

        model.set_rows([ROW, arrival])

        assert model.changed_rows() == frozenset({1})

    def test_an_edited_row_is_the_one_that_changed(self, model):
        edited = (7, "2026-09-05", "Breakfast", "Rolled Oats", 3.0, 570.0)

        model.set_rows([edited])

        assert model.changed_rows() == frozenset({0})

    def test_a_refresh_that_changed_nothing_says_nothing(self, model):
        model.set_rows([ROW])

        assert model.changed_rows() == frozenset()

    def test_a_deleted_row_does_not_wash_its_neighbour(self, model):
        model.set_rows([ROW, (11, "2026-09-07", "Lunch", "Rye", 1.0, 210.0)])

        model.set_rows([ROW])

        assert model.changed_rows() == frozenset()

    def test_a_reordered_ledger_changed_nothing(self, model):
        second = (11, "2026-09-07", "Lunch", "Rye", 1.0, 210.0)
        model.set_rows([ROW, second])

        model.set_rows([second, ROW])

        assert model.changed_rows() == frozenset()

    def test_a_row_whose_stored_value_is_None_is_not_read_as_absent(self, model):
        model.set_rows([ROW, ORPHANED])

        model.set_rows([ROW, ORPHANED])

        assert model.changed_rows() == frozenset()


class TestTheWashOnAChangedRow:
    @pytest.fixture
    def washed(self, model):
        model.set_rows([ROW, (11, "2026-09-07", "Lunch", "Rye", 1.0, 210.0)])
        model.highlight_changes(1.0)
        return model

    def background(self, model, row):
        return model.index(row, 0).data(Qt.ItemDataRole.BackgroundRole)

    def test_the_changed_row_answers_a_brush(self, washed):
        assert self.background(washed, 1) is not None

    def test_an_untouched_row_answers_nothing(self, washed):
        assert self.background(washed, 0) is None

    def test_the_wash_is_between_the_ground_and_the_accent(self, washed):
        colour = self.background(washed, 1).color()

        assert colour != ROW_GROUND
        assert colour != CHANGE_ACCENT
        for channel in ("red", "green", "blue"):
            low, high = sorted((getattr(ROW_GROUND, channel)(),
                                getattr(CHANGE_ACCENT, channel)()))
            assert low <= getattr(colour, channel)() <= high

    def test_it_is_paler_as_the_glow_decays(self, washed):
        peak = self.background(washed, 1).color()
        washed.highlight_changes(0.4)
        late = self.background(washed, 1).color()

        assert abs(late.blue() - ROW_GROUND.blue()) < abs(peak.blue() - ROW_GROUND.blue())

    def test_the_end_of_the_glow_drops_the_wash_and_the_set(self, washed):
        washed.highlight_changes(0.0)

        assert self.background(washed, 1) is None
        assert washed.changed_rows() == frozenset()

    def test_the_wash_reaches_every_column_of_the_row(self, washed):
        assert all(washed.index(1, column).data(Qt.ItemDataRole.BackgroundRole)
                   is not None
                   for column in range(washed.columnCount()))

    def test_it_repaints_only_the_rows_it_washed(self, washed):
        spans = []
        washed.dataChanged.connect(
            lambda top, bottom, roles: spans.append((top.row(), bottom.row())))

        washed.highlight_changes(0.5)

        assert spans == [(1, 1)]

    def test_a_row_the_next_refresh_dropped_is_not_repainted(self, washed):
        washed._rows = [ROW]

        washed.highlight_changes(0.5)

        assert washed.rowCount() == 1


class TestAnOptimisticRowIsWhatTheGlowPointsAt:
    def test_a_pending_insert_marks_its_own_row(self, model):
        position = model.insert_pending_row((None, "2026-09-07", "Lunch", "Rye"))

        assert position in model.changed_rows()

    def test_the_refresh_that_describes_it_marks_it_again(self, model):
        model.insert_pending_row((None, "2026-09-07", "Lunch", "Rye"))

        model.set_rows([ROW, (11, "2026-09-07", "Lunch", "Rye", 1.0, 210.0)])

        assert model.changed_rows() == frozenset({1})


class TestAFlagColumn:
    @pytest.fixture
    def flagged(self, qapp):
        built = LogTableModel(["Est", "Food Name", "Calories"],
                              {"Food Name": "food_item_id"}, table_idx=0)
        built.set_rows([FoodLogRow.from_server(
            [1, 1, "2026-09-05", "Dinner", "Restaurant Pizza", 1.0, 100.0, None,
             550.0, *([0.0] * 7)])])
        return built

    def test_a_set_flag_reads_as_a_mark(self, flagged):
        assert shown(flagged, 0, 0) == FLAG_SET_TEXT

    def test_a_clear_flag_reads_as_nothing(self, qapp, flagged):
        flagged.set_rows([FoodLogRow.from_server(
            [1, 0, "2026-09-05", "Dinner", "Rolled Oats", 1.0, 50.0, None,
             190.0, *([0.0] * 7)])])

        assert shown(flagged, 0, 0) == FLAG_CLEAR_TEXT

    def test_an_absent_flag_reads_as_nothing_rather_than_as_a_zero(self, flagged):
        flagged.set_rows([FoodLogRow.from_server(
            [1, None, "2026-09-05", "Dinner", "Rolled Oats", 1.0, 50.0, None,
             190.0, *([0.0] * 7)])])

        assert shown(flagged, 0, 0) == FLAG_CLEAR_TEXT

    def test_it_is_centred_rather_than_ranged_against_a_number_column(self, flagged):
        alignment = flagged.index(0, 0).data(Qt.ItemDataRole.TextAlignmentRole)

        assert alignment == ALIGN_CENTRE

    def test_a_flag_is_not_counted_as_a_number(self):
        numeric = numeric_fields(FoodLogRow)
        flags = boolean_fields(FoodLogRow)
        estimated = FoodLogRow._fields.index("estimated")

        assert estimated in flags
        assert estimated not in numeric

    def test_a_heading_answers_the_same_annotations_as_the_rows_it_heads(self):
        from src.database.rows import heading_type

        assert numeric_fields(heading_type(FoodLogRow)) == numeric_fields(FoodLogRow)
        assert boolean_fields(heading_type(FoodLogRow)) == boolean_fields(FoodLogRow)


class TestBothReadingsOfAnAmount:
    @pytest.fixture
    def amounts(self, qapp):
        built = LogTableModel(["Food Name", "Servings", "Grams"],
                              {"Food Name": "food_item_id", "Servings": "servings",
                               "Grams": "grams"}, table_idx=0)
        return built

    def test_both_columns_are_shown(self, amounts):
        amounts.set_rows([(1, "Rolled Oats", 2.0, 100.0)])

        assert (shown(amounts, 0, 1), shown(amounts, 0, 2)) == ("2.00", "100.00")

    def test_both_are_writable_because_typing_one_says_which_unit_this_is(
            self, amounts):
        assert editable_columns(["Food Name", "Servings", "Grams"],
                                {"Servings": "servings", "Grams": "grams"}) == [1, 2]

    def test_an_orphaned_row_keeps_the_amount_it_was_given(self, amounts):
        amounts.set_rows([(1, None, None, 100.0)])

        assert shown(amounts, 0, 2) == "100.00"
        assert shown(amounts, 0, 1) == ORPHAN_VALUE_TEXT
