import datetime
import math
import re
from dataclasses import dataclass
from typing import Any, Callable

from src.database.rows import completion_name
from src.domain import chores
from src.domain.clock import as_displayed_date, as_stored_date, minutes_of_day
from src.gui.completion import ranked_matches
from src.gui.domains import (
    BEVERAGE, CHORE, EVERY_DOMAIN, EXERCISE, FOOD, MOBILITY, PLAN, POMODORO,
    SUPPLEMENT)


class CommandError(ValueError):
    """A command the user must correct: bad syntax, bad value, or refusal."""

MEAL_SHORTCUTS = {"b": "Breakfast", "l": "Lunch", "d": "Dinner", "s": "Supplement"}
MEALS = tuple(MEAL_SHORTCUTS.values())

HIDE, SHOW, MOVE, RESET, TOGGLE = "hide", "show", "move", "reset", "toggle"
QUEUE_ADD, QUEUE_REMOVE, QUEUE_CLEAR = "add", "rm", "clear"
BREAK_LONG, BREAK_CANCEL = "long", "cancel"

MEAL_SET = "meal_set"
BEVERAGE_SET = "beverage_set"
SUPPLEMENT_SET = "supplement_set"
MOBILITY_SET = "mobility_set"
EXERCISE_SET = "exercise_set"

SET_CATALOG_DOMAINS = {
    MEAL_SET: FOOD,
    BEVERAGE_SET: BEVERAGE,
    SUPPLEMENT_SET: SUPPLEMENT,
    MOBILITY_SET: MOBILITY,
    EXERCISE_SET: EXERCISE,
}

CATALOG_READERS = {
    FOOD: lambda db: db.get_all_foods(),
    BEVERAGE: lambda db: db.get_all_beverages(),
    EXERCISE: lambda db: db.get_all_exercises(),
    SUPPLEMENT: lambda db: db.get_all_supplements(),
    MOBILITY: lambda db: db.get_all_mobility(),
    CHORE: lambda db: db.get_chores(),
    **{key: (lambda db, domain=domain: db.get_sets(domain))
       for key, domain in SET_CATALOG_DOMAINS.items()},
}
EVERY_CATALOG = tuple(CATALOG_READERS)

_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?", re.IGNORECASE)
_AMOUNT = re.compile(_NUMBER.pattern + "g?", re.IGNORECASE)
_CLOCK = re.compile(r"\d{1,2}:\d{1,2}")
_DATE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")


def catalog_names(db, catalog) -> list[str]:
    """Return the item names of one shared catalog, in catalog order."""
    return list(dict.fromkeys(completion_name(row) for row in CATALOG_READERS[catalog](db)))


@dataclass(frozen=True)
class Param:
    """One argument: how it is advertised, and the payload field it fills."""

    name: str | None
    label: str
    read: Callable[[str, str], Any]
    expects: str
    rest: bool = False
    catalogs: tuple = ()
    default: Callable[[], Any] | None = None
    looks_like: Callable[[str], Any] | None = None
    path: bool = False
    choices: tuple = ()

    def parse(self, token: str | None) -> dict:
        """Return the payload fields token gives, or the default's where it is None."""
        if token is None:
            value = self.default()
        else:
            token = token.strip()
            try:
                value = self.read(token, self.label)
            except CommandError:
                raise
            except Exception as exc:  # broad: any parser failure is reported as this argument
                raise CommandError(
                    f"{self.label} expects {self.expects}, got '{token}'") from exc
        return value if self.name is None else {self.name: value}

    @property
    def optional(self) -> bool:
        return self.default is not None

    def recognises(self, token: str) -> bool:
        """Report whether token could be this argument's value."""
        return self.looks_like is None or bool(self.looks_like(token.strip()))


def _today() -> str:
    return datetime.date.today().isoformat()


def _finite(written: str, label: str) -> float:
    """Read written as a number, refusing the infinities float accepts."""
    quantity = float(written)
    if not math.isfinite(quantity):
        raise CommandError(f"{label} must be a finite number, not '{written}'.")
    return quantity


def _as_written(value: str, label: str) -> str:
    return value


