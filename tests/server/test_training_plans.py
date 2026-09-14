import pytest

CYCLE = {
    "name": "Cycle 1",
    "start_date": "2026-09-14",
    "weeks": 4,
    "notes": "Rebuild",
    "sessions": [
        {
            "date": "2026-09-14", "week": 1, "name": "Upper A",
            "block": "re-entry",
            "movements": [
                {"exercise": "Overhead Press", "sets": 3, "target_low": 8,
                 "target_high": 12, "weight_kg": 16.5, "rpe": 7, "tempo": "3/3"},
                {"exercise": "Plank", "sets": 3, "target_low": 30,
                 "target_high": 30, "weight_kg": 0, "rpe": 6},
            ],
        },
        {
            "date": "2026-09-15", "week": 1, "name": "Lower A",
            "block": "re-entry",
            "movements": [
                {"exercise": "Overhead Press", "sets": 2, "target_low": 10,
                 "target_high": 10, "weight_kg": 12.5, "rpe": 6},
            ],
        },
    ],
}


@pytest.fixture
def plan_id(seeded_catalog, member_a):
    answer = member_a.post("/api/plans", json=CYCLE)
    assert answer.status_code == 200, answer.get_json()
    return answer.get_json()["plan_id"]


class TestDefiningACycle:
    def test_a_cycle_is_imported_whole(self, member_a, plan_id):
        answer = member_a.post("/api/plans", json=dict(CYCLE, name="Cycle 2"))
        assert answer.get_json() == {
            "status": "success", "plan_id": answer.get_json()["plan_id"],
            "sessions": 2, "movements": 3}

    def test_the_cycle_reports_how_many_sessions_it_holds(self, member_a, plan_id):
        (row,) = member_a.get("/api/plans").get_json()
        assert row[1:] == ["Cycle 1", "2026-09-14", 4, "Rebuild", 2]

    def test_a_movement_naming_nothing_in_the_catalog_is_refused(
        self, seeded_catalog, member_a
    ):
        broken = dict(CYCLE, name="Typo", sessions=[
            dict(CYCLE["sessions"][0],
                 movements=[{"exercise": "Nonexistent Lift", "sets": 3}])])
        answer = member_a.post("/api/plans", json=broken)
        assert answer.status_code == 400
        assert "Nonexistent Lift" in answer.get_json()["error"]

    def test_a_refused_session_leaves_no_half_written_cycle(
        self, seeded_catalog, member_a
    ):
        broken = dict(CYCLE, name="Typo", sessions=[
            CYCLE["sessions"][0],
            dict(CYCLE["sessions"][1],
                 movements=[{"exercise": "Nonexistent Lift", "sets": 3}])])
        member_a.post("/api/plans", json=broken)
        assert [row[1] for row in member_a.get("/api/plans").get_json()] == []

    def test_a_negative_load_is_refused_naming_the_movement(
        self, seeded_catalog, member_a
    ):
        broken = dict(CYCLE, name="Typo", sessions=[
            dict(CYCLE["sessions"][0],
                 movements=[{"exercise": "Plank", "sets": 3, "weight_kg": -5}])])
        answer = member_a.post("/api/plans", json=broken)
        assert answer.status_code == 400
        assert "Plank" in answer.get_json()["error"]

    def test_two_cycles_may_not_share_a_name(self, member_a, plan_id):
        assert member_a.post("/api/plans", json=CYCLE).status_code == 400


class TestOnePlanBelongsToOneMember:
    def test_the_other_member_does_not_see_it(self, member_b, plan_id):
        assert member_b.get("/api/plans").get_json() == []

    def test_the_other_member_cannot_read_its_sessions(self, member_b, plan_id):
        answer = member_b.get(f"/api/plans/{plan_id}/sessions")
        assert answer.status_code == 400

    def test_the_other_member_cannot_log_from_it(self, member_b, plan_id):
        answer = member_b.post(f"/api/plans/{plan_id}/log",
                               json={"date": "2026-09-14"})
        assert answer.status_code == 400

    def test_the_other_member_cannot_edit_a_movement(self, member_a, member_b, plan_id):
        (movement, *_) = member_a.get(f"/api/plans/{plan_id}/movements").get_json()
        answer = member_b.patch(f"/api/logs/plan_movements/{movement[0]}",
                                json={"col": "weight_kg", "val": 99})
        assert answer.status_code == 404

    def test_both_members_may_hold_a_cycle_of_the_same_name(self, member_b, plan_id):
        assert member_b.post("/api/plans", json=CYCLE).status_code == 200


class TestReadingACycle:
    def test_sessions_come_back_in_calendar_order(self, member_a, plan_id):
        rows = member_a.get(f"/api/plans/{plan_id}/sessions").get_json()
        assert [row[1] for row in rows] == ["2026-09-14", "2026-09-15"]

    def test_a_session_reports_how_many_movements_it_holds(self, member_a, plan_id):
        (upper, lower) = member_a.get(f"/api/plans/{plan_id}/sessions").get_json()
        assert (upper[-1], lower[-1]) == (2, 1)

    def test_a_movement_carries_the_day_it_belongs_to(self, member_a, plan_id):
        rows = member_a.get(f"/api/plans/{plan_id}/movements").get_json()
        assert [(row[1], row[4]) for row in rows] == [
            ("2026-09-14", "Overhead Press"), ("2026-09-14", "Plank"),
            ("2026-09-15", "Overhead Press")]

    def test_a_movement_carries_the_metric_its_target_is_in(self, member_a, plan_id):
        rows = member_a.get(f"/api/plans/{plan_id}/movements").get_json()
        assert [row[-1] for row in rows] == ["Reps", "Seconds", "Reps"]


