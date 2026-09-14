import datetime

import pytest
from PyQt6.QtCore import QCoreApplication, QThreadPool

from src.gui.commands import COMMANDS
from src.gui.domains import TAB_DOMAINS
from src.gui.main_window import MainWindow


class FakeCommandLine:
    def __init__(self):
        self._text = ""
        self.focus_cleared = False
        self.cache_invalidations = 0

    def invalidate_catalog_cache(self):
        self.cache_invalidations += 1

    def text(self):
        return self._text

    def setText(self, value):
        self._text = value

    def clear(self):
        self._text = ""

    def clearFocus(self):
        self.focus_cleared = True


class FakeStatusBar:
    def __init__(self):
        self.message = ""

    def setText(self, value):
        self.message = value


class FakeTabs:
    def count(self):
        return len(TAB_DOMAINS)

    def currentIndex(self):
        return 0


class FakeGraphs:
    def __init__(self):
        self.dims = None

    def set_grid_dims(self, value):
        self.dims = value


class FakePulser:
    def __init__(self):
        self.colours = []

    def pulse(self, colour):
        self.colours.append(colour)


class CommandBar:
    execute_command = MainWindow.execute_command
    _invoke_command = MainWindow._invoke_command
    _on_command_finished = MainWindow._on_command_finished
    _on_command_raised = MainWindow._on_command_raised
    return_to_normal = MainWindow.return_to_normal
    _report_failure = MainWindow._report_failure
    _apply_view_effect = MainWindow._apply_view_effect
    mark_all_tabs_stale = MainWindow.mark_all_tabs_stale
    mark_domains_stale = MainWindow.mark_domains_stale
    _show_optimistically = MainWindow._show_optimistically

    def __init__(self, db):
        self.db = db
        self.command_line = FakeCommandLine()
        self.status_bar = FakeStatusBar()
        self.mode_label = FakeStatusBar()
        self.tabs = FakeTabs()
        self.status_pulser = FakePulser()
        self.dirty_tabs = set()
        self.tab_indices = {key: index for index, key in enumerate(TAB_DOMAINS)}
        self.views = {}
        self.mode = "COMMAND"
        self.refreshed_tab = None
        self._command_in_flight = False

    def submit(self, text):
        self.command_line.setText(text)
        self.execute_command()
        self.settle()
        return self

    def settle(self):
        QThreadPool.globalInstance().waitForDone(5000)
        QCoreApplication.processEvents()

    def set_mode(self, mode):
        self.mode = mode
        self.mode_label.setText(f" Mode: {mode}")

    def setFocus(self):
        self.command_line.clearFocus()

    def _refresh_visible_tab(self):
        self.refreshed_tab = self.tabs.currentIndex()


@pytest.fixture
def bar(qapp, recording_db):
    return CommandBar(recording_db)


@pytest.fixture
def today():
    return datetime.date.today().isoformat()


