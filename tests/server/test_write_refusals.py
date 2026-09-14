import pytest

OATS = {
    "name": "Rolled Oats", "category": "Grain", "energy": 379.0,
    "fat_total": 6.5, "fat_saturated": 1.1, "carbs_total": 67.7,
    "carbs_sugars": 0.99, "fibre": 10.1, "protein": 13.2, "salt": 0.02,
    "serving_size": 40.0,
}


class TestAPayloadThatCannotBeRead:
    @pytest.mark.parametrize("path, body", [
        ("/api/logs/food", {"servings": 1}),
        ("/api/logs/beverage", {"date": "2026-09-05"}),
        ("/api/logs/exercise", {"date": "2026-09-05"}),
        ("/api/logs/supplement", {}),
        ("/api/logs/mobility", {"mob_name": "Hip Opener"}),
        ("/api/pomodoro/heartbeat", {"date": "2026-09-05"}),
        ("/api/pomodoro/event", {"event_type": "start"}),
    ])
    def test_a_missing_field_is_named(self, member_a, path, body):
        response = member_a.post(path, json=body)

        assert response.status_code == 400
        assert response.headers["Content-Type"].startswith("application/json")
        assert "Missing required field" in response.get_json()["error"]

    def test_a_body_that_is_not_an_object_is_refused(self, member_a):
        response = member_a.post("/api/logs/food", json=["not", "an", "object"])

        assert response.status_code == 400
        assert "JSON object" in response.get_json()["error"]

    def test_the_answer_is_always_json_a_client_can_read(self, member_a):
        response = member_a.post("/api/logs/food", json={})

        assert response.get_json()["error"]


class TestAValueThatMustNotBeStored:
    def test_text_in_a_numeric_column_is_refused_on_definition(self, member_a):
        response = member_a.post("/api/catalog/food", json=dict(OATS, energy="12o"))

        assert response.status_code == 400
        assert "energy" in response.get_json()["error"]
        assert member_a.get("/api/catalog/food").get_json() == []

    @pytest.mark.parametrize("written", ["1e400", "inf", "-inf", "nan"])
    def test_a_value_that_is_not_finite_is_refused(self, member_a, written):
        response = member_a.post(
            "/api/catalog/beverage",
            json={"name": "Rocket Fuel", "caffeine_mg": written, "antioxidants_mg": 0},
        )

        assert response.status_code == 400
        assert member_a.get("/api/catalog/beverage").get_json() == []

    def test_a_stored_number_keeps_its_declared_type(self, member_a, server_db):
        member_a.post("/api/catalog/food", json=dict(OATS, energy="379"))

        conn = server_db.get_connection()
        try:
            row = conn.execute("SELECT typeof(energy) AS kind FROM food_items").fetchone()
        finally:
            conn.close()
        assert row["kind"] == "real"

    def test_a_date_that_is_not_a_date_is_refused(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)
        member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Lunch",
            "food_name": "Rolled Oats", "servings": 1.0,
        })
        (row,) = member_a.get("/api/logs/food").get_json()

        response = member_a.patch(f"/api/logs/food_logs/{row[0]}",
                                  json={"col": "date", "val": "not-a-date"})

        assert response.status_code == 400
        assert "YYYY-MM-DD" in response.get_json()["error"]
        assert member_a.get("/api/logs/food").get_json()[0][2] == "2026-09-05"

    def test_a_log_write_with_a_bad_date_is_refused(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)

        response = member_a.post("/api/logs/food", json={
            "date": "05.09.2026", "meal_type": "Lunch",
            "food_name": "Rolled Oats", "servings": 1.0,
        })

        assert response.status_code == 400, "DD.MM.YYYY is a display format"


class TestAWriteThatMatchedNothing:
    @pytest.fixture
    def a_food_log_of_member_a(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)
        member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Lunch",
            "food_name": "Rolled Oats", "servings": 1.0,
        })
        (row,) = member_a.get("/api/logs/food").get_json()
        return row[0]

    def test_editing_the_other_members_row_is_refused_not_confirmed(
        self, member_b, a_food_log_of_member_a
    ):
        response = member_b.patch(f"/api/logs/food_logs/{a_food_log_of_member_a}",
                                  json={"col": "servings", "val": 99})

        assert response.status_code == 404

    def test_and_the_row_is_untouched(self, member_a, member_b, a_food_log_of_member_a):
        member_b.patch(f"/api/logs/food_logs/{a_food_log_of_member_a}",
                       json={"col": "servings", "val": 99})

        assert member_a.get("/api/logs/food").get_json()[0][5] == 1.0

    def test_deleting_the_other_members_row_is_refused_not_confirmed(
        self, member_b, a_food_log_of_member_a
    ):
        response = member_b.delete(f"/api/logs/food_logs/{a_food_log_of_member_a}")

        assert response.status_code == 404

    def test_and_the_row_survives(self, member_a, member_b, a_food_log_of_member_a):
        member_b.delete(f"/api/logs/food_logs/{a_food_log_of_member_a}")

        assert len(member_a.get("/api/logs/food").get_json()) == 1

    def test_deleting_a_row_that_never_existed_is_refused(self, member_a):
        assert member_a.delete("/api/logs/food_logs/999999").status_code == 404

    def test_editing_a_row_that_never_existed_is_refused(self, member_a):
        response = member_a.patch("/api/logs/food_logs/999999",
                                  json={"col": "servings", "val": 2})
        assert response.status_code == 404