class TestEditingAPlanInPlace:
    @pytest.fixture
    def movement_id(self, member_a, plan_id):
        (row, *_) = member_a.get(f"/api/plans/{plan_id}/movements").get_json()
        return row[0]

    def test_a_load_can_be_corrected(self, member_a, plan_id, movement_id):
        assert member_a.patch(f"/api/logs/plan_movements/{movement_id}",
                              json={"col": "weight_kg", "val": 18.5}).status_code == 200
        (row, *_) = member_a.get(f"/api/plans/{plan_id}/movements").get_json()
        assert row[8] == 18.5

    def test_the_movement_itself_can_be_swapped_by_name(
        self, member_a, plan_id, movement_id
    ):
        member_a.patch(f"/api/logs/plan_movements/{movement_id}",
                       json={"col": "exercise_item_id", "val": "Plank"})
        (row, *_) = member_a.get(f"/api/plans/{plan_id}/movements").get_json()
        assert row[4] == "Plank"

    def test_a_column_the_plan_derives_is_not_writable(
        self, member_a, movement_id
    ):
        answer = member_a.patch(f"/api/logs/plan_movements/{movement_id}",
                                json={"col": "session_id", "val": 2})
        assert answer.status_code == 400

    def test_deleting_a_session_takes_its_movements_with_it(
        self, member_a, plan_id
    ):
        (upper, _lower) = member_a.get(f"/api/plans/{plan_id}/sessions").get_json()
        member_a.delete(f"/api/logs/plan_sessions/{upper[0]}")
        rows = member_a.get(f"/api/plans/{plan_id}/movements").get_json()
        assert [row[1] for row in rows] == ["2026-09-15"]


class TestLoggingAPlannedSession:
    def test_every_movement_becomes_one_ordinary_exercise_row(
        self, member_a, plan_id
    ):
        answer = member_a.post(f"/api/plans/{plan_id}/log",
                               json={"date": "2026-09-14"})
        assert answer.get_json() == {"status": "success", "rows": 2,
                                     "session": "Upper A"}
        assert len(member_a.get("/api/logs/exercise").get_json()) == 2

    def test_the_bottom_of_the_range_is_what_is_written(self, member_a, plan_id):
        member_a.post(f"/api/plans/{plan_id}/log", json={"date": "2026-09-14"})
        press = [row for row in member_a.get("/api/logs/exercise").get_json()
                 if row[2] == "Overhead Press"][0]
        assert press[4:9] == [8, 8, 8, 0, 0]

    def test_the_prescribed_load_and_effort_come_with_it(self, member_a, plan_id):
        member_a.post(f"/api/plans/{plan_id}/log", json={"date": "2026-09-14"})
        press = [row for row in member_a.get("/api/logs/exercise").get_json()
                 if row[2] == "Overhead Press"][0]
        assert (press[9], press[10]) == (16.5, 7.0)

    def test_a_seconds_movement_writes_its_hold(self, member_a, plan_id):
        member_a.post(f"/api/plans/{plan_id}/log", json={"date": "2026-09-14"})
        plank = [row for row in member_a.get("/api/logs/exercise").get_json()
                 if row[2] == "Plank"][0]
        assert plank[4:9] == [30, 30, 30, 0, 0]

    def test_a_day_with_nothing_planned_is_refused(self, member_a, plan_id):
        answer = member_a.post(f"/api/plans/{plan_id}/log",
                               json={"date": "2026-09-16"})
        assert answer.status_code == 400
        assert "2026-09-16" in answer.get_json()["error"]

    def test_a_malformed_date_is_refused_rather_than_read_as_today(
        self, member_a, plan_id
    ):
        answer = member_a.post(f"/api/plans/{plan_id}/log",
                               json={"date": "14.09.2026"})
        assert answer.status_code == 400

    def test_the_rows_are_not_attributed_to_a_workout(self, member_a, plan_id):
        member_a.post(f"/api/plans/{plan_id}/log", json={"date": "2026-09-14"})
        assert all(row[3] is None
                   for row in member_a.get("/api/logs/exercise").get_json())

    def test_a_movement_whose_exercise_was_deleted_refuses_the_whole_session(
        self, member_a, plan_id
    ):
        member_a.delete("/api/catalog/items/Plank")
        answer = member_a.post(f"/api/plans/{plan_id}/log",
                               json={"date": "2026-09-14"})
        assert answer.status_code == 400
        assert not member_a.get("/api/logs/exercise").get_json()


class TestDeletingACycle:
    def test_it_takes_its_sessions_and_movements_with_it(self, member_a, plan_id):
        assert member_a.delete(f"/api/logs/training_plans/{plan_id}").status_code == 200
        assert member_a.get("/api/plans").get_json() == []

    def test_the_exercise_rows_it_produced_survive_it(self, member_a, plan_id):
        member_a.post(f"/api/plans/{plan_id}/log", json={"date": "2026-09-14"})
        member_a.delete(f"/api/logs/training_plans/{plan_id}")
        assert len(member_a.get("/api/logs/exercise").get_json()) == 2
