import pytest

from src.database.rows import (BeverageLogRow, ExerciseLogRow, FoodLogRow,
                               MobilityLogRow, PlanMovementRow, PlanSessionRow,
                               SupplementLogRow, TrainingPlanRow)

BREAKFAST = {"date": "2026-09-05", "meal_type": "Breakfast",
             "food_name": "Rolled Oats", "servings": 2.0}
COFFEE = {"date": "2026-09-05", "time": "08:30", "bev_name": "Black Coffee", "servings": 1.0}
PRESS = {"date": "2026-09-05", "ex_name": "Overhead Press",
         "set1": 7, "set2": 9, "set3": 5, "set4": 0, "set5": 0,
         "weight_kg": 30.0, "rpe": 8.0}
STACK = {"date": "2026-09-05", "supp_name": "Morning Stack", "servings": 2.0}
STRETCH = {"date": "2026-09-05", "mob_name": "Hip Opener", "duration_mins": 20.0}


class TestFoodRow:
    def test_each_field_names_the_column_it_holds(self, db_client, seeded_catalog, member_a):
        member_a.post("/api/logs/food", json=BREAKFAST)

        (row,) = db_client.get_food_logs()

        assert isinstance(row, FoodLogRow)
        assert (row.date, row.meal_type, row.name, row.servings) == (
            "2026-09-05", "Breakfast", "Rolled Oats", 2.0
        )
        assert row.energy_kcal == pytest.approx(380.0 * 0.5 * 2.0)
        assert row.protein_g == pytest.approx(13.0 * 0.5 * 2.0)
        assert row.fibre_g == pytest.approx(10.0 * 0.5 * 2.0)


