import pytest

from src.database.rows import (BeverageLogRow, DailyTotals, ExerciseLogRow,
                               FoodLogRow, MatchedTotals, MobilityLogRow,
                               SupplementLogRow, grouped_by_set, heading_over,
                               heading_type, total)


def food(row_id, date, meal, name, meal_set=None, servings=1.0, kcal=100.0,
         protein=10.0, grams=None, estimated=0):
    return FoodLogRow.from_server(
        [row_id, estimated, date, meal, name, servings,
         grams if grams is not None else 50.0, meal_set, kcal, protein,
         20.0, 2.0, 5.0, 1.0, 0.5, 3.0])


def is_heading(row):
    return getattr(row, "is_heading", False)


class TestRowsLoggedOnTheirOwn:
    def test_they_pass_through_untouched(self):
        rows = [food(1, "2026-09-07", "Lunch", "Chicken"),
                food(2, "2026-09-07", "Dinner", "Rice")]
        assert grouped_by_set(rows) == rows

    def test_an_empty_ledger_stays_empty(self):
        assert grouped_by_set([]) == []

    def test_an_orphaned_row_is_not_a_group(self):
        rows = [food(1, "2026-09-07", "Lunch", None)]
        assert grouped_by_set(rows) == rows


class TestAHeadingOverEachLoggedSet:
    @pytest.fixture
    def grouped(self):
        return grouped_by_set([
            food(1, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal", kcal=380.0,
                 grams=100.0),
            food(2, "2026-09-07", "Breakfast", "Blueberries", "Blue Oatmeal",
                 kcal=29.0, grams=50.0),
            food(3, "2026-09-07", "Lunch", "Chicken"),
        ])

    def test_the_heading_comes_first_in_its_group(self, grouped):
        assert is_heading(grouped[0])
        assert [row.name for row in grouped] == [
            "Blue Oatmeal", "Oats", "Blueberries", "Chicken"]

    def test_it_names_the_set_in_the_food_column(self, grouped):
        assert grouped[0].name == "Blue Oatmeal"

    def test_it_carries_the_date_and_meal_of_its_rows(self, grouped):
        assert (grouped[0].date, grouped[0].meal_type) == ("2026-09-07", "Breakfast")

    def test_it_totals_the_nutrients_under_it(self, grouped):
        assert grouped[0].energy_kcal == pytest.approx(409.0)
        assert grouped[0].protein_g == pytest.approx(20.0)

    def test_it_totals_the_grams_under_it(self, grouped):
        assert grouped[0].grams == pytest.approx(150.0)

    def test_it_reports_no_servings_of_its_own(self, grouped):
        assert grouped[0].servings is None

    def test_it_carries_no_meal_set_of_its_own(self, grouped):
        assert grouped[0].meal_set is None

    def test_it_claims_nothing_about_being_an_estimate(self, grouped):
        assert grouped[0].estimated is None

    def test_it_has_no_id(self, grouped):
        assert grouped[0].id is None

    def test_it_says_it_is_a_heading(self, grouped):
        assert grouped[0].is_heading is True

    def test_an_ordinary_row_does_not(self, grouped):
        assert getattr(grouped[1], "is_heading", False) is False

    def test_it_is_still_the_shape_of_the_rows_it_heads(self, grouped):
        assert isinstance(grouped[0], FoodLogRow)
        assert grouped[0]._fields == FoodLogRow._fields


