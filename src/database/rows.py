from typing import NamedTuple, Optional

from src.domain import formulas, plans


def _count(value):
    """Format a rep or second count, kept whole where it is whole."""
    number = float(value or 0.0)
    return int(number) if number.is_integer() else number


def _written(value) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def total(rows, field: str) -> float:
    """Sum one field across rows, counting an orphan's None as zero."""
    return sum(float(getattr(row, field, None) or 0.0) for row in rows)

_HEADING_TYPES = {}


def heading_type(row_type):
    """Return row_type again, marked as a heading."""
    made = _HEADING_TYPES.get(row_type)
    if made is None:
        made = type(f"{row_type.__name__}Heading", (row_type,), {"is_heading": True})
        _HEADING_TYPES[row_type] = made
    return made


def heading_over(rows):
    """Build the heading for rows, which are one logged set at one moment."""
    first = rows[0]
    cls = type(first)
    values = dict.fromkeys(cls._fields)
    for field in cls.GROUP_FIELDS:
        values[field] = getattr(first, field)
    values[cls.NAME_FIELD] = getattr(first, cls.SET_FIELD)
    for field in cls.HEADING_TOTALS:
        values[field] = total(rows, field)
    return heading_type(cls)(**values)


def grouped_by_set(rows):
    """Return rows with a heading inserted over each logged set."""
    if not rows:
        return list(rows)
    cls = type(rows[0])
    set_field = getattr(cls, "SET_FIELD", None)
    if set_field is None:
        return list(rows)

    out, seen = [], {}
    for row in rows:
        set_name = getattr(row, set_field, None)
        key = set_name and (set_name, *(getattr(row, field, None)
                                        for field in cls.GROUP_FIELDS))
        if not key:
            out.append(row)
            continue
        if key not in seen:
            seen[key] = [len(out), []]
            out.append(None)
        seen[key][1].append(row)
        out.append(row)

    for position, group in seen.values():
        out[position] = heading_over(group)
    return out


class FoodLogRow(NamedTuple):
    """GET /api/logs/food — nutrients already scaled by the amount eaten."""

    id: int
    estimated: bool
    date: str
    meal_type: str
    name: Optional[str]
    servings: Optional[float]
    grams: Optional[float]
    meal_set: Optional[str]
    energy_kcal: float
    protein_g: float
    carbs_g: float
    sugars_g: float
    fat_g: float
    saturated_fat_g: float
    salt_g: float
    fibre_g: float

    SET_FIELD = "meal_set"
    NAME_FIELD = "name"
    GROUP_FIELDS = ("date", "meal_type")
    HEADING_TOTALS = ("grams", "energy_kcal", "protein_g", "carbs_g", "sugars_g",
                      "fat_g", "saturated_fat_g", "salt_g", "fibre_g")

    @classmethod
    def from_server(cls, row) -> "FoodLogRow":
        id_, estimated, *rest = row
        return cls(id_, bool(estimated), *rest)


class DailyTotals(NamedTuple):
    """One day of DBAnalyticsMixin.get_daily_aggregates."""

    date: str
    energy_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    salt_g: float
    fibre_g: float
    sugars_g: float
    estimated_kcal: float
    estimated_rows: int

    @classmethod
    def of(cls, date: str, rows) -> "DailyTotals":
        """Sum one day's food rows."""
        estimates = [row for row in rows if getattr(row, "estimated", False)]
        return cls(date, *(total(rows, field) for field in NUTRIENT_FIELDS),
                   total(estimates, "energy_kcal"), len(estimates))

    @property
    def estimated_share(self) -> float:
        """Return what fraction of the day's energy was estimated."""
        return self.estimated_kcal / self.energy_kcal if self.energy_kcal else 0.0

NUTRIENT_FIELDS = ("energy_kcal", "protein_g", "carbs_g", "fat_g", "salt_g",
                   "fibre_g", "sugars_g")


