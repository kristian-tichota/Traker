import pytest

from src.database.analytics import DBAnalyticsMixin
from src.database.rows import (DailyTotals, ExerciseLogRow, FoodLogRow,
                               MobilityLogRow)


class StubLogSource(DBAnalyticsMixin):
    def __init__(self, food=(), exercise=(), mobility=()):
        self._food = list(food)
        self._exercise = list(exercise)
        self._mobility = list(mobility)

    @staticmethod
    def _since(rows, since):
        return rows if since is None else [r for r in rows if r.date >= since]

    def get_food_logs(self, since=None):
        return self._since(self._food, since)

    def get_exercise_logs(self, since=None):
        return self._since(self._exercise, since)

    def get_mobility_logs(self, since=None):
        return self._since(self._mobility, since)


def food_row(date, cal=0.0, prot=0.0, carb=0.0, sugar=0.0, fat=0.0,
             sat_fat=0.0, salt=0.0, fibre=0.0, estimated=0):
    return FoodLogRow.from_server(
        [1, estimated, date, "Breakfast", "Rolled Oats", 1.0, 50.0, None,
         cal, prot, carb, sugar, fat, sat_fat, salt, fibre]
    )


def exercise_row(date, sets=(7, 7, 7, 0, 0), weight=30.0, rpe=7.0,
                 muscle_group="Shoulders", metric_type="Reps", name="Overhead Press"):
    return ExerciseLogRow.from_server(
        [1, date, name, None, *sets, weight, rpe, muscle_group, metric_type]
    )


def mobility_row(date, duration=30.0, mets=3.0, name="Hip Opener"):
    return MobilityLogRow.from_server([1, date, name, None, duration, mets])


class TestDailyAggregates:
    def test_rows_on_the_same_day_are_summed(self):
        source = StubLogSource(food=[
            food_row("2026-09-05", cal=300.0, prot=20.0),
            food_row("2026-09-05", cal=450.0, prot=15.0),
        ])

        (day,) = source.get_daily_aggregates()

        assert day[0] == "2026-09-05"
        assert day[1] == pytest.approx(750.0)
        assert day[2] == pytest.approx(35.0)

    def test_days_come_back_in_chronological_order(self):
        source = StubLogSource(food=[
            food_row("2026-09-05"), food_row("2026-09-01"), food_row("2026-09-03"),
        ])

        assert [day[0] for day in source.get_daily_aggregates()] == [
            "2026-09-01", "2026-09-03", "2026-09-05",
        ]

    def test_each_tracked_nutrient_lands_in_its_own_slot(self):
        source = StubLogSource(food=[food_row(
            "2026-09-05", cal=700.0, prot=30.0, carb=80.0,
            sugar=12.0, fat=25.0, salt=2.0, fibre=9.0,
        )])

        (day,) = source.get_daily_aggregates()

        assert day == ("2026-09-05", 700.0, 30.0, 80.0, 25.0, 2.0, 9.0, 12.0,
                       0.0, 0)

    def test_an_orphaned_row_contributes_zero_rather_than_failing(self):
        orphan = FoodLogRow.from_server(
            [1, 0, "2026-09-05", "Breakfast", None, 1.0, None, None, *([None] * 8)]
        )
        source = StubLogSource(food=[orphan, food_row("2026-09-05", cal=200.0)])

        (day,) = source.get_daily_aggregates()

        assert day[1] == pytest.approx(200.0)

    def test_no_logs_produce_no_days(self):
        assert StubLogSource().get_daily_aggregates() == []


