import pytest

from src.config import PALETTE
from src.gui.components.calorie_bar import AnimatedProgressBar

pytestmark = pytest.mark.gui

BIOMETRICS = {"weight_kg": 75.0, "height_cm": 180.0, "age": 30, "gender": "M"}
MAINTENANCE = ((10 * 75.0) + (6.25 * 180.0) - (5 * 30) + 5) * 1.55


@pytest.fixture
def bar_factory(qapp, profile_path):
    created = []

    def _build(metric_type="calories", goals=None, biometrics=None):
        bar = AnimatedProgressBar(metric_type)
        bar.timer.stop()
        bar.profile.data = {
            "biometrics": dict(BIOMETRICS, **(biometrics or {})),
            "goals": dict({"activity_level": 1.55}, **(goals or {})),
        }
        bar._recalculate_targets()
        created.append(bar)
        return bar

    yield _build
    for bar in created:
        bar.deleteLater()


class TestEnergyTarget:
    @pytest.mark.parametrize(
        "goal, expected_offset",
        [("lose_weight", -300.0), ("gain_weight", +300.0), ("maintain_weight", 0.0)],
    )
    def test_the_target_follows_the_declared_goal(self, bar_factory, goal, expected_offset):
        bar = bar_factory(goals={"goal_type": goal, "daily_adjustment_kcal": 300})

        assert bar.target_val == pytest.approx(MAINTENANCE + expected_offset)

    def test_the_sign_comes_from_the_goal_not_from_the_number(self, bar_factory):
        losing = bar_factory(goals={"goal_type": "lose_weight", "daily_adjustment_kcal": 300})
        also_losing = bar_factory(goals={"goal_type": "lose_weight", "daily_adjustment_kcal": -300})

        assert losing.target_val < MAINTENANCE
        assert losing.target_val == pytest.approx(also_losing.target_val)

    def test_a_missing_goal_maintains_weight(self, bar_factory):
        bar = bar_factory(goals={"daily_adjustment_kcal": 300})

        assert bar.goal_type == "maintain_weight"
        assert bar.target_val == pytest.approx(MAINTENANCE)

    def test_the_goal_is_read_case_insensitively(self, bar_factory):
        bar = bar_factory(goals={"goal_type": " Lose_Weight ", "daily_adjustment_kcal": 300})

        assert bar.goal_type == "lose_weight"

    def test_two_members_score_the_same_catalog_against_opposite_targets(self, bar_factory):
        losing = bar_factory(goals={"goal_type": "lose_weight", "daily_adjustment_kcal": 400})
        gaining = bar_factory(goals={"goal_type": "gain_weight", "daily_adjustment_kcal": 400})

        assert losing.target_val == pytest.approx(MAINTENANCE - 400)
        assert gaining.target_val == pytest.approx(MAINTENANCE + 400)
        assert gaining.target_val - losing.target_val == pytest.approx(800)

    def test_the_scale_leaves_headroom_above_the_target(self, bar_factory):
        bar = bar_factory(goals={"goal_type": "gain_weight", "daily_adjustment_kcal": 300,
                                 "overflow_buffer": 500, "tick_markers": [-300, 0, 300]})

        assert bar.max_val > bar.target_val
        assert bar.max_buffer == 500


class TestOtherMetrics:
    def test_protein_targets_body_weight_times_the_multiplier(self, bar_factory):
        bar = bar_factory("protein", goals={"protein_multiplier": 2.0})

        assert bar.target_val == pytest.approx(150.0)
        assert bar.unit == "g prot"

    def test_salt_targets_the_configured_ceiling(self, bar_factory):
        bar = bar_factory("salt", goals={"salt_g": 6.0})

        assert bar.target_val == pytest.approx(6.0)
        assert bar.unit == "g salt"

    def test_caffeine_targets_the_sleep_safe_threshold(self, bar_factory):
        bar = bar_factory("caffeine", goals={"max_sleep_caffeine": 25.0})

        assert bar.target_val == pytest.approx(25.0)
        assert bar.unit == "mg caff"


class TestColourReading:
    @staticmethod
    def _colour(bar, intake, burned=0.0):
        bar.set_value(intake)
        bar.set_burned_value(burned)
        bar.displayed_value = bar.actual_value
        bar.displayed_burned_value = bar.burned_value
        return bar._get_bar_color().name()

    def test_a_deficit_reads_as_on_plan_when_losing(self, bar_factory):
        bar = bar_factory(goals={"goal_type": "lose_weight", "daily_adjustment_kcal": 300})

        assert self._colour(bar, bar.target_val - 500) == PALETTE["green"]

    def test_a_large_surplus_warns_when_losing(self, bar_factory):
        bar = bar_factory(goals={"goal_type": "lose_weight", "daily_adjustment_kcal": 300})

        assert self._colour(bar, bar.target_val + 900) != PALETTE["green"]

    def test_a_deficit_reads_as_short_when_gaining(self, bar_factory):
        bar = bar_factory(goals={"goal_type": "gain_weight", "daily_adjustment_kcal": 300})

        assert self._colour(bar, bar.target_val - 900) != PALETTE["green"]

    def test_landing_near_the_target_reads_as_on_plan_when_gaining(self, bar_factory):
        bar = bar_factory(goals={"goal_type": "gain_weight", "daily_adjustment_kcal": 300})

        assert self._colour(bar, bar.target_val) == PALETTE["green"]

    def test_energy_is_counted_net_of_what_was_burned(self, bar_factory):
        bar = bar_factory(goals={"goal_type": "lose_weight", "daily_adjustment_kcal": 300})
        over_target = bar.target_val + 900

        assert self._colour(bar, over_target) != PALETTE["green"]
        assert self._colour(bar, over_target, burned=900) == PALETTE["green"]

    def test_salt_warns_only_upwards(self, bar_factory):
        bar = bar_factory("salt", goals={"salt_g": 5.0})

        assert self._colour(bar, 2.0) == PALETTE["green"]
        assert self._colour(bar, 5.0) == PALETTE["green"]
        assert self._colour(bar, 9.0) != PALETTE["green"]

    def test_protein_is_a_floor_not_a_ceiling(self, bar_factory):
        bar = bar_factory("protein", goals={"protein_multiplier": 2.0})

        assert self._colour(bar, bar.target_val) == PALETTE["green"]
        assert self._colour(bar, bar.target_val + 60) == PALETTE["green"]


class TestAnimation:
    def test_the_displayed_value_eases_towards_the_new_one(self, bar_factory):
        bar = bar_factory()
        bar.set_value(1000.0)

        bar.update_animation()

        assert 0.0 < bar.displayed_value < 1000.0, "the bar animates rather than jumping"

    def test_the_displayed_value_settles_on_the_real_one(self, bar_factory):
        bar = bar_factory()
        bar.set_value(1000.0)

        for _ in range(200):
            bar.update_animation()

        assert bar.displayed_value == pytest.approx(1000.0)

    def test_the_burn_deduction_animates_too(self, bar_factory):
        bar = bar_factory()
        bar.set_burned_value(400.0)

        bar.update_animation()

        assert 0.0 < bar.displayed_burned_value < 400.0
