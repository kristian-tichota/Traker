import pytest

from src.gui.completion import best_match, completion_tail
from tests.conftest import BLACK_COFFEE, HIP_OPENER, MORNING_STACK, OATS, OVERHEAD_PRESS


class TestCatalogRoundTrip:
    def test_food_tuples_are_ordered_for_the_food_database_table(self, db_client):
        db_client.add_food_item(OATS)

        (item,) = db_client.get_all_foods()

        assert len(item) == 12
        assert item[1] == "Rolled Oats"
        assert item[2] == "Carbs"
        assert item[3] == 380.0
        assert item[9] == 13.0
        assert item[11] == 50.0

    def test_beverage_tuples_carry_caffeine_then_antioxidants(self, db_client):
        db_client.add_beverage_item(BLACK_COFFEE)

        (item,) = db_client.get_all_beverages()

        assert item[1:] == ("Black Coffee", 80.0, 200.0)

    def test_exercise_tuples_end_with_the_metric_type(self, db_client):
        db_client.add_exercise_item(OVERHEAD_PRESS)

        (item,) = db_client.get_all_exercises()

        assert len(item) == 10
        assert item[1] == "Overhead Press"
        assert item[9] == "Reps"

    def test_supplement_tuples_list_every_micronutrient(self, db_client):
        db_client.add_supplement_item(MORNING_STACK)

        (item,) = db_client.get_all_supplements()

        assert len(item) == 14
        assert item[2] == 500.0
        assert item[4] == 5.0

    def test_mobility_tuples_carry_intensity_and_notes(self, db_client):
        db_client.add_mobility_item(HIP_OPENER)

        (item,) = db_client.get_all_mobility()

        assert item[1:] == ("Hip Opener", 3.0, "Daily")

    def test_exercise_names_are_offered_for_completion(self, db_client):
        db_client.add_exercise_item(OVERHEAD_PRESS)
        db_client.add_exercise_item(dict(OVERHEAD_PRESS, name="Plank", metric_type="Seconds"))

        assert set(db_client.get_all_exercise_names()) == {"Overhead Press", "Plank"}

    def test_a_rejected_definition_comes_back_as_a_reason(self, db_client):
        db_client.add_food_item(OATS)

        success, message = db_client.add_food_item(OATS)

        assert success is False
        assert "UNIQUE constraint failed" in message

    def test_a_successful_definition_reports_success(self, db_client):
        assert db_client.add_food_item(OATS) == (True, "Success")


class TestLogRoundTrip:
    @pytest.fixture
    def stocked(self, db_client):
        db_client.add_food_item(OATS)
        db_client.add_beverage_item(BLACK_COFFEE)
        db_client.add_exercise_item(OVERHEAD_PRESS)
        db_client.add_supplement_item(MORNING_STACK)
        db_client.add_mobility_item(HIP_OPENER)
        return db_client

    def test_a_food_log_round_trips_with_derived_macros(self, stocked):
        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 2.0})

        (row,) = stocked.get_food_logs()

        assert row.meal_type == "Breakfast"
        assert row.name == "Rolled Oats"
        assert row.energy_kcal == pytest.approx(380.0 * 0.5 * 2.0)
        assert (row.servings, row.grams) == (2.0, pytest.approx(100.0))

    def test_logging_an_unknown_item_returns_the_servers_reason(self, stocked):
        success, message = stocked.add_food_log({
            "date": "2026-09-05", "meal_type": "Breakfast",
            "food_name": "Ghost Oats", "servings": 1.0,
        })

        assert success is False
        assert "Ghost Oats" in message

    def test_a_mobility_log_round_trips(self, stocked):
        stocked.add_mobility_log({"date": "2026-09-05", "mob_name": "Hip Opener",
                                  "duration_mins": 20.0})

        (row,) = stocked.get_mobility_logs()

        assert (row.name, row.duration_mins, row.mets) == ("Hip Opener", 20.0, 3.0)
        assert row.routine_set is None

    def test_a_supplement_log_round_trips(self, stocked):
        stocked.add_supplement_log({"date": "2026-09-05", "supp_name": "Morning Stack",
                                    "servings": 1.0})

        (row,) = stocked.get_supplement_logs()

        assert row.name == "Morning Stack"
        assert row.b12_mcg == 500.0
        assert row.stack is None

    def test_deleting_a_record_removes_only_that_row(self, stocked):
        for servings in (1.0, 2.0):
            stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                                  "food_name": "Rolled Oats", "servings": servings})
        rows = stocked.get_food_logs()

        assert stocked.delete_record("food_logs", rows[0][0]) == (True, "Success")
        assert len(stocked.get_food_logs()) == 1

    def test_an_inline_edit_translates_the_header_to_a_column(self, stocked):
        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 1.0})
        (row,) = stocked.get_food_logs()

        success, _ = stocked.update_record(
            "food_logs", row[0], "Servings", "3", {"Servings": "servings"}
        )

        assert success is True
        assert stocked.get_food_logs()[0].servings == 3.0

    def test_an_unmapped_header_never_reaches_the_server(self, stocked):
        success, message = stocked.update_record("food_logs", 1, "Mystery", "1", {})

        assert success is False
        assert "mapping failed" in message

    def test_removing_a_catalog_item_by_name_orphans_the_log(self, stocked):
        stocked.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                              "food_name": "Rolled Oats", "servings": 1.0})

        success, message = stocked.delete_item_by_name("Rolled Oats")
        assert success
        assert message == " Removed 'Rolled Oats' from 1 catalog.", (
            "the server counts what it removed; saying 'every catalog' for one "
            "row is the same overclaim as confirming a write that matched nothing"
        )

        (row,) = stocked.get_food_logs()
        assert row.name is None
        assert stocked.get_daily_aggregates()[0].energy_kcal == 0.0


