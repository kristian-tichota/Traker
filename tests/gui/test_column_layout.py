from collections import namedtuple

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QKeyEvent

from src.gui.columns import (
    ColumnError, ColumnLayout, describe, rearranged, resolve_column, setting_key)
from src.gui.commands import COMMANDS, HIDE, MOVE, RESET, SHOW, TOGGLE, resolve
from src.gui.filtering import parse
from src.database.rows import FoodLogRow
from src.gui.views.beverage_view import BeveragesView
from src.gui.views.exercise_view import ExerciseView
from src.gui.views.food_views import FoodView
from src.gui.views.mobility_view import MobilityView
from src.gui.views.supplement_view import SupplementsView

HEADERS = ["Est", "Date", "Food Name", "Servings", "Calories", "Protein", "Sugars"]


def declared():
    return ColumnLayout.declared(HEADERS)


class TestALayoutIsAPermutationPlusAHiddenSet:
    def test_an_unarranged_table_shows_what_it_declares(self):
        layout = declared()

        assert layout.order == tuple(HEADERS)
        assert layout.visible == tuple(HEADERS)
        assert layout.hidden == frozenset()
        assert layout.is_default(HEADERS)

    def test_a_hidden_column_keeps_its_place(self):
        layout = declared().hide("Servings")

        assert layout.order == tuple(HEADERS)
        assert layout.visible == ("Est", "Date", "Food Name", "Calories",
                                  "Protein", "Sugars")
        assert layout.show("Servings") == declared()

    def test_moving_counts_the_columns_the_member_can_see(self):
        layout = declared().hide("Est").move("Calories", 1)

        assert layout.visible[0] == "Calories"
        assert layout.move("Calories", 3).visible == (
            "Date", "Food Name", "Calories", "Servings", "Protein", "Sugars")

    def test_moving_to_the_last_position_is_allowed(self):
        layout = declared().move("Est", len(HEADERS))

        assert layout.visible[-1] == "Est"

    def test_a_layout_is_immutable(self):
        layout = declared()
        layout.hide("Sugars").move("Protein", 1)

        assert layout == declared()


class TestWhatIsRefused:
    def test_the_last_visible_column_cannot_be_hidden(self):
        layout = ColumnLayout(tuple(HEADERS), frozenset(HEADERS[1:]))

        assert layout.visible == ("Est",)
        assert not layout.can_hide("Est")
        with pytest.raises(ColumnError):
            layout.hide("Est")

    def test_a_column_this_table_does_not_have_is_refused(self):
        with pytest.raises(ColumnError):
            declared().hide("Caffeine (mg)")

    def test_a_position_past_the_end_is_refused(self):
        with pytest.raises(ColumnError, match="7 columns"):
            declared().move("Est", 8)

    def test_a_position_counts_from_one(self):
        with pytest.raises(ColumnError):
            declared().move("Est", 0)

    def test_a_hidden_column_is_shown_before_it_is_moved(self):
        layout = declared().hide("Sugars")

        with pytest.raises(ColumnError, match="hidden"):
            layout.move("Sugars", 1)

    def test_hiding_what_is_already_hidden_changes_nothing(self):
        layout = declared().hide("Sugars")

        assert layout.hide("Sugars") == layout


class TestTheStoredForm:
    def test_a_layout_survives_the_round_trip(self):
        layout = declared().hide("Sugars").hide("Est").move("Calories", 2)

        assert ColumnLayout.parse(layout.encoded, HEADERS) == layout

    def test_hidden_columns_are_marked_in_the_stored_value(self):
        assert declared().hide("Sugars").encoded.endswith("|-Sugars")

    def test_a_column_a_later_version_added_appears(self):
        stored = declared().encoded
        grown = [*HEADERS, "Fibre"]

        layout = ColumnLayout.parse(stored, grown)

        assert layout.order == tuple(grown)
        assert "Fibre" in layout.visible

    def test_a_column_this_version_no_longer_shows_is_dropped(self):
        layout = ColumnLayout.parse("Date|Retired Column|Est", HEADERS)

        assert "Retired Column" not in layout.order
        assert layout.order[:2] == ("Date", "Est")

    def test_nothing_stored_means_the_declared_columns(self):
        assert ColumnLayout.parse("", HEADERS) == declared()
        assert ColumnLayout.parse(None, HEADERS) == declared()

    def test_a_value_naming_the_same_column_twice_is_read_once(self):
        layout = ColumnLayout.parse("Date|Date|Est", HEADERS)

        assert layout.order.count("Date") == 1

    def test_the_key_is_per_table(self):
        assert setting_key("food_logs") == "columns_food_logs"
        assert setting_key("food_items") != setting_key("food_logs")


