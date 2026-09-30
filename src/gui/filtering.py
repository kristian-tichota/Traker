import re
from operator import ge, gt, le, lt

from src.domain.clock import as_stored_date
from src.gui.commands import MEAL_SHORTCUTS
from src.gui.completion import normalize

OPERATORS = (">=", "<=", "!=", ":", "=", ">", "<")

_ORDERINGS = {">": gt, "<": lt, ">=": ge, "<=": le}

_TERM = re.compile(r"^(?P<field>\w+)(?P<op>"
                   + "|".join(re.escape(operator) for operator in OPERATORS)
                   + r")(?P<value>.*)$")

_CZECH_DATE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")
_SHORT_HOUR = re.compile(r"^\d:\d{2}$")
_DATE_OR_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}:\d{2}$|^\d{1,2}\.\d{1,2}\.\d{4}$")

ALIASES = {
    "kcal": "Calories", "cal": "Calories", "cals": "Calories",
    "prot": "Protein", "protein": "Protein",
    "carb": "Carbs", "carbs": "Carbs", "sugar": "Sugars", "sugars": "Sugars",
    "fat": "Fats", "salt": "Salt", "fibre": "Fibre", "fiber": "Fibre",
    "food": "Food Name", "name": "Food Name",
    "meal": "Meal Type", "serv": "Servings", "servings": "Servings",
    "g": "Grams", "grams": "Grams",
    "est": "Est", "estimated": "Est",
    "set": ("Meal Set", "Stack", "Drink Set", "Routine Set", "Workout"),
    "mealset": "Meal Set", "stack": "Stack", "workout": "Workout",
    "date": "Date", "time": "Time",
    "ex": "Exercise", "exercise": "Exercise", "weight": "Weight (kg)",
    "rpe": "Perceived Effort", "muscle": "Muscle Group",
    "vol": "Total Volume", "volume": "Total Volume", "1rm": "1RM",
    "bev": "Beverage Name", "caffeine": "Caffeine (mg)",
    "supp": "Supplement Name", "routine": "Routine Name",
    "mins": "Duration (mins)", "duration": "Duration (mins)",
}

_MEAL_SHORTCUTS = {key: normalize(value) for key, value in MEAL_SHORTCUTS.items()}


class FilterError(ValueError):
    """A filter the member must correct."""


def _as_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_stored(value: str) -> str:
    """Return a Czech date or an H:MM time as the row stores it, else unchanged."""
    stripped = value.strip()
    if _CZECH_DATE.match(stripped):
        return as_stored_date(stripped)
    return "0" + stripped if _SHORT_HOUR.match(stripped) else value


def fold(values_by_header: dict) -> tuple:
    """Return (row text, {header: folded cell}), the form a term compares against."""
    by_header = {header: "" if value is None else normalize(str(value))
                 for header, value in values_by_header.items()}
    return " ".join(text for text in by_header.values() if text), by_header


def resolve_field(token: str, headers) -> str:
    """Return the header a field token names, or raise."""
    folded = normalize(token)
    by_fold = {normalize(header): header for header in headers}
    named = ALIASES.get(folded, ())
    for candidate in ((named,) if isinstance(named, str) else named) + (folded,):
        if normalize(candidate) in by_fold:
            return by_fold[normalize(candidate)]

    matches = [header for key, header in by_fold.items() if key.startswith(folded)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise FilterError(
            f"'{token}' matches {len(matches)} columns: {', '.join(matches)}")
    raise FilterError(
        f"No column called '{token}'. Columns: {', '.join(sorted(by_fold.values()))}")


class Term:
    """One condition."""

    def __init__(self, field, operator, value):
        self.field = field
        self.operator = operator
        self.value = value
        self._folded = normalize(_as_stored(str(value)))
        self._number = _as_number(value)
        self._meal = _MEAL_SHORTCUTS.get(self._folded) if field == "Meal Type" else None

    def matches(self, values_by_header: dict, folded) -> bool:
        """Report whether a row matches, given its typed cells and their fold."""
        if self.field is None:
            return self._folded in folded[0]
        value, cell = values_by_header.get(self.field), folded[1].get(self.field)
        if self.operator in (":", "="):
            return self._equalish(value, cell)
        if self.operator == "!=":
            return not self._equalish(value, cell)
        if value is None:
            return False
        if self._number is None:
            return _ORDERINGS[self.operator](cell, self._folded)
        other = _as_number(value)
        return other is not None and _ORDERINGS[self.operator](other, self._number)

    def _equalish(self, value, cell) -> bool:
        """Match by containment on text and exactly on numbers."""
        if value is None:
            return self._folded in ("", "-", "none")
        if self._number is not None:
            other = _as_number(value)
            if other is not None:
                return other == self._number
        if self._meal is not None:
            return cell == self._meal
        return self._folded in cell


class Query:
    """A parsed filter: terms that all have to match."""

    def __init__(self, terms):
        self.terms = tuple(terms)
        self.fields = tuple({term.field for term in self.terms if term.field is not None})

    def __len__(self):
        return len(self.terms)

    def matches(self, values_by_header: dict, folded=None) -> bool:
        """Report whether every term matches, folding the row where no fold is given."""
        folded = folded or fold(values_by_header)
        return all(term.matches(values_by_header, folded) for term in self.terms)

EMPTY = Query(())


def parse(text: str, headers) -> Query:
    """Read a filter line, or raise FilterError naming what is wrong."""
    terms = []
    for token in (text or "").split():
        match = None if _DATE_OR_TIME.match(token) else _TERM.match(token)
        if match is None:
            terms.append(Term(None, ":", token))
            continue

        field_token, operator, value = match.group("field", "op", "value")
        if not value:
            raise FilterError(f"'{field_token}{operator}' is missing a value.")

        field = resolve_field(field_token, headers)
        if operator in _ORDERINGS and _as_number(value) is None \
                and not _DATE_OR_TIME.match(value):
            raise FilterError(
                f"'{value}' is not a number or a date, so '{field} {operator}' "
                f"cannot be compared.")
        terms.append(Term(field, operator, value))
    return Query(terms) if terms else EMPTY