class TestLogCommands:
    def test_a_food_log_reads_quantity_first_and_name_last(self, bar, today):
        bar.submit("log 1.5 Breakfast Rolled Oats")

        assert bar.db.last("add_food_log") == {
            "date": today, "servings": 1.5,
            "meal_type": "Breakfast", "food_name": "Rolled Oats",
        }

    @pytest.mark.parametrize(
        "shortcut, meal",
        [("b", "Breakfast"), ("l", "Lunch"), ("d", "Dinner"), ("s", "Supplement")],
    )
    def test_meal_types_have_single_letter_shortcuts(self, bar, shortcut, meal):
        bar.submit(f"log 1 {shortcut} Rolled Oats")

        assert bar.db.last("add_food_log")["meal_type"] == meal

    def test_a_spelled_out_meal_type_is_capitalised(self, bar):
        bar.submit("log 1 breakfast Rolled Oats")

        assert bar.db.last("add_food_log")["meal_type"] == "Breakfast"

    def test_the_trailing_remainder_is_the_item_name(self, bar):
        bar.submit("log 1 b Greek Yoghurt With Honey")

        assert bar.db.last("add_food_log")["food_name"] == "Greek Yoghurt With Honey"

    def test_a_beverage_log_records_a_clock_time(self, bar, today):
        bar.submit("bevlog 1 08:30 Black Coffee")

        assert bar.db.last("add_beverage_log") == {
            "date": today, "servings": 1.0, "time": "08:30", "bev_name": "Black Coffee",
        }

    def test_an_exercise_log_pads_the_unused_set_slots(self, bar, today):
        bar.submit("exlog 7,7,7 30 8 Overhead Press")

        assert bar.db.last("add_exercise_log") == {
            "date": today, "set1": 7.0, "set2": 7.0, "set3": 7.0, "set4": 0.0, "set5": 0.0,
            "weight_kg": 30.0, "rpe": 8.0, "ex_name": "Overhead Press",
        }

    def test_a_full_five_set_scheme_is_kept(self, bar):
        bar.submit("exlog 10,9,8,7,6 40 9 Bench Press")

        payload = bar.db.last("add_exercise_log")
        assert [payload[f"set{n}"] for n in range(1, 6)] == [10.0, 9.0, 8.0, 7.0, 6.0]

    def test_a_single_set_is_accepted(self, bar):
        bar.submit("exlog 12 20 7 Overhead Press")

        payload = bar.db.last("add_exercise_log")
        assert [payload[f"set{n}"] for n in range(1, 6)] == [12.0, 0.0, 0.0, 0.0, 0.0]

    def test_a_supplement_log_reads_servings_then_name(self, bar, today):
        bar.submit("supplog 2 Morning Stack")

        assert bar.db.last("add_supplement_log") == {
            "date": today, "servings": 2.0, "supp_name": "Morning Stack",
        }

    def test_a_mobility_log_reads_minutes_then_name(self, bar, today):
        bar.submit("moblog 20 Hip Opener")

        assert bar.db.last("add_mobility_log") == {
            "date": today, "duration_mins": 20.0, "mob_name": "Hip Opener",
        }

    def test_every_log_command_dates_the_row_today(self, bar, today):
        bar.submit("log 1 b Rolled Oats")

        assert bar.db.last("add_food_log")["date"] == today


class TestServingsOrGrams:
    def test_a_bare_number_is_servings(self, bar):
        bar.submit("log 2 b Rolled Oats")

        payload = bar.db.last("add_food_log")
        assert payload["servings"] == 2.0
        assert "grams" not in payload

    def test_a_g_suffix_is_grams(self, bar):
        bar.submit("log 100g b Rolled Oats")

        payload = bar.db.last("add_food_log")
        assert payload["grams"] == 100.0
        assert "servings" not in payload, (
            "the two are alternatives; sending both is refused by the store")

    @pytest.mark.parametrize("written, grams", [("100g", 100.0), ("100G", 100.0),
                                                ("12.5g", 12.5)])
    def test_the_suffix_is_read_either_case_and_with_a_fraction(
            self, bar, written, grams):
        bar.submit(f"log {written} b Rolled Oats")

        assert bar.db.last("add_food_log")["grams"] == grams

    def test_leaving_the_amount_out_means_one_serving(self, bar):
        bar.submit("log b Rolled Oats")

        payload = bar.db.last("add_food_log")
        assert payload == {"date": payload["date"], "servings": 1.0,
                           "meal_type": "Breakfast", "food_name": "Rolled Oats"}

    def test_a_name_of_several_words_survives_an_omitted_amount(self, bar):
        bar.submit("log l Rice and beans")

        assert bar.db.last("add_food_log")["food_name"] == "Rice and beans"

    @pytest.mark.parametrize("line, says", [
        ("log 0 b Rolled Oats", "more than zero"),
        ("log -1 b Rolled Oats", "more than zero"),
        ("log 0g b Rolled Oats", "more than zero"),
        ("log 1e400 b Rolled Oats", "finite"),
    ])
    def test_an_amount_that_is_not_one_is_refused(self, bar, line, says):
        bar.submit(line)

        assert says in bar.status_bar.message
        assert bar.db.calls == [], "nothing reached the service"

    def test_a_mistyped_amount_is_reported_as_one_rather_than_shifting_along(self, bar):
        bar.submit("log x b Rolled Oats")

        assert "not a meal" in bar.status_bar.message
        assert bar.db.calls == [], "nothing reached the service"

    def test_the_confirmation_reads_back_the_unit_that_was_typed(self, bar):
        bar.submit("log 100g b Rolled Oats")
        assert "100 g of Rolled Oats" in bar.status_bar.message

        bar.submit("log 2 b Rolled Oats")
        assert "2 x Rolled Oats" in bar.status_bar.message