class TestExerciseHistory:
    def test_only_the_named_movement_is_returned(self):
        source = StubLogSource(exercise=[
            exercise_row("2026-09-05", name="Overhead Press"),
            exercise_row("2026-09-05", name="Plank", metric_type="Seconds"),
        ])

        timeline = source.get_exercise_history_by_name("Overhead Press")

        assert len(timeline) == 1

    def test_the_lookup_ignores_capitalisation(self):
        source = StubLogSource(exercise=[exercise_row("2026-09-05")])

        assert len(source.get_exercise_history_by_name("overhead press")) == 1

    def test_an_orphaned_row_matches_nothing(self):
        source = StubLogSource(exercise=[exercise_row("2026-09-05", name=None)])

        assert source.get_exercise_history_by_name("Overhead Press") == []

    def test_the_timeline_is_ordered_oldest_first(self):
        source = StubLogSource(exercise=[
            exercise_row("2026-09-05"), exercise_row("2026-09-01"), exercise_row("2026-09-03"),
        ])

        dates = [point[0] for point in source.get_exercise_history_by_name("Overhead Press")]
        assert dates == ["2026-09-01", "2026-09-03", "2026-09-05"]

    @pytest.mark.exact
    def test_volume_and_estimate_for_repetition_work(self):
        source = StubLogSource(exercise=[exercise_row("2026-09-05", sets=(7, 7, 7, 0, 0))])

        (date, volume, onerm, sets_str, weight, rpe) = source.get_exercise_history_by_name(
            "Overhead Press"
        )[0]

        assert volume == pytest.approx(21 * 30.0)
        assert onerm == pytest.approx(30.0 / (1.0278 - 0.0278 * 7))
        assert (weight, rpe) == (30.0, 7.0)

    def test_trailing_empty_sets_are_trimmed_from_the_label(self):
        source = StubLogSource(exercise=[exercise_row("2026-09-05", sets=(10, 8, 0, 0, 0))])

        assert source.get_exercise_history_by_name("Overhead Press")[0][3] == "10,8"

    def test_a_row_with_no_sets_is_labelled_zero(self):
        source = StubLogSource(exercise=[exercise_row("2026-09-05", sets=(0, 0, 0, 0, 0))])

        assert source.get_exercise_history_by_name("Overhead Press")[0][3] == "0"

    def test_time_based_work_reports_no_volume_and_no_maximum(self):
        source = StubLogSource(exercise=[exercise_row(
            "2026-09-05", sets=(60, 45, 0, 0, 0), weight=0.0,
            metric_type="Seconds", name="Plank",
        )])

        (point,) = source.get_exercise_history_by_name("Plank")
        _, volume, onerm, sets_str, _, _ = point

        assert volume == 0.0
        assert onerm == 0.0
        assert sets_str == "60,45", "the sets themselves are still shown"

    def test_it_agrees_with_the_exercise_tab(self):
        row = exercise_row("2026-09-05", sets=(60, 45, 0, 0, 0), weight=0.0,
                           metric_type="Seconds", name="Plank")
        source = StubLogSource(exercise=[row])

        (point,) = source.get_exercise_history_by_name("Plank")

        assert point[1] == row.volume
        assert point[3] == row.sets_display
        assert row.onerm == "N/A"

    def test_a_harder_effort_contributes_more(self, profile_path):
        def burn(rpe):
            source = StubLogSource(exercise=[exercise_row("2026-09-05", rpe=rpe, muscle_group="Legs")])
            return source.get_activity_heatmap_data()["2026-09-05"]["breakdown"]["Exercise_MET_hrs"]

        assert burn(9.0) > burn(7.0) > burn(5.0)

    def test_an_effort_rating_outside_the_scale_is_clamped(self, profile_path):
        def burn(rpe):
            source = StubLogSource(exercise=[exercise_row("2026-09-05", rpe=rpe, muscle_group="Legs")])
            return source.get_activity_heatmap_data()["2026-09-05"]["breakdown"]["Exercise_MET_hrs"]

        assert burn(50.0) == pytest.approx(burn(10.0))
        assert burn(0.0) == pytest.approx(burn(1.0))

    def test_a_row_with_no_working_sets_contributes_nothing(self, profile_path):
        source = StubLogSource(exercise=[exercise_row("2026-09-05", sets=(0, 0, 0, 0, 0))])

        assert source.get_activity_heatmap_data()["2026-09-05"]["breakdown"] == {}

    @pytest.mark.exact
    def test_mobility_work_is_duration_times_intensity_above_baseline(self, profile_path):
        source = StubLogSource(mobility=[mobility_row("2026-09-05", duration=30.0, mets=3.0)])

        points = source.get_activity_heatmap_data()

        expected = (3.0 - 1.55) * (30.0 / 60.0) * 0.85
        assert points["2026-09-05"]["breakdown"]["Mobility"] == pytest.approx(expected)

    def test_work_below_the_baseline_never_contributes_a_negative_amount(self, profile_path):
        source = StubLogSource(mobility=[mobility_row("2026-09-05", duration=60.0, mets=1.0)])

        assert source.get_activity_heatmap_data()["2026-09-05"]["breakdown"]["Mobility"] == 0.0

    def test_the_estimate_is_discounted_by_the_configured_share(self, write_profile):
        write_profile("[goals]\nactivity_level = 1.55\nneat_tax_percent = 50.0\n")
        source = StubLogSource(mobility=[mobility_row("2026-09-05", duration=60.0, mets=3.55)])

        points = source.get_activity_heatmap_data()

        assert points["2026-09-05"]["breakdown"]["Mobility"] == pytest.approx(2.0 * 1.0 * 0.5)

    def test_a_hundred_percent_tax_withholds_everything(self, write_profile):
        write_profile("[goals]\nneat_tax_percent = 100.0\n")
        source = StubLogSource(mobility=[mobility_row("2026-09-05", mets=9.0)])

        assert source.get_activity_heatmap_data()["2026-09-05"]["breakdown"]["Mobility"] == 0.0

    def test_both_kinds_of_work_land_on_the_same_day(self, profile_path):
        source = StubLogSource(
            exercise=[exercise_row("2026-09-05", muscle_group="Legs")],
            mobility=[mobility_row("2026-09-05")],
        )

        breakdown = source.get_activity_heatmap_data()["2026-09-05"]["breakdown"]

        assert set(breakdown) == {"Exercise_MET_hrs", "Mobility"}

    def test_repeat_entries_on_one_day_accumulate(self, profile_path):
        source = StubLogSource(mobility=[
            mobility_row("2026-09-05", duration=30.0), mobility_row("2026-09-05", duration=30.0),
        ])
        single = StubLogSource(mobility=[mobility_row("2026-09-05", duration=30.0)])

        assert source.get_activity_heatmap_data()["2026-09-05"]["breakdown"]["Mobility"] == pytest.approx(
            2 * single.get_activity_heatmap_data()["2026-09-05"]["breakdown"]["Mobility"]
        )

    def test_no_activity_produces_no_points(self, profile_path):
        assert StubLogSource().get_activity_heatmap_data() == {}


