import pytest

BREAKFAST = {"date": "2026-09-05", "meal_type": "Breakfast",
             "food_name": "Rolled Oats", "servings": 1.0}
COFFEE = {"date": "2026-09-05", "time": "08:30", "bev_name": "Black Coffee", "servings": 1.0}
PRESS = {"date": "2026-09-05", "ex_name": "Overhead Press",
         "set1": 7, "set2": 7, "set3": 7, "set4": 0, "set5": 0,
         "weight_kg": 30.0, "rpe": 8.0}

FOOD_COLUMNS = ["id", "estimated", "date", "meal_type", "name", "servings",
                "grams", "meal_set", "cal", "prot", "carb", "sugar", "fat",
                "sat_fat", "salt", "fibre"]
BEVERAGE_COLUMNS = ["id", "date", "time", "name", "drink_set", "servings",
                    "antioxidants", "caffeine"]
EXERCISE_COLUMNS = ["id", "date", "name", "workout", "set1", "set2", "set3",
                    "set4", "set5", "weight_kg", "rpe", "muscle_group",
                    "metric_type"]
MOBILITY_COLUMNS = ["id", "date", "name", "routine_set", "duration_mins", "mets"]
SUPPLEMENT_COLUMNS = ["id", "date", "name", "stack", "servings", "b12", "iodine",
                      "creatine", "d3", "k2", "dha", "epa", "calcium",
                      "magnesium", "zinc", "c", "l_theanine"]


class TestFoodLogShape:
    @pytest.fixture
    def row(self, seeded_catalog, member_a):
        member_a.post("/api/logs/food", json=dict(BREAKFAST, servings=2.0))
        (row,) = member_a.get("/api/logs/food").get_json()
        return row

    def test_column_count_and_order(self, row):
        assert len(row) == len(FOOD_COLUMNS)
        assert row[FOOD_COLUMNS.index("date")] == "2026-09-05"
        assert row[FOOD_COLUMNS.index("meal_type")] == "Breakfast"
        assert row[FOOD_COLUMNS.index("name")] == "Rolled Oats"
        assert row[FOOD_COLUMNS.index("servings")] == 2.0

    @pytest.mark.exact
    @pytest.mark.parametrize(
        "column, per_hundred_grams",
        [("cal", 380.0), ("prot", 13.0), ("carb", 60.0), ("sugar", 1.0),
         ("fat", 7.0), ("sat_fat", 1.2), ("salt", 0.0), ("fibre", 10.0)],
    )
    def test_every_nutrient_scales_by_serving_size_and_servings(self, row, column, per_hundred_grams):
        expected = per_hundred_grams * (50.0 / 100.0) * 2.0
        assert row[FOOD_COLUMNS.index(column)] == pytest.approx(expected)

    def test_correcting_the_catalog_corrects_history(self, seeded_catalog, member_a):
        member_a.post("/api/logs/food", json=BREAKFAST)
        (item,) = member_a.get("/api/catalog/food").get_json()

        member_a.patch(f"/api/logs/food_items/{item['id']}", json={"col": "energy", "val": "500"})

        (row,) = member_a.get("/api/logs/food").get_json()
        assert row[FOOD_COLUMNS.index("cal")] == pytest.approx(500.0 * 0.5)

    def test_rows_are_newest_first(self, seeded_catalog, member_a):
        for date in ("2026-09-01", "2026-09-05", "2026-09-03"):
            member_a.post("/api/logs/food", json=dict(BREAKFAST, date=date))

        dates = [row[FOOD_COLUMNS.index("date")] for row in member_a.get("/api/logs/food").get_json()]
        assert dates == ["2026-09-05", "2026-09-03", "2026-09-01"]

    def test_an_item_is_found_regardless_of_capitalisation(self, seeded_catalog, member_a):
        response = member_a.post("/api/logs/food", json=dict(BREAKFAST, food_name="rolled oats"))

        assert response.status_code == 200
        (row,) = member_a.get("/api/logs/food").get_json()
        assert row[FOOD_COLUMNS.index("name")] == "Rolled Oats"