class TestTheArgumentsAMemberNeedNotType:
    def test_a_drink_defaults_to_one_serving_now(self, bar, today):
        bar.submit("bevlog Black Coffee")

        payload = bar.db.last("add_beverage_log")
        assert payload["servings"] == 1.0
        assert payload["bev_name"] == "Black Coffee"
        assert len(payload["time"]) == 5 and ":" in payload["time"]

    def test_the_time_defaults_to_now_rather_than_to_a_fixed_hour(self, bar):
        import datetime as _datetime

        bar.submit("bevlog Black Coffee")

        assert bar.db.last("add_beverage_log")["time"] == (
            _datetime.datetime.now().strftime("%H:%M"))

    def test_a_count_alone_still_reads_as_a_count(self, bar):
        bar.submit("bevlog 2 Black Coffee")

        assert bar.db.last("add_beverage_log")["servings"] == 2.0

    def test_a_time_alone_still_reads_as_a_time(self, bar):
        bar.submit("bevlog 14:30 Black Coffee")

        payload = bar.db.last("add_beverage_log")
        assert (payload["servings"], payload["time"]) == (1.0, "14:30")

    def test_both_together_read_in_order(self, bar):
        bar.submit("bevlog 2 14:30 Black Coffee")

        payload = bar.db.last("add_beverage_log")
        assert (payload["servings"], payload["time"]) == (2.0, "14:30")

    def test_a_malformed_time_is_reported_rather_than_taken_for_a_name(self, bar):
        bar.submit("bevlog 25:99 Black Coffee")

        assert "24-hour time" in bar.status_bar.message
        assert bar.db.calls == [], "nothing reached the service"

    def test_a_supplement_stack_defaults_to_one(self, bar):
        bar.submit("supplog Morning")

        payload = bar.db.last("add_supplement_log")
        assert (payload["servings"], payload["supp_name"]) == (1.0, "Morning")


class TestAnEstimateForAMealNobodyHasALabelFor:
    def test_it_reads_calories_then_the_meal_then_what_it_was(self, bar, today):
        bar.submit("quick 550 d Restaurant Pizza")

        assert bar.db.last("add_quick_food_log") == {
            "date": today, "energy_kcal": 550.0, "meal_type": "Dinner",
            "food_name": "Restaurant Pizza",
        }

    def test_the_description_may_be_several_words(self, bar):
        bar.submit("quick 800 l Someone's Birthday Cake")

        assert bar.db.last("add_quick_food_log")["food_name"] == (
            "Someone's Birthday Cake")

    def test_the_confirmation_says_the_day_now_reads_as_estimated(self, bar):
        bar.submit("quick 550 d Restaurant Pizza")

        said = bar.status_bar.message
        assert "estimate of 550 kcal" in said
        assert "estimated" in said

    def test_it_writes_the_food_domain(self, bar):
        assert COMMANDS["quick"].domains == ("food",)

    def test_its_row_is_shown_as_an_estimate_at_once(self):
        command = COMMANDS["quick"]
        row = command.pending_row(command.parse("550 d Restaurant Pizza"))

        assert row[1] is True


