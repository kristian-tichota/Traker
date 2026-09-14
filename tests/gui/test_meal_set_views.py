import datetime

import pytest
from PyQt6.QtCore import Qt

from src.database.rows import FoodLogRow
from src.gui.commands import COMMANDS, CommandError, EVERY_CATALOG, MEAL_SET
from src.gui.components.cmd_line import CommandLineEdit
from src.gui.filtering import parse
from src.gui.models.log_table import ORPHAN_NAME_TEXT, ORPHAN_VALUE_TEXT
from src.gui.views.food_views import FoodView

pytestmark = pytest.mark.gui


def food(row_id, meal, name, meal_set=None, servings=1.0, kcal=100.0,
         grams=None, estimated=0):
    return FoodLogRow.from_server(
        [row_id, estimated, datetime.date.today().isoformat(), meal, name, servings,
         grams if grams is not None else (servings or 0) * 50.0, meal_set,
         kcal, 10.0, 20.0, 2.0, 5.0, 1.0, 0.5, 3.0])

LEDGER = [
    food(1, "Breakfast", "Rolled Oats", "Blue Oatmeal", servings=2.0, kcal=380.0),
    food(2, "Breakfast", "Blueberries", "Blue Oatmeal", servings=0.5, kcal=28.5),
    food(3, "Lunch", "Grilled Chicken", servings=1.5, kcal=330.0),
]


@pytest.fixture
def view(qapp, profile_path, recording_db, settled):
    recording_db.food_logs = list(LEDGER)
    recording_db.foods = ["Rolled Oats", "Blueberries", "Grilled Chicken"]
    recording_db.meal_sets = {
        "Blue Oatmeal": [("Rolled Oats", 100.0), ("Blueberries", 50.0)]}
    built = FoodView(recording_db)
    built.refresh()
    settled()
    yield built
    built.shutdown()
    built.deleteLater()


def column(view, header, table_idx=0):
    return view.headers[table_idx].index(header)


def shown(view, header, table_idx=0):
    proxy = view.proxy_for(table_idx)
    index = column(view, header, table_idx)
    return [proxy.index(row, index).data() for row in range(proxy.rowCount())]


class TestTheDefinitionCommand:
    def test_it_reads_a_semicolon_separated_recipe(self):
        payload = COMMANDS["mealdefine"].parse(
            "Blue Oatmeal; Rolled Oats 100; Blueberries 50")
        assert payload == {
            "name": "Blue Oatmeal",
            "components": [{"item_name": "Rolled Oats", "amount": 100.0},
                           {"item_name": "Blueberries", "amount": 50.0}]}

    def test_a_gram_suffix_is_allowed(self):
        payload = COMMANDS["mealdefine"].parse("Set; Rolled Oats 100g")
        assert payload["components"] == [{"item_name": "Rolled Oats", "amount": 100.0}]

    def test_a_food_name_may_contain_spaces(self):
        payload = COMMANDS["mealdefine"].parse("Set; Extra Mature Cheddar 30")
        assert payload["components"][0]["item_name"] == "Extra Mature Cheddar"

    @pytest.mark.parametrize("line, says", [
        ("Set; Rolled Oats", "amount in grams"),
        ("Set; Rolled Oats abc", "not an amount"),
        ("Set; Rolled Oats -5", "more than zero"),
        ("Set; Rolled Oats 0", "more than zero"),
        ("Set; Rolled Oats 1e400", "finite"),
        ("Set;", "at least one component"),
    ])
    def test_a_malformed_recipe_is_refused_with_the_reason(self, line, says):
        with pytest.raises(CommandError) as refusal:
            COMMANDS["mealdefine"].parse(line)
        assert says in str(refusal.value)

    def test_it_writes_the_food_domain(self):
        assert COMMANDS["mealdefine"].domains == ("food",)

    @pytest.mark.parametrize("typed, hint", [
        ("", " [Meal Set Name];[Food 100; Other Food 50]"),
        ("Blue Oatmeal;", " [Food 100; Other Food 50]"),
        ("Blue Oatmeal; Rolled Oats 100;", " [Food 100; Other Food 50]"),
        ("Blue Oatmeal; A 1; B 2; C 3;", " [Food 100; Other Food 50]"),
    ])
    def test_the_hint_keeps_saying_the_shape_of_an_ingredient(self, typed, hint):
        assert COMMANDS["mealdefine"].hint_for_fields(typed) == hint

    def test_a_fixed_field_definition_still_runs_out_of_fields(self):
        assert COMMANDS["mobdefine"].hint_for_fields("a;1") == " [mets];[notes]"
        assert COMMANDS["mobdefine"].hint_for_fields("a;1;note; more") == " [notes]"

    def test_the_confirmation_counts_the_ingredients(self):
        command = COMMANDS["mealdefine"]
        assert "3 components" in command.confirm(command.parse(
            "Set; A 1; B 2; C 3"))
        assert "1 component." in command.confirm(command.parse("Set; A 1"))

    def test_the_old_name_still_reaches_it(self):
        from src.gui.commands import commands_for

        assert COMMANDS["mealdefine"] is COMMANDS["mealset"]
        assert commands_for("meal")[0].name == "mealset"
        assert "mealdefine" not in [c.name for c in commands_for("meal")]


