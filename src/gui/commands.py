import datetime
import math
import re
from dataclasses import dataclass
from typing import Any, Callable

from src.database.rows import completion_name
from src.domain import chores
from src.domain.clock import as_displayed_date, as_stored_date, minutes_of_day
from src.gui.completion import ranked_matches


class CommandError(ValueError):
    """A command the user must correct: bad syntax, bad value, or refusal."""

MEAL_SHORTCUTS = {"b": "Breakfast", "l": "Lunch", "d": "Dinner", "s": "Supplement"}

CLEARING_WORDS = ("clear", "rm", "delete")

HIDE, SHOW, MOVE, RESET, TOGGLE = "hide", "show", "move", "reset", "toggle"
COLUMN_ACTIONS = (HIDE, SHOW, MOVE, RESET)

QUEUE_ADD, QUEUE_REMOVE, QUEUE_CLEAR = "add", "rm", "clear"
QUEUE_ACTIONS = (QUEUE_REMOVE, QUEUE_CLEAR)

BREAK_LONG, BREAK_CANCEL = "long", "cancel"
BREAK_ACTIONS = (BREAK_LONG, BREAK_CANCEL)

from src.gui.domains import (
    BEVERAGE, CHORE, EVERY_DOMAIN, EXERCISE, FOOD, MOBILITY, PLAN, POMODORO,
    SUPPLEMENT)

EVERY_DOMAIN_WRITTEN = EVERY_DOMAIN

MEAL_SET = "meal_set"
BEVERAGE_SET = "beverage_set"
SUPPLEMENT_SET = "supplement_set"
MOBILITY_SET = "mobility_set"
EXERCISE_SET = "exercise_set"

CHORE_CATALOG = "chore"

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
    CHORE_CATALOG: lambda db: db.get_chores(),
    **{key: (lambda db, domain=domain: db.get_sets(domain))
       for key, domain in SET_CATALOG_DOMAINS.items()},
}
EVERY_CATALOG = tuple(CATALOG_READERS)


def catalog_names(db, catalogs) -> list[str]:
    """The item names of the given shared catalogs, in catalog order."""
    names = []
    for key in catalogs:
        names.extend(completion_name(row) for row in CATALOG_READERS[key](db))
    return list(dict.fromkeys(names))


@dataclass(frozen=True)
class Param:
    """One argument: how it is advertised, and how it becomes payload fields."""

    label: str
    read: Callable[[str], dict]
    expects: str = "a value"
    rest: bool = False
    catalogs: tuple = ()
    default: Callable[[], dict] = None
    looks_like: Callable[[str], bool] = None

    def parse(self, token: str) -> dict:
        token = token.strip()
        try:
            return self.read(token)
        except CommandError:
            raise
        except Exception as exc:  # broad: any parser failure is reported as this argument
            raise CommandError(f"{self.label} expects {self.expects}, got '{token}'") from exc

    @property
    def optional(self) -> bool:
        return self.default is not None

    def recognises(self, token: str) -> bool:
        """Whether token could be this argument's value."""
        if self.looks_like is None:
            return True
        return bool(self.looks_like(token.strip()))


def _finite(written, label: str) -> float:
    """written as a number, refusing the infinities float accepts."""
    quantity = float(written)
    if not math.isfinite(quantity):
        raise CommandError(f"{label} must be a finite number, not '{written}'.")
    return quantity


def _read_number(name: str, label: str):
    def read(value):
        return {name: _finite(value, label)}

    return read


def number(name: str, label: str = None) -> Param:
    label = label or f"[{name}]"
    return Param(label, _read_number(name, label), "a number")


def text(name: str, label: str = None) -> Param:
    return Param(label or f"[{name}]", lambda v: {name: v}, "some text")


def _read_non_empty(name: str, label: str):
    def read(value):
        if not value:
            raise CommandError(f"{label} must not be empty.")
        return {name: value}

    return read


def required_text(name: str, label: str = None, expects: str = "a name",
                  rest: bool = False) -> Param:
    """A name that must be given."""
    label = label or f"[{name}]"
    return Param(label, _read_non_empty(name, label), expects, rest=rest)


def free_text(name: str, label: str = None) -> Param:
    """A trailing field that may itself contain the field separator."""
    return Param(label or f"[{name}]", lambda v: {name: v}, "some text", rest=True)