class TestDefineCommands:
    def test_a_food_definition_reads_semicolon_separated_fields_positionally(self, bar):
        bar.submit("define Rolled Oats;Carbs;380;7;1.2;60;1;10;13;0;50")

        assert bar.db.last("add_food_item") == {
            "name": "Rolled Oats", "category": "Carbs", "energy": 380.0,
            "fat_total": 7.0, "fat_saturated": 1.2, "carbs_total": 60.0,
            "carbs_sugars": 1.0, "fibre": 10.0, "protein": 13.0,
            "salt": 0.0, "serving_size": 50.0,
        }

    def test_a_beverage_definition(self, bar):
        bar.submit("bevdefine Black Coffee;80;200")

        assert bar.db.last("add_beverage_item") == {
            "name": "Black Coffee", "caffeine_mg": 80.0, "antioxidants_mg": 200.0,
        }

    def test_an_exercise_definition(self, bar):
        bar.submit("exdefine Overhead Press;Shoulders;Push;Triceps;Frontal;Compound;Dumbbell;Bilateral;Reps")

        payload = bar.db.last("add_exercise_item")
        assert payload["name"] == "Overhead Press"
        assert payload["muscle_group"] == "Shoulders"
        assert payload["metric_type"] == "Reps"

    def test_a_mobility_definition(self, bar):
        bar.submit("mobdefine Hip Opener;3.0;Daily before training")

        assert bar.db.last("add_mobility_item") == {
            "name": "Hip Opener", "mets": 3.0, "notes": "Daily before training",
        }

    def test_a_supplement_definition_needs_all_thirteen_fields(self, bar):
        bar.submit("suppdefine Morning Stack;500;150;5;4000;100;500;500;800;400;15;500;200")

        payload = bar.db.last("add_supplement_item")
        assert payload["name"] == "Morning Stack"
        assert payload["b12_mcg"] == 500.0
        assert payload["l_theanine_mg"] == 200.0

    def test_surrounding_whitespace_is_trimmed_from_names(self, bar):
        bar.submit("mobdefine   Hip Opener  ;3.0;  notes  ")

        assert bar.db.last("add_mobility_item")["name"] == "Hip Opener"


class TestRejectedInput:
    @pytest.mark.parametrize(
        "text",
        ["log", "log 1", "log 1 Breakfast",
         "bevlog 1", "exlog 7,7,7 30", "supplog 1", "moblog", "rm",
         "track 1", "graphlayout"],
    )
    def test_a_log_command_missing_arguments_writes_nothing(self, bar, text):
        bar.submit(text)

        assert bar.db.calls == []
        assert "Execution Fail" in bar.status_bar.message

    @pytest.mark.parametrize(
        "text",
        ["define", "bevdefine", "exdefine", "suppdefine", "mobdefine",
         "define only;two", "suppdefine Stack;1;2;3"],
    )
    def test_a_definition_missing_fields_writes_nothing(self, bar, text):
        bar.submit(text)

        assert bar.db.calls == []
        assert bar.status_bar.message.startswith(" Execution Fail")

    def test_an_unknown_word_is_reported_as_an_unknown_command(self, bar):
        bar.submit("frobnicate 1 2 3")

        assert "Unknown command" in bar.status_bar.message
        assert bar.db.calls == []

    def test_a_non_numeric_quantity_is_rejected(self, bar):
        bar.submit("log lots b Rolled Oats")

        assert bar.db.calls == []
        assert "Execution Fail" in bar.status_bar.message

    def test_a_rejected_command_stays_in_the_bar_for_correction(self, bar):
        bar.submit("log 1 Breakfast")

        assert bar.command_line.text() == "log 1 Breakfast"

    def test_a_rejected_command_pulses_a_warning(self, bar):
        bar.submit("frobnicate")

        assert bar.status_pulser.colours == ["#dc322f"]

    def test_a_rejected_command_leaves_the_tabs_alone(self, bar):
        bar.submit("frobnicate")

        assert bar.dirty_tabs == set()

    def test_a_server_refusal_is_surfaced_verbatim(self, bar):
        bar.db.result = (False, "Food 'Ghost Oats' not found in catalog.")

        bar.submit("log 1 b Ghost Oats")

        assert "not found in catalog" in bar.status_bar.message
        assert bar.command_line.text() == "log 1 b Ghost Oats"

    def test_an_empty_bar_simply_returns_to_normal_mode(self, bar):
        bar.submit("   ")

        assert bar.mode == "NORMAL"
        assert bar.db.calls == []
        assert "Execution Fail" not in bar.status_bar.message

    def test_a_definition_missing_fields_is_answered_with_the_syntax(self, bar):
        bar.submit("define Rolled Oats;Carbs")

        assert COMMANDS["define"].usage in bar.status_bar.message

    def test_a_definition_with_too_many_fields_is_refused(self, bar):
        bar.submit("bevdefine Black Coffee;80;200;7")

        assert bar.db.calls == []
        assert "Execution Fail" in bar.status_bar.message

    def test_a_bad_value_names_the_argument_it_belongs_to(self, bar):
        bar.submit("exlog 7,7,7 heavy 8 Bench Press")

        assert "[weight]" in bar.status_bar.message
        assert bar.db.calls == []

    def test_more_than_five_sets_is_refused_rather_than_truncated(self, bar):
        bar.submit("exlog 5,5,5,5,5,5 40 8 Bench Press")

        assert bar.db.calls == []
        assert "five sets" in bar.status_bar.message

    def test_a_slot_outside_the_grid_is_refused(self, bar):
        bar.submit("track 47 Overhead Press")

        assert bar.db.calls == []
        assert "between 1 and 9" in bar.status_bar.message


