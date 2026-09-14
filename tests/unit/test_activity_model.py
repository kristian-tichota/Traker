import pytest

from src.domain import activity


class TestMuscleGroupFactor:
    @pytest.mark.exact
    @pytest.mark.parametrize("group", ["Legs", "Back", "Chest", "Full Body",
                                       "Glutes", "Quads", "Hamstrings"])
    def test_a_compound_group_scales_up(self, group):
        assert activity.muscle_group_factor(group) == 1.25

    @pytest.mark.exact
    @pytest.mark.parametrize("group", ["Arms", "Biceps", "Triceps", "Shoulders",
                                       "Core", "Abs", "Calf", "Calves"])
    def test_an_isolation_group_scales_down(self, group):
        assert activity.muscle_group_factor(group) == 0.80

    @pytest.mark.parametrize("group", ["Neck", "", None, "Grip"])
    def test_an_unrecognised_group_is_not_guessed_at(self, group):
        assert activity.muscle_group_factor(group) == 1.00

    def test_the_match_ignores_capitalisation(self):
        assert activity.muscle_group_factor("LEGS") == activity.muscle_group_factor("legs")


class TestEffortFactor:
    @pytest.mark.exact
    def test_the_reference_effort_counts_as_itself(self):
        assert activity.effort_factor(7.0) == 1.0

    @pytest.mark.exact
    def test_a_maximal_set_counts_as_ten_sevenths(self):
        assert activity.effort_factor(10.0) == pytest.approx(10.0 / 7.0)

    @pytest.mark.exact
    @pytest.mark.parametrize("rpe, clamped", [(0.0, 1.0), (-5.0, 1.0), (15.0, 10.0)])
    def test_a_rating_off_the_scale_is_clamped(self, rpe, clamped):
        assert activity.effort_factor(rpe) == pytest.approx(clamped / 7.0)

    def test_no_rating_is_treated_as_the_reference(self):
        assert activity.effort_factor(None) == 1.0


class TestStrengthMetHours:
    BASELINE = 1.55
    NO_TAX = 1.0

    @pytest.mark.exact
    def test_the_whole_formula(self):
        met_hours = activity.strength_met_hours(
            active_sets=3, muscle_group="Legs", rpe=7.0,
            activity_level=self.BASELINE, tax_multiplier=self.NO_TAX,
        )

        expected = (5.0 * 1.25 * 1.0 - 1.55) * (3 * 0.0125)
        assert met_hours == pytest.approx(expected)

    @pytest.mark.exact
    def test_a_set_counts_as_forty_five_seconds(self):
        assert activity.HOURS_PER_SET * 3600 == pytest.approx(45.0)

    @pytest.mark.exact
    def test_work_at_or_below_the_baseline_contributes_nothing(self):
        met_hours = activity.strength_met_hours(
            active_sets=3, muscle_group="Biceps", rpe=1.0,
            activity_level=10.0, tax_multiplier=self.NO_TAX,
        )

        assert met_hours == 0.0, "never a negative contribution"

    def test_a_compound_set_outweighs_an_isolation_set(self):
        common = dict(active_sets=3, rpe=8.0, activity_level=self.BASELINE,
                      tax_multiplier=self.NO_TAX)

        assert (activity.strength_met_hours(muscle_group="Legs", **common)
                > activity.strength_met_hours(muscle_group="Biceps", **common))

    def test_a_harder_set_outweighs_an_easier_one(self):
        common = dict(active_sets=3, muscle_group="Legs", activity_level=self.BASELINE,
                      tax_multiplier=self.NO_TAX)

        assert (activity.strength_met_hours(rpe=10.0, **common)
                > activity.strength_met_hours(rpe=5.0, **common))


class TestMobilityMetHours:
    @pytest.mark.exact
    def test_intensity_comes_from_the_catalog_and_duration_from_the_log(self):
        met_hours = activity.mobility_met_hours(
            duration_mins=30.0, mets=3.0, activity_level=1.55, tax_multiplier=1.0
        )

        assert met_hours == pytest.approx((3.0 - 1.55) * 0.5)

    def test_a_routine_below_the_baseline_contributes_nothing(self):
        assert activity.mobility_met_hours(30.0, 1.0, 1.55, 1.0) == 0.0


class TestTheNeatTax:
    @pytest.mark.exact
    def test_the_declared_share_is_withheld(self):
        assert activity.neat_tax_multiplier(15.0) == pytest.approx(0.85)

    @pytest.mark.exact
    def test_a_full_tax_withholds_everything(self):
        assert activity.neat_tax_multiplier(100.0) == 0.0

    def test_a_tax_beyond_a_hundred_percent_never_goes_negative(self):
        assert activity.neat_tax_multiplier(150.0) == 0.0

    def test_no_tax_leaves_the_estimate_whole(self):
        assert activity.neat_tax_multiplier(0.0) == 1.0
