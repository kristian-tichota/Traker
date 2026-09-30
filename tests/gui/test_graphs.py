import numpy as np
import pytest

from src.database.rows import BeverageLogRow, DailyTotals, ExerciseLogRow
from src.gui.graphs.caffeine_graph import CaffeineGraphView
from src.gui.graphs.exercise_graph import timelines_by_name
from src.gui.graphs.food_graph import FoodGraphView

pytestmark = pytest.mark.gui


@pytest.fixture
def food_graph(qapp, profile_path, recording_db, settled):
    view = FoodGraphView(recording_db)
    view.pulse_timer.stop()
    settled()
    yield view
    view.deleteLater()


@pytest.fixture
def caffeine_graph(qapp, profile_path, recording_db):
    view = CaffeineGraphView(recording_db)
    view.pulse_timer.stop()
    yield view
    view.deleteLater()


def aggregate(date, calories=0.0, protein=0.0, carbs=0.0,
              fat=0.0, salt=0.0, fibre=0.0, sugar=0.0,
              estimated_kcal=0.0, estimated_rows=0, burn=0.0):
    return DailyTotals(date, calories, protein, carbs, fat, salt, fibre, sugar,
                       estimated_kcal, estimated_rows, burn)


class TestRollingAverage:
    def test_a_window_of_one_returns_the_raw_series(self, food_graph):
        raw = np.array([100.0, 200.0, 300.0, 400.0, 500.0])

        np.testing.assert_array_equal(food_graph._compute_rolling_avg(raw, window=1), raw)

    def test_a_window_of_three_averages_each_run_of_three(self, food_graph):
        raw = np.array([100.0, 200.0, 300.0, 400.0, 500.0])

        smoothed = food_graph._compute_rolling_avg(raw, window=3)

        np.testing.assert_allclose(smoothed, [200.0, 300.0, 400.0])

    def test_smoothing_shortens_the_series_by_the_window(self, food_graph):
        raw = np.arange(30, dtype=float)

        assert len(food_graph._compute_rolling_avg(raw, window=7)) == 30 - 7 + 1

    def test_a_window_longer_than_the_data_yields_no_points(self, food_graph):
        raw = np.array([100.0, 200.0])

        assert len(food_graph._compute_rolling_avg(raw, window=7)) == 0

    def test_a_window_wider_than_the_history_still_renders(self, food_graph):
        food_graph.rolling_period = 7
        rows = [aggregate(f"2026-09-{day:02d}", calories=2000.0) for day in range(1, 4)]

        food_graph.draw_chart(rows)

        assert food_graph.anim_nodes == [], "nothing to pulse without a point"

    def test_a_flat_series_smooths_to_itself(self, food_graph):
        raw = np.full(10, 2000.0)

        np.testing.assert_allclose(food_graph._compute_rolling_avg(raw, window=7), 2000.0)


class TestNutrientChart:
    def test_the_window_follows_the_stored_preference(self, qapp, profile_path, recording_db, settled):
        recording_db.settings["food_graph_period"] = "7 Days (Weekly Average)"

        view = FoodGraphView(recording_db)
        view.pulse_timer.stop()
        settled()

        assert view.rolling_period == 7
        view.deleteLater()

    def test_the_default_window_is_a_single_day(self, food_graph):
        assert food_graph.rolling_period == 1

    def test_a_day_with_no_data_renders_an_empty_chart(self, food_graph):
        food_graph.draw_chart([])

        assert food_graph.anim_nodes == []

    def test_six_nutrients_are_charted(self, food_graph):
        rows = [aggregate(f"2026-09-{day:02d}", calories=2000.0 + day, protein=140.0,
                          fat=70.0, salt=5.0, fibre=30.0, sugar=40.0)
                for day in range(1, 11)]

        food_graph.draw_chart(rows)

        assert food_graph.axes.shape == (2, 3)
        assert len(food_graph.anim_nodes) == 6, "each chart pulses its latest point"

    def test_the_goal_lines_come_from_the_members_profile(self, food_graph):
        food_graph.profile.data = {
            "biometrics": {"weight_kg": 75.0, "height_cm": 180.0, "age": 30, "gender": "M"},
            "goals": {"activity_level": 1.55, "daily_adjustment_kcal": 200,
                      "protein_multiplier": 2.0, "salt_g": 5.0},
        }

        food_graph.draw_chart([aggregate("2026-09-01", calories=2000.0)])

        assert food_graph.profile.calculate_target_calories() == pytest.approx(2681.5)
        assert food_graph.profile.calculate_target_protein() == pytest.approx(150.0)

    def test_the_goal_line_is_the_one_the_calorie_bar_aims_at(self, food_graph):
        from src.domain import formulas

        food_graph.profile.data = {
            "biometrics": {"weight_kg": 75.0, "height_cm": 180.0, "age": 30, "gender": "M"},
            "goals": {"activity_level": 1.55, "daily_adjustment_kcal": 200,
                      "goal_type": "lose_weight", "protein_multiplier": 2.0},
        }

        assert food_graph.profile.calculate_target_calories() == pytest.approx(
            formulas.energy_target(food_graph.profile.calculate_tdee(), 200, "lose_weight")
        ) == pytest.approx(2481.5)