class TestTheBarDoesNotBlockTheInterface:
    def test_the_write_runs_off_the_interface_thread(self, bar, recording_db):
        import threading

        on_main = []
        original = recording_db.add_food_log

        def watched(payload):
            on_main.append(threading.current_thread() is threading.main_thread())
            return original(payload)

        recording_db.add_food_log = watched

        bar.submit("log 1 b Rolled Oats")

        assert on_main == [False]

    def test_a_second_enter_before_the_first_answers_writes_once(self, bar):
        bar.command_line.setText("log 1 b Rolled Oats")
        bar.execute_command()
        bar.execute_command()
        bar.settle()

        assert [name for name, _ in bar.db.calls] == ["add_food_log"]

    def test_the_bar_accepts_a_command_again_once_the_first_has_landed(self, bar):
        bar.submit("log 1 b Rolled Oats")

        bar.submit("log 2 b Greek Yoghurt")

        assert len([name for name, _ in bar.db.calls if name == "add_food_log"]) == 2

    def test_a_refusal_releases_the_bar_too(self, bar):
        bar.db.result = (False, "the service said no")
        bar.submit("log 1 b Rolled Oats")

        bar.db.result = (True, "Success")
        bar.submit("log 1 b Rolled Oats")

        assert len([name for name, _ in bar.db.calls if name == "add_food_log"]) == 2


