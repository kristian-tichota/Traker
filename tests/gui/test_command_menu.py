import pytest
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QKeyEvent

from src.gui.commands import (COMMANDS, belongs_to, candidates_for,
                              commands_for)
from src.gui.components.cmd_line import CommandLineEdit
from src.gui.components.command_menu import MAX_ROWS, CommandMenu, rows_for
from src.gui.domains import BEVERAGE, CHORE, EXERCISE, FOOD, POMODORO, SUPPLEMENT

pytestmark = [pytest.mark.gui, pytest.mark.accessibility]


def settle(qapp):
    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()


@pytest.fixture
def bar(qapp, profile_path, recording_db):
    widget = CommandLineEdit(recording_db)
    settle(qapp)
    yield widget
    widget.deleteLater()


def names(rows):
    return [row.left for row in rows]


def marked(rows):
    picked = [row for row in rows if row.selected]
    return picked[0] if picked else None


def press(widget, key, modifier=Qt.KeyboardModifier.NoModifier):
    widget.event(QKeyEvent(QKeyEvent.Type.KeyPress, key, modifier))


class TestWhatCanBeTypedHere:
    def test_an_empty_bar_lists_every_command(self):
        assert len(rows_for("")) == MAX_ROWS + 1
        assert names(rows_for(""))[0] in COMMANDS

    def test_the_visible_tabs_own_commands_come_first(self):
        listed = names(rows_for("", (SUPPLEMENT,)))[:3]

        assert set(listed) == {"supplog", "suppset", "suppdefine"}

    def test_they_are_marked_as_belonging_to_the_tab(self):
        rows = rows_for("", (SUPPLEMENT,))

        own = [row.left for row in rows if row.accent == "green"]
        assert set(own) == {"supplog", "suppset", "suppdefine"}

    def test_the_rest_follow_in_declaration_order(self):
        rows = names(rows_for("", (SUPPLEMENT,)))

        assert rows[3:6] == ["log", "quick", "mealset"]

    def test_a_tab_is_listed_by_what_it_is_about_not_what_it_reads(self):
        listed = names(rows_for("", (FOOD,)))[:4]

        assert set(listed) == {"log", "quick", "mealset", "define"}

    def test_a_command_that_writes_every_domain_is_nobodys_own(self):
        assert not belongs_to(COMMANDS["rm"], (SUPPLEMENT,))
        assert not belongs_to(COMMANDS["track"], (EXERCISE,))

    def test_a_tab_with_no_subject_leaves_the_order_alone(self):
        assert names(rows_for("", ())) == names(rows_for(""))


class TestTypingNarrowsTheList:
    def test_only_the_commands_it_could_become_are_listed(self):
        assert names(rows_for("bev")) == ["bevlog", "bevset", "bevdefine"]

    def test_the_match_quality_that_ranks_item_names_ranks_these(self):
        assert names(rows_for("log"))[0] == "log"
        assert "bevlog" in names(rows_for("log"))

    def test_a_better_match_outranks_the_visible_tab(self):
        listed = names(rows_for("bev", (SUPPLEMENT,)))

        assert listed[0] == "bevlog"

    def test_the_tab_settles_a_draw_between_equal_matches(self):
        on_supplements = names(rows_for("set", (SUPPLEMENT,)))
        on_beverages = names(rows_for("set", (BEVERAGE,)))

        assert on_supplements.index("suppset") < on_supplements.index("bevset")
        assert on_beverages.index("bevset") < on_beverages.index("suppset")

    def test_letters_in_order_find_a_command_they_do_not_open(self):
        assert "setdsi" in names(rows_for("sdsi"))

    def test_a_word_matching_no_command_says_so(self):
        rows = rows_for("frobnicate")

        assert len(rows) == 1
        assert rows[0].right == "matches no command"

    def test_an_unfinished_word_with_a_space_still_lists_candidates(self):
        assert names(rows_for("supp ")) == ["supplog", "suppset", "suppdefine"]


