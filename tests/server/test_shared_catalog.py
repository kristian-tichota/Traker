import pytest

from tests.conftest import BLACK_COFFEE, HIP_OPENER, MORNING_STACK, OATS, OVERHEAD_PRESS

DOMAINS = ["food", "beverage", "exercise", "supplement", "mobility"]


class TestSharing:
    def test_an_item_defined_by_one_member_is_visible_to_the_other(self, member_a, member_b):
        member_a.post("/api/catalog/food", json=OATS)

        names = [item["name"] for item in member_b.get("/api/catalog/food").get_json()]
        assert names == ["Rolled Oats"]

    def test_reading_a_domain_returns_every_entry_whoever_defined_it(self, member_a, member_b):
        member_a.post("/api/catalog/beverage", json=BLACK_COFFEE)
        member_b.post("/api/catalog/beverage", json={
            "name": "Green Tea", "caffeine_mg": 30.0, "antioxidants_mg": 400.0,
        })

        for member in (member_a, member_b):
            names = {item["name"] for item in member.get("/api/catalog/beverage").get_json()}
            assert names == {"Black Coffee", "Green Tea"}

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_every_domain_starts_empty(self, member_a, domain):
        assert member_a.get(f"/api/catalog/{domain}").get_json() == []

    def test_an_unknown_domain_is_rejected(self, member_a):
        assert member_a.get("/api/catalog/sleep").status_code == 400
        assert member_a.post("/api/catalog/sleep", json={"name": "Nap"}).status_code == 400


class TestStoredAttributes:
    def test_food_records_macros_per_hundred_grams_and_a_serving_size(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)
        (item,) = member_a.get("/api/catalog/food").get_json()
        assert item["energy"] == 380.0
        assert item["serving_size"] == 50.0
        assert {"protein", "carbs_total", "carbs_sugars", "fat_total",
                "fat_saturated", "salt", "fibre"} <= set(item)

    def test_beverages_record_caffeine_and_antioxidants_per_serving(self, member_a):
        member_a.post("/api/catalog/beverage", json=BLACK_COFFEE)
        (item,) = member_a.get("/api/catalog/beverage").get_json()
        assert (item["caffeine_mg"], item["antioxidants_mg"]) == (80.0, 200.0)

    def test_exercises_record_how_the_movement_is_measured(self, member_a):
        member_a.post("/api/catalog/exercise", json=OVERHEAD_PRESS)
        (item,) = member_a.get("/api/catalog/exercise").get_json()
        assert item["metric_type"] == "Reps"
        assert item["muscle_group"] == "Shoulders"
        assert item["movement_pattern"] == "Push"

    def test_supplements_default_every_untracked_micronutrient_to_zero(self, member_a):
        member_a.post("/api/catalog/supplement", json=MORNING_STACK)
        (item,) = member_a.get("/api/catalog/supplement").get_json()
        assert item["b12_mcg"] == 500.0
        assert item["iodine_mcg"] == 0.0, "unlisted doses must read as zero, not null"
        assert item["l_theanine_mg"] == 0.0

    def test_mobility_records_an_intensity_and_free_text_notes(self, member_a):
        member_a.post("/api/catalog/mobility", json=HIP_OPENER)
        (item,) = member_a.get("/api/catalog/mobility").get_json()
        assert item["mets"] == 3.0
        assert item["notes"] == "Daily"


class TestUniqueness:
    def test_a_duplicate_name_is_rejected_with_the_conflict_named(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)

        response = member_a.post("/api/catalog/food", json=dict(OATS, energy=999.0))

        assert response.status_code == 400
        assert "UNIQUE constraint failed" in response.get_json()["error"]

    def test_the_existing_item_is_left_untouched_by_a_rejected_redefinition(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)

        member_a.post("/api/catalog/food", json=dict(OATS, energy=999.0))

        (item,) = member_a.get("/api/catalog/food").get_json()
        assert item["energy"] == 380.0

    def test_the_other_member_cannot_shadow_a_name_either(self, member_a, member_b):
        member_a.post("/api/catalog/food", json=OATS)
        assert member_b.post("/api/catalog/food", json=OATS).status_code == 400

    def test_the_same_name_may_exist_in_a_different_domain(self, member_a):
        member_a.post("/api/catalog/food", json=dict(OATS, name="Matcha"))
        response = member_a.post("/api/catalog/beverage", json={
            "name": "Matcha", "caffeine_mg": 40.0, "antioxidants_mg": 500.0,
        })
        assert response.status_code == 200