class TestSuccessfulOutcome:
    def test_the_bar_clears_and_returns_to_normal_mode(self, bar):
        bar.submit("log 1 b Rolled Oats")

        assert bar.command_line.text() == ""
        assert bar.command_line.focus_cleared is True
        assert bar.mode == "NORMAL"

    def test_only_the_tabs_reading_what_changed_are_marked_stale(self, bar):
        bar.submit("log 1 b Rolled Oats")

        stale = {key for key, index in bar.tab_indices.items()
                 if index in bar.dirty_tabs}
        assert stale == {"food", "food_graphs"}
        assert bar.refreshed_tab == 0

    def test_a_food_log_leaves_the_unrelated_tabs_alone(self, bar):
        bar.submit("log 1 b Rolled Oats")

        untouched = {"exercise", "supplements", "mobility", "beverages",
                     "pomodoro", "caffeine_graph", "supplement_graphs"}
        stale = {key for key, index in bar.tab_indices.items()
                 if index in bar.dirty_tabs}
        assert not (stale & untouched)

    def test_a_tab_deriving_from_two_subjects_is_marked_by_either(self, bar):
        bar.submit("exlog 7,7,7 40 8 Overhead Press")

        stale = {key for key, index in bar.tab_indices.items()
                 if index in bar.dirty_tabs}
        assert stale == {"exercise", "exercise_graphs", "heatmap", "food", "plans"}

    def test_a_catalog_definition_dirties_that_subjects_log_tabs_too(self, bar):
        bar.submit("define Oats;Carbs;380;7;1.2;60;1;10;13;0;50")

        stale = {key for key, index in bar.tab_indices.items()
                 if index in bar.dirty_tabs}
        assert "food" in stale

    def test_removing_an_item_may_have_touched_any_catalog(self, bar):
        bar.submit("rm Rolled Oats")

        assert bar.dirty_tabs == set(range(bar.tabs.count()))

    def test_a_chart_preference_dirties_nothing(self, bar):
        bar.submit("graphlayout 3x3")

        assert bar.dirty_tabs == set()

    def test_the_status_bar_pulses_to_acknowledge_the_write(self, bar):
        bar.submit("log 1 b Rolled Oats")

        assert bar.status_pulser.colours == ["#268bd2"]


class TestCatalogRemoval:
    def test_removal_takes_the_whole_trailing_name(self, bar):
        bar.submit("rm Greek Yoghurt With Honey")

        assert bar.db.last("delete_item_by_name") == "Greek Yoghurt With Honey"

    def test_a_successful_removal_names_the_item(self, bar):
        bar.submit("rm Rolled Oats")

        assert "Rolled Oats" in bar.status_bar.message

    def test_a_refused_removal_is_reported(self, bar):
        bar.db.result = (False, "server said no")

        bar.submit("rm Rolled Oats")

        assert "server said no" in bar.status_bar.message


class TestViewCommands:
    def test_tracking_pins_an_exercise_to_a_graph_slot(self, bar):
        bar.submit("track 3 Overhead Press")

        assert bar.db.last("set_setting") == ("ex_graph_slot_3", "Overhead Press")
        assert "slot 3" in bar.status_bar.message

    def test_a_layout_choice_is_persisted(self, bar):
        bar.submit("graphlayout 3x3")

        assert bar.db.last("set_setting") == ("ex_graph_layout_dims", "3x3")
        assert "3x3" in bar.status_bar.message

    @pytest.mark.parametrize("layout", ["2x2", "2x3", "3x3"])
    def test_the_supported_layouts_are_accepted(self, bar, layout):
        bar.submit(f"graphlayout {layout}")

        assert "Execution Fail" not in bar.status_bar.message

    def test_an_unsupported_layout_is_refused(self, bar):
        bar.submit("graphlayout 9x9")

        assert "Supported layouts" in bar.status_bar.message
        assert bar.db.calls == []


class TestStressOverrideCommand:
    def test_a_date_is_taken_in_the_readable_format_and_stored_as_iso(self, bar):
        bar.submit("setdsi 05.09.2026 0.8")

        assert bar.db.last("set_pomodoro_dsi_override") == {
            "date": "2026-09-05", "override_dsi": 0.8,
        }

    def test_an_iso_date_is_refused_with_the_expected_format(self, bar):
        bar.submit("setdsi 2026-09-05 0.8")

        assert "DD.MM.YYYY" in bar.status_bar.message
        assert bar.db.calls == []

    def test_a_non_numeric_value_is_refused(self, bar):
        bar.submit("setdsi 05.09.2026 lots")

        assert "must be a number" in bar.status_bar.message

    @pytest.mark.parametrize("word", ["clear", "rm", "delete"])
    def test_the_override_can_be_cleared(self, bar, word):
        bar.submit(f"setdsi 05.09.2026 {word}")

        assert bar.db.last("clear_pomodoro_dsi_override") == "2026-09-05"
        assert "Removed visual DSI override" in bar.status_bar.message

    def test_a_refused_override_is_reported(self, bar):
        bar.db.result = (False, "server said no")

        bar.submit("setdsi 05.09.2026 0.8")

        assert "server said no" in bar.status_bar.message


