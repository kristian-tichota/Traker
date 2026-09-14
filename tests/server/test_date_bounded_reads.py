import pytest

LOGS = [
    ("food", "/api/logs/food", {"meal_type": "Breakfast", "food_name": "Rolled Oats",
                                "servings": 1.0}, 2),
    ("beverage", "/api/logs/beverage", {"time": "08:00", "bev_name": "Black Coffee",
                                        "servings": 1.0}, 1),
    ("exercise", "/api/logs/exercise", {"ex_name": "Overhead Press", "set1": 8,
                                        "weight_kg": 40.0, "rpe": 7.0}, 1),
    ("supplement", "/api/logs/supplement", {"supp_name": "Morning Stack",
                                            "servings": 1.0}, 1),
    ("mobility", "/api/logs/mobility", {"mob_name": "Hip Opener",
                                        "duration_mins": 20.0}, 1),
]

IDS = [name for name, _, _, _ in LOGS]


@pytest.fixture
def three_days(seeded_catalog):
    for _name, path, body, _date_at in LOGS:
        for date in ("2026-09-01", "2026-09-03", "2026-09-05"):
            response = seeded_catalog.post(path, json=dict(body, date=date))
            assert response.status_code == 200, response.get_data(as_text=True)
    return seeded_catalog


@pytest.mark.parametrize("name, path, _body, date_at", LOGS, ids=IDS)
class TestABoundedReadAnswersOnlyItsWindow:
    def test_without_a_bound_the_whole_ledger_comes_back(
            self, three_days, name, path, _body, date_at):
        assert len(three_days.get(path).get_json()) == 3

    def test_a_bound_excludes_everything_older(
            self, three_days, name, path, _body, date_at):
        rows = three_days.get(path, query_string={"since": "2026-09-03"}).get_json()

        assert [row[date_at] for row in rows] == ["2026-09-05", "2026-09-03"]

    def test_the_bound_is_inclusive_of_its_own_day(
            self, three_days, name, path, _body, date_at):
        rows = three_days.get(path, query_string={"since": "2026-09-05"}).get_json()

        assert [row[date_at] for row in rows] == ["2026-09-05"]

    def test_a_bound_past_the_history_answers_nothing(
            self, three_days, name, path, _body, date_at):
        assert three_days.get(path, query_string={"since": "2026-10-01"}).get_json() == []

    def test_an_empty_bound_is_the_same_as_none(
            self, three_days, name, path, _body, date_at):
        assert len(three_days.get(path, query_string={"since": ""}).get_json()) == 3

    def test_a_malformed_bound_is_refused_rather_than_ignored(
        self, three_days, name, path, _body, date_at
    ):
        response = three_days.get(path, query_string={"since": "05.09.2026"})

        assert response.status_code == 400
        assert "YYYY-MM-DD" in response.get_json()["error"]

    def test_the_bound_does_not_reach_across_members(
        self, three_days, member_b, name, path, _body, date_at
    ):
        assert member_b.get(path, query_string={"since": "2026-09-01"}).get_json() == []


class TestTheClientPassesItsWindowThrough:
    def test_a_bounded_getter_asks_for_only_its_window(self, db_client, three_days):
        assert len(db_client.get_food_logs(since="2026-09-03")) == 2

    def test_an_unbounded_getter_still_reads_the_ledger(self, db_client, three_days):
        assert len(db_client.get_food_logs()) == 3

    def test_the_activity_data_bounds_both_of_its_reads(self, db_client, three_days):
        points = db_client.get_activity_heatmap_data(since="2026-09-05")

        assert sorted(points) == ["2026-09-05"]

    def test_the_activity_data_is_unbounded_by_default(self, db_client, three_days):
        assert sorted(db_client.get_activity_heatmap_data()) == [
            "2026-09-01", "2026-09-03", "2026-09-05",
        ]