class TestBeverageRow:
    def test_each_field_names_the_column_it_holds(self, db_client, seeded_catalog, member_a):
        member_a.post("/api/logs/beverage", json=COFFEE)

        (row,) = db_client.get_beverage_logs()

        assert isinstance(row, BeverageLogRow)
        assert (row.date, row.time, row.name) == ("2026-09-05", "08:30", "Black Coffee")
        assert row.caffeine_mg == pytest.approx(80.0)
        assert row.antioxidants_mg == pytest.approx(200.0)
        assert row.sleep_wait.endswith(" hrs")

    def test_the_wait_is_the_last_column_the_table_renders(
        self, db_client, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/beverage", json=COFFEE)

        (row,) = db_client.get_beverage_logs()

        assert row[-1] == row.sleep_wait


class TestExerciseRow:
    def test_each_field_names_the_column_it_holds(self, db_client, seeded_catalog, member_a):
        member_a.post("/api/logs/exercise", json=PRESS)

        (row,) = db_client.get_exercise_logs()

        assert isinstance(row, ExerciseLogRow)
        assert (row.date, row.name, row.muscle_group) == (
            "2026-09-05", "Overhead Press", "Shoulders"
        )
        assert row.sets == (7, 9, 5, 0, 0)
        assert (row.weight_kg, row.rpe) == (30.0, 8.0)
        assert (row.total_reps, row.max_reps) == (21, 9)

    def test_the_metric_type_survives_the_reshaping(
        self, db_client, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/exercise", json=PRESS)
        member_a.post("/api/logs/exercise", json=dict(
            PRESS, ex_name="Plank", set1=60, set2=45, set3=0, weight_kg=0.0,
        ))

        by_name = {row.name: row for row in db_client.get_exercise_logs()}

        assert by_name["Overhead Press"].metric_type == "Reps"
        assert by_name["Plank"].metric_type == "Seconds"

    def test_the_columns_the_exercise_tab_renders_stop_before_the_metric_type(
        self, db_client, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/exercise", json=PRESS)

        (row,) = db_client.get_exercise_logs()

        assert row[1:ExerciseLogRow.DISPLAY_COLUMNS + 1][-1] == row.onerm
        assert len(row) == ExerciseLogRow.DISPLAY_COLUMNS + 2, "id, the shown columns, metric_type"


class TestSupplementRow:
    def test_each_field_names_the_column_it_holds(self, db_client, seeded_catalog, member_a):
        member_a.post("/api/logs/supplement", json=STACK)

        (row,) = db_client.get_supplement_logs()

        assert isinstance(row, SupplementLogRow)
        assert (row.date, row.name, row.servings) == ("2026-09-05", "Morning Stack", 2.0)
        assert row.b12_mcg == pytest.approx(1000.0), "500 mcg, two servings"
        assert row.creatine_g == pytest.approx(10.0)
        assert row.zinc_mg == pytest.approx(30.0)


class TestMobilityRow:
    def test_each_field_names_the_column_it_holds(self, db_client, seeded_catalog, member_a):
        member_a.post("/api/logs/mobility", json=STRETCH)

        (row,) = db_client.get_mobility_logs()

        assert isinstance(row, MobilityLogRow)
        assert (row.date, row.name) == ("2026-09-05", "Hip Opener")
        assert row.duration_mins == pytest.approx(20.0)
        assert row.mets == pytest.approx(3.0), "intensity comes from the catalog, not the log"


class TestRowsAreStillTuples:
    def test_a_row_indexes_and_unpacks_like_the_list_it_replaced(
        self, db_client, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/mobility", json=STRETCH)

        (row,) = db_client.get_mobility_logs()
        row_id, date, name, routine_set, duration, mets = row

        assert isinstance(row, tuple)
        assert (row[0], row[1], row[5]) == (row_id, date, mets)
        assert (name, duration) == ("Hip Opener", 20.0)
        assert routine_set is None, "logged on its own, not as part of a set"


class TestPlanRows:
    CYCLE = {
        "name": "Cycle 1", "start_date": "2026-09-14", "weeks": 4,
        "sessions": [{
            "date": "2026-09-14", "week": 1, "name": "Upper A", "block": "re-entry",
            "movements": [{"exercise": "Overhead Press", "sets": 3,
                           "target_low": 8, "target_high": 12,
                           "weight_kg": 16.5, "rpe": 7.0, "tempo": "3/3"}],
        }],
    }

    @pytest.fixture
    def cycle_id(self, db_client, seeded_catalog, member_a):
        return member_a.post("/api/plans", json=self.CYCLE).get_json()["plan_id"]

    def test_a_cycle_names_the_columns_it_holds(self, db_client, cycle_id):
        (row,) = db_client.get_training_plans()

        assert isinstance(row, TrainingPlanRow)
        assert (row.name, row.start_date, row.weeks) == ("Cycle 1", "2026-09-14", 4)
        assert row.session_count == 1

    def test_a_session_names_the_columns_it_holds(self, db_client, cycle_id):
        (row,) = db_client.get_plan_sessions(cycle_id)

        assert isinstance(row, PlanSessionRow)
        assert (row.date, row.week, row.name) == ("2026-09-14", 1, "Upper A")
        assert (row.block, row.movement_count) == ("re-entry", 1)

    def test_a_movement_names_the_columns_it_holds(self, db_client, cycle_id):
        (row,) = db_client.get_plan_movements(cycle_id)

        assert isinstance(row, PlanMovementRow)
        assert (row.date, row.session, row.name) == (
            "2026-09-14", "Upper A", "Overhead Press")
        assert (row.sets, row.target_low, row.target_high) == (3, 8.0, 12.0)
        assert (row.weight_kg, row.rpe, row.tempo) == (16.5, 7.0, "3/3")

    def test_a_movement_carries_the_metric_its_target_is_measured_in(
        self, db_client, cycle_id
    ):
        (row,) = db_client.get_plan_movements(cycle_id)

        assert row.metric_type == "Reps"

    def test_logging_a_planned_session_writes_ordinary_exercise_rows(
        self, db_client, cycle_id
    ):
        success, _message = db_client.log_planned_session({"date": "2026-09-14"})

        (row,) = db_client.get_exercise_logs()
        assert success
        assert isinstance(row, ExerciseLogRow)
        assert (row.name, row.sets, row.weight_kg) == (
            "Overhead Press", (8, 8, 8, 0, 0), 16.5)

    def test_a_household_with_no_plan_refuses_rather_than_writing(self, db_client):
        success, message = db_client.log_planned_session({"date": "2026-09-14"})

        assert not success
        assert "no training plan" in message.lower()