class MatchedTotals(NamedTuple):
    """What a filter's matched set comes to, for the summary line under the table."""

    rows: int
    servings: float
    grams: float
    energy_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    salt_g: float
    fibre_g: float
    sugars_g: float
    estimated_rows: int
    first_date: Optional[str]
    last_date: Optional[str]

    @classmethod
    def of(cls, rows) -> "MatchedTotals":
        rows = [row for row in rows
                if row is not None and not getattr(row, "is_heading", False)]
        dates = sorted(str(date) for date in
                       (getattr(row, "date", None) for row in rows) if date)
        return cls(len(rows), total(rows, "servings"), total(rows, "grams"),
                   *(total(rows, field) for field in NUTRIENT_FIELDS),
                   sum(1 for row in rows if getattr(row, "estimated", False)),
                   dates[0] if dates else None, dates[-1] if dates else None)


def _by_name(cls, row):
    """Return row, a JSON object, as cls, matched field by field."""
    try:
        return cls(*(row[field] for field in cls._fields))
    except (KeyError, TypeError) as missing:
        raise ValueError(
            f"{cls.__name__} cannot be built from {sorted(row)}: {missing}") from None


def completion_name(row) -> str:
    """Return the name a member types to reach this row from the command line."""
    return getattr(row, type(row).COMPLETION_FIELD, "") or ""


class FoodItemRow(NamedTuple):
    """GET /api/catalog/food — one food's label, per 100 g."""

    id: int
    name: str
    category: str
    energy: float
    fat_total: float
    fat_saturated: float
    carbs_total: float
    carbs_sugars: float
    fibre: float
    protein: float
    salt: float
    serving_size: float

    COMPLETION_FIELD = "name"

    @classmethod
    def from_server(cls, row) -> "FoodItemRow":
        return _by_name(cls, row)


class BeverageItemRow(NamedTuple):
    """GET /api/catalog/beverage — one drink, per serving."""

    id: int
    name: str
    caffeine_mg: float
    antioxidants_mg: float

    COMPLETION_FIELD = "name"

    @classmethod
    def from_server(cls, row) -> "BeverageItemRow":
        return _by_name(cls, row)


class ExerciseItemRow(NamedTuple):
    """GET /api/catalog/exercise — how one movement is classified."""

    id: int
    name: str
    muscle_group: str
    movement_pattern: str
    secondary_muscles: Optional[str]
    plane_of_motion: Optional[str]
    joint_mechanics: Optional[str]
    equipment_type: Optional[str]
    unilateral_bilateral: Optional[str]
    metric_type: str

    COMPLETION_FIELD = "name"

    @classmethod
    def from_server(cls, row) -> "ExerciseItemRow":
        return _by_name(cls, row)


class SupplementItemRow(NamedTuple):
    """GET /api/catalog/supplement — one product's doses, per serving."""

    id: int
    name: str
    b12_mcg: float
    iodine_mcg: float
    creatine_g: float
    d3_iu: float
    k2_mcg: float
    dha_mg: float
    epa_mg: float
    calcium_mg: float
    magnesium_mg: float
    zinc_mg: float
    c_mg: float
    l_theanine_mg: float

    COMPLETION_FIELD = "name"

    @classmethod
    def from_server(cls, row) -> "SupplementItemRow":
        return _by_name(cls, row)


class MobilityItemRow(NamedTuple):
    """GET /api/catalog/mobility — one routine and how hard it is."""

    id: int
    name: str
    mets: float
    notes: Optional[str]

    COMPLETION_FIELD = "name"

    @classmethod
    def from_server(cls, row) -> "MobilityItemRow":
        return _by_name(cls, row)


class SetComponentRow(NamedTuple):
    """GET /api/catalog/sets/<domain> — one component of one set."""

    id: Optional[int]
    set_name: str
    name: Optional[str]
    amount: Optional[float]

    COMPLETION_FIELD = "set_name"

    @property
    def grams(self) -> Optional[float]:
        return self.amount

    @classmethod
    def from_server(cls, row) -> "SetComponentRow":
        return cls(*row)


class WorkoutComponentRow(NamedTuple):
    """GET /api/catalog/sets/exercise — one movement of one workout."""

    id: Optional[int]
    set_name: str
    name: Optional[str]
    set1: Optional[float]
    set2: Optional[float]
    set3: Optional[float]
    set4: Optional[float]
    set5: Optional[float]
    weight_kg: Optional[float]
    rpe: Optional[float]

    COMPLETION_FIELD = "set_name"

    @classmethod
    def from_server(cls, row) -> "WorkoutComponentRow":
        return cls(*row)