def _non_empty(value: str, label: str) -> str:
    if not value:
        raise CommandError(f"{label} must not be empty.")
    return value


def number(name: str, label: str = None, default=None) -> Param:
    return Param(name, label or f"[{name}]", _finite, "a number", default=default,
                 looks_like=_NUMBER.fullmatch)


def text(name: str, label: str = None, rest: bool = False, default=None) -> Param:
    return Param(name, label or f"[{name}]", _as_written, "some text", rest=rest,
                 default=default)


def required_text(name: str, label: str = None, expects: str = "a name",
                  rest: bool = False) -> Param:
    """Declare a name that must be given."""
    return Param(name, label or f"[{name}]", _non_empty, expects, rest=rest)


def item(name: str, label: str, catalogs) -> Param:
    """Declare a trailing catalog item name, the argument Tab completes."""
    return Param(name, label, _non_empty, "a catalog item name", rest=True,
                 catalogs=tuple(catalogs))


def one_of(name: str, label: str, allowed, refusal: str, default=None) -> Param:
    """Declare one of a fixed set of words, which a default lets be left out."""
    def read(value, label):
        if value not in allowed:
            raise CommandError(refusal)
        return value

    return Param(name, label, read, "one of " + ", ".join(allowed), default=default,
                 looks_like=allowed.__contains__, choices=tuple(allowed))


def display_date(name: str, label: str, default=None) -> Param:
    """Declare a date as DD.MM.YYYY, which a default lets be left out."""
    return Param(name, label, _read_display_date, "a date as DD.MM.YYYY",
                 default=default, looks_like=_DATE.fullmatch)


def optional_position(name: str, label: str) -> Param:
    """Declare a position counted from 1, which may be left out."""
    return Param(name, label, _read_position, "a column position from 1",
                 default=lambda: None, looks_like=_NUMBER.fullmatch)


def components(name: str, label: str, unit: str, catalogs) -> Param:
    """Declare the component list of a named set: Item 100; Other Item 50."""
    shape = f"needs a name and an amount in {unit}, as 'Rolled Oats 100'."

    def read(value, label):
        parsed = []
        for field, item_name, (written,) in _each_component(value, 1, shape):
            if not _AMOUNT.fullmatch(written):
                raise CommandError(
                    f"'{written}' is not an amount in {unit}, in '{field}'.")
            quantity = _finite(written.rstrip("gG"), label)
            if quantity <= 0:
                raise CommandError(f"{item_name} needs more than zero {unit}.")
            parsed.append({"item_name": item_name, "amount": quantity})
        if not parsed:
            raise CommandError("A set needs at least one component.")
        return parsed

    example = label.strip("[]").split(";")[0].strip()
    return Param(name, label, read, f"one or more '{example}', separated by ';', in {unit}",
                 rest=True, catalogs=tuple(catalogs))


def _read_amount(value: str, label: str) -> dict:
    """Read servings, or grams where the amount ends in g."""
    if not _AMOUNT.fullmatch(value):
        raise CommandError(
            f"'{value}' is not an amount — 2 for servings, or 100g for grams.")
    in_grams = value[-1:].lower() == "g"
    quantity = _finite(value[:-1] if in_grams else value, label)
    if quantity <= 0:
        raise CommandError("An amount has to be more than zero.")
    return {"grams" if in_grams else "servings": quantity}


def _read_display_date(value: str, label: str) -> str:
    stored = as_stored_date(value, default="")
    if not stored:
        raise CommandError(f"{label} must be a date, as 25.12.2026.")
    return stored


def _read_cadence(value: str, label: str) -> int:
    """Read days between occurrences, or weeks with a w: 7, 2w, 4w."""
    weeks = value[-1:].lower() == "w"
    days = _finite(value[:-1] if weeks else value, label)
    if weeks:
        days *= chores.DAYS_IN_WEEK
    if days < 1:
        raise CommandError(f"{label} is at least one day.")
    return int(days)