class TestCaffeineForecast:
    @staticmethod
    def beverage_row(date, time, caffeine):
        return BeverageLogRow.from_server(
            [1, date, time, "Black Coffee", None, 1.0, 0.0, caffeine], "0.0 hrs"
        )

    def test_an_empty_log_renders_an_empty_chart(self, caffeine_graph):
        caffeine_graph.draw_chart([])

        assert caffeine_graph.ax.get_ylim()[1] > 0, "the axes still frame the threshold"

    def test_the_chart_reads_the_members_own_half_life_and_threshold(self, caffeine_graph):
        caffeine_graph.profile.data = {
            "goals": {"sleep_time": "22:00", "caffeine_half_life": 6.0,
                      "max_sleep_caffeine": 40.0},
        }

        caffeine_graph.draw_chart([])

        assert caffeine_graph.profile.get_metric("goals", "caffeine_half_life") == 6.0

    def test_a_dose_drunk_after_bedtime_is_not_decayed_into_the_past(self, caffeine_graph):
        import datetime

        today = datetime.date.today().isoformat()
        caffeine_graph.profile.data = {"goals": {"sleep_time": "23:00"}}

        caffeine_graph.draw_chart([self.beverage_row(today, "23:30", 80.0)])

        assert caffeine_graph.ax.get_ylim()[1] >= 80.0

    def test_a_dose_drunk_long_before_bedtime_has_mostly_decayed(self, caffeine_graph):
        import datetime

        today = datetime.date.today().isoformat()
        caffeine_graph.profile.data = {
            "goals": {"sleep_time": "23:00", "caffeine_half_life": 5.0, "max_sleep_caffeine": 20.0},
        }

        caffeine_graph.draw_chart([self.beverage_row(today, "08:00", 80.0)])

        assert caffeine_graph.ax.get_ylim()[1] < 80.0

    def test_a_log_older_than_the_window_is_ignored(self, caffeine_graph):
        caffeine_graph.draw_chart([self.beverage_row("2020-01-01", "08:00", 400.0)])

        assert caffeine_graph.ax.get_ylim()[1] < 400.0

    def test_an_unparseable_time_does_not_break_the_chart(self, caffeine_graph):
        import datetime

        today = datetime.date.today().isoformat()

        caffeine_graph.draw_chart([self.beverage_row(today, "not a time", 80.0)])

        assert caffeine_graph.ax.get_ylim()[1] > 0


class TestTheEstimatedShareIsHatchedOnTheCalorieChart:
    @staticmethod
    def hatched(ax):
        return [artist for artist in ax.collections if artist.get_hatch()]

    def test_a_day_with_an_estimate_is_hatched(self, food_graph):
        food_graph.draw_chart([
            aggregate("2026-09-01", calories=2100.0, estimated_kcal=550.0,
                      estimated_rows=1)])

        assert self.hatched(food_graph.axes[0, 0])

    def test_nothing_is_hatched_when_nothing_was_estimated(self, food_graph):
        food_graph.draw_chart([aggregate("2026-09-01", calories=2100.0)])

        assert self.hatched(food_graph.axes[0, 0]) == []

    def test_only_the_calorie_panel_carries_it(self, food_graph):
        food_graph.draw_chart([
            aggregate("2026-09-01", calories=2100.0, protein=90.0,
                      estimated_kcal=550.0, estimated_rows=1)])

        others = [ax for row in food_graph.axes for ax in row
                  if ax is not food_graph.axes[0, 0]]
        assert all(self.hatched(ax) == [] for ax in others)

    def test_the_render_survives_a_window_wider_than_the_history(self, food_graph):
        food_graph.rolling_period = 7
        food_graph.draw_chart([
            aggregate(f"2026-09-{day:02d}", calories=2000.0, estimated_kcal=100.0,
                      estimated_rows=1) for day in range(1, 4)])

        assert self.hatched(food_graph.axes[0, 0]) == []


