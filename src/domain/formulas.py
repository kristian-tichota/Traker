import math

EPLEY_INTERCEPT = 1.0278
EPLEY_SLOPE = 0.0278

EPLEY_MAX_REPS = math.floor(EPLEY_INTERCEPT / EPLEY_SLOPE)


def estimated_1rm(weight: float, max_reps: float):
    """The Epley-style one-rep maximum, or None where it is undefined."""
    if max_reps <= 0:
        return 0.0
    denominator = EPLEY_INTERCEPT - (EPLEY_SLOPE * max_reps)
    if denominator <= 0.0:
        return None
    return weight / denominator


def one_rep_max_or_weight(weight: float, max_reps: float) -> float:
    """estimated_1rm for charting, where a number is always required."""
    estimate = estimated_1rm(weight, max_reps)
    return weight if estimate is None else estimate


def training_volume(total_reps: float, weight: float) -> float:
    """Sum of all sets multiplied by the weight."""
    return total_reps * weight


def daily_stress_index(focus_s: float, focus_ot_s: float,
                       rest_s: float, rest_ot_s: float) -> float:
    """Penalty over recovery, both in seconds."""
    penalty = focus_s + focus_ot_s
    recovery = rest_s + rest_ot_s
    if recovery > 0:
        return penalty / recovery
    return penalty if penalty > 0 else 0.0


def caffeine_residual(dose_mg: float, hours_elapsed: float, half_life_hours: float) -> float:
    """What is left of a dose after hours_elapsed."""
    if dose_mg <= 0:
        return 0.0
    if half_life_hours <= 0:
        return 0.0
    elapsed = max(0.0, hours_elapsed)
    return dose_mg * (0.5 ** (elapsed / half_life_hours))


def residual_at_bedtime(dose_mg: float, drunk_at_minutes: float,
                         bedtime_minutes: float, half_life_hours: float) -> float:
    """What is left of a dose by the time the member goes to bed."""
    hours = max(0.0, (bedtime_minutes - drunk_at_minutes) / 60.0)
    return caffeine_residual(dose_mg, hours, half_life_hours)


def hours_until_caffeine_safe(dose_mg: float, threshold_mg: float, half_life_hours: float) -> float:
    """How long dose_mg needs to decay to threshold_mg."""
    if dose_mg <= threshold_mg or threshold_mg <= 0 or half_life_hours <= 0:
        return 0.0
    return half_life_hours * math.log2(dose_mg / threshold_mg)

LOSE_WEIGHT, GAIN_WEIGHT, MAINTAIN_WEIGHT = "lose_weight", "gain_weight", "maintain_weight"


def normalise_goal(goal_type) -> str:
    """The declared goal, folded."""
    goal = str(goal_type or "").strip().lower()
    return goal if goal in (LOSE_WEIGHT, GAIN_WEIGHT) else MAINTAIN_WEIGHT


def goal_adjustment(adjustment_kcal: float, goal_type) -> float:
    """The daily adjustment, signed by the goal rather than by how it was written."""
    goal = normalise_goal(goal_type)
    if goal == LOSE_WEIGHT:
        return -abs(adjustment_kcal)
    if goal == GAIN_WEIGHT:
        return abs(adjustment_kcal)
    return 0.0


def energy_target(maintenance_kcal: float, adjustment_kcal: float, goal_type) -> float:
    """Maintenance need, adjusted in the direction of the member's goal."""
    return maintenance_kcal + goal_adjustment(adjustment_kcal, goal_type)