def item(name: str, label: str, catalogs) -> Param:
    """A trailing catalog item name — the argument Tab completes."""
    return Param(label, _read_non_empty(name, label), "a catalog item name",
                 rest=True, catalogs=tuple(catalogs))


def _looks_like_an_amount(token: str) -> bool:
    try:
        float(token.rstrip("gG"))
    except ValueError:
        return False
    return True


def _looks_like_a_number(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True

_CLOCK_SHAPE = re.compile(r"^\d{1,2}:\d{1,2}$")


def _looks_like_a_clock_time(token: str) -> bool:
    return bool(_CLOCK_SHAPE.match(token))


def amount(label: str = "[1 or 100g]") -> Param:
    """How much was eaten: servings, or grams if it ends in g."""
    def read(value):
        value = value.strip()
        if not _looks_like_an_amount(value):
            raise CommandError(
                f"'{value}' is not an amount — 2 for servings, or 100g for grams.")
        in_grams = value[-1:] in ("g", "G")
        quantity = _finite(value.rstrip("gG"), label)
        if quantity <= 0:
            raise CommandError("An amount has to be more than zero.")
        return {"grams" if in_grams else "servings": quantity}

    return Param(label, read, "servings, or grams as 100g",
                 default=lambda: {"servings": 1.0},
                 looks_like=_looks_like_an_amount)

_LOOKS_LIKE_A_DATE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")


def _read_display_date(name: str, label: str):
    def read(value):
        stored = as_stored_date(value, default="")
        if not stored:
            raise CommandError(f"{label} must be a date, as 25.12.2026.")
        return {name: stored}

    return read


def optional_display_date(name: str, label: str) -> Param:
    """A leading date that may be left out, meaning today."""
    return Param(label, _read_display_date(name, label), "a date as DD.MM.YYYY",
                 default=lambda: {name: datetime.date.today().isoformat()},
                 looks_like=lambda token: bool(_LOOKS_LIKE_A_DATE.match(token.strip())))

_LOOKS_LIKE_A_CADENCE = re.compile(r"^\d+(\.\d+)?[wW]?$")


def cadence(name: str, label: str) -> Param:
    """Days between occurrences, or weeks with a w: 7, 2w, 4w."""
    def read(value):
        text = value.strip()
        weeks = text[-1:].lower() == "w"
        days = _finite(text[:-1] if weeks else text, label)
        if weeks:
            days *= chores.DAYS_IN_WEEK
        if days < 1:
            raise CommandError(f"{label} is at least one day.")
        return {name: int(days)}

    return Param(label, read, "days, or weeks as 2w",
                 looks_like=lambda token: bool(
                     _LOOKS_LIKE_A_CADENCE.match(token.strip())))


def optional_number(name: str, label: str, fallback: float = 1.0) -> Param:
    """A leading count that may be left out, meaning fallback."""
    return Param(label, _read_number(name, label), "a number",
                 default=lambda: {name: fallback},
                 looks_like=_looks_like_a_number)


def _example(label: str) -> str:
    """A label read back as the example it is."""
    return label.strip("[]").split(";")[0].strip()


def _each_component(value: str, trailing: int, shape: str):
    """The semicolon-separated fields of a set definition, one at a time."""
    for field in value.split(";"):
        field = field.strip()
        if not field:
            continue
        parts = field.rsplit(maxsplit=trailing)
        if len(parts) != trailing + 1:
            raise CommandError(f"'{field}' {shape}")
        yield field, parts[0].strip(), parts[1:]


def components(name: str, label: str, unit: str, catalogs) -> Param:
    """The component list of a named set: Item 100; Other Item 50."""
    shape = f"needs a name and an amount in {unit}, as 'Rolled Oats 100'."

    def read(value):
        parsed = []
        for field, item_name, (written,) in _each_component(value, 1, shape):
            if not _looks_like_an_amount(written):
                raise CommandError(
                    f"'{written}' is not an amount in {unit}, in '{field}'.")
            quantity = _finite(written.rstrip("gG"), label)
            if quantity <= 0:
                raise CommandError(f"{item_name} needs more than zero {unit}.")
            parsed.append({"item_name": item_name, "amount": quantity})
        if not parsed:
            raise CommandError("A set needs at least one component.")
        return {name: parsed}

    return Param(label, read,
                 f"one or more '{_example(label)}', separated by ';', in {unit}",
                 rest=True, catalogs=tuple(catalogs))


def workout_components(name: str, label: str) -> Param:
    """The movement list of a workout: Bench 8,8,6 60 8; Plank 60 0 6."""
    shape = ("needs a movement, its sets, its weight and its effort, "
             "as 'Bench Press 8,8,6 60 8'.")

    def read(value):
        parsed = []
        for _field, ex_name, rest in _each_component(value, 3, shape):
            written_sets, written_weight, written_rpe = rest
            entry = {"item_name": ex_name}
            entry.update(_read_set_scheme(written_sets, label))
            entry["weight_kg"] = _finite(written_weight, label)
            entry["rpe"] = _finite(written_rpe, label)
            if not 0 <= entry["rpe"] <= 10:
                raise CommandError(
                    f"{ex_name}: effort is 0 to 10, not '{written_rpe}'.")
            parsed.append(entry)
        if not parsed:
            raise CommandError("A workout needs at least one movement.")
        return {name: parsed}

    return Param(label, read,
                 f"one or more '{_example(label)}', separated by ';'",
                 rest=True, catalogs=(EXERCISE,))


def _read_clock_time(name: str, label: str):
    def read(value):
        if minutes_of_day(value) is None:
            raise CommandError(f"{label} must be a 24-hour time as HH:MM, not '{value}'.")
        return {name: value.strip()}

    return read


def optional_clock_time(name: str, label: str) -> Param:
    """A time that may be left out, meaning now."""
    return Param(label, _read_clock_time(name, label), "a time as HH:MM",
                 default=lambda: {name: datetime.datetime.now().strftime("%H:%M")},
                 looks_like=_looks_like_a_clock_time)

MEALS = tuple(MEAL_SHORTCUTS.values())


def meal_type(name: str, label: str) -> Param:
    """One of the four meals, by name or by initial."""
    def read(value):
        meal = MEAL_SHORTCUTS.get(value.lower(), value).capitalize()
        if meal not in MEALS:
            raise CommandError(
                f"'{value}' is not a meal — one of {'/'.join(MEALS)}, "
                f"or {'/'.join(MEAL_SHORTCUTS)}.")
        return {name: meal}

    return Param(label, read, "a meal type, or one of " + "/".join(MEAL_SHORTCUTS))


def _read_set_scheme(value: str, label: str) -> dict:
    """7,7,7 as the five set columns."""
    reps = [part.strip() for part in value.split(",")]
    if len(reps) > 5:
        raise CommandError(f"{label} takes at most five sets.")
    counts = [_finite(rep, label) for rep in reps] + [0.0] * (5 - len(reps))
    return {f"set{n}": counts[n - 1] for n in range(1, 6)}


def set_scheme(label: str) -> Param:
    return Param(label, lambda value: _read_set_scheme(value, label),
                 "comma-separated rep counts")


def readable_date(name: str, label: str) -> Param:
    def read(value):
        return {name: datetime.datetime.strptime(value, "%d.%m.%Y").strftime("%Y-%m-%d")}

    return Param(label, read, "a date as DD.MM.YYYY")


def graph_slot(name: str, label: str) -> Param:
    def read(value):
        slot = int(value)
        if not 1 <= slot <= 9:
            raise CommandError(f"{label} must be between 1 and 9.")
        return {name: slot}

    return Param(label, read, "a slot number from 1 to 9")


def _read_one_of(name: str, allowed, refusal: str):
    def read(value):
        if value not in allowed:
            raise CommandError(refusal)
        return {name: value}

    return read


def one_of(name: str, label: str, allowed, refusal: str) -> Param:
    return Param(label, _read_one_of(name, allowed, refusal),
                 "one of " + ", ".join(allowed))


def optional_one_of(name: str, label: str, allowed, refusal: str,
                    fallback: str) -> Param:
    """One of a fixed set of words, which may be left out."""
    return Param(label, _read_one_of(name, allowed, refusal),
                 "one of " + ", ".join(allowed),
                 default=lambda: {name: fallback},
                 looks_like=lambda token: token in allowed)


def optional_position(name: str, label: str) -> Param:
    """A position counted from 1, which may be left out."""
    def read(value):
        position = int(value)
        if position < 1:
            raise CommandError(f"{label} counts from 1.")
        return {name: position}

    return Param(label, read, "a column position from 1",
                 default=lambda: {name: None},
                 looks_like=_looks_like_a_number)


def optional_text(name: str, label: str) -> Param:
    """A trailing name that may be left out altogether."""
    return Param(label, lambda value: {name: value}, "some text", rest=True,
                 default=lambda: {name: ""})


def dsi_value(name: str, label: str) -> Param:
    """A stress-index override, or one of the words that removes it."""
    def read(value):
        if value.lower() in CLEARING_WORDS:
            return {name: None}
        try:
            return {name: _finite(value, label)}
        except CommandError:
            raise
        except ValueError:
            raise CommandError("DSI value must be a number or 'clear'.") from None

    return Param(label, read, "a number or 'clear'")


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
    invoke: Callable[[Any, dict], tuple]
    confirm: Callable[[dict], str]
    separator: str = " "
    dated: bool = False
    reports_result: bool = False
    view_effect: ViewEffect | None = None

    window_effect: str | None = None
    domain: str | tuple | None = None

    optimistic: "OptimisticRow | None" = None

    aliases: tuple = ()

    def pending_row(self, payload: dict):
        """The row to insert optimistically, or None."""
        if self.optimistic is None:
            return None
        values = {**payload, **dict(self.optimistic.fixed)}
        return (None, *(values.get(field) for field in self.optimistic.fields))

    @property
    def domains(self) -> tuple:
        """What this command may have changed, always as a tuple."""
        if self.domain is None:
            return ()
        if isinstance(self.domain, str):
            return (self.domain,)
        return tuple(self.domain)

    @property
    def usage(self) -> str:
        return self.separator.join(param.label for param in self.params)

    @property
    def syntax_hint(self) -> str:
        return " " + self.usage

    def name_position(self, text: str = "") -> int | None:
        """Token index at which the catalog-completed name begins, or None."""
        if self.separator != " ":
            return None
        if not any(param.catalogs for param in self.params):
            return None
        return 1 + self._leading_tokens(text.split()[1:])

    def _walk(self, tokens):
        """(tokens taken, arguments settled) for the arguments before the trailing one."""
        used = settled = 0
        ran_out = False
        for param in self.params:
            if param.rest:
                break
            token = None if ran_out or used >= len(tokens) else tokens[used]
            if param.optional:
                if token is None:
                    break
                if not param.recognises(token):
                    settled += 1
                    continue
            if token is None:
                ran_out = True
                used += 1
                continue
            used += 1
            settled += 1
        return used, settled

    def awaiting_name(self, text: str) -> bool:
        """Whether the catalog name is the only argument left to give."""
        answerable = sum(1 for param in self.params if not param.rest)
        return self._walk(text.split()[1:])[1] == answerable

    def _leading_tokens(self, tokens) -> int:
        return self._walk(tokens)[0]

    @property
    def catalogs(self) -> tuple:
        for param in self.params:
            if param.catalogs:
                return param.catalogs
        return ()

    def name_fragment(self, text: str) -> str:
        """The part of text the user has typed into the name position."""
        index = self.name_position(text)
        if index is None:
            return ""
        tokens = text.split(maxsplit=index)
        return tokens[index] if len(tokens) > index else ""

    def hint_for_position(self, position: int, text: str = "") -> str:
        """The arguments still owed, given what has been typed so far."""
        if text:
            typed = text.split()[1:]
            consumed = self._walk(typed)[1]
        else:
            consumed = position - 1
        if 0 <= consumed < len(self.params):
            return " " + " ".join(param.label for param in self.params[consumed:])
        return ""

    def current_argument(self, text: str) -> int | None:
        """Index of the argument being asked for, None once all are answered."""
        tokens = text.split(maxsplit=1)
        remainder = tokens[1] if len(tokens) > 1 else ""
        if self.separator != " ":
            index = remainder.count(";")
        else:
            index = self._walk(remainder.split())[1]
        if index < len(self.params):
            return index
        if self.params and self.params[-1].rest:
            return len(self.params) - 1
        return None

    def hint_for_fields(self, remainder: str) -> str:
        """The definition fields still owed, given what is typed after the name."""
        index = remainder.count(";")
        if 0 <= index < len(self.params):
            return " " + ";".join(param.label for param in self.params[index:])
        if self.params and self.params[-1].rest:
            return " " + self.params[-1].label
        return ""

    def field_being_typed(self, remainder: str):
        """The Param the caret is inside, for a ;-separated command."""
        index = remainder.count(";")
        if index >= len(self.params):
            last = self.params[-1]
            return last if last.rest else None
        return self.params[index]

    def field_fragment(self, remainder: str) -> str:
        """What has been typed into the catalog name of the current field."""
        field = remainder.rsplit(";", 1)[-1].strip()
        if not field:
            return ""
        parts = field.rsplit(maxsplit=1)
        if len(parts) == 2 and _looks_like_an_amount(parts[1]):
            return ""
        return field

    def split(self, remainder: str) -> list[str]:
        """The argument tokens; a trailing rest argument keeps its separators."""
        if not remainder.strip():
            return []
        if self.separator != " ":
            if self.params[-1].rest:
                return remainder.split(self.separator, len(self.params) - 1)
            return remainder.split(self.separator)
        if self.params[-1].rest:
            return remainder.split(None, self._leading_tokens(remainder.split()))
        return remainder.split()

    def _assign(self, tokens):
        """Each argument paired with its token, or with None where it was left out."""
        pairs, position = [], 0
        for param in self.params:
            token = tokens[position] if position < len(tokens) else None
            if param.optional and (token is None or (
                    not param.rest and not param.recognises(token))):
                pairs.append((param, None))
                continue
            pairs.append((param, token))
            position += 1
        if position != len(tokens) or any(
                token is None and not param.optional for param, token in pairs):
            raise CommandError(f"Syntax: {self.name} {self.usage}")
        return pairs

    def parse(self, remainder: str) -> dict:
        tokens = self.split(remainder)
        if self.separator != " ":
            if len(tokens) != len(self.params):
                raise CommandError(f"Syntax: {self.name} {self.usage}")
            pairs = list(zip(self.params, tokens))
        else:
            pairs = self._assign(tokens)

        payload = {"date": datetime.date.today().isoformat()} if self.dated else {}
        for param, token in pairs:
            payload.update(param.default() if token is None else param.parse(token))
        return payload


def _carried_out_by_the_window(db, payload):
    """The invoke of a command the window carries out."""
    raise CommandError("This is carried out by the window, not by a write.")


def _quantity(value: float) -> str:
    """1.0 reads as "1", 1.5 as "1.5"."""
    return f"{value:g}"


def _confirm_new_chore(payload) -> str:
    """What was defined, read back with the rule it will follow."""
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
    """A define command: semicolon-separated fields, one catalog write."""
    return Command(
        name=name,
        params=params,
        separator=";",
        invoke=lambda db, payload, method=method: getattr(db, method)(payload),
        confirm=lambda payload: f" Defined '{payload['name']}' in the shared catalog.",
        domain=domain,
    )


def _amount_written(payload: dict) -> str:
    """How much was logged, in the unit the member typed it in."""
    if payload.get("grams") is not None:
        return f"{_quantity(payload['grams'])} g of"
    return f"{_quantity(payload['servings'])} x"


def _set_definition(name: str, domain: str, word: str, component_param: Param,
                    label: str, aliases: tuple = ()) -> Command:
    """A *set command: one named bundle of catalog items, defined in a line."""
    return Command(
        name=name,
        params=(required_text("name", label,
                              "a name no item or set of this domain already has"),
                component_param),
        separator=";",
        invoke=lambda db, payload, domain=domain: db.add_set(domain, payload),
        confirm=lambda payload, word=word: (
            f" Defined the {word} '{payload['name']}' from "
            f"{len(payload['components'])} "
            f"{'component' if len(payload['components']) == 1 else 'components'}."),
        domain=domain,
        aliases=aliases,
    )

_COMMAND_LIST = [
    Command(
        name="log",
        params=(
            amount(),
            meal_type("meal_type", "[MealType]"),
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
            meal_type("meal_type", "[MealType]"),
            free_text("food_name", "[What it was]"),
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
            optional_number("servings", "[1]"),
            optional_clock_time("time", "[HH:MM=now]"),
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
            set_scheme("[sets: 7,7,7]"),
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
        params=(optional_display_date("date", "[DD.MM.YYYY=today]"),),
        invoke=lambda db, payload: db.log_planned_session(payload),
        confirm=lambda p: (
            f" Logged the session planned for {as_displayed_date(p['date'])}."),
        domain=(EXERCISE, PLAN),
    ),
    _set_definition("exset", EXERCISE, "workout",
                    workout_components("components",
                                       "[Bench Press 8,8,6 60 8; Plank 60 0 6]"),
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
            optional_number("servings", "[1]"),
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
        required_text("name"), number("mets"), free_text("notes"),
    ), "add_mobility_item", MOBILITY),
    Command(
        name="rm",
        params=(item("name", "[Item Profile Catalog Name]", EVERY_CATALOG),),
        invoke=lambda db, payload: db.delete_item_by_name(payload["name"]),
        confirm=lambda p: f" Removed '{p['name']}'.",
        reports_result=True,
        domain=EVERY_DOMAIN_WRITTEN,
    ),
    Command(
        name="track",
        params=(
            graph_slot("slot", "[slot_num: 1-9]"),
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
        name="cols",
        params=(
            optional_one_of("action", "[hide/show/move/reset]", COLUMN_ACTIONS,
                            "Say hide, show, move or reset — or name a column "
                            "on its own to switch it off or back on.", TOGGLE),
            optional_position("position", "[position]"),
            optional_text("column", "[Column]"),
        ),
        invoke=_carried_out_by_the_window,
        confirm=lambda payload: " Columns rearranged.",
        window_effect="arrange_columns",
        aliases=("columns",),
    ),
    Command(
        name="break",
        params=(
            optional_one_of("action", "[long/cancel]", BREAK_ACTIONS,
                            "Say long to make the next break the long one, or "
                            "cancel to take that back.", ""),
        ),
        invoke=_carried_out_by_the_window,
        confirm=lambda payload: " Next break changed.",
        window_effect="queue_long_break",
    ),
    Command(
        name="rest",
        params=(
            optional_one_of("action", "[rm/clear]", QUEUE_ACTIONS,
                            "Say rm with a number, or clear — or name a file "
                            "on its own to queue it.", QUEUE_ADD),
            optional_position("position", "[n]"),
            optional_text("entry", "[path]"),
        ),
        invoke=_carried_out_by_the_window,
        confirm=lambda payload: " Break queue changed.",
        window_effect="queue_rest",
        aliases=("queue",),
    ),
    Command(
        name="chore",
        params=(
            item("name", "[Chore]", (CHORE_CATALOG,)),
        ),
        dated=True,
        invoke=lambda db, payload: db.complete_chore(payload),
        confirm=lambda p: f" Ticked '{p['name']}' off today.",
        domain=CHORE,
        aliases=("done",),
    ),
    Command(
        name="chorenew",
        params=(
            cadence("period_days", "[Every N days or Nw]"),
            optional_display_date("anchor", "[First DD.MM.YYYY]"),
            optional_number("grace_days", "[Grace days]", None),
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
            readable_date("date", "[DD.MM.YYYY]"),
            dsi_value("override_dsi", "[DSI Value or 'clear']"),
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
    """The first word of a line, folded the way COMMANDS is keyed."""
    tokens = text.split(maxsplit=1)
    return tokens[0].lower() if tokens else ""


def naming_a_command(text: str) -> bool:
    """Whether the caret is still inside the command word itself."""
    tokens = text.split(maxsplit=1)
    return len(tokens) <= 1 and not text[-1:].isspace()


def command_being_typed(text: str):
    """The command whose arguments are being given, or None."""
    if naming_a_command(text):
        return None
    return COMMANDS.get(command_word(text))


def candidates_for(text: str, domains=()) -> list:
    """The commands this line could still become, best first."""
    if command_being_typed(text) is not None:
        return []
    return commands_for(command_word(text), domains)


def belongs_to(command: Command, domains) -> bool:
    """Whether command is one of domains’ own."""
    written = set(command.domains)
    return bool(written) and written <= set(domains)


def commands_for(typed: str, domains=()) -> list:
    """Every command a half-typed word could become, best answer first."""
    by_name = {command.name: command for command in _COMMAND_LIST}
    ranked = ranked_matches(typed, list(by_name),
                            prefer=lambda name: belongs_to(by_name[name], domains))
    return [by_name[name] for name in ranked]


def token_position(text: str) -> int:
    """Index of the token the caret is in: 0 is the command word itself."""
    words = text.split()
    return len(words) if text[-1:].isspace() else len(words) - 1