class BeverageLogRow(NamedTuple):
    """GET /api/logs/beverage, plus the client-side wait-until-sleep-safe column."""

    id: int
    date: str
    time: str
    name: Optional[str]
    drink_set: Optional[str]
    servings: float
    antioxidants_mg: float
    caffeine_mg: float
    sleep_wait: str

    SET_FIELD = "drink_set"
    NAME_FIELD = "name"
    GROUP_FIELDS = ("date", "time")
    HEADING_TOTALS = ("antioxidants_mg", "caffeine_mg")

    @classmethod
    def from_server(cls, row, sleep_wait: str) -> "BeverageLogRow":
        return cls(*row, sleep_wait)


class ExerciseLogRow(NamedTuple):
    """GET /api/logs/exercise, plus the totals and estimate computed on read."""

    id: int
    date: str
    name: Optional[str]
    workout: Optional[str]
    set1: int
    set2: int
    set3: int
    set4: int
    set5: int
    weight_kg: float
    rpe: float
    muscle_group: Optional[str]
    total_reps: int
    max_reps: int
    volume: float
    onerm: str
    metric_type: Optional[str]

    DISPLAY_COLUMNS = 15

    SET_FIELD = "workout"
    NAME_FIELD = "name"
    GROUP_FIELDS = ("date",)
    HEADING_TOTALS = ("volume",)

    @classmethod
    def from_server(cls, row) -> "ExerciseLogRow":
        (id_, date, name, workout, s1, s2, s3, s4, s5, weight, rpe,
         muscle_group, metric_type) = row
        sets = [_count(value) for value in (s1, s2, s3, s4, s5)]
        total_reps = sum(sets)
        max_reps = max(sets)

        if metric_type == "Seconds":
            volume = 0.0
            onerm = "N/A"
        else:
            volume = formulas.training_volume(total_reps, weight)
            estimate = formulas.estimated_1rm(weight, max_reps)
            onerm = "N/A" if estimate is None else f"{estimate:.1f}"

        return cls(
            id_, date, name, workout, *sets,
            weight, rpe, muscle_group,
            _count(total_reps), _count(max_reps), volume, onerm, metric_type,
        )

    @property
    def sets(self):
        return (self.set1, self.set2, self.set3, self.set4, self.set5)

    @property
    def is_time_based(self) -> bool:
        return self.metric_type == "Seconds"

    @property
    def active_sets(self) -> int:
        """Return how many of the five sets were worked."""
        return sum(1 for value in self.sets if value > 0)

    @property
    def sets_display(self) -> str:
        """Return the worked sets as the Exercise tab and the graph show them."""
        worked = list(self.sets)
        while len(worked) > 1 and worked[-1] == 0:
            worked.pop()
        return ",".join(_written(value) for value in worked)

    @property
    def one_rep_max(self) -> float:
        """Return the estimate as a number, for a timeline that must plot one."""
        if self.is_time_based:
            return 0.0
        return formulas.one_rep_max_or_weight(self.weight_kg, self.max_reps)


class SupplementLogRow(NamedTuple):
    """GET /api/logs/supplement — doses already scaled by servings."""

    id: int
    date: str
    name: Optional[str]
    stack: Optional[str]
    servings: float
    b12_mcg: float
    iodine_mcg: float
    creatine_g: float
    d3_iu: float
    k2_mcg: float
    dha_mg: float
    epa_mg: float
    calcium_mg: float
    magnesium_mg: float
    zinc_mg: float
    c_mg: float
    l_theanine_mg: float

    SET_FIELD = "stack"
    NAME_FIELD = "name"
    GROUP_FIELDS = ("date",)
    HEADING_TOTALS = ("b12_mcg", "iodine_mcg", "creatine_g", "d3_iu", "k2_mcg",
                      "dha_mg", "epa_mg", "calcium_mg", "magnesium_mg",
                      "zinc_mg", "c_mg", "l_theanine_mg")

    @classmethod
    def from_server(cls, row) -> "SupplementLogRow":
        return cls(*row)