class TestTheMenuIsBounded:
    def test_at_most_the_cap_is_shown_and_the_rest_are_counted(self):
        rows = rows_for("")

        assert len([row for row in rows if row.left]) <= MAX_ROWS
        assert rows[-1].right == f"+{len(commands_for('')) - MAX_ROWS} more"

    def test_the_selected_row_is_always_on_screen(self):
        last = len(commands_for("")) - 1
        rows = rows_for("", (), last)

        assert marked(rows) is not None
        assert marked(rows).left == commands_for("")[last].name

    def test_the_selection_may_reach_every_candidate(self):
        assert len(candidates_for("", ())) == len(commands_for(""))

    def test_an_argument_list_is_not_a_list_of_choices(self):
        assert candidates_for("supplog ", ()) == []


class TestWhatTheCommandTakes:
    def test_each_argument_is_listed_with_what_it_expects(self):
        rows = rows_for("bevlog ")

        assert names(rows) == ["bevlog", "[1]", "[HH:MM=now]",
                               "[Beverage or Drink Set]"]
        assert rows[-1].right == "a catalog item name"

    def test_the_argument_the_bar_is_waiting_for_is_marked(self):
        assert marked(rows_for("log ")).left == "[1 or 100g]"
        assert marked(rows_for("log 1 ")).left == "[MealType]"
        assert marked(rows_for("log 1 b ")).left == "[Food or Meal Set]"

    def test_an_omitted_optional_argument_moves_the_mark_along(self):
        assert marked(rows_for("log b ")).left == "[Food or Meal Set]"

    def test_an_argument_that_may_be_left_out_says_so(self):
        rows = {row.left: row.right for row in rows_for("bevlog ")}

        assert rows["[1]"].endswith("may be left out")
        assert "may be left out" not in rows["[Beverage or Drink Set]"]

    def test_the_heading_shows_the_fields_separated_the_way_they_are_typed(self):
        assert rows_for("suppset ")[0].right == "[Stack Name];[B12 1; Creatine 1]"
        assert rows_for("log ")[0].right.startswith("[1 or 100g] [MealType]")

    def test_a_long_definition_is_windowed_around_the_field_being_typed(self):
        rows = rows_for("define " + "x;" * 8)

        assert rows[0].left == "define"
        assert marked(rows).left == "[protein]"
        assert rows[-1].right.endswith("more")


class TestDefiningASetIsReadableOffTheMenu:
    @pytest.mark.parametrize("command,unit,example", [
        ("suppset", "servings", "B12 1"),
        ("mealset", "grams", "Food 100"),
        ("bevset", "servings", "Drink 1"),
        ("mobset", "minutes", "Hip Opener 10"),
    ])
    def test_the_components_field_names_its_unit_and_shows_an_example(
            self, command, unit, example):
        components = rows_for(f"{command} ")[-1].right

        assert unit in components
        assert example in components

    def test_the_set_name_carries_the_rule_a_member_cannot_see(self):
        assert "no item or set" in rows_for("suppset ")[1].right

    def test_a_workout_says_what_each_movement_carries(self):
        assert "Bench Press 8,8,6 60 8" in rows_for("exset ")[-1].right

    def test_every_domains_set_command_is_on_its_own_tab(self):
        for domain, command in ((FOOD, "mealset"), (BEVERAGE, "bevset"),
                                (SUPPLEMENT, "suppset"), (EXERCISE, "exset")):
            assert command in names(rows_for("", (domain,)))