class TestChoreCommands:
    def test_a_chore_is_ticked_off_today(self, bar):
        bar.submit("chore Vacuum the flat")

        assert bar.db.last("complete_chore") == {
            "name": "Vacuum the flat", "date": datetime.date.today().isoformat(),
        }

    def test_done_reaches_the_same_command(self, bar):
        bar.submit("done Bins")

        assert bar.db.last("complete_chore")["name"] == "Bins"

    def test_a_cadence_in_days_is_stored_as_days(self, bar):
        bar.submit("chorenew 7 11.09.2026 Vacuum")

        assert bar.db.last("add_chore")["period_days"] == 7

    @pytest.mark.parametrize("typed,days", [
        ("2w", 14), ("4w", 28), ("1w", 7), ("2W", 14),
    ])
    def test_weeks_reach_the_store_as_days(self, bar, typed, days):
        bar.submit(f"chorenew {typed} 11.09.2026 Vacuum")

        assert bar.db.last("add_chore")["period_days"] == days

    def test_the_confirmation_names_the_day_it_will_keep(self, bar):
        bar.submit("chorenew 2w 11.09.2026 Vacuum")

        assert "always a Fri" in bar.status_bar.message

    def test_a_cadence_that_is_not_whole_weeks_says_the_day_drifts(self, bar):
        bar.submit("chorenew 30 11.09.2026 Descale")

        assert "the day drifts" in bar.status_bar.message

    def test_a_sub_weekly_chore_says_nothing_about_a_day_it_never_had(self, bar):
        bar.submit("chorenew 3 Water the plants")

        assert "drift" not in bar.status_bar.message

    def test_the_confirmation_names_the_grace_it_derived(self, bar):
        bar.submit("chorenew 7 11.09.2026 Vacuum")

        assert "2 days' grace" in bar.status_bar.message

    def test_an_omitted_anchor_means_today(self, bar):
        bar.submit("chorenew 7 Vacuum the flat")

        assert bar.db.last("add_chore")["anchor"] == datetime.date.today().isoformat()

    def test_a_name_of_several_words_needs_no_quoting(self, bar):
        bar.submit("chorenew 2w Change the bed linen")

        assert bar.db.last("add_chore")["name"] == "Change the bed linen"

    def test_a_grace_may_be_pinned_between_the_date_and_the_name(self, bar):
        bar.submit("chorenew 7 11.09.2026 1 Vacuum")

        written = bar.db.last("add_chore")
        assert (written["grace_days"], written["name"]) == (1, "Vacuum")

    def test_an_unpinned_grace_is_left_for_the_client_to_derive(self, bar):
        bar.submit("chorenew 7 11.09.2026 Vacuum")

        assert bar.db.last("add_chore")["grace_days"] is None

    def test_a_name_beginning_with_a_digit_is_not_eaten_as_a_grace(self, bar):
        bar.submit("chorenew 7 2nd bathroom")

        assert bar.db.last("add_chore")["name"] == "2nd bathroom"

    @pytest.mark.parametrize("typed", ["chorenew 0 Vacuum", "chorenew 0w Vacuum"])
    def test_a_cadence_of_less_than_a_day_is_refused(self, bar, typed):
        bar.submit(typed)

        assert "at least one day" in bar.status_bar.message
        assert bar.db.calls == []

    def test_a_chore_with_no_cadence_is_refused_with_the_syntax(self, bar):
        bar.submit("chorenew Vacuum")

        assert "Syntax: chorenew" in bar.status_bar.message
        assert bar.db.calls == []

    def test_a_refused_tick_is_reported(self, bar):
        bar.db.result = (False, "There is no chore called 'Hoover'.")

        bar.submit("chore Hoover")

        assert "Hoover" in bar.status_bar.message