class TestTheLogWritePathIsGuardedToo:
    @pytest.fixture
    def a_press(self, member_a):
        member_a.post("/api/catalog/exercise", json={
            "name": "Overhead Press", "muscle_group": "Shoulders",
            "movement_pattern": "Push", "metric_type": "Reps",
        })

    @pytest.mark.parametrize("written", ["1e400", "inf", "nan"])
    def test_a_rep_count_that_is_not_finite_is_refused(self, member_a, a_press, written):
        response = member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Overhead Press",
            "set1": written, "weight_kg": 30.0, "rpe": 8.0,
        })

        assert response.status_code == 400
        assert member_a.get("/api/logs/exercise").get_json() == []

    def test_text_where_a_weight_belongs_is_refused(self, member_a, a_press):
        response = member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Overhead Press",
            "set1": 7, "weight_kg": "thirty", "rpe": 8.0,
        })

        assert response.status_code == 400
        assert "weight_kg" in response.get_json()["error"]

    def test_a_beverage_time_that_is_not_a_time_is_refused(self, member_a):
        member_a.post("/api/catalog/beverage", json={
            "name": "Black Coffee", "caffeine_mg": 80.0, "antioxidants_mg": 0.0,
        })

        response = member_a.post("/api/logs/beverage", json={
            "date": "2026-09-05", "time": "half past eight",
            "bev_name": "Black Coffee", "servings": 1.0,
        })

        assert response.status_code == 400
        assert "HH:MM" in response.get_json()["error"]

    def test_a_well_formed_log_still_goes_through(self, member_a, a_press):
        response = member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Overhead Press",
            "set1": 7, "set2": 7, "weight_kg": 30.0, "rpe": 8.0,
        })

        assert response.status_code == 200
        (row,) = member_a.get("/api/logs/exercise").get_json()
        assert row[4] == 7 and row[6] == 0, "unsent sets default to zero"

    def test_a_missing_item_is_still_refused_at_the_point_of_logging(self, member_a):
        response = member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Never Defined",
            "set1": 7, "weight_kg": 30.0, "rpe": 8.0,
        })

        assert response.status_code == 400
        assert "not found in catalog" in response.get_json()["error"]


class TestABodyThatEscapedBothHandlers:
    def test_an_empty_catalog_body_names_the_field_it_wants(self, member_a):
        response = member_a.post("/api/catalog/beverage", json={})

        assert response.status_code == 400
        assert response.headers["Content-Type"].startswith("application/json")
        assert "name" in response.get_json()["error"]

    @pytest.mark.parametrize("value", [{"a": 1}, [1, 2]])
    def test_a_json_object_where_a_value_belongs_is_refused(self, member_a, value):
        response = member_a.post(
            "/api/catalog/beverage",
            json={"name": "Rocket Fuel", "caffeine_mg": value, "antioxidants_mg": 0},
        )

        assert response.status_code == 400
        assert member_a.get("/api/catalog/beverage").get_json() == []

    def test_a_name_that_is_not_text_is_refused(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)
        response = member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Lunch",
            "food_name": {"$ne": None}, "servings": 1.0,
        })

        assert response.status_code == 400
        assert response.headers["Content-Type"].startswith("application/json")

    def test_every_refusal_is_json_whatever_it_was(self, member_a):
        for path, body in [
            ("/api/catalog/beverage", {}),
            ("/api/catalog/beverage", {"name": "X", "caffeine_mg": ["a"], "antioxidants_mg": 0}),
            ("/api/pomodoro/dsi-override", {"date": "2026-09-05", "override_dsi": "high"}),
        ]:
            response = member_a.post(path, json=body)
            assert response.headers["Content-Type"].startswith("application/json"), path
            assert "error" in response.get_json(), path


