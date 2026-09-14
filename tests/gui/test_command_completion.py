import pytest
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QKeyEvent

from src.gui.completion import best_match, completion_tail, normalize
from src.gui.components.cmd_line import CommandLineEdit

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


@pytest.fixture
def focused_bar(bar, qapp):
    bar.show()
    bar.activateWindow()
    bar.setFocus()
    qapp.processEvents()
    assert bar.hasFocus()
    return bar


def press_tab(widget):
    widget.event(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier))


class TestCommandNameHints:
    def test_a_prefix_offers_the_rest_of_the_command_name(self, bar):
        bar.setText("bev")

        assert bar.completion_text == "log"
        assert bar.hint_text.startswith("log [1] [HH:MM=now]")

    def test_the_hint_continues_with_the_argument_list(self, bar):
        bar.setText("mobl")

        assert bar.hint_text == "og [mins or set multiple] [Routine or Routine Set]"

    def test_tab_accepts_the_command_name(self, bar):
        bar.setText("expl"[:2])
        press_tab(bar)

        assert bar.text() == "exlog"

    def test_an_unknown_prefix_offers_nothing(self, bar):
        bar.setText("frob")

        assert bar.completion_text == ""
        assert bar.hint_text == ""

    def test_an_empty_bar_shows_no_hint(self, bar):
        bar.setText("log")
        bar.setText("")

        assert bar.hint_text == ""


class TestArgumentHints:
    def test_only_the_arguments_still_missing_are_advertised(self, bar):
        bar.setText("bevlog ")
        assert bar.hint_text == " [1] [HH:MM=now] [Beverage or Drink Set]"

        bar.setText("bevlog 1 ")
        assert bar.hint_text == " [HH:MM=now] [Beverage or Drink Set]"

    def test_an_argument_left_out_is_no_longer_advertised(self, bar):
        bar.setText("bevlog 14:30 ")

        assert bar.hint_text == bar.EMPTY_NAME_HINT

    def test_the_name_prompt_waits_until_the_name_is_all_that_is_left(self, bar):
        bar.setText("bevlog ")
        assert bar.hint_text != bar.EMPTY_NAME_HINT

        bar.setText("bevlog 1 14:30 ")
        assert bar.hint_text == bar.EMPTY_NAME_HINT

    def test_the_optional_arguments_are_advertised_before_anything_is_typed(self, bar):
        bar.setText("log ")

        assert bar.hint_text == " [1 or 100g] [MealType] [Food or Meal Set]"

    def test_a_definition_advertises_the_remaining_semicolon_fields(self, bar):
        bar.setText("bevdefine Black Coffee;")

        assert bar.hint_text == " [caffeine_mg];[antioxidants_mg]"

    def test_the_last_definition_field_advertises_only_itself(self, bar):
        bar.setText("bevdefine Black Coffee;80;")

        assert bar.hint_text == " [antioxidants_mg]"

    def test_a_definition_past_its_last_field_advertises_nothing(self, bar):
        bar.setText("bevdefine Black Coffee;80;200;")

        assert bar.hint_text == ""

    def test_an_argument_whose_label_contains_spaces_stays_whole(self, bar):
        bar.setText("exlog ")
        assert bar.hint_text == " [sets: 7,7,7] [weight] [rpe] [Exercise Name]"

        bar.setText("exlog 7,7,7 ")
        assert bar.hint_text == " [weight] [rpe] [Exercise Name]"

        bar.setText("exlog 7,7,7 30 ")
        assert bar.hint_text == " [rpe] [Exercise Name]"

    def test_a_single_argument_command_advertises_nothing_once_answered(self, bar):
        bar.setText("graphlayout 2x2 ")

        assert bar.hint_text == ""