class TestReportedFailures:
    def test_a_refused_beverage_log_is_reported(self, bar):
        bar.db.result = (False, "Beverage 'Ghost Coffee' not found in catalog.")

        bar.submit("bevlog 1 08:30 Ghost Coffee")

        assert "not found" in bar.status_bar.message

    def test_a_duplicate_definition_is_reported(self, bar):
        bar.db.result = (False, "UNIQUE constraint failed: food_items.name")

        bar.submit("define Rolled Oats;Carbs;380;7;1.2;60;1;10;13;0;50")

        assert "UNIQUE" in bar.status_bar.message

    @pytest.mark.parametrize(
        "text",
        ["log 1 b Rolled Oats", "bevlog 1 08:30 Black Coffee",
         "exlog 7,7,7 30 8 Bench Press", "supplog 1 Morning Stack",
         "moblog 20 Hip Opener", "define A;B;1;2;3;4;5;6;7;8;9",
         "bevdefine A;1;2", "exdefine A;B;C;D;E;F;G;H;Reps",
         "suppdefine A;1;2;3;4;5;6;7;8;9;10;11;12", "mobdefine A;3;notes",
         "rm Rolled Oats", "track 1 Plank", "graphlayout 3x3",
         "setdsi 05.09.2026 0.8"],
    )
    def test_every_command_surfaces_a_refusal(self, bar, text):
        bar.db.result = (False, "the service said no")

        bar.submit(text)

        assert "the service said no" in bar.status_bar.message
        assert bar.command_line.text() == text

    def test_a_refused_command_never_claims_success(self, bar):
        bar.db.result = (False, "the service said no")

        bar.submit("supplog 1 Morning Stack")

        assert bar.status_pulser.colours == ["#dc322f"]
        assert bar.dirty_tabs == set()


class TestConfirmation:
    @pytest.mark.parametrize(
        "text, expected",
        [("log 1.5 b Rolled Oats", "Rolled Oats"),
         ("supplog 1 Morning Stack", "Morning Stack"),
         ("moblog 20 Hip Opener", "Hip Opener"),
         ("define Oats;Carbs;380;7;1.2;60;1;10;13;0;50", "Oats"),
         ("rm Rolled Oats", "Rolled Oats"),
         ("track 3 Plank", "slot 3"),
         ("graphlayout 3x3", "3x3"),
         ("setdsi 05.09.2026 0.8", "0.80")],
    )
    def test_a_successful_command_names_what_it_wrote(self, bar, text, expected):
        bar.submit(text)

        assert expected in bar.status_bar.message
        assert "Mode: NORMAL" not in bar.status_bar.message

    def test_a_whole_serving_reads_without_a_decimal_point(self, bar):
        bar.submit("log 1 b Rolled Oats")

        assert "1 x Rolled Oats" in bar.status_bar.message

    def test_a_layout_change_is_mirrored_by_the_graph_tab(self, bar):
        bar.views["exercise_graphs"] = FakeGraphs()

        bar.submit("graphlayout 2x3")

        assert bar.views["exercise_graphs"].dims == "2x3"

    def test_the_view_effect_goes_through_the_view_not_its_widget(self, bar):
        bar.views["exercise_graphs"] = FakeGraphs()

        bar.submit("graphlayout 2x3")

        assert [call for call in bar.db.calls if call[0] == "set_setting"] == [
            ("set_setting", ("ex_graph_layout_dims", "2x3"))
        ], "the layout is stored once, by the command, and not again by a widget"

    def test_a_layout_change_survives_the_graph_tab_being_switched_off(self, bar):
        bar.submit("graphlayout 2x3")

        assert bar.db.last("set_setting") == ("ex_graph_layout_dims", "2x3")
