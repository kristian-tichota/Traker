import pytest

from tests.conftest import OATS


class TestCatalogValueRanges:
    @pytest.mark.parametrize(
        "field",
        ["energy", "fat_total", "fat_saturated", "carbs_total",
         "carbs_sugars", "fibre", "protein", "salt"],
    )
    def test_a_negative_nutrient_is_refused(self, member_a, field):
        response = member_a.post("/api/catalog/food", json=dict(OATS, **{field: -1.0}))

        assert response.status_code == 400
        assert "CHECK constraint failed" in response.get_json()["error"]
        assert member_a.get("/api/catalog/food").get_json() == [], "nothing may be written"

    @pytest.mark.parametrize("serving_size", [0.0, -50.0])
    def test_a_non_positive_serving_size_is_refused(self, member_a, serving_size):
        response = member_a.post("/api/catalog/food", json=dict(OATS, serving_size=serving_size))
        assert response.status_code == 400

    def test_negative_caffeine_is_refused(self, member_a):
        response = member_a.post("/api/catalog/beverage", json={
            "name": "Anti-Coffee", "caffeine_mg": -80.0, "antioxidants_mg": 0.0,
        })
        assert response.status_code == 400

    def test_a_non_positive_metabolic_intensity_is_refused(self, member_a):
        response = member_a.post("/api/catalog/mobility", json={"name": "Coma", "mets": 0.0})
        assert response.status_code == 400

    def test_an_exercise_metric_outside_the_fixed_set_is_refused(self, member_a):
        response = member_a.post("/api/catalog/exercise", json={
            "name": "Vibes", "muscle_group": "Soul", "movement_pattern": "Float",
            "metric_type": "Kilometres",
        })
        assert response.status_code == 400
        assert "CHECK constraint failed" in response.get_json()["error"]

    @pytest.mark.parametrize("metric_type", ["Reps", "Seconds"])
    def test_the_two_supported_metrics_are_accepted(self, member_a, metric_type):
        response = member_a.post("/api/catalog/exercise", json={
            "name": f"Movement {metric_type}", "muscle_group": "Core",
            "movement_pattern": "Hold", "metric_type": metric_type,
        })
        assert response.status_code == 200


class TestReferentialIntegrity:
    @pytest.mark.parametrize(
        "endpoint, payload, missing_word",
        [
            ("food", {"date": "2026-09-05", "meal_type": "Breakfast",
                      "food_name": "Ghost Oats", "servings": 1.0}, "Food"),
            ("beverage", {"date": "2026-09-05", "time": "08:30",
                          "bev_name": "Ghost Coffee", "servings": 1.0}, "Beverage"),
            ("exercise", {"date": "2026-09-05", "ex_name": "Ghost Press",
                          "set1": 7, "set2": 0, "set3": 0, "set4": 0, "set5": 0,
                          "weight_kg": 30.0, "rpe": 8.0}, "Exercise"),
            ("supplement", {"date": "2026-09-05", "supp_name": "Ghost Stack",
                            "servings": 1.0}, "Supplement"),
            ("mobility", {"date": "2026-09-05", "mob_name": "Ghost Routine",
                          "duration_mins": 20.0}, "Mobility"),
        ],
    )
    def test_logging_an_unknown_item_is_refused_at_the_point_of_logging(
        self, member_a, endpoint, payload, missing_word
    ):
        response = member_a.post(f"/api/logs/{endpoint}", json=payload)

        assert response.status_code == 400
        error = response.get_json()["error"]
        assert missing_word in error
        assert "Ghost" in error, "the message must name the item"
        assert member_a.get(f"/api/logs/{endpoint}").get_json() == []