class TestColumnAllowlist:
    def test_a_column_outside_the_allowlist_is_refused(self, member_a):
        response = member_a.post("/api/catalog/food", json=dict(OATS, id=99))
        assert response.status_code == 400
        assert "id" in response.get_json()["error"]

    def test_an_injection_shaped_key_is_refused_before_it_reaches_sql(self, member_a):
        response = member_a.post("/api/catalog/food", json={
            "name": "Trojan", "energy); DROP TABLE food_items;--": 1,
        })
        assert response.status_code == 400
        assert member_a.get("/api/catalog/food").status_code == 200, "schema must survive"

    def test_a_partial_definition_uses_column_defaults(self, member_a):
        assert member_a.post("/api/catalog/supplement", json={"name": "Zinc only", "zinc_mg": 15.0}).status_code == 200

    def test_a_partial_definition_of_a_required_row_is_refused(self, member_a):
        response = member_a.post("/api/catalog/food", json={"name": "Half a food"})
        assert response.status_code == 400
        assert "NOT NULL" in response.get_json()["error"]


class TestDeletionByName:
    def test_removal_spans_every_domain(self, member_a):
        for domain, payload in [
            ("food", dict(OATS, name="Ambiguous")),
            ("beverage", dict(BLACK_COFFEE, name="Ambiguous")),
            ("mobility", dict(HIP_OPENER, name="Ambiguous")),
        ]:
            member_a.post(f"/api/catalog/{domain}", json=payload)

        member_a.delete("/api/catalog/items/Ambiguous")

        for domain in ("food", "beverage", "mobility"):
            assert member_a.get(f"/api/catalog/{domain}").get_json() == []

    def test_removal_ignores_capitalisation(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)

        member_a.delete("/api/catalog/items/rolled oats")

        assert member_a.get("/api/catalog/food").get_json() == []

    def test_a_name_with_spaces_survives_the_url(self, seeded_catalog, member_a):
        member_a.delete("/api/catalog/items/Overhead Press")

        names = {item["name"] for item in member_a.get("/api/catalog/exercise").get_json()}
        assert names == {"Plank"}

    def test_an_absent_name_is_not_broadcast_as_a_removal(self, member_a):
        from server.events import event_broadcaster

        queue_ = event_broadcaster.subscribe()
        try:
            member_a.delete("/api/catalog/items/Never Existed")
            assert queue_.empty(), "nothing was removed, so nothing changed"
        finally:
            event_broadcaster.unsubscribe(queue_)

    def test_removing_an_absent_name_says_so(self, member_a):
        response = member_a.delete("/api/catalog/items/Never Existed")

        assert response.status_code == 404
        assert "Never Existed" in response.get_json()["error"]

    def test_removing_a_name_reports_how_many_rows_went(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)

        body = member_a.delete("/api/catalog/items/Rolled Oats").get_json()

        assert body["removed"] == 1

    def test_a_removed_name_may_be_defined_again(self, member_a):
        member_a.post("/api/catalog/food", json=OATS)
        member_a.delete("/api/catalog/items/Rolled Oats")

        assert member_a.post("/api/catalog/food", json=dict(OATS, energy=42.0)).status_code == 200
        (item,) = member_a.get("/api/catalog/food").get_json()
        assert item["energy"] == 42.0