class TestPerMemberSeparation:
    def test_each_client_sees_only_its_own_logs(self, db_client, db_client_b):
        db_client.add_food_item(OATS)
        db_client.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                                "food_name": "Rolled Oats", "servings": 1.0})

        assert len(db_client.get_food_logs()) == 1
        assert db_client_b.get_food_logs() == []

    def test_both_clients_see_the_same_catalog(self, db_client, db_client_b):
        db_client.add_food_item(OATS)

        assert db_client_b.get_all_foods() == db_client.get_all_foods()


class TestSettingsRoundTrip:
    def test_a_setting_round_trips(self, db_client):
        db_client.set_setting("food_graph_period", "7 Days (Weekly Average)")

        assert db_client.get_setting("food_graph_period", "1 Day (Raw)") == "7 Days (Weekly Average)"

    def test_an_unset_setting_returns_the_default(self, db_client):
        assert db_client.get_setting("never_set", "fallback") == "fallback"


class TestTelemetryRoundTrip:
    def test_heartbeats_come_back_keyed_by_fractional_minute(self, db_client):
        db_client.log_pomodoro_heartbeat({
            "date": "2026-09-05", "minute_of_day": 600, "second": 30,
            "state": "focus", "mode": "Default",
        })

        heartbeats = db_client.get_pomodoro_heartbeats_for_day("2026-09-05")

        assert heartbeats == {600.5: ("focus", "Default")}

    def test_a_whole_minute_keys_on_an_integer_valued_float(self, db_client):
        db_client.log_pomodoro_heartbeat({
            "date": "2026-09-05", "minute_of_day": 600, "second": 0,
            "state": "rest", "mode": "Default",
        })

        assert db_client.get_pomodoro_heartbeats_for_day("2026-09-05") == {600.0: ("rest", "Default")}

    def test_the_daily_summary_comes_back_as_tuples(self, db_client):
        import datetime

        today = datetime.date.today().isoformat()
        db_client.log_pomodoro_heartbeat({
            "date": today, "minute_of_day": 600, "second": 0,
            "state": "focus", "mode": "Default",
        })

        assert db_client.get_pomodoro_daily_summary() == [(today, 1, 0, 0, 0)]

    def test_timeline_events_come_back_as_tuples(self, db_client):
        db_client.log_pomodoro_event({
            "timestamp": "2026-09-05T10:00:00", "event_type": "skipped_focus",
            "amount_ms": 1000,
        })

        assert db_client.get_pomodoro_events_for_day("2026-09-05") == [
            ("2026-09-05T10:00:00", "skipped_focus", 1000)
        ]

    def test_an_override_round_trips_and_can_be_cleared(self, db_client):
        db_client.set_pomodoro_dsi_override({"date": "2026-09-05", "override_dsi": 0.6})
        assert db_client.get_pomodoro_dsi_overrides() == {"2026-09-05": 0.6}

        db_client.clear_pomodoro_dsi_override("2026-09-05")

        assert db_client.get_pomodoro_dsi_overrides() == {}


class TestCompletionsTheServerCanResolve:
    RIZEK = dict(OATS, name="Řízek s bramborem")

    @pytest.fixture
    def stocked(self, db_client):
        db_client.add_food_item(self.RIZEK)
        return db_client

    def _complete(self, typed, names):
        match = best_match(typed, names)
        tail = completion_tail(typed, match)
        return typed + tail if tail is not None else match

    @pytest.mark.parametrize("typed", ["rizek", "Rizek", "řízek", "Řízek s", "bramborem"])
    def test_an_accepted_completion_logs_against_the_catalog_item(self, stocked, typed):
        names = [item[1] for item in stocked.get_all_foods()]

        completed = self._complete(typed, names)
        success, message = stocked.add_food_log({
            "date": "2026-09-05", "servings": 1.0,
            "meal_type": "Lunch", "food_name": completed,
        })

        assert success, f"completing '{typed}' produced '{completed}', which {message}"

    def test_appending_the_tail_to_a_stripped_name_would_not_have_resolved(self, stocked):
        success, _ = stocked.add_food_log({
            "date": "2026-09-05", "servings": 1.0,
            "meal_type": "Lunch", "food_name": "rizek s bramborem",
        })

        assert success is False