class TestFuzzyCompletion:
    @pytest.mark.parametrize("typed", ["rol", "Rol", "ROLLED"])
    def test_a_prefix_completes_in_place(self, bar, typed):
        bar.setText(f"log 1 b {typed}")

        assert bar.is_fuzzy_replacement is False
        assert bar.completion_text == "Rolled Oats"[len(typed):]

        press_tab(bar)

        assert bar.text() == f"log 1 b {typed}" + "Rolled Oats"[len(typed):]

    def test_a_substring_match_is_offered_as_a_replacement(self, bar):
        bar.setText("log 1 b Yoghurt")

        assert bar.is_fuzzy_replacement is True
        assert bar.completion_text == "Greek Yoghurt"
        assert bar.hint_text == " -> (Greek Yoghurt)"

    def test_a_subsequence_match_is_offered_as_a_replacement(self, bar):
        bar.setText("log 1 b rlo")

        assert bar.is_fuzzy_replacement is True
        assert bar.completion_text in {"Rolled Oats", "Rolled Oat Bar"}

    def test_a_prefix_match_beats_a_substring_match(self, bar):
        bar.setText("log 1 b oat")

        assert bar.completion_text == "Rolled Oats"

    def test_the_shortest_name_wins_among_equally_good_matches(self, bar):
        bar.setText("log 1 b Rolled Oat")

        press_tab(bar)
        assert bar.text() == "log 1 b Rolled Oats"

    def test_accents_are_ignored_when_matching(self, bar):
        bar.setText("log 1 b bramborem")

        assert bar.is_fuzzy_replacement is True
        press_tab(bar)
        assert bar.text() == "log 1 b Řízek s bramborem"

    def test_a_diacritic_free_prefix_is_offered_as_a_replacement(self, bar):
        bar.setText("log 1 b rizek")

        assert bar.is_fuzzy_replacement is True
        assert bar.completion_text == "Řízek s bramborem"

        press_tab(bar)

        assert bar.text() == "log 1 b Řízek s bramborem"

    def test_a_prefix_typed_with_its_accents_completes_in_place(self, bar):
        bar.setText("log 1 b Řízek s")

        assert bar.is_fuzzy_replacement is False
        assert bar.completion_text == " bramborem"

    def test_only_letter_case_may_differ_from_the_catalog_spelling(self, bar):
        bar.setText("log 1 b rIzEk")

        assert bar.is_fuzzy_replacement is True

    def test_nothing_matching_says_so_and_tab_changes_nothing(self, bar):
        bar.setText("log 1 b zzzz")

        assert bar.hint_text == " [No match found]"
        press_tab(bar)
        assert bar.text() == "log 1 b zzzz"

    def test_tab_keeps_the_focus_even_with_nothing_to_complete(self, focused_bar):
        focused_bar.setText("log 1 b zzzz")

        press_tab(focused_bar)

        assert focused_bar.hasFocus()

    def test_an_empty_name_position_prompts_for_one(self, bar):
        bar.setText("log 1 b ")

        assert bar.hint_text == " [Item Name]"


class TestASuggestionThatIsNotReadyYet:
    def test_the_bar_offers_nothing_until_the_names_land(
        self, qapp, profile_path, recording_db
    ):
        bar = CommandLineEdit(recording_db)

        bar.setText("log 1 b Rolled")

        assert bar.hint_text == ""
        assert bar.completion_text == ""
        bar.deleteLater()

    def test_the_suggestion_appears_as_soon_as_the_names_do(
        self, qapp, profile_path, recording_db
    ):
        bar = CommandLineEdit(recording_db)
        bar.setText("log 1 b Rolled")

        settle(qapp)

        assert bar.completion_text == " Oats"
        bar.deleteLater()

    def test_an_empty_name_position_still_prompts_for_one(
        self, qapp, profile_path, recording_db
    ):
        bar = CommandLineEdit(recording_db)

        bar.setText("log 1 b ")

        assert bar.hint_text == bar.EMPTY_NAME_HINT
        bar.deleteLater()