class TestLoggingTakesEither:
    def test_the_log_command_completes_from_foods_and_sets(self):
        assert COMMANDS["log"].catalogs == ("food", MEAL_SET)

    def test_removal_still_reaches_every_catalog_including_sets(self):
        assert MEAL_SET in EVERY_CATALOG
        assert COMMANDS["rm"].catalogs == EVERY_CATALOG


@pytest.mark.accessibility
class TestCompletingAnIngredient:
    @pytest.fixture
    def bar(self, qapp, profile_path, recording_db, settled):
        recording_db.foods = ["Rolled Oats", "Blueberries"]
        built = CommandLineEdit(recording_db)
        settled()
        yield built
        built.deleteLater()

    def test_a_prefix_completes_in_place(self, bar):
        bar.setText("mealdefine Blue Oatmeal; Rolled Oa")
        assert bar.completion_text == "ts"

    def test_accepting_it_keeps_the_earlier_fields(self, bar):
        bar.setText("mealdefine Blue Oatmeal; Rolled Oa")
        bar.accept_completion()
        assert bar.text() == "mealdefine Blue Oatmeal; Rolled Oats"

    def test_it_completes_the_second_ingredient_too(self, bar):
        bar.setText("mealdefine Set; Rolled Oats 100; Blueb")
        bar.accept_completion()
        assert bar.text() == "mealdefine Set; Rolled Oats 100; Blueberries"

    def test_a_replacement_keeps_the_earlier_fields(self, bar):
        bar.setText("mealdefine Set; Rolled Oats 100; blubries")
        assert bar.is_fuzzy_replacement
        bar.accept_completion()
        assert bar.text() == "mealdefine Set; Rolled Oats 100; Blueberries"

    def test_nothing_is_offered_once_an_amount_is_being_typed(self, bar):
        bar.setText("mealdefine Set; Rolled Oats 10")
        assert bar.completion_text == ""

    def test_the_set_name_field_completes_from_nothing(self, bar):
        bar.setText("mealdefine Blue Oat")
        assert bar.completion_text == ""


class TestTheLedgerHeading:
    def test_a_logged_set_is_headed(self, view):
        assert shown(view, "Food Name") == [
            "Blue Oatmeal", "Rolled Oats", "Blueberries", "Grilled Chicken"]

    def test_the_heading_totals_the_rows_under_it(self, view):
        assert shown(view, "Calories")[0] == "408.50"

    def test_it_shows_no_servings(self, view):
        assert shown(view, "Servings")[0] == ""

    def test_it_shows_no_meal_set_of_its_own(self, view):
        assert shown(view, "Meal Set")[0] == ""

    def test_the_rows_under_it_name_the_set(self, view):
        assert shown(view, "Meal Set")[1:3] == ["Blue Oatmeal", "Blue Oatmeal"]

    def test_a_food_logged_alone_names_none(self, view):
        assert shown(view, "Meal Set")[3] == ORPHAN_NAME_TEXT

    def test_the_model_knows_which_rows_are_headings(self, view):
        model = view.model_for(0)
        assert [model.is_heading(row) for row in range(model.rowCount())] == [
            True, False, False, False]

    def test_a_heading_is_not_editable(self, view):
        model = view.model_for(0)
        editable = column(view, "Servings")
        assert not (model.flags(model.index(0, editable))
                    & Qt.ItemFlag.ItemIsEditable)
        assert model.flags(model.index(1, editable)) & Qt.ItemFlag.ItemIsEditable

    def test_typing_into_a_heading_writes_nothing(self, view, recording_db):
        model = view.model_for(0)
        assert not model.setData(
            model.index(0, column(view, "Servings")), "9", Qt.ItemDataRole.EditRole)
        assert not recording_db.called("update_record")

    def test_a_heading_carries_no_id(self, view):
        model = view.model_for(0)
        assert model.row_id(model.index(0, 0)) is None