class TestNamingAColumn:
    @pytest.mark.accessibility
    @pytest.mark.parametrize("typed, header", [
        ("kcal", "Calories"), ("cal", "Calories"), ("Calories", "Calories"),
        ("prot", "Protein"), ("serv", "Servings"), ("est", "Est"),
        ("sugar", "Sugars"), ("food", "Food Name"),
    ])
    def test_a_column_is_named_the_way_a_filter_names_one(self, typed, header):
        assert resolve_column(typed, declared()) == header

    def test_a_hidden_column_can_still_be_named(self):
        assert resolve_column("sugar", declared().hide("Sugars")) == "Sugars"

    def test_a_word_naming_no_column_is_refused(self):
        with pytest.raises(ColumnError, match="No column called"):
            resolve_column("caffeine", declared())


class TestWhatColsMeans:
    def test_naming_only_a_column_toggles_it(self):
        off, said = rearranged(declared(), HEADERS, TOGGLE, "sugar", None)
        assert off.is_hidden("Sugars") and "hidden" in said

        on, said = rearranged(off, HEADERS, TOGGLE, "sugar", None)
        assert not on.is_hidden("Sugars") and "shown" in said

    def test_hide_and_show_say_which_they_mean(self):
        off, _ = rearranged(declared(), HEADERS, HIDE, "sugar", None)
        assert off.is_hidden("Sugars")
        assert rearranged(off, HEADERS, HIDE, "sugar", None)[0] == off
        assert not rearranged(off, HEADERS, SHOW, "sugar", None)[0].hidden

    def test_move_needs_a_position(self):
        with pytest.raises(ColumnError, match="Which position"):
            rearranged(declared(), HEADERS, MOVE, "kcal", None)

    def test_reset_goes_back_to_the_declared_columns(self):
        arranged = declared().hide("Sugars").move("Calories", 1)

        settled, _ = rearranged(arranged, HEADERS, RESET, "", None)

        assert settled == declared()

    def test_the_layout_reads_back_as_shown_then_hidden(self):
        line = describe(declared().hide("Sugars"))

        assert line.startswith("Est, Date, Food Name")
        assert line.endswith("hidden: Sugars")
        assert "Sugars," not in line.split("hidden")[0]

Entry = namedtuple("Entry", "text checkable checked enabled")


def press(widget, key):
    widget.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key,
                                   Qt.KeyboardModifier.NoModifier))


def shown(view, table_idx=0):
    return list(view.column_layout(table_idx).visible)


@pytest.fixture
def food(qapp, profile_path, recording_db, settled):
    recording_db.food_logs = [
        FoodLogRow.from_server([1, 0, "2026-09-05", "Breakfast", "Rolled Oats",
                                1.0, 50.0, None,
                                312.4, 20.0, 40.0, 2.0, 5.0, 1.0, 0.5, 8.0]),
        FoodLogRow.from_server([2, 0, "2026-09-05", "Lunch", "Grilled Salmon",
                                2.0, 300.0, None,
                                9.0, 30.0, 0.0, 0.0, 12.0, 2.0, 1.0, 0.0]),
    ]
    view = FoodView(recording_db)
    view.refresh()
    settled()
    yield view
    view.shutdown()


@pytest.mark.gui
class TestTheHeaderIsTheState:
    def test_a_new_table_shows_what_it_declares(self, food):
        assert shown(food) == food.headers[0]

    def test_applying_a_layout_moves_and_hides_the_sections(self, food):
        declared_headers = food.headers[0]
        layout = food.column_layout(0).hide("Sugars").move("Calories", 2)

        food.apply_column_layout(0, layout)

        header = food.table.horizontalHeader()
        assert header.isSectionHidden(declared_headers.index("Sugars"))
        assert shown(food)[:2] == ["Est", "Calories"]
        assert food.model_for(0)._headers == declared_headers

    def test_a_rearrangement_does_not_move_the_values(self, food, settled):
        food.refresh()
        settled()
        food.set_column_layout(0, food.column_layout(0).move("Calories", 1))

        model = food.model_for(0)
        column = food.headers[0].index("Calories")

        assert model.headerData(column, Qt.Orientation.Horizontal) == "Calories"

    def test_the_stored_layout_is_read_on_arrival_at_the_tab(self, food, settled):
        food.db.settings[setting_key("food_logs")] = "Calories|Date|-Sugars"

        food.load_column_layouts()
        settled()

        assert shown(food)[:2] == ["Calories", "Date"]
        assert "Sugars" not in shown(food)

    def test_the_whole_tab_is_read_in_one_request(self, food, settled):
        food.load_column_layouts()
        settled()

        batches = [batch for batch in food.db.setting_batches
                   if any(key.startswith("columns_") for key in batch)]
        assert len(batches) == 1
        assert set(batches[0]) == {setting_key("food_logs"),
                                  setting_key("food_items"),
                                  setting_key("food_set_components")}

    def test_it_is_read_once_however_often_the_tab_is_revisited(self, food, settled):
        food.load_column_layouts()
        food.load_column_layouts()
        settled()

        assert len([b for b in food.db.setting_batches
                    if any(k.startswith("columns_") for k in b)]) == 1

    def test_a_stored_layout_does_not_undo_what_the_member_just_did(self, food, settled):
        food.db.settings[setting_key("food_logs")] = "Sugars|Date"
        food.set_column_layout(0, food.column_layout(0).hide("Sugars"))

        food.load_column_layouts()
        settled()

        assert "Sugars" not in shown(food)