def _read_clock_time(value: str, label: str) -> str:
    """Read a 24-hour time, stored zero-padded so that it sorts as text."""
    minutes = minutes_of_day(value)
    if minutes is None:
        raise CommandError(f"{label} must be a 24-hour time as HH:MM, not '{value}'.")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _read_meal(value: str, label: str) -> str:
    meal = MEAL_SHORTCUTS.get(value.lower(), value).capitalize()
    if meal not in MEALS:
        raise CommandError(
            f"'{value}' is not a meal — one of {'/'.join(MEALS)}, "
            f"or {'/'.join(MEAL_SHORTCUTS)}.")
    return meal


def _read_set_scheme(value: str, label: str) -> dict:
    """Read 7,7,7 as the five set columns."""
    reps = value.split(",")
    if len(reps) > 5:
        raise CommandError(f"{label} takes at most five sets.")
    counts = [_finite(rep, label) for rep in reps] + [0.0] * (5 - len(reps))
    return {f"set{n}": count for n, count in enumerate(counts, 1)}


def _read_slot(value: str, label: str) -> int:
    slot = int(value)
    if not 1 <= slot <= 9:
        raise CommandError(f"{label} must be between 1 and 9.")
    return slot


def _read_position(value: str, label: str) -> int:
    counted = int(value)
    if counted < 1:
        raise CommandError(f"{label} counts from 1.")
    return counted


def _read_dsi(value: str, label: str):
    """Read a stress-index override, or one of the words that removes it."""
    if value.lower() in ("clear", "rm", "delete"):
        return None
    if not _NUMBER.fullmatch(value):
        raise CommandError("DSI value must be a number or 'clear'.")
    return _finite(value, label)


def _each_component(value: str, trailing: int, shape: str):
    """Yield the semicolon-separated fields of a set definition, one at a time."""
    for field in value.split(";"):
        field = field.strip()
        if not field:
            continue
        parts = field.rsplit(maxsplit=trailing)
        if len(parts) != trailing + 1:
            raise CommandError(f"'{field}' {shape}")
        yield field, parts[0].strip(), parts[1:]


def _read_workout(value: str, label: str) -> list:
    """Read the movement list of a workout: Bench 8,8,6 60 8; Plank 60 0 6."""
    shape = ("needs a movement, its sets, its weight and its effort, "
             "as 'Bench Press 8,8,6 60 8'.")
    parsed = []
    for _field, ex_name, (sets, weight, rpe) in _each_component(value, 3, shape):
        entry = {"item_name": ex_name, **_read_set_scheme(sets, label),
                 "weight_kg": _finite(weight, label), "rpe": _finite(rpe, label)}
        if not 0 <= entry["rpe"] <= 10:
            raise CommandError(f"{ex_name}: effort is 0 to 10, not '{rpe}'.")
        parsed.append(entry)
    if not parsed:
        raise CommandError("A workout needs at least one movement.")
    return parsed


MEAL_TYPE = Param("meal_type", "[MealType]", _read_meal,
                  "a meal type, or one of " + "/".join(MEAL_SHORTCUTS))


@dataclass(frozen=True)
class ViewEffect:
    """A view that must mirror a command's result without waiting for a refresh."""
    view: str
    method: str
    field: str


@dataclass(frozen=True)
class OptimisticRow:
    """A row a command can put on screen before the refresh brings it back."""
    view: str
    fields: tuple
    fixed: tuple = ()