class TestAValueOmittedRatherThanWrong:
    def test_a_patch_without_a_value_is_refused(self, member_a):
        member_a.post("/api/catalog/exercise", json={
            "name": "Press", "muscle_group": "Shoulders", "movement_pattern": "Push",
            "secondary_muscles": "Triceps", "metric_type": "Reps",
        })

        response = member_a.patch("/api/logs/exercise_items/1", json={"col": "secondary_muscles"})

        assert response.status_code == 400
        assert "val" in response.get_json()["error"]

    def test_and_the_column_keeps_its_value(self, member_a):
        member_a.post("/api/catalog/exercise", json={
            "name": "Press", "muscle_group": "Shoulders", "movement_pattern": "Push",
            "secondary_muscles": "Triceps", "metric_type": "Reps",
        })

        member_a.patch("/api/logs/exercise_items/1", json={"col": "secondary_muscles"})

        assert member_a.get("/api/catalog/exercise").get_json()[0]["secondary_muscles"] == "Triceps"


class TestAQuantityThatCannotBeNegative:
    @pytest.fixture
    def a_press(self, member_a):
        member_a.post("/api/catalog/exercise", json={
            "name": "Press", "muscle_group": "Shoulders",
            "movement_pattern": "Push", "metric_type": "Reps",
        })
        return member_a

    def test_a_negative_rep_count_is_refused_on_the_log_write(self, a_press):
        response = a_press.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Press", "weight_kg": 50, "rpe": 8, "set1": -10,
        })

        assert response.status_code == 400
        assert a_press.get("/api/logs/exercise").get_json() == []

    def test_a_negative_rep_count_is_refused_on_an_inline_edit(self, a_press):
        a_press.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Press", "weight_kg": 50, "rpe": 8, "set1": 10,
        })
        (row,) = a_press.get("/api/logs/exercise").get_json()

        response = a_press.patch(f"/api/logs/exercise_logs/{row[0]}", json={"col": "set1", "val": -10})

        assert response.status_code == 400
        assert a_press.get("/api/logs/exercise").get_json()[0][4] == 10.0

    def test_a_negative_micronutrient_dose_is_refused(self, member_a):
        response = member_a.post("/api/catalog/supplement", json={"name": "Bad Stack", "zinc_mg": -500})

        assert response.status_code == 400
        assert member_a.get("/api/catalog/supplement").get_json() == []

    def test_a_null_set_is_refused(self, a_press):
        response = a_press.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Press", "weight_kg": 50, "rpe": 8, "set1": None,
        })

        assert response.status_code == 400


class TestASetExpansionGoesBackThroughTheGate:
    @pytest.fixture
    def a_meal_set(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)
        member_a.post("/api/catalog/sets/food", json={
            "name": "Blue Oatmeal",
            "components": [{"item_name": "Rolled Oats", "amount": 100.0}],
        })
        return member_a

    @pytest.fixture
    def a_drink_set(self, member_a):
        member_a.post("/api/catalog/beverage", json={
            "name": "Black Coffee", "caffeine_mg": 80.0, "antioxidants_mg": 0.0,
        })
        member_a.post("/api/catalog/sets/beverage", json={
            "name": "Morning", "components": [{"item_name": "Black Coffee", "amount": 2.0}],
        })
        return member_a

    def test_a_multiplier_whose_product_is_not_finite_is_refused(self, a_meal_set):
        response = a_meal_set.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Breakfast",
            "food_name": "Blue Oatmeal", "servings": 1e307,
        })

        assert response.status_code == 400
        assert a_meal_set.get("/api/logs/food").get_json() == []

    def test_the_refusal_names_the_set_and_the_component(self, a_meal_set):
        response = a_meal_set.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Breakfast",
            "food_name": "Blue Oatmeal", "servings": 1e307,
        })

        reason = response.get_json()["error"]
        assert "Blue Oatmeal" in reason and "Rolled Oats" in reason

    def test_every_domains_expansion_is_guarded(self, a_drink_set):
        response = a_drink_set.post("/api/logs/beverage", json={
            "date": "2026-09-05", "time": "08:00",
            "bev_name": "Morning", "servings": 1e308,
        })

        assert response.status_code == 400
        assert a_drink_set.get("/api/logs/beverage").get_json() == []

    def test_an_ordinary_multiplier_still_logs(self, a_meal_set):
        response = a_meal_set.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Breakfast",
            "food_name": "Blue Oatmeal", "servings": 2.0,
        })

        assert response.status_code == 200
        (row,) = a_meal_set.get("/api/logs/food").get_json()
        assert row[6] == 200.0, "two of a 100 g recipe is 200 g"