@pytest.mark.gui
class TestItIsRemembered:
    def test_arranging_a_table_stores_the_layout_for_this_member(self, food, settled):
        food.set_column_layout(0, food.column_layout(0).hide("Sugars"))
        settled()

        key, value = food.db.last("set_setting")
        assert key == setting_key("food_logs")
        assert ColumnLayout.parse(value, food.headers[0]) == food.column_layout(0)

    def test_each_of_a_tabs_tables_is_remembered_separately(self, food, settled):
        food.set_column_layout(1, food.column_layout(1).hide("Salt (g)"))
        settled()

        assert food.db.last("set_setting")[0] == setting_key("food_items")

    def test_a_column_switched_off_is_still_off_when_the_tab_is_rebuilt(
            self, food, settled, recording_db):
        food.set_column_layout(0, food.column_layout(0).hide("Sugars"))
        settled()

        rebuilt = FoodView(recording_db)
        rebuilt.load_column_layouts()
        settled()
        try:
            assert "Sugars" not in shown(rebuilt)
        finally:
            rebuilt.shutdown()

    def test_a_refused_write_is_reported_and_not_swallowed(self, food, settled):
        messages = []
        food.status_message.connect(messages.append)
        food.db.result = (False, "service unavailable")

        food.set_column_layout(0, food.column_layout(0).hide("Sugars"))
        settled()

        assert any("not saved" in message for message in messages)

    def test_dragging_a_heading_stores_where_it_landed(self, food, settled):
        header = food.table.horizontalHeader()

        header.moveSection(header.visualIndex(food.headers[0].index("Calories")), 0)
        settled()

        assert shown(food)[0] == "Calories"
        assert ColumnLayout.parse(food.db.last("set_setting")[1],
                                  food.headers[0]) == food.column_layout(0)

    def test_a_rearrangement_the_view_asked_for_is_not_reported_as_a_drag(
            self, food, settled):
        food.apply_column_layout(0, food.column_layout(0).move("Calories", 1))
        settled()

        assert not food.db.called("set_setting")