class MobilityLogRow(NamedTuple):
    """GET /api/logs/mobility — intensity comes from the catalog entry."""

    id: int
    date: str
    name: Optional[str]
    routine_set: Optional[str]
    duration_mins: float
    mets: float

    SET_FIELD = "routine_set"
    NAME_FIELD = "name"
    GROUP_FIELDS = ("date",)
    HEADING_TOTALS = ("duration_mins",)

    @classmethod
    def from_server(cls, row) -> "MobilityLogRow":
        return cls(*row)


class PomodoroDailyRow(NamedTuple):
    """GET /api/pomodoro/daily-summary — minutes per state, one row per day."""

    date: str
    focus_mins: int
    rest_mins: int
    focus_overtime_mins: int
    rest_overtime_mins: int

    @classmethod
    def from_server(cls, row) -> "PomodoroDailyRow":
        return cls(*row)


class TrainingPlanRow(NamedTuple):
    """GET /api/plans — one training cycle, without its sessions."""

    id: int
    name: str
    start_date: str
    weeks: int
    notes: Optional[str]
    session_count: int

    COMPLETION_FIELD = "name"

    @classmethod
    def from_server(cls, row) -> "TrainingPlanRow":
        return cls(*row)


class PlanSessionRow(NamedTuple):
    """GET /api/plans/<id>/sessions — one prescribed day."""

    id: int
    date: str
    week: int
    name: str
    block: Optional[str]
    notes: Optional[str]
    movement_count: int

    @classmethod
    def from_server(cls, row) -> "PlanSessionRow":
        return cls(*row)


class PlanMovementRow(NamedTuple):
    """GET /api/plans/<id>/movements — one prescribed movement."""

    id: int
    date: str
    session: str
    position: int
    name: Optional[str]
    sets: int
    target_low: float
    target_high: float
    weight_kg: float
    rpe: float
    tempo: Optional[str]
    grouping: Optional[str]
    notes: Optional[str]
    metric_type: Optional[str]

    @classmethod
    def from_server(cls, row) -> "PlanMovementRow":
        return cls(*row)


class PlannedMovementRow(NamedTuple):
    """One prescribed movement beside what was actually logged against it."""

    id: int
    position: int
    name: Optional[str]
    sets: int
    target_low: float
    target_high: float
    weight_kg: float
    rpe: float
    tempo: Optional[str]
    logged: str
    result: str
    notes: Optional[str]

    DISPLAY_COLUMNS = 11

    @classmethod
    def of(cls, movement, log_row) -> "PlannedMovementRow":
        """Join one PlanMovementRow to the log row for its day, where there is one."""
        return cls(
            movement.id, movement.position, movement.name, movement.sets,
            _count(movement.target_low), _count(movement.target_high),
            movement.weight_kg, movement.rpe, movement.tempo,
            plans.logged_text(log_row), plans.verdict(movement, log_row),
            movement.notes)


class ChoreRow(NamedTuple):
    """GET /api/chores — one recurring chore, with when it was last seen to."""

    id: int
    name: str
    period_days: int
    anchor: str
    grace_days: Optional[int]
    notes: Optional[str]
    active: int
    last_done: Optional[str]
    done_count: int

    COMPLETION_FIELD = "name"

    @classmethod
    def from_server(cls, row) -> "ChoreRow":
        return _by_name(cls, row)


class ChoreDoneRow(NamedTuple):
    """GET /api/chores/completions — one chore, done once, by one member."""

    id: int
    date: str
    name: str
    done_by: Optional[str]

    @classmethod
    def from_server(cls, row) -> "ChoreDoneRow":
        return cls(*row)


class ChoreBoardRow(NamedTuple):
    """One line of the Chores tab: a chore, and what its cadence implies."""

    id: int
    name: str
    period_days: int
    grace_days: int
    anchor: str
    lands_on: str
    last_done: Optional[str]
    next_due: Optional[str]
    standing: str
    done_count: int
    active: int
    notes: Optional[str]

    @classmethod
    def of(cls, entry, words) -> "ChoreBoardRow":
        """Return one src.domain.chores.Standing as a row of the board."""
        chore = entry.chore
        return cls(entry.id, entry.name, entry.period_days, entry.grace_days,
                   chore.anchor, entry.lands_on, chore.last_done, entry.due_iso,
                   words.get(entry.standing, ""), chore.done_count,
                   chore.active, chore.notes)