class TestMovingThroughTheCandidates:
    def test_ctrl_n_and_ctrl_p_move_the_selection(self, bar):
        bar.setText("bev")
        assert bar.menu_index == 0

        press(bar, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        assert bar.menu_index == 1
        press(bar, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)
        assert bar.menu_index == 0

    def test_the_arrows_do_the_same(self, bar):
        bar.setText("bev")

        press(bar, Qt.Key.Key_Down)
        assert bar.menu_index == 1
        press(bar, Qt.Key.Key_Up)
        assert bar.menu_index == 0

    def test_the_selection_wraps_at_both_ends(self, bar):
        bar.setText("bev")

        press(bar, Qt.Key.Key_Up)
        assert bar.menu_index == 2
        press(bar, Qt.Key.Key_Down)
        assert bar.menu_index == 0

    def test_tab_writes_the_selected_candidate(self, bar):
        bar.setText("bev")
        press(bar, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        press(bar, Qt.Key.Key_Tab)

        assert bar.text() == "bevset"

    def test_the_hint_follows_the_selection(self, bar):
        bar.setText("bev")
        press(bar, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)

        assert bar.hint_text.startswith("set [")

    def test_the_next_keystroke_returns_to_the_best_match(self, bar):
        bar.setText("bev")
        press(bar, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        bar.setText("bevl")

        assert bar.menu_index == 0

    def test_nothing_to_pick_moves_nothing(self, bar):
        bar.setText("supplog ")

        press(bar, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        assert bar.menu_index == 0


class TestCompletingACommandByFuzzyMatch:
    def test_a_prefix_still_appends_only_the_tail(self, bar):
        bar.setText("bev")

        assert bar.completion_text == "log"
        assert not bar.is_fuzzy_replacement

    def test_letters_in_order_replace_the_whole_word(self, bar):
        bar.setText("sdsi")

        assert bar.is_fuzzy_replacement
        assert bar.completing_command
        assert bar.hint_text.startswith(" -> (setdsi)")

        press(bar, Qt.Key.Key_Tab)
        assert bar.text() == "setdsi"

    def test_the_replacement_does_not_disturb_an_item_name(self, bar):
        bar.setText("log 1 b rizek")
        press(bar, Qt.Key.Key_Tab)

        assert bar.text() == "log 1 b Řízek s bramborem"

    def test_the_visible_tabs_command_is_what_a_bare_letter_offers(self, bar):
        bar.set_relevant_domains((SUPPLEMENT,))
        bar.setText("s")

        assert bar.completion_text == "upplog"


class TestTheMenuWidget:
    def test_it_renders_the_rows_it_was_given(self, qapp):
        menu = CommandMenu()
        menu.render_for("suppset ", (SUPPLEMENT,))

        assert menu.rows[0].left == "suppset"
        assert menu.rows[1].selected
        menu.deleteLater()

    def test_a_row_it_has_nothing_for_is_hidden(self, qapp):
        menu = CommandMenu()
        menu.render_for("suppset ", (SUPPLEMENT,))
        qapp.processEvents()

        assert all(not label.isVisibleTo(menu)
                   for label in menu._labels[len(menu.rows)])
        menu.deleteLater()

    def test_it_survives_a_paint(self, qapp):
        from PyQt6.QtGui import QPixmap

        menu = CommandMenu()
        menu.render_for("", (FOOD,))
        menu.resize(900, 120)
        pixmap = QPixmap(menu.size())
        menu.render(pixmap)

        assert not pixmap.isNull()
        menu.deleteLater()


class TestTheMenuBelongsToCommandMode:
    def test_it_is_hidden_until_command_mode(self, window):
        window.show()

        window.set_mode("NORMAL")
        assert not window.command_menu.isVisible()

        window.set_mode("COMMAND")
        assert window.command_menu.isVisible()

        window.set_mode("SHEET")
        assert not window.command_menu.isVisible()

    def test_entering_command_mode_fills_it(self, window):
        window.set_mode("COMMAND")

        assert window.command_menu.rows

    def test_it_follows_what_the_bar_is_offering(self, window, settled):
        window.set_mode("COMMAND")
        window.command_line.setText("bev")
        settled()

        assert names(window.command_menu.rows) == ["bevlog", "bevset", "bevdefine"]

    def test_the_visible_tab_ranks_it(self, window, settled):
        window.tabs.setCurrentIndex(window.tab_indices["supplements"])
        window.command_line.setText("")
        settled()

        assert names(window.command_menu.rows)[:3] == [
            "supplog", "suppset", "suppdefine"]

    def test_a_tab_is_ranked_by_its_own_command_not_by_what_it_reads(self, window):
        assert window._tab_subject(window.tab_indices["food"]) == (FOOD,)

    def test_a_tab_without_a_command_falls_back_to_what_it_shows(self, window):
        assert window._tab_subject(
            window.tab_indices["pomodoro"]) == (POMODORO, CHORE)
        assert window._tab_subject(
            window.tab_indices["caffeine_graph"]) == (BEVERAGE,)