class TestTheCalorieChartCanNetOffTraining:
    @staticmethod
    def plotted(ax):
        return ax.lines[0].get_ydata()

    @staticmethod
    def burn_note(ax):
        return [text.get_text() for text in ax.texts if "trained off" in text.get_text()]

    def test_what_was_eaten_is_the_default(self, food_graph):
        assert food_graph.nets_training is False

    def test_the_series_follows_the_stored_preference(
        self, qapp, profile_path, recording_db, settled
    ):
        recording_db.settings["food_graph_calorie_series"] = "net"

        view = FoodGraphView(recording_db)
        view.pulse_timer.stop()
        settled()

        assert view.nets_training is True
        view.deleteLater()

    def test_both_preferences_are_read_in_one_request(self, food_graph, recording_db):
        assert ("food_graph_period", "food_graph_calorie_series") \
            in recording_db.setting_batches

    def test_the_eaten_series_plots_the_logged_energy(self, food_graph):
        food_graph.draw_chart([aggregate("2026-09-01", calories=2400.0, burn=600.0)])

        assert self.plotted(food_graph.axes[0, 0]) == pytest.approx([2400.0])

    def test_the_net_series_takes_the_training_burn_off(self, food_graph):
        food_graph.set_calorie_series("net")

        food_graph.draw_chart([aggregate("2026-09-01", calories=2400.0, burn=600.0)])

        assert self.plotted(food_graph.axes[0, 0]) == pytest.approx([1800.0])

    def test_a_day_without_training_plots_the_same_either_way(self, food_graph):
        day = aggregate("2026-09-01", calories=2400.0)
        food_graph.draw_chart([day])
        eaten = self.plotted(food_graph.axes[0, 0])

        food_graph.set_calorie_series("net")
        food_graph.reset_axes()
        food_graph.draw_chart([day])

        assert self.plotted(food_graph.axes[0, 0]) == pytest.approx(eaten)

    def test_the_panel_title_says_which_series_it_is(self, food_graph):
        food_graph.draw_chart([aggregate("2026-09-01", calories=2400.0)])
        assert food_graph.axes[0, 0].get_title().startswith("Calories")

        food_graph.set_calorie_series("net")
        food_graph.reset_axes()
        food_graph.draw_chart([aggregate("2026-09-01", calories=2400.0)])

        assert food_graph.axes[0, 0].get_title().startswith("Net Calories")

    def test_only_the_calorie_panel_is_netted(self, food_graph):
        food_graph.set_calorie_series("net")

        food_graph.draw_chart([aggregate("2026-09-01", calories=2400.0, protein=140.0,
                                         burn=600.0)])

        assert self.plotted(food_graph.axes[0, 1]) == pytest.approx([140.0])

    def test_the_net_series_says_what_it_took_off(self, food_graph):
        food_graph.set_calorie_series("net")

        food_graph.draw_chart([aggregate("2026-09-01", calories=2400.0, burn=600.0)])

        assert self.burn_note(food_graph.axes[0, 0]) == ["\u2212600 kcal/day trained off"]

    def test_the_eaten_series_says_nothing_about_a_burn(self, food_graph):
        food_graph.draw_chart([aggregate("2026-09-01", calories=2400.0, burn=600.0)])

        assert self.burn_note(food_graph.axes[0, 0]) == []

    def test_a_stretch_with_no_training_in_it_is_unannotated(self, food_graph):
        food_graph.set_calorie_series("net")

        food_graph.draw_chart([aggregate("2026-09-01", calories=2400.0)])

        assert self.burn_note(food_graph.axes[0, 0]) == []

    def test_choosing_from_the_control_remembers_the_series(self, food_graph,
                                                            recording_db, settled):
        food_graph.series_select.setCurrentText("Net of Training")
        settled()

        assert recording_db.settings["food_graph_calorie_series"] == "net"
        assert food_graph.nets_training is True

    def test_an_unsupported_series_is_refused_rather_than_adopted(self, food_graph):
        food_graph.set_calorie_series("gross")

        assert food_graph.nets_training is False


def logged(date, name, weight=60.0):
    return ExerciseLogRow.from_server(
        [1, date, name, None, 5, 5, 5, 0, 0, weight, 8.0, "Legs", "Reps"])


class TestATimelineIsReadByName:
    ROWS = [logged("2026-09-03", "Back Squat", 70.0), logged("2026-09-02", "Bench Press"),
            logged("2026-09-01", "back squat", 65.0), logged("2026-09-02", None)]

    def test_only_the_named_movement_is_read_oldest_first(self):
        timeline = timelines_by_name(self.ROWS, ["Back Squat"])["Back Squat"]

        assert [(date, weight) for date, _v, _o, _s, weight, _r in timeline] == [
            ("2026-09-01", 65.0), ("2026-09-03", 70.0)]

    def test_an_orphan_or_unrequested_name_reads_as_nothing(self):
        assert timelines_by_name(self.ROWS, ["Deadlift", None]) == {"Deadlift": []}

    def test_a_point_carries_what_the_hover_says(self):
        (point,) = timelines_by_name([logged("2026-09-01", "Plank")], ["Plank"])["Plank"]

        assert point[1:4] == (900.0, logged("2026-09-01", "Plank").one_rep_max, "5,5,5")