class TestSortingAndFilteringDropTheHeadings:
    def test_sorting_drops_them(self, view):
        view.sort_by(column(view, "Calories"), Qt.SortOrder.AscendingOrder)
        assert shown(view, "Food Name") == [
            "Blueberries", "Grilled Chicken", "Rolled Oats"]

    def test_the_tag_survives_the_sort(self, view):
        view.sort_by(column(view, "Calories"), Qt.SortOrder.AscendingOrder)
        assert shown(view, "Meal Set") == [
            "Blue Oatmeal", ORPHAN_NAME_TEXT, "Blue Oatmeal"]

    def test_clearing_the_sort_brings_them_back(self, view):
        view.sort_by(column(view, "Calories"), Qt.SortOrder.AscendingOrder)
        view.clear_sort()
        assert shown(view, "Food Name")[0] == "Blue Oatmeal"

    def test_filtering_drops_them(self, view):
        view.apply_filter(parse("oats", view.headers[0]))
        assert shown(view, "Food Name") == ["Rolled Oats"]

    def test_the_set_column_is_filterable_by_alias(self, view):
        view.apply_filter(parse("set:oatmeal", view.headers[0]))
        assert shown(view, "Food Name") == ["Rolled Oats", "Blueberries"]

    def test_the_matched_totals_count_rows_not_headings(self, view):
        view.apply_filter(parse("set:oatmeal", view.headers[0]))
        totals = view.matched_totals()
        assert totals.rows == 2
        assert totals.energy_kcal == pytest.approx(408.5)

    def test_clearing_the_filter_brings_them_back(self, view):
        view.apply_filter(parse("set:oatmeal", view.headers[0]))
        view.clear_filter()
        assert shown(view, "Food Name")[0] == "Blue Oatmeal"


class TestTheProgressBarsReadTheLedgerNotTheHeadings:
    def test_the_day_is_not_counted_twice(self, view):
        assert view.cal_bar.actual_value == pytest.approx(738.5)


class TestTheMealSetsPane:
    def test_it_lists_one_row_per_ingredient(self, view):
        assert shown(view, "Meal Set", 2) == ["Blue Oatmeal", "Blue Oatmeal"]
        assert shown(view, "Food Name", 2) == ["Rolled Oats", "Blueberries"]

    def test_it_shows_the_amount_in_grams(self, view):
        assert shown(view, "Grams", 2) == ["100.00", "50.00"]

    def test_its_rows_are_meal_set_components(self, view):
        assert view.tables[2] == "food_set_components"

    def test_the_amount_is_editable_and_the_set_name_is_not(self, view):
        assert view.editable_columns(2) == [
            column(view, "Food Name", 2), column(view, "Grams", 2)]

    def test_a_set_whose_ingredients_are_gone_still_shows(self, qapp, profile_path,
                                                          recording_db, settled):
        recording_db.meal_sets = {"Blue Oatmeal": []}
        built = FoodView(recording_db)
        built.refresh()
        settled()
        try:
            assert shown(built, "Meal Set", 2) == ["Blue Oatmeal"]
            assert shown(built, "Food Name", 2) == [ORPHAN_NAME_TEXT]
            assert shown(built, "Grams", 2) == [ORPHAN_VALUE_TEXT]
        finally:
            built.shutdown()
            built.deleteLater()