@pytest.mark.gui
class TestTheMouseCanDoWhatTheKeyboardCan:
    def menu_of(self, view, monkeypatch, table_idx=0):
        entries = []

        def capture(self, *args, **kwargs):
            entries.extend(
                Entry(action.text(), action.isCheckable(), action.isChecked(),
                      action.isEnabled())
                for action in self.actions() if not action.isSeparator())
            return None

        monkeypatch.setattr("PyQt6.QtWidgets.QMenu.exec", capture)
        view.on_header_menu_requested(table_idx, QPoint(1, 1))
        return entries

    def test_every_column_is_listed_whether_it_is_shown_or_not(
            self, food, monkeypatch):
        food.apply_column_layout(0, food.column_layout(0).hide("Sugars"))

        listed = {entry.text: entry for entry in self.menu_of(food, monkeypatch)}

        for header in food.headers[0]:
            assert header in listed, f"{header} is not offered"
        assert listed["Sugars"].checkable and not listed["Sugars"].checked
        assert listed["Calories"].checked

    def test_the_menu_is_in_the_order_the_columns_are_shown(self, food, monkeypatch):
        food.apply_column_layout(0, food.column_layout(0).move("Calories", 1))

        offered = self.menu_of(food, monkeypatch)

        assert [entry.text for entry in offered][:2] == ["Calories", "Est"]

    def test_choosing_a_shown_column_switches_it_off(self, food, settled, monkeypatch):
        chosen = {}

        def choose(self, *args, **kwargs):
            chosen["action"] = next(a for a in self.actions() if a.text() == "Sugars")
            return chosen["action"]

        monkeypatch.setattr("PyQt6.QtWidgets.QMenu.exec", choose)
        food.on_header_menu_requested(0, QPoint(1, 1))
        settled()

        assert "Sugars" not in shown(food)
        assert food.db.called("set_setting")

    def test_choosing_a_hidden_column_brings_it_back(self, food, settled, monkeypatch):
        food.apply_column_layout(0, food.column_layout(0).hide("Sugars"))

        def choose(self, *args, **kwargs):
            return next(a for a in self.actions() if a.text() == "Sugars")

        monkeypatch.setattr("PyQt6.QtWidgets.QMenu.exec", choose)
        food.on_header_menu_requested(0, QPoint(1, 1))
        settled()

        assert "Sugars" in shown(food)
        assert ColumnLayout.parse(food.db.last("set_setting")[1],
                                  food.headers[0]).is_default(food.headers[0])

    def test_the_last_visible_column_cannot_be_switched_off_from_the_menu(
            self, food, monkeypatch):
        layout = food.column_layout(0)
        for header in food.headers[0][1:]:
            layout = layout.hide(header)
        food.apply_column_layout(0, layout)

        listed = {entry.text: entry for entry in self.menu_of(food, monkeypatch)}

        assert not listed["Est"].enabled
        assert listed["Sugars"].enabled, "a hidden column is always offered"

    def test_the_menu_can_put_the_whole_layout_back(self, food, settled, monkeypatch):
        food.apply_column_layout(0, food.column_layout(0).hide("Sugars"))

        def choose(self, *args, **kwargs):
            return next(a for a in self.actions() if "Reset" in a.text())

        monkeypatch.setattr("PyQt6.QtWidgets.QMenu.exec", choose)
        food.on_header_menu_requested(0, QPoint(1, 1))
        settled()

        assert food.column_layout(0).is_default(food.headers[0])

    def test_dismissing_the_menu_changes_nothing(self, food, settled, monkeypatch):
        monkeypatch.setattr("PyQt6.QtWidgets.QMenu.exec",
                            lambda self, *a, **k: None)

        food.on_header_menu_requested(0, QPoint(1, 1))
        settled()

        assert food.column_layout(0).is_default(food.headers[0])
        assert not food.db.called("set_setting")


@pytest.mark.gui
@pytest.mark.accessibility
class TestTheCursorFollowsWhatIsOnScreen:
    def test_hjkl_moves_in_the_order_the_member_sees(self, food, settled):
        food.apply_column_layout(0, food.column_layout(0).move("Calories", 1))
        table = food.table
        table.setCurrentIndex(table.model().index(0, food.headers[0].index("Calories")))

        press(table, table.key_right)

        assert food.headers[0][table.currentIndex().column()] == "Est"

    def test_a_hidden_column_is_stepped_over(self, food, settled):
        food.apply_column_layout(0, food.column_layout(0).hide("Date"))
        table = food.table
        table.setCurrentIndex(table.model().index(0, food.headers[0].index("Est")))

        press(table, table.key_right)

        assert food.headers[0][table.currentIndex().column()] == "Meal Type"

    def test_the_cursor_stops_at_the_last_visible_column(self, food, settled):
        food.apply_column_layout(0, food.column_layout(0).hide("Fibre"))
        table = food.table
        table.setCurrentIndex(table.model().index(0, food.headers[0].index("Salt")))

        press(table, table.key_right)

        assert food.headers[0][table.currentIndex().column()] == "Salt"

    def test_the_cursor_leaves_a_column_that_has_just_been_hidden(self, food, settled):
        table = food.table
        table.setCurrentIndex(table.model().index(0, food.headers[0].index("Sugars")))

        food.apply_column_layout(0, food.column_layout(0).hide("Sugars"))

        column = table.currentIndex().column()
        assert not table.horizontalHeader().isSectionHidden(column)
        assert food.headers[0][column] == "Est"

    def test_entering_the_sheet_lands_on_a_column_that_is_shown(self, food, settled):
        food.apply_column_layout(0, food.column_layout(0).hide("Est"))

        food.table.focus_first_cell()

        assert food.headers[0][food.table.currentIndex().column()] == "Date"


@pytest.mark.gui
class TestNoTableDeclaresAColumnTwice:
    @pytest.mark.parametrize("build", [
        FoodView, BeveragesView, ExerciseView, SupplementsView, MobilityView])
    def test_every_header_of_every_table_is_its_own_name(
            self, build, qapp, profile_path, recording_db):
        view = build(recording_db)
        try:
            for headers in view.headers:
                assert len(set(headers)) == len(headers), headers
        finally:
            view.shutdown()