class TestCompletionAcceptance:
    def test_accepting_a_replacement_leaves_earlier_arguments_untouched(self, bar):
        bar.setText("log 2.5 Breakfast Yoghurt")

        press_tab(bar)

        assert bar.text() == "log 2.5 Breakfast Greek Yoghurt"

    def test_an_exercise_name_keeps_its_three_leading_arguments(self, bar):
        bar.setText("exlog 7,7,7 30 8 Bench")

        press_tab(bar)

        assert bar.text() == "exlog 7,7,7 30 8 Bench Press"

    def test_removal_completes_across_every_catalog(self, bar):
        bar.setText("rm Green")

        press_tab(bar)

        assert bar.text() == "rm Green Tea"

    def test_tracking_completes_exercise_names(self, bar):
        bar.setText("track 1 Plan")

        press_tab(bar)

        assert bar.text() == "track 1 Plank"

    def test_a_supplement_name_completes(self, bar):
        bar.setText("supplog 1 Evening")

        press_tab(bar)

        assert bar.text() == "supplog 1 Evening Stack"

    def test_a_mobility_routine_completes(self, bar):
        bar.setText("moblog 20 Hip")

        press_tab(bar)

        assert bar.text() == "moblog 20 Hip Opener"

    def test_the_suggestion_is_consumed_by_accepting_it(self, bar):
        bar.setText("log 1 b Yoghurt")
        press_tab(bar)

        assert bar.completion_text == ""
        assert bar.hint_text == ""
        assert bar.is_fuzzy_replacement is False

    def test_completion_sources_the_shared_catalog(self, bar, qapp, recording_db):
        recording_db.foods.append("Sourdough Bread")
        bar.invalidate_catalog_cache()
        settle(qapp)

        bar.setText("log 1 b Sourdo")
        press_tab(bar)

        assert bar.text() == "log 1 b Sourdough Bread"


class TestPrefilledCommand:
    def test_a_tab_prefills_its_own_command_with_a_trailing_space(self, focused_bar):
        focused_bar.set_default_command("log")

        assert focused_bar.text() == "log "

    def test_the_caret_sits_at_the_end_with_nothing_selected(self, focused_bar):
        focused_bar.set_default_command("log")

        assert focused_bar.cursorPosition() == len("log ")
        assert not focused_bar.hasSelectedText()

    def test_switching_tabs_replaces_an_untouched_prefill(self, focused_bar):
        focused_bar.set_default_command("log")
        focused_bar.set_default_command("bevlog")

        assert focused_bar.text() == "bevlog "

    def test_a_half_typed_command_is_not_replaced_by_a_tab_switch(self, focused_bar):
        focused_bar.set_default_command("log")
        focused_bar.setText("log 1 b Rolled Oats")

        focused_bar.set_default_command("bevlog")

        assert focused_bar.text() == "log 1 b Rolled Oats"

    def test_entering_the_bar_prefills_the_tabs_command(self, bar, qapp):
        bar.set_default_command("bevlog")

        bar.show()
        bar.activateWindow()
        bar.setFocus()
        qapp.processEvents()

        assert bar.text() == "bevlog "

    def test_a_half_typed_command_survives_losing_focus(self, focused_bar):
        focused_bar.setText("log 1 b Rolled")

        focused_bar.clearFocus()

        assert focused_bar.text() == "log 1 b Rolled"


class TestNormalisation:
    @pytest.mark.parametrize(
        "text, expected",
        [("Rolled Oats", "rolled oats"), ("Řízek", "rizek"),
         ("CAFÉ", "cafe"), ("Müsli", "musli")],
    )
    def test_names_are_folded_to_plain_lowercase_ascii(self, text, expected):
        assert normalize(text) == expected


class TestMatchRanking:
    CATALOG = ["Rolled Oat Bar", "Rolled Oats", "Greek Yoghurt"]

    def test_a_prefix_beats_a_substring(self):
        assert best_match("rolled", self.CATALOG) == "Rolled Oats"

    def test_a_substring_beats_a_subsequence(self):
        assert best_match("yoghurt", self.CATALOG) == "Greek Yoghurt"

    def test_the_shortest_name_wins_a_tie(self):
        assert best_match("rolled oat", self.CATALOG) == "Rolled Oats"

    def test_the_answer_does_not_depend_on_catalog_order(self):
        assert best_match("oat", self.CATALOG) == best_match("oat", self.CATALOG[::-1])

    def test_a_fragment_matching_nothing_has_no_answer(self):
        assert best_match("zzzz", self.CATALOG) is None

    def test_an_appended_tail_must_reconstruct_the_catalog_name(self):
        assert "rol" + completion_tail("rol", "Rolled Oats") == "rolled Oats"
        assert completion_tail("rizek", "Řízek s bramborem") is None