class TestTheMixinThroughTheRealClient:
    PLANK = {"date": "2026-09-05", "ex_name": "Plank", "set1": 60, "set2": 45,
             "set3": 0, "set4": 0, "set5": 0, "weight_kg": 0.0, "rpe": 6.0}

    def test_time_based_work_reaches_the_seconds_branch_through_the_real_client(
        self, db_client, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/exercise", json=self.PLANK)

        (point,) = db_client.get_exercise_history_by_name("Plank")
        _, volume, onerm, sets_str, _, _ = point

        assert volume == 0.0, "time-based work has no volume"
        assert onerm == pytest.approx(0.0), "and no one-rep maximum"
        assert sets_str == "60,45"

    def test_repetition_work_still_charts_volume_and_the_estimate(
        self, db_client, seeded_catalog, member_a
    ):
        member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Overhead Press",
            "set1": 7, "set2": 7, "set3": 7, "set4": 0, "set5": 0,
            "weight_kg": 30.0, "rpe": 8.0,
        })

        (point,) = db_client.get_exercise_history_by_name("Overhead Press")
        _, volume, onerm, _, _, _ = point

        assert volume == pytest.approx(21 * 30.0)
        assert onerm == pytest.approx(30.0 / (1.0278 - 0.0278 * 7))

    def test_the_heatmap_reads_the_muscle_group_off_the_clients_row(
        self, db_client, seeded_catalog, member_a, profile_path
    ):
        member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Overhead Press",
            "set1": 7, "set2": 7, "set3": 7, "set4": 0, "set5": 0,
            "weight_kg": 30.0, "rpe": 7.0,
        })

        points = db_client.get_activity_heatmap_data()

        assert points["2026-09-05"]["breakdown"]["Exercise_MET_hrs"] > 0.0


class TestHowMuchOfADayWasGuessed:
    def test_a_day_with_no_estimates_reports_none(self):
        source = StubLogSource(food=[food_row("2026-09-05", cal=400.0)])

        (day,) = source.get_daily_aggregates()

        assert (day.estimated_kcal, day.estimated_rows) == (0.0, 0)
        assert day.estimated_share == 0.0

    def test_only_the_estimated_rows_are_counted(self):
        source = StubLogSource(food=[
            food_row("2026-09-05", cal=1550.0),
            food_row("2026-09-05", cal=550.0, estimated=1),
        ])

        (day,) = source.get_daily_aggregates()

        assert day.energy_kcal == pytest.approx(2100.0)
        assert day.estimated_kcal == pytest.approx(550.0)
        assert day.estimated_rows == 1
        assert day.estimated_share == pytest.approx(550.0 / 2100.0)

    def test_a_day_with_nothing_logged_has_no_share_rather_than_dividing_by_zero(self):
        assert DailyTotals.of("2026-09-05", []).estimated_share == 0.0