class TestBroadcasts:
    @pytest.fixture
    def listener(self):
        from server.events import event_broadcaster

        queue_ = event_broadcaster.subscribe()
        yield queue_
        event_broadcaster.unsubscribe(queue_)

    @staticmethod
    def _events(queue_):
        import json
        import queue as queue_module

        received = []
        while True:
            try:
                received.append(json.loads(queue_.get_nowait()[len("data: "):]))
            except queue_module.Empty:
                return received

    def test_defining_an_item_is_broadcast(self, member_a, listener):
        member_a.post("/api/catalog/food", json=OATS)

        (event,) = self._events(listener)
        assert event["event"] == "catalog_updated"
        assert event["data"]["domain"] == "food"
        assert event["data"]["action"] == "insert"

    def test_a_rejected_definition_is_not_broadcast(self, member_a, listener):
        member_a.post("/api/catalog/food", json=OATS)
        self._events(listener)

        member_a.post("/api/catalog/food", json=OATS)

        assert self._events(listener) == []

    def test_removing_an_item_is_broadcast(self, member_a, listener):
        member_a.post("/api/catalog/food", json=OATS)
        self._events(listener)

        member_a.delete("/api/catalog/items/Rolled Oats")

        (event,) = self._events(listener)
        assert event["data"]["action"] == "delete"
        assert event["data"]["name"] == "Rolled Oats"

    def test_editing_a_catalog_row_is_broadcast(self, member_a, listener):
        member_a.post("/api/catalog/food", json=OATS)
        self._events(listener)

        member_a.patch("/api/logs/food_items/1", json={"col": "energy", "val": "400"})

        (event,) = self._events(listener)
        assert event["data"]["action"] == "update"
        assert event["data"]["col"] == "energy"

    def test_recording_a_personal_log_disturbs_nobody(self, seeded_catalog, member_a, listener):
        self._events(listener)

        member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Breakfast",
            "food_name": "Rolled Oats", "servings": 1.0,
        })

        assert self._events(listener) == [], "log writes must not be broadcast"


class TestNamesAreOneIdentityHoweverTheyAreCapitalised:
    OATS = {
        "name": "Rolled Oats", "category": "Grain", "energy": 380.0,
        "fat_total": 7.0, "fat_saturated": 1.2, "carbs_total": 60.0,
        "carbs_sugars": 1.0, "fibre": 10.0, "protein": 13.0, "salt": 0.0,
        "serving_size": 100.0,
    }

    def test_a_case_variant_of_an_existing_name_is_refused(self, member_a):
        member_a.post("/api/catalog/food", json=self.OATS)

        response = member_a.post("/api/catalog/food", json=dict(self.OATS, name="ROLLED OATS", energy=1.0))

        assert response.status_code == 400
        assert len(member_a.get("/api/catalog/food").get_json()) == 1

    def test_the_other_member_cannot_add_one_either(self, member_a, member_b):
        member_a.post("/api/catalog/food", json=self.OATS)

        assert member_b.post("/api/catalog/food", json=dict(self.OATS, name="rolled oats")).status_code == 400

    def test_renaming_a_row_onto_a_case_variant_is_refused(self, member_a):
        member_a.post("/api/catalog/food", json=self.OATS)
        member_a.post("/api/catalog/food", json=dict(self.OATS, name="Porridge", energy=1.0))
        rows = {r["name"]: r["id"] for r in member_a.get("/api/catalog/food").get_json()}

        response = member_a.patch(f"/api/logs/food_items/{rows['Porridge']}",
                                  json={"col": "name", "val": "ROLLED OATS"})

        assert response.status_code == 400

    def test_a_log_resolves_to_the_one_row_that_name_can_mean(self, member_a):
        member_a.post("/api/catalog/food", json=self.OATS)
        member_a.post("/api/catalog/food", json=dict(self.OATS, name="ROLLED OATS", energy=1.0))

        member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Lunch",
            "food_name": "Rolled Oats", "servings": 1.0,
        })

        (row,) = member_a.get("/api/logs/food").get_json()
        assert row[4] == "Rolled Oats"
        assert row[6] == 100.0, "grams"
        assert row[8] == 380.0, "the macros of the item whose name was typed"