class TestBeverageLogShape:
    @pytest.fixture
    def row(self, seeded_catalog, member_a):
        member_a.post("/api/logs/beverage", json=dict(COFFEE, servings=2.0))
        (row,) = member_a.get("/api/logs/beverage").get_json()
        return row

    def test_column_count_and_order(self, row):
        assert len(row) == len(BEVERAGE_COLUMNS)
        assert row[BEVERAGE_COLUMNS.index("time")] == "08:30"
        assert row[BEVERAGE_COLUMNS.index("name")] == "Black Coffee"

    @pytest.mark.exact
    def test_caffeine_and_antioxidants_scale_with_servings(self, row):
        assert row[BEVERAGE_COLUMNS.index("caffeine")] == pytest.approx(160.0)
        assert row[BEVERAGE_COLUMNS.index("antioxidants")] == pytest.approx(400.0)

    def test_rows_are_ordered_by_date_then_time(self, seeded_catalog, member_a):
        for time in ("08:30", "14:00", "06:15"):
            member_a.post("/api/logs/beverage", json=dict(COFFEE, time=time))

        times = [row[BEVERAGE_COLUMNS.index("time")]
                 for row in member_a.get("/api/logs/beverage").get_json()]
        assert times == ["14:00", "08:30", "06:15"]


class TestExerciseLogShape:
    @pytest.fixture
    def row(self, seeded_catalog, member_a):
        member_a.post("/api/logs/exercise", json=PRESS)
        (row,) = member_a.get("/api/logs/exercise").get_json()
        return row

    def test_column_count_and_order(self, row):
        assert len(row) == len(EXERCISE_COLUMNS)
        assert row[EXERCISE_COLUMNS.index("name")] == "Overhead Press"
        assert row[EXERCISE_COLUMNS.index("weight_kg")] == 30.0
        assert row[EXERCISE_COLUMNS.index("rpe")] == 8.0

    def test_unused_set_slots_are_recorded_as_zero(self, row):
        sets = [row[EXERCISE_COLUMNS.index(f"set{n}")] for n in range(1, 6)]
        assert sets == [7, 7, 7, 0, 0]

    def test_the_kinesiology_metadata_rides_along_for_the_client_maths(self, row):
        assert row[EXERCISE_COLUMNS.index("muscle_group")] == "Shoulders"
        assert row[EXERCISE_COLUMNS.index("metric_type")] == "Reps"

    def test_a_time_based_movement_carries_its_metric(self, seeded_catalog, member_a):
        member_a.post("/api/logs/exercise", json=dict(PRESS, ex_name="Plank", set1=60))

        (row,) = member_a.get("/api/logs/exercise").get_json()
        assert row[EXERCISE_COLUMNS.index("metric_type")] == "Seconds"


class TestMobilityAndSupplementShape:
    def test_mobility_intensity_comes_from_the_catalog_not_the_log(self, seeded_catalog, member_a):
        member_a.post("/api/logs/mobility", json={
            "date": "2026-09-05", "mob_name": "Hip Opener", "duration_mins": 20.0,
        })

        (row,) = member_a.get("/api/logs/mobility").get_json()
        assert len(row) == len(MOBILITY_COLUMNS)
        assert row[MOBILITY_COLUMNS.index("duration_mins")] == 20.0
        assert row[MOBILITY_COLUMNS.index("mets")] == 3.0

    def test_supplement_doses_scale_with_servings(self, seeded_catalog, member_a):
        member_a.post("/api/logs/supplement", json={
            "date": "2026-09-05", "supp_name": "Morning Stack", "servings": 2.0,
        })

        (row,) = member_a.get("/api/logs/supplement").get_json()
        assert len(row) == len(SUPPLEMENT_COLUMNS)
        assert row[SUPPLEMENT_COLUMNS.index("b12")] == pytest.approx(1000.0)
        assert row[SUPPLEMENT_COLUMNS.index("creatine")] == pytest.approx(10.0)
        assert row[SUPPLEMENT_COLUMNS.index("iodine")] == pytest.approx(0.0)


