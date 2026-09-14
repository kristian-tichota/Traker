import math

import pytest

from src.domain import formulas


class TestEstimatedOneRepMax:
    @pytest.mark.exact
    @pytest.mark.parametrize("weight, best_set", [(30.0, 1), (30.0, 7), (42.5, 12), (100.0, 36)])
    def test_it_is_the_weight_over_the_epley_divisor(self, weight, best_set):
        assert formulas.estimated_1rm(weight, best_set) == pytest.approx(
            weight / (1.0278 - 0.0278 * best_set)
        )

    @pytest.mark.exact
    def test_a_single_repetition_estimates_the_weight_itself(self):
        assert formulas.estimated_1rm(60.0, 1) == pytest.approx(60.0)

    @pytest.mark.exact
    @pytest.mark.parametrize("best_set", [0, -1])
    def test_no_repetitions_estimates_zero(self, best_set):
        assert formulas.estimated_1rm(60.0, best_set) == 0.0

    @pytest.mark.exact
    @pytest.mark.parametrize("best_set", [37, 40, 120])
    def test_past_the_domain_there_is_no_estimate(self, best_set):
        assert formulas.estimated_1rm(50.0, best_set) is None

    def test_the_charting_variant_never_returns_a_negative_maximum(self):
        assert formulas.one_rep_max_or_weight(50.0, 40) == 50.0

    def test_the_charting_variant_agrees_inside_the_domain(self):
        assert formulas.one_rep_max_or_weight(50.0, 8) == formulas.estimated_1rm(50.0, 8)


class TestTrainingVolume:
    @pytest.mark.exact
    def test_volume_is_total_repetitions_times_the_weight(self):
        assert formulas.training_volume(21, 30.0) == pytest.approx(630.0)


class TestDailyStressIndex:
    @pytest.mark.exact
    def test_the_index_is_penalty_over_recovery(self):
        index = formulas.daily_stress_index(
            focus_s=3600, focus_ot_s=600, rest_s=1200, rest_ot_s=400)

        assert index == pytest.approx((3600 + 600) / (1200 + 400))

    @pytest.mark.exact
    def test_every_second_of_a_state_counts_the_same_as_any_other(self):
        assert formulas.daily_stress_index(600, 0, 0, 600) == pytest.approx(
            formulas.daily_stress_index(0, 600, 600, 0))

    @pytest.mark.exact
    def test_a_day_of_the_prescribed_split_comes_out_at_one(self):
        assert formulas.daily_stress_index(30 * 60, 0, 30 * 60, 0) == pytest.approx(1.0)

    @pytest.mark.exact
    def test_penalty_with_no_recovery_is_the_penalty_total(self):
        index = formulas.daily_stress_index(
            focus_s=1800, focus_ot_s=0, rest_s=0, rest_ot_s=0)

        assert index == pytest.approx(1800.0), "not a division by zero"

    @pytest.mark.exact
    def test_a_day_with_nothing_logged_scores_zero(self):
        assert formulas.daily_stress_index(0, 0, 0, 0) == 0.0

    @pytest.mark.exact
    def test_minutes_and_milliseconds_agree_once_converted_to_seconds(self):
        from_minutes = formulas.daily_stress_index(30 * 60, 5 * 60, 10 * 60, 2 * 60)
        from_millis = formulas.daily_stress_index(
            30 * 60_000 / 1000.0, 5 * 60_000 / 1000.0,
            10 * 60_000 / 1000.0, 2 * 60_000 / 1000.0)

        assert from_minutes == pytest.approx(from_millis)


class TestCaffeine:
    @pytest.mark.exact
    def test_a_dose_halves_every_half_life(self):
        assert formulas.caffeine_residual(80.0, 5.0, 5.0) == pytest.approx(40.0)
        assert formulas.caffeine_residual(80.0, 10.0, 5.0) == pytest.approx(20.0)

    @pytest.mark.exact
    def test_the_residual_follows_one_half_to_the_power_of_elapsed_over_half_life(self):
        assert formulas.caffeine_residual(95.0, 3.5, 6.0) == pytest.approx(
            95.0 * (0.5 ** (3.5 / 6.0))
        )

    def test_a_drink_logged_after_bedtime_does_not_decay_backwards(self):
        assert formulas.caffeine_residual(80.0, -2.0, 5.0) == pytest.approx(80.0)

    def test_the_wait_inverts_the_decay(self):
        wait = formulas.hours_until_caffeine_safe(80.0, 20.0, 5.0)

        assert wait == pytest.approx(5.0 * math.log2(80.0 / 20.0))
        assert formulas.caffeine_residual(80.0, wait, 5.0) == pytest.approx(20.0)

    @pytest.mark.parametrize("dose", [0.0, 5.0, 20.0])
    def test_a_dose_at_or_below_the_threshold_needs_no_wait(self, dose):
        assert formulas.hours_until_caffeine_safe(dose, 20.0, 5.0) == 0.0