@dataclass(frozen=True)
class Command:
    name: str
    params: tuple
    confirm: Callable[[dict], str]
    invoke: Callable[[Any, dict], tuple] | None = None
    separator: str = " "
    dated: bool = False
    reports_result: bool = False
    view_effect: ViewEffect | None = None
    window_effect: str | None = None
    domain: str | tuple | None = None
    optimistic: OptimisticRow | None = None
    aliases: tuple = ()

    def pending_row(self, payload: dict):
        """Return the row to insert optimistically, or None."""
        if self.optimistic is None:
            return None
        values = {**payload, **dict(self.optimistic.fixed)}
        return (None, *(values.get(field) for field in self.optimistic.fields))

    @property
    def domains(self) -> tuple:
        """Return what this command may have changed, always as a tuple."""
        if self.domain is None:
            return ()
        if isinstance(self.domain, str):
            return (self.domain,)
        return tuple(self.domain)

    @property
    def usage(self) -> str:
        return self.separator.join(param.label for param in self.params)

    @property
    def catalogs(self) -> tuple:
        return next((param.catalogs for param in self.params if param.catalogs), ())

    def _walk(self, tokens):
        """Return (tokens taken, arguments settled) for all but the trailing argument."""
        used = settled = 0
        for param in self.params:
            if param.rest:
                break
            token = tokens[used] if used < len(tokens) else None
            if param.optional and token is None:
                break
            if param.optional and not param.recognises(token):
                settled += 1
                continue
            used += 1
            settled += token is not None
        return used, settled

    def name_position(self, text: str) -> int | None:
        """Return the token index where the catalog-completed name begins, or None."""
        if self.separator != " " or not self.catalogs:
            return None
        return 1 + self._walk(text.split()[1:])[0]

    def awaiting_name(self, text: str) -> bool:
        """Report whether the catalog name is the only argument left to give."""
        answerable = sum(1 for param in self.params if not param.rest)
        return self._walk(text.split()[1:])[1] == answerable

    def trailing_text(self, text: str) -> str:
        """Return what has been typed into the trailing argument, spaces kept."""
        index = 1 + self._walk(text.split()[1:])[0]
        parts = text.split(maxsplit=index)
        return parts[index] if len(parts) > index else ""

    def path_fragment(self, text: str) -> str:
        """Return the path being typed, or "" where this command takes none."""
        if self.separator != " " or not self.params[-1].path:
            return ""
        return self.trailing_text(text)

    def open_words(self, text: str) -> dict:
        """Return the fixed words a leading argument still accepts, by label."""
        if self._walk(text.split()[1:])[0]:
            return {}
        return {word: param.label for param in self.params if not param.rest
                for word in param.choices}

    def current_argument(self, text: str) -> int | None:
        """Return the index of the argument being asked for, None once all are given."""
        if self.separator != " ":
            index = text.count(self.separator)
        else:
            index = self._walk(text.split()[1:])[1]
        if index < len(self.params):
            return index
        return len(self.params) - 1 if self.params[-1].rest else None

    def hint(self, text: str) -> str:
        """Return the arguments still owed, given what has been typed."""
        index = self.current_argument(text)
        if index is None:
            return ""
        return " " + self.separator.join(param.label for param in self.params[index:])

    def field_fragment(self, remainder: str) -> str:
        """Return what has been typed into the catalog name of the current field."""
        field = remainder.rsplit(";", 1)[-1].strip()
        parts = field.rsplit(maxsplit=1)
        if len(parts) == 2 and _AMOUNT.fullmatch(parts[1]):
            return ""
        return field

    def _assign(self, tokens):
        """Pair each argument with its token, or with None where it was left out."""
        pairs, used = [], 0
        for param in self.params:
            token = tokens[used] if used < len(tokens) else None
            if param.optional and (token is None or not param.recognises(token)):
                pairs.append((param, None))
                continue
            if token is None:
                raise CommandError(f"Syntax: {self.name} {self.usage}")
            pairs.append((param, token))
            used += 1
        if used != len(tokens):
            raise CommandError(f"Syntax: {self.name} {self.usage}")
        return pairs

    def parse(self, remainder: str) -> dict:
        """Read what follows the command word as the payload of its write."""
        rest = self.params[-1].rest
        if self.separator != " ":
            tokens = remainder.split(self.separator, len(self.params) - 1 if rest else -1)
            if not remainder.strip() or len(tokens) != len(self.params):
                raise CommandError(f"Syntax: {self.name} {self.usage}")
            pairs = zip(self.params, tokens)
        else:
            words = remainder.split()
            pairs = self._assign(
                remainder.split(None, self._walk(words)[0]) if rest and words else words)

        payload = {"date": _today()} if self.dated else {}
        for param, token in pairs:
            payload.update(param.parse(token))
        return payload


def _quantity(value: float) -> str:
    """Format 1.0 as "1" and 1.5 as "1.5"."""
    return f"{value:g}"


