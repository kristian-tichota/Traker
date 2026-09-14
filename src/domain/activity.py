BASE_MET = 5.0

COMPOUND_FACTOR = 1.25
ISOLATION_FACTOR = 0.80
UNCLASSIFIED_FACTOR = 1.00

COMPOUND_GROUPS = ('leg', 'back', 'chest', 'full', 'glute', 'quad', 'ham', 'compound')

ISOLATION_GROUPS = ('arm', 'bicep', 'tricep', 'shoulder', 'core', 'ab',
                    'calf', 'calv', 'isolation')

REFERENCE_RPE = 7.0
MIN_RPE = 1.0
MAX_RPE = 10.0

HOURS_PER_SET = 0.0125


def muscle_group_factor(muscle_group) -> float:
    """How much mass the named group moves, relative to an average movement."""
    name = (muscle_group or "").lower()
    if any(word in name for word in COMPOUND_GROUPS):
        return COMPOUND_FACTOR
    if any(word in name for word in ISOLATION_GROUPS):
        return ISOLATION_FACTOR
    return UNCLASSIFIED_FACTOR


def effort_factor(rpe) -> float:
    """Perceived effort as a multiple of the reference effort, clamped to the scale."""
    value = REFERENCE_RPE if rpe is None else float(rpe)
    return max(MIN_RPE, min(MAX_RPE, value)) / REFERENCE_RPE


def strength_met_hours(active_sets: int, muscle_group, rpe,
                       activity_level: float, tax_multiplier: float) -> float:
    """MET-hours a set of strength work adds above the member's own baseline."""
    adjusted_met = BASE_MET * muscle_group_factor(muscle_group) * effort_factor(rpe)
    return _above_baseline(adjusted_met, activity_level) * (active_sets * HOURS_PER_SET) * tax_multiplier


def mobility_met_hours(duration_mins: float, mets: float,
                       activity_level: float, tax_multiplier: float) -> float:
    """MET-hours a mobility routine adds; its intensity comes from the catalog."""
    return _above_baseline(mets, activity_level) * (duration_mins / 60.0) * tax_multiplier


def neat_tax_multiplier(neat_tax_percent: float) -> float:
    """The share of the estimate that survives the compensatory-movement discount."""
    return max(0.0, 1.0 - (neat_tax_percent / 100.0))


def _above_baseline(met: float, activity_level: float) -> float:
    """Only effort beyond what the member's TDEE already assumes counts."""
    return max(0.0, met - activity_level)


def kcal_from_met_hours(met_hours: float, weight_kg: float) -> float:
    """MET-hours as calories for a member of this weight."""
    return met_hours * weight_kg