class TestLogValueRanges:
    def test_a_row_with_an_out_of_range_effort_rating_is_not_stored(
        self, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Overhead Press",
            "set1": 7, "set2": 0, "set3": 0, "set4": 0, "set5": 0,
            "weight_kg": 30.0, "rpe": 15.0,
        })

        assert member_a.get("/api/logs/exercise").get_json() == []

    def test_a_row_with_a_negative_load_is_not_stored(self, seeded_catalog, member_a):
        member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Overhead Press",
            "set1": 7, "set2": 0, "set3": 0, "set4": 0, "set5": 0,
            "weight_kg": -30.0, "rpe": 8.0,
        })

        assert member_a.get("/api/logs/exercise").get_json() == []

    def test_a_row_with_a_meal_type_outside_the_closed_set_is_not_stored(
        self, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Brunch",
            "food_name": "Rolled Oats", "servings": 1.0,
        })

        assert member_a.get("/api/logs/food").get_json() == []

    @pytest.mark.parametrize("meal", ["Breakfast", "Lunch", "Dinner", "Supplement"])
    def test_the_four_meal_types_are_accepted(self, seeded_catalog, member_a, meal):
        response = member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": meal,
            "food_name": "Rolled Oats", "servings": 1.0,
        })
        assert response.status_code == 200

    @pytest.mark.parametrize("servings", [0.0, -1.0])
    def test_a_non_positive_quantity_is_not_stored(self, seeded_catalog, member_a, servings):
        member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Breakfast",
            "food_name": "Rolled Oats", "servings": servings,
        })

        assert member_a.get("/api/logs/food").get_json() == []

    def test_a_non_positive_mobility_duration_is_not_stored(self, seeded_catalog, member_a):
        member_a.post("/api/logs/mobility", json={
            "date": "2026-09-05", "mob_name": "Hip Opener", "duration_mins": 0.0,
        })

        assert member_a.get("/api/logs/mobility").get_json() == []

    @pytest.mark.parametrize(
        "endpoint, payload",
        [
            ("food", {"date": "2026-09-05", "meal_type": "Brunch",
                      "food_name": "Rolled Oats", "servings": 1.0}),
            ("exercise", {"date": "2026-09-05", "ex_name": "Overhead Press",
                          "set1": 7, "set2": 0, "set3": 0, "set4": 0, "set5": 0,
                          "weight_kg": 30.0, "rpe": 15.0}),
        ],
    )
    def test_a_rejected_log_write_reports_the_reason(self, seeded_catalog, member_a, endpoint, payload):
        response = member_a.post(f"/api/logs/{endpoint}", json=payload)

        assert 400 <= response.status_code < 500
        assert "error" in response.get_json()


class TestDeletionSemantics:
    def test_deleting_a_log_row_leaves_the_catalog_item(self, seeded_catalog, member_a):
        member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Breakfast",
            "food_name": "Rolled Oats", "servings": 1.0,
        })
        (row,) = member_a.get("/api/logs/food").get_json()

        member_a.delete(f"/api/logs/food_logs/{row[0]}")

        assert member_a.get("/api/logs/food").get_json() == []
        assert len(member_a.get("/api/catalog/food").get_json()) == 1

    def test_deleting_a_log_row_leaves_the_members_other_rows(self, seeded_catalog, member_a):
        for servings in (1.0, 2.0, 3.0):
            member_a.post("/api/logs/food", json={
                "date": "2026-09-05", "meal_type": "Breakfast",
                "food_name": "Rolled Oats", "servings": servings,
            })
        rows = member_a.get("/api/logs/food").get_json()

        member_a.delete(f"/api/logs/food_logs/{rows[0][0]}")

        assert len(member_a.get("/api/logs/food").get_json()) == 2

    def test_a_table_outside_the_allowlist_cannot_be_deleted_from(self, member_a):
        response = member_a.delete("/api/logs/users/1")

        assert response.status_code == 400
        assert response.get_json()["error"] == "Unauthorized target table"

    def test_a_table_outside_the_allowlist_cannot_be_patched(self, member_a):
        response = member_a.patch("/api/logs/users/1", json={"col": "username", "val": "hacker"})

        assert response.status_code == 400
        assert response.get_json()["error"] == "Unauthorized target table"

    def test_a_column_outside_the_mutable_allowlist_is_refused_by_name(self, seeded_catalog, member_a):
        response = member_a.patch("/api/logs/food_items/1", json={"col": "id", "val": "99"})

        assert response.status_code == 400
        assert "'id'" in response.get_json()["error"], "the response must name the offending field"