def _confirm_new_chore(payload) -> str:
    """Read back what was defined, with the rule it will follow."""
    period = payload["period_days"]
    grace = payload.get("grace_days")
    if grace is None:
        grace = chores.default_grace(period)

    every = "every day" if period == 1 else f"every {_quantity(period)} days"
    said = (f" '{payload['name']}' recurs {every} from "
            f"{as_displayed_date(payload['anchor'])}")
    if period >= chores.DAYS_IN_WEEK:
        lands = chores.lands_on(payload["anchor"], period)
        said += (f" — always a {lands}" if lands != chores.DRIFTS
                 else " — the day drifts")
    owned = "day's" if grace == 1 else "days'"
    return f"{said}, {_quantity(grace)} {owned} grace."


def _clear_or_set_dsi(db, payload):
    if payload["override_dsi"] is None:
        return db.clear_pomodoro_dsi_override(payload["date"])
    return db.set_pomodoro_dsi_override(payload)


def _confirm_dsi(payload):
    if payload["override_dsi"] is None:
        return f" Removed visual DSI override for {payload['date']}."
    return (f" Override set: Visual DSI for {payload['date']} is now pinned to "
            f"{payload['override_dsi']:.2f}")


def _definition(name: str, params: tuple, method: str, domain: str) -> Command:
    """Build a define command: semicolon-separated fields, one catalog write."""
    return Command(
        name=name,
        params=params,
        separator=";",
        invoke=lambda db, payload: getattr(db, method)(payload),
        confirm=lambda payload: f" Defined '{payload['name']}' in the shared catalog.",
        domain=domain,
    )


def _amount_written(payload: dict) -> str:
    """Read back how much was logged, in the unit it was typed in."""
    if payload.get("grams") is not None:
        return f"{_quantity(payload['grams'])} g of"
    return f"{_quantity(payload['servings'])} x"


def _set_definition(name: str, domain: str, word: str, component_param: Param,
                    label: str, aliases: tuple = ()) -> Command:
    """Build a *set command: one named bundle of catalog items, in a line."""
    def confirm(payload):
        count = len(payload["components"])
        return (f" Defined the {word} '{payload['name']}' from {count} "
                f"{'component' if count == 1 else 'components'}.")

    return Command(
        name=name,
        params=(required_text("name", label,
                              "a name no item or set of this domain already has"),
                component_param),
        separator=";",
        invoke=lambda db, payload: db.add_set(domain, payload),
        confirm=confirm,
        domain=domain,
        aliases=aliases,
    )

