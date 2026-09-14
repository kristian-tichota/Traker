import pytest

OATS = {
    "name": "Rolled Oats", "category": "Carbs", "energy": 380.0,
    "fat_total": 7.0, "fat_saturated": 1.2, "carbs_total": 60.0,
    "carbs_sugars": 1.0, "fibre": 10.0, "protein": 13.0,
    "salt": 0.0, "serving_size": 50.0,
}


@pytest.fixture
def stocked(db_client, member_a):
    member_a.post("/api/catalog/food", json=OATS)
    return db_client


class TestASecondReadCostsNothing:
    def test_the_same_read_twice_reaches_the_service_once(self, stocked):
        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 1.0})

        first = stocked.get_food_logs()
        before = stocked.cache.hits
        second = stocked.get_food_logs()

        assert second == first
        assert stocked.cache.hits == before + 1

    def test_a_bounded_read_is_served_from_the_tables_full_download(self, stocked):
        for date in ("2026-01-01", "2026-08-01", "2026-09-05"):
            stocked.add_food_log({"date": date, "meal_type": "Breakfast",
                                  "food_name": "Rolled Oats", "servings": 1.0})
        whole = stocked.get_food_logs()
        assert len(whole) == 3

        before = stocked.cache.hits
        recent = stocked.get_food_logs(since="2026-08-01")

        assert stocked.cache.hits == before + 1
        assert [row.date for row in recent] == ["2026-09-05", "2026-08-01"]

    def test_the_bounded_answer_matches_what_the_server_would_have_said(
            self, stocked):
        for date in ("2026-01-01", "2026-08-01", "2026-09-05"):
            stocked.add_food_log({"date": date, "meal_type": "Breakfast",
                                  "food_name": "Rolled Oats", "servings": 1.0})

        stocked.get_food_logs()
        from_cache = stocked.get_food_logs(since="2026-08-01")

        stocked.invalidate()
        from_wire = stocked.get_food_logs(since="2026-08-01")

        assert from_cache == from_wire

    def test_each_domain_is_cached_separately(self, stocked, member_a):
        stocked.get_food_logs()

        assert "food" in stocked.cache.cached_domains()
        assert "exercise" not in stocked.cache.cached_domains()


class TestAWriteIsNeverServedStale:
    def test_a_new_log_appears_in_the_next_read(self, stocked):
        stocked.get_food_logs()

        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 1.0})

        assert len(stocked.get_food_logs()) == 1

    def test_a_deleted_row_is_gone_from_the_next_read(self, stocked):
        for servings in (1.0, 2.0):
            stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                                  "food_name": "Rolled Oats", "servings": servings})
        rows = stocked.get_food_logs()

        stocked.delete_record("food_logs", rows[0].id)

        assert len(stocked.get_food_logs()) == 1

    def test_an_edited_row_reads_back_edited(self, stocked):
        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 1.0})
        (row,) = stocked.get_food_logs()

        stocked.update_record("food_logs", row.id, "Servings", "3",
                              {"Servings": "servings"})

        assert stocked.get_food_logs()[0].servings == 3.0

    def test_a_bounded_read_after_a_write_is_not_stale_either(self, stocked):
        stocked.get_food_logs(since="2026-01-01")
        stocked.get_food_logs()

        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 1.0})

        assert len(stocked.get_food_logs(since="2026-01-01")) == 1

    def test_a_write_to_one_domain_does_not_drop_another(self, stocked, member_a):
        member_a.post("/api/catalog/mobility",
                      json={"name": "Hip Opener", "mets": 3.0, "notes": ""})
        stocked.get_mobility_logs()
        held = len(stocked.cache)

        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 1.0})

        assert "mobility" in stocked.cache.cached_domains()
        assert len(stocked.cache) < held + 1

    def test_a_refused_write_does_not_drop_the_cache(self, stocked):
        stocked.get_food_logs()
        held = len(stocked.cache)

        ok, _message = stocked.add_food_log({"date": "2026-09-05"})

        assert ok is False
        assert len(stocked.cache) == held


class TestACatalogEditDropsTheLogsThatDeriveFromIt:
    def test_editing_a_foods_energy_changes_the_logs_kcal(self, stocked, member_a):
        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 1.0})
        before = stocked.get_food_logs()[0].energy_kcal
        assert before == pytest.approx(190.0)

        (item,) = [row for row in stocked.get_all_foods() if row[1] == "Rolled Oats"]
        stocked.update_record("food_items", item[0], "Energy (kcal)", "500",
                              {"Energy (kcal)": "energy"})

        assert stocked.get_food_logs()[0].energy_kcal == pytest.approx(250.0)

    def test_the_other_members_catalog_edit_reaches_this_client(
            self, stocked, db_client_b, member_b):
        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 1.0})
        db_client_b.add_food_log({"date": "2026-09-05", "meal_type": "Lunch",
                                  "food_name": "Rolled Oats", "servings": 1.0})
        assert db_client_b.get_food_logs()[0].energy_kcal == pytest.approx(190.0)

        (item,) = [row for row in stocked.get_all_foods() if row[1] == "Rolled Oats"]
        stocked.update_record("food_items", item[0], "Energy (kcal)", "500",
                              {"Energy (kcal)": "energy"})

        db_client_b.invalidate(("food",))

        assert db_client_b.get_food_logs()[0].energy_kcal == pytest.approx(250.0)

    def test_defining_a_new_food_drops_the_food_reads(self, stocked):
        stocked.get_all_foods()
        stocked.get_food_logs()

        stocked.add_food_item(dict(OATS, name="Steel Cut Oats"))

        assert "food" not in stocked.cache.cached_domains()


class TestAFailedReadIsNeverRemembered:
    def test_an_unreachable_service_is_not_cached_as_an_empty_ledger(
            self, db_client, offline_requests):
        assert db_client.get_food_logs() == []

        assert "food" not in db_client.cache.cached_domains()

    def test_the_read_is_retried_once_the_service_is_back(
            self, db_client, monkeypatch, bridge_requests, member_a):
        import requests

        member_a.post("/api/catalog/food", json=OATS)
        db_client.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                                "food_name": "Rolled Oats", "servings": 1.0})

        def refuse(*args, **kwargs):
            raise requests.ConnectionError("down")

        working = requests.get
        monkeypatch.setattr(requests, "get", refuse)
        assert db_client.get_food_logs() == []

        monkeypatch.setattr(requests, "get", working)
        assert len(db_client.get_food_logs()) == 1

    def test_a_genuinely_empty_ledger_is_cached(self, db_client):
        assert db_client.get_food_logs() == []

        assert "food" in db_client.cache.cached_domains()