class TestOrphanedRows:
    @pytest.fixture
    def orphan(self, seeded_catalog, member_a):
        member_a.post("/api/logs/food", json=dict(BREAKFAST, servings=3.0))
        member_a.delete("/api/catalog/items/Rolled Oats")
        (row,) = member_a.get("/api/logs/food").get_json()
        return row

    def test_the_row_keeps_its_date_and_quantity(self, orphan):
        assert orphan[FOOD_COLUMNS.index("date")] == "2026-09-05"
        assert orphan[FOOD_COLUMNS.index("servings")] == 3.0

    def test_the_row_loses_its_item_name(self, orphan):
        assert orphan[FOOD_COLUMNS.index("name")] is None

    def test_the_derived_nutrients_are_no_longer_reported(self, orphan):
        assert all(orphan[index] is None
                   for index in range(FOOD_COLUMNS.index("cal"), len(FOOD_COLUMNS)))

    def test_the_grams_go_with_them_for_a_row_logged_in_servings(self, orphan):
        assert orphan[FOOD_COLUMNS.index("grams")] is None

    def test_redefining_the_name_does_not_reattach_the_orphan(self, orphan, member_a):
        from tests.conftest import OATS

        member_a.post("/api/catalog/food", json=OATS)

        (row,) = member_a.get("/api/logs/food").get_json()
        assert row[FOOD_COLUMNS.index("name")] is None


class TestInlineEdits:
    def test_a_log_row_can_be_repointed_at_another_catalog_item_by_name(
        self, seeded_catalog, member_a
    ):
        from tests.conftest import OATS

        member_a.post("/api/catalog/food", json=dict(OATS, name="Muesli", energy=400.0))
        member_a.post("/api/logs/food", json=BREAKFAST)
        (row,) = member_a.get("/api/logs/food").get_json()

        response = member_a.patch(
            f"/api/logs/food_logs/{row[0]}", json={"col": "food_item_id", "val": "muesli"}
        )

        assert response.status_code == 200
        assert member_a.get("/api/logs/food").get_json()[0][FOOD_COLUMNS.index("name")] == "Muesli"

    def test_repointing_at_an_unknown_item_is_refused(self, seeded_catalog, member_a):
        member_a.post("/api/logs/food", json=BREAKFAST)
        (row,) = member_a.get("/api/logs/food").get_json()

        response = member_a.patch(
            f"/api/logs/food_logs/{row[0]}", json={"col": "food_item_id", "val": "Nonexistent"}
        )

        assert response.status_code == 400
        assert "food_items" in response.get_json()["error"]

    def test_a_numeric_string_is_stored_as_a_number(self, seeded_catalog, member_a):
        member_a.post("/api/logs/food", json=BREAKFAST)
        (row,) = member_a.get("/api/logs/food").get_json()

        member_a.patch(f"/api/logs/food_logs/{row[0]}", json={"col": "servings", "val": "2.5"})

        assert member_a.get("/api/logs/food").get_json()[0][FOOD_COLUMNS.index("servings")] == 2.5

    def test_a_text_value_is_stored_as_text(self, seeded_catalog, member_a):
        member_a.post("/api/logs/food", json=BREAKFAST)
        (row,) = member_a.get("/api/logs/food").get_json()

        member_a.patch(f"/api/logs/food_logs/{row[0]}", json={"col": "meal_type", "val": "Dinner"})

        assert member_a.get("/api/logs/food").get_json()[0][FOOD_COLUMNS.index("meal_type")] == "Dinner"

    def test_an_iso_date_is_stored_as_text_not_arithmetic(self, seeded_catalog, member_a):
        member_a.post("/api/logs/food", json=BREAKFAST)
        (row,) = member_a.get("/api/logs/food").get_json()

        member_a.patch(f"/api/logs/food_logs/{row[0]}", json={"col": "date", "val": "2026-01-15"})

        assert member_a.get("/api/logs/food").get_json()[0][FOOD_COLUMNS.index("date")] == "2026-01-15"