_COMMAND_LIST = [
    Command(
        name="log",
        params=(
            Param(None, "[1 or 100g]", _read_amount, "servings, or grams as 100g",
                  default=lambda: {"servings": 1.0}, looks_like=_AMOUNT.fullmatch),
            MEAL_TYPE,
            item("food_name", "[Food or Meal Set]", (FOOD, MEAL_SET)),
        ),
        dated=True,
        invoke=lambda db, payload: db.add_food_log(payload),
        confirm=lambda p: (f" Logged {_amount_written(p)} {p['food_name']} "
                           f"({p['meal_type']})."),
        domain=FOOD,
        optimistic=OptimisticRow("food", (
            "estimated", "date", "meal_type", "food_name", "servings", "grams")),
    ),
    Command(
        name="quick",
        params=(
            number("energy_kcal", "[kcal]"),
            MEAL_TYPE,
            text("food_name", "[What it was]", rest=True),
        ),
        dated=True,
        invoke=lambda db, payload: db.add_quick_food_log(payload),
        confirm=lambda p: (f" Logged '{p['food_name']}' ({p['meal_type']}) as an "
                           f"estimate of {_quantity(p['energy_kcal'])} kcal — "
                           f"macros unknown, so the day reads as estimated."),
        domain=FOOD,
        optimistic=OptimisticRow("food", (
            "estimated", "date", "meal_type", "food_name", "servings", "grams"),
            fixed=(("estimated", True), ("servings", 1.0))),
    ),
    _set_definition("mealset", FOOD, "meal set",
                    components("components", "[Food 100; Other Food 50]",
                               "grams", (FOOD,)),
                    "[Meal Set Name]", aliases=("mealdefine",)),
    _definition("define", (
        required_text("name"), text("category"), number("energy"),
        number("fat_total"), number("fat_saturated"), number("carbs_total"),
        number("carbs_sugars"), number("fibre"), number("protein"),
        number("salt"), number("serving_size"),
    ), "add_food_item", FOOD),
    Command(
        name="bevlog",
        params=(
            number("servings", "[1]", default=lambda: 1.0),
            Param("time", "[HH:MM=now]", _read_clock_time, "a time as HH:MM",
                  default=lambda: datetime.datetime.now().strftime("%H:%M"),
                  looks_like=_CLOCK.fullmatch),
            item("bev_name", "[Beverage or Drink Set]", (BEVERAGE, BEVERAGE_SET)),
        ),
        dated=True,
        invoke=lambda db, payload: db.add_beverage_log(payload),
        confirm=lambda p: f" Logged {_quantity(p['servings'])} x {p['bev_name']} at {p['time']}.",
        domain=BEVERAGE,
        optimistic=OptimisticRow("beverages", (
            "date", "time", "bev_name", "drink_set", "servings")),
    ),
    _set_definition("bevset", BEVERAGE, "drink set",
                    components("components", "[Drink 1; Other Drink 2]",
                               "servings", (BEVERAGE,)),
                    "[Drink Set Name]"),
    _definition("bevdefine", (
        required_text("name"), number("caffeine_mg"), number("antioxidants_mg"),
    ), "add_beverage_item", BEVERAGE),
    Command(
        name="exlog",
        params=(
            Param(None, "[sets: 7,7,7]", _read_set_scheme, "comma-separated rep counts"),
            number("weight_kg", "[weight]"),
            number("rpe"),
            item("ex_name", "[Exercise Name]", (EXERCISE,)),
        ),
        dated=True,
        invoke=lambda db, payload: db.add_exercise_log(payload),
        confirm=lambda p: (f" Logged {p['ex_name']} @ {_quantity(p['weight_kg'])} kg, "
                           f"RPE {_quantity(p['rpe'])}."),
        domain=EXERCISE,
        optimistic=OptimisticRow("exercise", (
            "date", "ex_name", "workout", "set1", "set2", "set3", "set4", "set5",
            "weight_kg", "rpe"), fixed=(("workout", ""),)),
    ),
    Command(
        name="wlog",
        params=(item("name", "[Workout Name]", (EXERCISE_SET,)),),
        dated=True,
        invoke=lambda db, payload: db.add_workout_log(payload),
        confirm=lambda p: f" Logged the workout '{p['name']}'.",
        domain=EXERCISE,
    ),
    Command(
        name="planlog",
        params=(display_date("date", "[DD.MM.YYYY=today]", _today),),
        invoke=lambda db, payload: db.log_planned_session(payload),
        confirm=lambda p: (
            f" Logged the session planned for {as_displayed_date(p['date'])}."),
        domain=(EXERCISE, PLAN),
    ),
    _set_definition("exset", EXERCISE, "workout",
                    Param("components", "[Bench Press 8,8,6 60 8; Plank 60 0 6]",
                          _read_workout,
                          "one or more 'Bench Press 8,8,6 60 8', separated by ';'",
                          rest=True, catalogs=(EXERCISE,)),
                    "[Workout Name]"),
    _definition("exdefine", (
        required_text("name"), text("muscle_group"), text("movement_pattern"),
        text("secondary_muscles"), text("plane_of_motion"), text("joint_mechanics"),
        text("equipment_type"), text("unilateral_bilateral"),
        one_of("metric_type", "[Reps/Seconds]", ("Reps", "Seconds"),
               "Metric type must be 'Reps' or 'Seconds'."),
    ), "add_exercise_item", EXERCISE),
    Command(
        name="supplog",
        params=(
            number("servings", "[1]", default=lambda: 1.0),
            item("supp_name", "[Supplement or Stack]", (SUPPLEMENT, SUPPLEMENT_SET)),
        ),
        dated=True,
        invoke=lambda db, payload: db.add_supplement_log(payload),
        confirm=lambda p: f" Logged {_quantity(p['servings'])} x {p['supp_name']}.",
        domain=SUPPLEMENT,
        optimistic=OptimisticRow("supplements", (
            "date", "supp_name", "stack", "servings")),
    ),
    _set_definition("suppset", SUPPLEMENT, "stack",
                    components("components", "[B12 1; Creatine 1]",
                               "servings", (SUPPLEMENT,)),
                    "[Stack Name]"),
    _definition("suppdefine", (
        required_text("name"), number("b12_mcg"), number("iodine_mcg"),
        number("creatine_g"), number("d3_iu"), number("k2_mcg"), number("dha_mg"),
        number("epa_mg"), number("calcium_mg"), number("magnesium_mg"),
        number("zinc_mg"), number("c_mg"), number("l_theanine_mg"),
    ), "add_supplement_item", SUPPLEMENT),
    Command(
        name="moblog",
        params=(
            number("duration_mins", "[mins or set multiple]"),
            item("mob_name", "[Routine or Routine Set]", (MOBILITY, MOBILITY_SET)),
        ),
        dated=True,
        invoke=lambda db, payload: db.add_mobility_log(payload),
        confirm=lambda p: f" Logged {_quantity(p['duration_mins'])} min of {p['mob_name']}.",
        domain=MOBILITY,
        optimistic=OptimisticRow("mobility", (
            "date", "mob_name", "routine_set", "duration_mins")),
    ),
    _set_definition("mobset", MOBILITY, "routine set",
                    components("components", "[Hip Opener 10; Thoracic 5]",
                               "minutes", (MOBILITY,)),
                    "[Routine Set Name]"),
    _definition("mobdefine", (
        required_text("name"), number("mets"), text("notes", rest=True),
    ), "add_mobility_item", MOBILITY),
    Command(
        name="rm",
        params=(item("name", "[Item Profile Catalog Name]", EVERY_CATALOG),),
        invoke=lambda db, payload: db.delete_item_by_name(payload["name"]),
        confirm=lambda p: f" Removed '{p['name']}'.",
        reports_result=True,
        domain=EVERY_DOMAIN,
    ),
    Command(
        name="track",
        params=(
            Param("slot", "[slot_num: 1-9]", _read_slot, "a slot number from 1 to 9"),
            item("name", "[Exercise Name]", (EXERCISE,)),
        ),
        invoke=lambda db, p: db.set_setting(f"ex_graph_slot_{p['slot']}", p["name"]),
        confirm=lambda p: f" Pinned analytics slot {p['slot']} to '{p['name']}'.",
    ),
    Command(
        name="graphlayout",
        params=(one_of("dims", "[2x2 / 2x3 / 3x3]", ("2x2", "2x3", "3x3"),
                       "Supported layouts: 2x2, 2x3, or 3x3"),),
        invoke=lambda db, p: db.set_setting("ex_graph_layout_dims", p["dims"]),
        confirm=lambda p: f" Analytics presentation matrix shifted to {p['dims']}.",
        view_effect=ViewEffect("exercise_graphs", "set_grid_dims", "dims"),
    ),
    Command(
        name="calseries",
        params=(one_of("series", "[eaten / net]", ("eaten", "net"),
                       "Say eaten for what was logged, or net for that less "
                       "the training burn."),),
        invoke=lambda db, p: db.set_setting("food_graph_calorie_series", p["series"]),
        confirm=lambda p: f" Calorie chart now plots '{p['series']}'.",
        view_effect=ViewEffect("food_graphs", "set_calorie_series", "series"),
    ),
    Command(
        name="cols",
        params=(
            one_of("action", "[hide/show/move/reset]", (HIDE, SHOW, MOVE, RESET),
                   "Say hide, show, move or reset — or name a column "
                   "on its own to switch it off or back on.", lambda: TOGGLE),
            optional_position("position", "[position]"),
            text("column", "[Column]", rest=True, default=lambda: ""),
        ),
        confirm=lambda payload: " Columns rearranged.",
        window_effect="arrange_columns",
        aliases=("columns",),
    ),
    Command(
        name="break",
        params=(
            one_of("action", "[long/cancel]", (BREAK_LONG, BREAK_CANCEL),
                   "Say long to make the next break the long one, or "
                   "cancel to take that back.", lambda: ""),
        ),
        confirm=lambda payload: " Next break changed.",
        window_effect="queue_long_break",
    ),
    Command(
        name="rest",
        params=(
            one_of("action", "[rm/clear]", (QUEUE_REMOVE, QUEUE_CLEAR),
                   "Say rm with a number, or clear — or name a file "
                   "on its own to queue it.", lambda: QUEUE_ADD),
            optional_position("position", "[n]"),
            Param("entry", "[path]", _as_written, "a file or folder path", rest=True,
                  default=lambda: "", path=True),
        ),
        confirm=lambda payload: " Break queue changed.",
        window_effect="queue_rest",
        aliases=("queue",),
    ),
    Command(
        name="chore",
        params=(item("name", "[Chore]", (CHORE,)),),
        dated=True,
        invoke=lambda db, payload: db.complete_chore(payload),
        confirm=lambda p: f" Ticked '{p['name']}' off today.",
        domain=CHORE,
        aliases=("done",),
    ),
    Command(
        name="chorenew",
        params=(
            Param("period_days", "[Every N days or Nw]", _read_cadence,
                  "days, or weeks as 2w"),
            display_date("anchor", "[First DD.MM.YYYY]", _today),
            number("grace_days", "[Grace days]", default=lambda: None),
            required_text("name", "[Chore]",
                          "a name no other chore already has", rest=True),
        ),
        invoke=lambda db, payload: db.add_chore(payload),
        confirm=_confirm_new_chore,
        domain=CHORE,
    ),
    Command(
        name="setdsi",
        params=(
            display_date("date", "[DD.MM.YYYY]"),
            Param("override_dsi", "[DSI Value or 'clear']", _read_dsi,
                  "a number or 'clear'"),
        ),
        invoke=_clear_or_set_dsi,
        confirm=_confirm_dsi,
        domain=POMODORO,
    ),
]