@pytest.mark.gui
class TestATableSaysWhenItTakesFocus:
    def test_taking_focus_names_the_table(self, food, qapp):
        named = []
        food.t_items.focus_taken.connect(named.append)

        food.show()
        food.t_items.activateWindow()
        food.t_items.setFocus()
        qapp.processEvents()
        food.hide()

        assert named == [food.t_items]


@pytest.mark.gui
class TestTheMatchedSetLineFollowsTheColumns:
    def test_a_nutrient_switched_off_is_not_totalled_under_the_table(
            self, food, settled):
        food.apply_filter(parse("date>01.01.2000", food.headers[0]))
        with_calories = food.summary_label.text()

        food.set_column_layout(0, food.column_layout(0).hide("Calories"))

        assert "kcal" in with_calories
        assert "kcal" not in food.summary_label.text()


@pytest.mark.gui
class TestColsFromTheCommandBar:
    def submit(self, window, text, settled):
        window.command_line.setText(text)
        window.execute_command()
        settled()
        return window.status_bar.text()

    @pytest.fixture
    def food_tab(self, window, settled):
        window.tabs.setCurrentIndex(window.tab_indices["food"])
        settled()
        return window.views["food"]

    def test_cols_alone_reads_the_layout_back(self, window, food_tab, settled):
        food_tab.apply_column_layout(0, food_tab.column_layout(0).hide("Sugars"))

        line = self.submit(window, "cols", settled)

        assert "Food Log Ledger" in line
        assert "hidden: Sugars" in line
        assert not food_tab.db.called("set_setting"), "reading stores nothing"

    def test_a_column_named_on_its_own_is_toggled(self, window, food_tab, settled):
        assert "hidden" in self.submit(window, "cols sugar", settled)
        assert "Sugars" not in shown(food_tab)

        assert "shown" in self.submit(window, "cols sugar", settled)
        assert "Sugars" in shown(food_tab)

    def test_hide_show_move_and_reset(self, window, food_tab, settled):
        self.submit(window, "cols hide Sugars", settled)
        assert "Sugars" not in shown(food_tab)

        self.submit(window, "cols show Sugars", settled)
        assert "Sugars" in shown(food_tab)

        self.submit(window, "cols move 1 kcal", settled)
        assert shown(food_tab)[0] == "Calories"

        self.submit(window, "cols reset", settled)
        assert food_tab.column_layout(0).is_default(food_tab.headers[0])

    def test_a_column_whose_name_has_a_space_is_named_in_full(
            self, window, food_tab, settled):
        self.submit(window, "cols hide Sat Fat", settled)

        assert "Sat Fat" not in shown(food_tab)

    def test_what_was_typed_is_stored(self, window, food_tab, settled):
        self.submit(window, "cols hide Sugars", settled)

        key, value = food_tab.db.last("set_setting")
        assert key == setting_key("food_logs")
        assert "-Sugars" in value

    def test_a_refusal_leaves_the_text_in_the_bar_to_correct(
            self, window, food_tab, settled):
        window.set_mode("COMMAND")

        line = self.submit(window, "cols hide Caffeine", settled)

        assert "No column called" in line
        assert window.command_line.text() == "cols hide Caffeine"
        assert window.current_mode == "COMMAND"

    def test_it_acts_on_the_table_the_member_was_last_in(
            self, window, food_tab, settled):
        food_tab.t_items.focus_taken.emit(food_tab.t_items)

        line = self.submit(window, "cols hide Category", settled)

        assert "Food Item Database" in line
        assert "Category" not in shown(food_tab, 1)
        assert shown(food_tab, 0) == food_tab.headers[0], "the ledger is untouched"

    def test_the_ledger_is_the_default_table(self, window, food_tab, settled):
        line = self.submit(window, "cols hide Sugars", settled)

        assert "Food Log Ledger" in line

    def test_a_tab_with_no_table_says_so(self, window, settled):
        window.tabs.setCurrentIndex(window.tab_indices["food_graphs"])
        settled()

        assert "No table to arrange" in self.submit(window, "cols", settled)

    def test_the_command_is_in_the_grammar_like_any_other(self):
        command, remainder = resolve("cols hide Sugars")

        assert command is COMMANDS["cols"]
        assert command is COMMANDS["columns"], "the plural spelling reaches it too"
        assert command.window_effect == "arrange_columns"
        assert command.domains == (), "it writes no household data"
        assert command.parse(remainder) == {
            "action": HIDE, "position": None, "column": "Sugars"}
