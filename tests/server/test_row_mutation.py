import pytest

from server.tables import CATALOG_TABLES, USER_LOG_TABLES, get_spec

BREAKFAST = {"date": "2026-09-05", "meal_type": "Breakfast",
             "food_name": "Rolled Oats", "servings": 1.0}
COFFEE = {"date": "2026-09-05", "time": "08:30", "bev_name": "Black Coffee", "servings": 1.0}


@pytest.fixture
def food_log_id(seeded_catalog, member_a):
    member_a.post("/api/logs/food", json=BREAKFAST)
    (row,) = member_a.get("/api/logs/food").get_json()
    return row[0]


@pytest.fixture
def oats_id(seeded_catalog, member_a):
    (item,) = [i for i in member_a.get("/api/catalog/food").get_json()
               if i["name"] == "Rolled Oats"]
    return item["id"]


class TestTheAllowlistIsPerTable:
    def test_a_column_from_another_table_is_refused_before_sqlite_sees_it(
        self, member_a, food_log_id
    ):
        response = member_a.patch(
            f"/api/logs/food_logs/{food_log_id}", json={"col": "caffeine_mg", "val": "80"}
        )

        assert response.status_code == 400
        error = response.get_json()["error"]
        assert "caffeine_mg" in error and "food_logs" in error
        assert "no such column" not in error, "the allowlist answers, not sqlite"

    def test_a_catalog_column_is_refused_on_a_log_table(self, member_a, food_log_id):
        response = member_a.patch(
            f"/api/logs/food_logs/{food_log_id}", json={"col": "energy", "val": "500"}
        )

        assert response.status_code == 400

    def test_a_log_column_is_refused_on_a_catalog_table(self, member_a, oats_id):
        response = member_a.patch(
            f"/api/logs/food_items/{oats_id}", json={"col": "servings", "val": "3"}
        )

        assert response.status_code == 400

    def test_the_columns_each_table_does_accept_still_work(self, member_a, food_log_id):
        for column, value in [("servings", "2.5"), ("meal_type", "Dinner"),
                              ("date", "2026-01-15")]:
            response = member_a.patch(
                f"/api/logs/food_logs/{food_log_id}", json={"col": column, "val": value}
            )
            assert response.status_code == 200, column

    def test_every_registered_table_is_either_a_catalog_or_a_log(self):
        assert CATALOG_TABLES.isdisjoint(USER_LOG_TABLES)
        for name in CATALOG_TABLES | USER_LOG_TABLES:
            assert get_spec(name).mutable_columns, f"{name} declares no writable column"


class TestValuesTakeTheColumnsDeclaredType:
    def test_a_numeric_name_is_stored_as_text(self, member_a, oats_id):
        member_a.patch(f"/api/logs/food_items/{oats_id}", json={"col": "name", "val": "5"})

        (item,) = [i for i in member_a.get("/api/catalog/food").get_json()
                   if i["id"] == oats_id]
        assert item["name"] == "5"

    def test_a_name_that_looks_like_a_decimal_keeps_its_spelling(self, member_a, oats_id):
        member_a.patch(f"/api/logs/food_items/{oats_id}", json={"col": "name", "val": "2.50"})

        (item,) = [i for i in member_a.get("/api/catalog/food").get_json()
                   if i["id"] == oats_id]
        assert item["name"] == "2.50"

    def test_a_numeric_column_stores_a_number_not_a_string(self, member_a, oats_id):
        member_a.patch(f"/api/logs/food_items/{oats_id}", json={"col": "energy", "val": "412.5"})

        (item,) = [i for i in member_a.get("/api/catalog/food").get_json()
                   if i["id"] == oats_id]
        assert item["energy"] == pytest.approx(412.5)
        assert isinstance(item["energy"], float)

    def test_a_date_survives_untouched(self, member_a, food_log_id):
        member_a.patch(
            f"/api/logs/food_logs/{food_log_id}", json={"col": "date", "val": "2026-01-15"}
        )

        (row,) = member_a.get("/api/logs/food").get_json()
        assert row[2] == "2026-01-15"

    def test_a_clock_time_survives_untouched(self, seeded_catalog, member_a):
        member_a.post("/api/logs/beverage", json=COFFEE)
        (row,) = member_a.get("/api/logs/beverage").get_json()

        member_a.patch(f"/api/logs/beverage_logs/{row[0]}", json={"col": "time", "val": "21:45"})

        (updated,) = member_a.get("/api/logs/beverage").get_json()
        assert updated[2] == "21:45"

    def test_free_text_notes_are_not_read_as_a_number(self, seeded_catalog, member_a):
        (item,) = [i for i in member_a.get("/api/catalog/mobility").get_json()]

        member_a.patch(f"/api/logs/mobility_items/{item['id']}",
                       json={"col": "notes", "val": "30"})

        (updated,) = member_a.get("/api/catalog/mobility").get_json()
        assert updated["notes"] == "30"

    def test_text_in_a_numeric_column_is_refused_rather_than_stored(
        self, member_a, oats_id
    ):
        response = member_a.patch(
            f"/api/logs/food_items/{oats_id}", json={"col": "energy", "val": "12o"}
        )

        assert response.status_code == 400
        assert "energy" in response.get_json()["error"]

        (item,) = [i for i in member_a.get("/api/catalog/food").get_json()
                   if i["id"] == oats_id]
        assert item["energy"] == pytest.approx(380.0), "the original value is untouched"
