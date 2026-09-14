import math

import pytest

from src.database.rows import ExerciseLogRow

from src.config import CAFFEINE_HALF_LIFE, SLEEP_CAFFEINE_THRESHOLD

PRESS = {"date": "2026-09-05", "ex_name": "Overhead Press",
         "set1": 7, "set2": 7, "set3": 7, "set4": 0, "set5": 0,
         "weight_kg": 30.0, "rpe": 8.0}

EX = {field: index for index, field in enumerate(ExerciseLogRow._fields)}
EX["weight"] = EX["weight_kg"]


class TestExerciseDerivations:
    @pytest.mark.exact
    def test_volume_is_total_repetitions_times_the_weight(self, db_client, seeded_catalog, member_a):
        member_a.post("/api/logs/exercise", json=PRESS)

        (row,) = db_client.get_exercise_logs()

        assert row[EX["total_reps"]] == 21
        assert row[EX["volume"]] == pytest.approx(21 * 30.0)

    @pytest.mark.exact
    @pytest.mark.parametrize(
        "best_set, weight",
        [(1, 30.0), (5, 30.0), (7, 30.0), (12, 42.5)],
    )
    def test_the_one_rep_maximum_follows_the_epley_style_formula(
        self, db_client, seeded_catalog, member_a, best_set, weight
    ):
        member_a.post("/api/logs/exercise", json=dict(
            PRESS, set1=best_set, set2=0, set3=0, weight_kg=weight,
        ))

        (row,) = db_client.get_exercise_logs()

        expected = weight / (1.0278 - (0.0278 * best_set))
        assert row[EX["onerm"]] == f"{expected:.1f}"

    @pytest.mark.exact
    def test_the_best_single_set_drives_the_estimate_not_the_last_one(
        self, db_client, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/exercise", json=dict(PRESS, set1=5, set2=12, set3=3))

        (row,) = db_client.get_exercise_logs()

        assert row[EX["max_reps"]] == 12
        assert row[EX["onerm"]] == f"{30.0 / (1.0278 - 0.0278 * 12):.1f}"

    @pytest.mark.exact
    def test_a_row_with_no_repetitions_reports_a_zero_estimate(
        self, db_client, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/exercise", json=dict(PRESS, set1=0, set2=0, set3=0))

        (row,) = db_client.get_exercise_logs()

        assert row[EX["onerm"]] == "0.0"

    @pytest.mark.exact
    @pytest.mark.parametrize("best_set", [37, 60])
    def test_a_set_past_the_formulas_domain_reports_no_estimate(
        self, db_client, seeded_catalog, member_a, best_set
    ):
        member_a.post("/api/logs/exercise", json=dict(PRESS, set1=best_set, set2=0, set3=0))

        (row,) = db_client.get_exercise_logs()

        assert row[EX["onerm"]] == "N/A"
        assert row[EX["volume"]] == pytest.approx(best_set * 30.0), "volume is still meaningful"

    def test_time_based_work_reports_no_volume_and_no_estimate(
        self, db_client, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/exercise",
                      json=dict(PRESS, ex_name="Plank", set1=60, set2=45, set3=0))

        (row,) = db_client.get_exercise_logs()

        assert row[EX["volume"]] == 0.0
        assert row[EX["onerm"]] == "N/A"
        assert row[EX["total_reps"]] == 105, "the seconds still accumulate"

    def test_set_counts_are_presented_as_whole_numbers(self, db_client, seeded_catalog, member_a):
        member_a.post("/api/logs/exercise", json=PRESS)

        (row,) = db_client.get_exercise_logs()

        assert [row[EX["set1"] + n] for n in range(5)] == [7, 7, 7, 0, 0]
        assert all(isinstance(value, int) for value in row[EX["set1"]:EX["set1"] + 5])


class TestCaffeineWait:
    def _log(self, member_a, caffeine_mg, servings=1.0):
        member_a.post("/api/catalog/beverage", json={
            "name": f"Drink {caffeine_mg}", "caffeine_mg": caffeine_mg, "antioxidants_mg": 0.0,
        })
        member_a.post("/api/logs/beverage", json={
            "date": "2026-09-05", "time": "08:30",
            "bev_name": f"Drink {caffeine_mg}", "servings": servings,
        })

    @pytest.mark.exact
    @pytest.mark.parametrize("caffeine_mg", [80.0, 160.0, 21.0])
    def test_a_dose_above_the_threshold_reports_a_half_life_decay(
        self, db_client, member_a, caffeine_mg
    ):
        self._log(member_a, caffeine_mg)

        (row,) = db_client.get_beverage_logs()

        expected = CAFFEINE_HALF_LIFE * math.log2(caffeine_mg / SLEEP_CAFFEINE_THRESHOLD)
        assert row[-1] == f"{expected:.1f} hrs"

    @pytest.mark.parametrize("caffeine_mg", [0.0, 5.0, SLEEP_CAFFEINE_THRESHOLD])
    def test_a_dose_at_or_below_the_threshold_needs_no_wait(self, db_client, member_a, caffeine_mg):
        self._log(member_a, caffeine_mg)

        (row,) = db_client.get_beverage_logs()

        assert row[-1] == "0.0 hrs"

    def test_the_wait_is_computed_from_the_scaled_dose(self, db_client, member_a):
        self._log(member_a, 80.0, servings=2.0)

        (row,) = db_client.get_beverage_logs()

        expected = CAFFEINE_HALF_LIFE * math.log2(160.0 / SLEEP_CAFFEINE_THRESHOLD)
        assert row[-1] == f"{expected:.1f} hrs"

    def test_an_orphaned_drink_needs_no_wait(self, db_client, member_a):
        self._log(member_a, 80.0)
        member_a.delete("/api/catalog/items/Drink 80.0")

        (row,) = db_client.get_beverage_logs()

        assert row[-1] == "0.0 hrs"

    def test_the_wait_honours_the_members_own_caffeine_settings(
        self, db_client, member_a, profile_path
    ):
        profile_path.write_text(
            "[goals]\ncaffeine_half_life = 6.0\nmax_sleep_caffeine = 40.0\n", encoding="utf-8"
        )
        self._log(member_a, 80.0)

        (row,) = db_client.get_beverage_logs()

        assert row[-1] == f"{6.0 * math.log2(80.0 / 40.0):.1f} hrs"
