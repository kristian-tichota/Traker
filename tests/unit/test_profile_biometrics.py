import pytest


class TestBasalMetabolicRate:
    @pytest.mark.exact
    @pytest.mark.parametrize(
        "weight, height, age, gender, expected",
        [
            (75.0, 180.0, 30, "M", 1730.0),
            (65.0, 160.0, 25, "F", 1364.0),
            (75.0, 180.0, 30, "m", 1730.0),
            (0.0, 0.0, 0, "M", 5.0),
            (65.0, 160.0, 25, "X", 1364.0),
        ],
    )
    def test_formula(self, user_profile, weight, height, age, gender, expected):
        user_profile.data["biometrics"] = {
            "weight_kg": weight, "height_cm": height, "age": age, "gender": gender,
        }
        assert user_profile.calculate_bmr() == pytest.approx(expected)

    def test_falls_back_to_defaults_when_biometrics_are_absent(self, user_profile):
        user_profile.data.pop("biometrics", None)
        assert user_profile.calculate_bmr() == pytest.approx(1730.0)

    def test_string_biometrics_are_coerced(self, user_profile):
        user_profile.data["biometrics"] = {
            "weight_kg": "75", "height_cm": "180", "age": "30", "gender": " m ",
        }
        assert user_profile.calculate_bmr() == pytest.approx(1730.0)


class TestTotalDailyEnergyExpenditure:
    def test_scales_bmr_by_activity_level(self, user_profile):
        user_profile.data["biometrics"] = {
            "weight_kg": 75.0, "height_cm": 180.0, "age": 30, "gender": "M",
        }
        user_profile.data["goals"] = {"activity_level": 1.55}
        assert user_profile.calculate_tdee() == pytest.approx(1730.0 * 1.55)

    def test_defaults_to_moderate_activity(self, user_profile):
        user_profile.data["goals"] = {}
        assert user_profile.calculate_tdee() == pytest.approx(user_profile.calculate_bmr() * 1.55)


class TestCalorieTarget:
    @pytest.mark.parametrize(
        "goal, expected_offset",
        [("lose_weight", -300), ("gain_weight", +300), ("maintain_weight", 0)],
    )
    def test_the_adjustment_follows_the_declared_goal(self, user_profile, goal, expected_offset):
        user_profile.data["goals"] = {
            "activity_level": 1.5, "daily_adjustment_kcal": 300, "goal_type": goal,
        }
        assert user_profile.calculate_target_calories() == pytest.approx(
            user_profile.calculate_tdee() + expected_offset
        )

    def test_a_negative_adjustment_under_a_loss_goal_still_lowers_the_target(self, user_profile):
        user_profile.data["goals"] = {
            "activity_level": 1.5, "daily_adjustment_kcal": -400, "goal_type": "lose_weight",
        }
        assert user_profile.calculate_target_calories() == pytest.approx(
            user_profile.calculate_tdee() - 400
        )

    def test_a_profile_with_no_goal_maintains(self, user_profile):
        user_profile.data["goals"] = {"activity_level": 1.5, "daily_adjustment_kcal": 300}
        assert user_profile.calculate_target_calories() == pytest.approx(
            user_profile.calculate_tdee()
        )

    def test_it_agrees_with_the_calorie_bar(self, user_profile):
        from src.domain import formulas

        user_profile.data["goals"] = {
            "activity_level": 1.55, "daily_adjustment_kcal": 200, "goal_type": "lose_weight",
        }
        bar_side = formulas.energy_target(
            user_profile.calculate_tdee(), 200, user_profile.goal_type())

        assert user_profile.calculate_target_calories() == pytest.approx(bar_side)


class TestProteinTarget:
    def test_multiplies_body_weight(self, user_profile):
        user_profile.data["biometrics"] = {"weight_kg": 80.0}
        user_profile.data["goals"] = {"protein_multiplier": 1.8}
        assert user_profile.calculate_target_protein() == pytest.approx(144.0)

    def test_a_legacy_static_gram_target_still_wins(self, user_profile):
        user_profile.data["biometrics"] = {"weight_kg": 80.0}
        user_profile.data["goals"] = {"protein_g": 160.0}
        assert user_profile.calculate_target_protein() == pytest.approx(160.0)

    def test_the_multiplier_wins_when_both_are_present(self, user_profile):
        user_profile.data["biometrics"] = {"weight_kg": 80.0}
        user_profile.data["goals"] = {"protein_g": 200.0, "protein_multiplier": 2.0}
        assert user_profile.calculate_target_protein() == pytest.approx(160.0)