COMMANDS = {command.name: command for command in _COMMAND_LIST}
for _command in _COMMAND_LIST:
    for _alias in _command.aliases:
        COMMANDS.setdefault(_alias, _command)

_NAMES = tuple(command.name for command in _COMMAND_LIST)


def resolve(text: str):
    """Split a command line into its Command and the rest of the line."""
    tokens = text.split(maxsplit=1)
    if not tokens:
        raise CommandError("Nothing to run.")
    command = COMMANDS.get(tokens[0].lower())
    if command is None:
        raise CommandError(f"Unknown command sequence: '{tokens[0].lower()}'")
    return command, tokens[1] if len(tokens) > 1 else ""


def command_word(text: str) -> str:
    """Return the first word of a line, folded the way COMMANDS is keyed."""
    tokens = text.split(maxsplit=1)
    return tokens[0].lower() if tokens else ""


def naming_a_command(text: str) -> bool:
    """Report whether the caret is still inside the command word itself."""
    return len(text.split(maxsplit=1)) <= 1 and not text[-1:].isspace()


def command_being_typed(text: str):
    """Return the command whose arguments are being given, or None."""
    if naming_a_command(text):
        return None
    return COMMANDS.get(command_word(text))


def candidates_for(text: str, domains=()) -> list:
    """Return the commands this line could still become, best first."""
    if command_being_typed(text) is not None:
        return []
    return commands_for(command_word(text), domains)


def belongs_to(command: Command, domains) -> bool:
    """Report whether command is one of the given domains' own."""
    written = set(command.domains)
    return bool(written) and written <= set(domains)


def commands_for(typed: str, domains=()) -> list:
    """Return every command a half-typed word could become, best answer first."""
    ranked = ranked_matches(typed, _NAMES,
                            prefer=lambda name: belongs_to(COMMANDS[name], domains))
    return [COMMANDS[name] for name in ranked]


def token_position(text: str) -> int:
    """Return the index of the token the caret is in, 0 being the command word."""
    words = text.split()
    return len(words) if text[-1:].isspace() else len(words) - 1
