import pytest

BREAKFAST = {"date": "2026-09-05", "meal_type": "Breakfast",
             "food_name": "Rolled Oats", "servings": 1.0}


@pytest.fixture
def logs_from_both(seeded_catalog, member_a, member_b):
    member_a.post("/api/logs/food", json=dict(BREAKFAST, servings=1.0))
    member_b.post("/api/logs/food", json=dict(BREAKFAST, servings=9.0))
    return member_a, member_b


class TestReadScoping:
    def test_each_member_sees_only_their_own_rows(self, logs_from_both):
        member_a, member_b = logs_from_both

        (a_row,) = member_a.get("/api/logs/food").get_json()
        (b_row,) = member_b.get("/api/logs/food").get_json()

        assert a_row[5] == 1.0
        assert b_row[5] == 9.0

    def test_both_members_still_see_the_same_catalog(self, logs_from_both):
        member_a, member_b = logs_from_both

        assert member_a.get("/api/catalog/food").get_json() == member_b.get("/api/catalog/food").get_json()

    @pytest.mark.parametrize(
        "endpoint, payload",
        [
            ("food", BREAKFAST),
            ("beverage", {"date": "2026-09-05", "time": "08:30",
                          "bev_name": "Black Coffee", "servings": 1.0}),
            ("exercise", {"date": "2026-09-05", "ex_name": "Overhead Press",
                          "set1": 7, "set2": 7, "set3": 7, "set4": 0, "set5": 0,
                          "weight_kg": 30.0, "rpe": 8.0}),
            ("supplement", {"date": "2026-09-05", "supp_name": "Morning Stack",
                            "servings": 1.0}),
            ("mobility", {"date": "2026-09-05", "mob_name": "Hip Opener",
                          "duration_mins": 20.0}),
        ],
    )
    def test_every_log_domain_is_scoped_to_its_owner(
        self, seeded_catalog, member_a, member_b, endpoint, payload
    ):
        member_a.post(f"/api/logs/{endpoint}", json=payload)

        assert len(member_a.get(f"/api/logs/{endpoint}").get_json()) == 1
        assert member_b.get(f"/api/logs/{endpoint}").get_json() == []


class TestWriteScoping:
    def test_editing_the_other_members_log_row_changes_nothing(self, logs_from_both):
        member_a, member_b = logs_from_both
        (a_row,) = member_a.get("/api/logs/food").get_json()

        member_b.patch(f"/api/logs/food_logs/{a_row[0]}", json={"col": "servings", "val": "99"})

        assert member_a.get("/api/logs/food").get_json()[0][5] == 1.0

    def test_deleting_the_other_members_log_row_changes_nothing(self, logs_from_both):
        member_a, member_b = logs_from_both
        (a_row,) = member_a.get("/api/logs/food").get_json()

        member_b.delete(f"/api/logs/food_logs/{a_row[0]}")

        assert len(member_a.get("/api/logs/food").get_json()) == 1

    def test_a_member_can_edit_their_own_row(self, logs_from_both):
        member_a, _ = logs_from_both
        (a_row,) = member_a.get("/api/logs/food").get_json()

        response = member_a.patch(
            f"/api/logs/food_logs/{a_row[0]}", json={"col": "servings", "val": "2.5"}
        )

        assert response.status_code == 200
        assert member_a.get("/api/logs/food").get_json()[0][5] == 2.5

    def test_editing_a_shared_catalog_row_is_not_scoped_to_the_editor(
        self, seeded_catalog, member_a, member_b
    ):
        (item,) = member_a.get("/api/catalog/food").get_json()

        member_b.patch(f"/api/logs/food_items/{item['id']}", json={"col": "energy", "val": "400"})

        assert member_a.get("/api/catalog/food").get_json()[0]["energy"] == 400.0


class TestTelemetryScoping:
    def test_timer_history_is_personal(self, member_a, member_b):
        member_a.post("/api/pomodoro/heartbeat", json={
            "date": "2026-09-05", "minute_of_day": 600, "second": 0,
            "state": "focus", "mode": "Default",
        })

        assert len(member_a.get("/api/pomodoro/heartbeats/2026-09-05").get_json()) == 1
        assert member_b.get("/api/pomodoro/heartbeats/2026-09-05").get_json() == []

    def test_stress_overrides_are_personal(self, member_a, member_b):
        member_a.post("/api/pomodoro/dsi-override", json={"date": "2026-09-05", "override_dsi": 0.4})

        assert member_a.get("/api/pomodoro/dsi-overrides").get_json() == {"2026-09-05": 0.4}
        assert member_b.get("/api/pomodoro/dsi-overrides").get_json() == {}

    def test_timeline_events_are_personal(self, member_a, member_b):
        member_a.post("/api/pomodoro/event", json={
            "timestamp": "2026-09-05T10:00:00", "event_type": "resumed_focus", "amount_ms": 0,
        })

        assert len(member_a.get("/api/pomodoro/events/2026-09-05").get_json()) == 1
        assert member_b.get("/api/pomodoro/events/2026-09-05").get_json() == []

    def test_view_preferences_are_personal(self, member_a, member_b):
        member_a.post("/api/settings/ex_graph_slot_1", json={"value": "Overhead Press"})

        assert member_a.get("/api/settings/ex_graph_slot_1").get_json()["value"] == "Overhead Press"
        assert member_b.get("/api/settings/ex_graph_slot_1").get_json()["value"] == ""