class TestWhatCountsAsOneMeal:
    def test_the_same_set_at_two_meals_is_two_groups(self):
        grouped = grouped_by_set([
            food(1, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal"),
            food(2, "2026-09-07", "Dinner", "Oats", "Blue Oatmeal"),
        ])
        assert sum(is_heading(row) for row in grouped) == 2

    def test_the_same_set_on_two_days_is_two_groups(self):
        grouped = grouped_by_set([
            food(1, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal"),
            food(2, "2026-09-06", "Breakfast", "Oats", "Blue Oatmeal"),
        ])
        assert sum(is_heading(row) for row in grouped) == 2

    def test_two_sets_at_one_meal_are_two_groups(self):
        grouped = grouped_by_set([
            food(1, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal"),
            food(2, "2026-09-07", "Breakfast", "Egg", "Fry Up"),
        ])
        assert [row.name for row in grouped] == [
            "Blue Oatmeal", "Oats", "Fry Up", "Egg"]

    def test_logging_one_set_twice_at_one_meal_reads_as_one_meal(self):
        grouped = grouped_by_set([
            food(1, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal", kcal=380.0),
            food(2, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal", kcal=380.0),
        ])
        headings = [row for row in grouped if is_heading(row)]
        assert len(headings) == 1
        assert headings[0].energy_kcal == pytest.approx(760.0)

    def test_a_group_broken_by_another_row_keeps_one_heading(self):
        grouped = grouped_by_set([
            food(1, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal"),
            food(2, "2026-09-07", "Breakfast", "Toast"),
            food(3, "2026-09-07", "Breakfast", "Blueberries", "Blue Oatmeal"),
        ])
        assert [row.name for row in grouped] == [
            "Blue Oatmeal", "Oats", "Toast", "Blueberries"]


class TestTheHeadingUsesTheOneSummation:
    def test_it_agrees_with_the_days_totals_on_the_same_rows(self):
        rows = [food(1, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal", kcal=380.0),
                food(2, "2026-09-07", "Breakfast", "Blueberries", "Blue Oatmeal", kcal=29.0)]
        heading = heading_over(rows)
        day = DailyTotals.of("2026-09-07", rows)

        assert heading.energy_kcal == pytest.approx(day.energy_kcal)
        assert heading.protein_g == pytest.approx(day.protein_g)
        assert heading.energy_kcal == pytest.approx(total(rows, "energy_kcal"))

    def test_an_orphan_in_the_group_counts_as_zero_rather_than_raising(self):
        rows = [food(1, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal", kcal=380.0),
                FoodLogRow.from_server(
                    [2, 0, "2026-09-07", "Breakfast", None, 1.0, None,
                     "Blue Oatmeal", *([None] * 8)])]
        assert heading_over(rows).energy_kcal == pytest.approx(380.0)


class TestTheMatchedSetDoesNotCountAHeadingTwice:
    def test_headings_are_left_out_of_the_totals(self):
        rows = [food(1, "2026-09-07", "Breakfast", "Oats", "Blue Oatmeal", kcal=380.0),
                food(2, "2026-09-07", "Breakfast", "Blueberries", "Blue Oatmeal", kcal=29.0)]
        with_heading = grouped_by_set(rows)

        assert MatchedTotals.of(with_heading) == MatchedTotals.of(rows)
        assert MatchedTotals.of(with_heading).rows == 2


class TestOneMechanismForEveryDomain:
    def test_a_logged_stack_is_headed_and_its_doses_totalled(self):
        rows = [SupplementLogRow.from_server(
                    [1, "2026-09-07", "B12", "Morning", 1.0, 500.0, *([0.0] * 11)]),
                SupplementLogRow.from_server(
                    [2, "2026-09-07", "Creatine", "Morning", 1.0, 0.0, 0.0, 5.0,
                     *([0.0] * 9)])]
        grouped = grouped_by_set(rows)

        assert [row.name for row in grouped] == ["Morning", "B12", "Creatine"]
        assert grouped[0].b12_mcg == pytest.approx(500.0)
        assert grouped[0].creatine_g == pytest.approx(5.0)
        assert grouped[0].servings is None

    def test_a_drink_set_groups_by_the_time_it_was_drunk(self):
        rows = [BeverageLogRow.from_server(
                    [1, "2026-09-07", "07:30", "Coffee", "Wake Up", 1.0, 200.0, 80.0], ""),
                BeverageLogRow.from_server(
                    [2, "2026-09-07", "07:30", "Water", "Wake Up", 1.0, 0.0, 0.0], ""),
                BeverageLogRow.from_server(
                    [3, "2026-09-07", "15:00", "Coffee", "Wake Up", 1.0, 200.0, 80.0], "")]
        grouped = grouped_by_set(rows)

        assert sum(is_heading(row) for row in grouped) == 2
        assert grouped[0].caffeine_mg == pytest.approx(80.0)

    def test_a_routine_set_totals_its_minutes_and_not_its_intensity(self):
        rows = [MobilityLogRow.from_server([1, "2026-09-07", "Hips", "Evening", 10.0, 3.0]),
                MobilityLogRow.from_server([2, "2026-09-07", "Spine", "Evening", 5.0, 2.5])]
        heading = grouped_by_set(rows)[0]

        assert heading.duration_mins == pytest.approx(15.0)
        assert heading.mets is None

    def test_a_workout_totals_its_volume_and_not_its_loads(self):
        rows = [ExerciseLogRow.from_server(
                    [1, "2026-09-07", "Bench", "Push Day", 8, 8, 6, 0, 0, 60.0, 8.0,
                     "Chest", "Reps"]),
                ExerciseLogRow.from_server(
                    [2, "2026-09-07", "Press", "Push Day", 8, 8, 0, 0, 0, 30.0, 7.0,
                     "Shoulders", "Reps"])]
        heading = grouped_by_set(rows)[0]

        assert heading.name == "Push Day"
        assert heading.volume == pytest.approx(total(rows, "volume"))
        assert (heading.weight_kg, heading.rpe, heading.total_reps) == (None, None, None)

    def test_a_heading_type_is_made_once_per_row_type(self):
        assert heading_type(FoodLogRow) is heading_type(FoodLogRow)
        assert heading_type(FoodLogRow) is not heading_type(SupplementLogRow)
