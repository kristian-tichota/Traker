import re

from src.domain.clock import as_stored_date
from src.gui.commands import MEAL_SHORTCUTS
from src.gui.completion import normalize

OPERATORS = (">=", "<=", "!=", ":", "=", ">", "<")

_TERM = re.compile(r"^(?P<field>\w+)(?P<op>"
                   + "|".join(re.escape(operator) for operator in OPERATORS)
                   + r")(?P<value>.*)$")

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


def resolve_field(token: str, headers) -> str:
    """The header a field token names, or raise."""
    folded = normalize(token)
    alias = ALIASES.get(folded)
    if alias is not None:
        for candidate in ((alias,) if isinstance(alias, str) else alias):
            for header in headers:
                if normalize(header) == normalize(candidate):
                    return header

    for header in headers:
        if normalize(header) == folded:
            return header
    matches = [header for header in headers if normalize(header).startswith(folded)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise FilterError(
            f"'{token}' matches {len(matches)} columns: {', '.join(matches)}")

    known = ", ".join(sorted({*headers}))
    raise FilterError(f"No column called '{token}'. Columns: {known}")


class Term:
    """One condition."""

    def __init__(self, field, operator, value):
        self.field = field
        self.operator = operator
        self.value = value
        self._folded = normalize(_as_iso_if_a_date(str(value)))
        self._number = _as_number(value)

    def __repr__(self):
        if self.field is None:
            return f"Term(any ~ {self.value!r})"
        return f"Term({self.field!r} {self.operator} {self.value!r})"

    def matches(self, values_by_header: dict, folded=None) -> bool:
        """Whether a row matches; folded is the caller's cached text and cells."""
        if self.field is None:
            if folded is not None:
                return self._folded in folded[0]
            return any(self._contains(value) for value in values_by_header.values())
        return self._compare(values_by_header.get(self.field),
                             None if folded is None else folded[1].get(self.field))

    def _contains(self, value) -> bool:
        """Bare-word match: the folded needle anywhere in the folded cell."""
        if value is None:
            return False
        return self._folded in normalize(str(value))

    def _compare(self, value, folded_cell=None) -> bool:
        if self.operator in (":", "="):
            return self._equalish(value, folded_cell)
        if self.operator == "!=":
            return not self._equalish(value, folded_cell)

        left, right = self._orderable(value, folded_cell)
        if left is None:
            return False
        if self.operator == ">":
            return left > right
        if self.operator == "<":
            return left < right
        if self.operator == ">=":
            return left >= right
        return left <= right

    def _equalish(self, value, folded_cell=None) -> bool:
        """Containment on text, exact on numbers."""
        if value is None:
            return self._folded in ("", "-", "none")
        if self._number is not None:
            other = _as_number(value)
            if other is not None:
                return other == self._number
        folded_value = normalize(str(value)) if folded_cell is None else folded_cell
        if self.field == "Meal Type" and self._folded in _MEAL_SHORTCUTS:
            return folded_value == _MEAL_SHORTCUTS[self._folded]
        return self._folded in folded_value

    def _orderable(self, value, folded_cell=None):
        """(cell, needle) as comparable types, or (None, None)."""
        if value is None:
            return None, None
        if self._number is not None:
            other = _as_number(value)
            return (other, self._number) if other is not None else (None, None)
        return (normalize(str(value)) if folded_cell is None else folded_cell), self._folded


class Query:
    """A parsed filter: terms that all have to match."""

    def __init__(self, terms):
        self.terms = list(terms)

    def __bool__(self):
        return bool(self.terms)

    @property
    def fields(self) -> tuple:
        """The columns whose typed value some term has to read."""
        return tuple({term.field for term in self.terms if term.field is not None})

    def __len__(self):
        return len(self.terms)

    def __repr__(self):
        return f"Query({self.terms!r})"

    def matches(self, values_by_header: dict, folded=None) -> bool:
        """Terms AND together."""
        return all(term.matches(values_by_header, folded) for term in self.terms)

EMPTY = Query(())


def parse(text: str, headers) -> Query:
    """Read a filter line, or raise FilterError naming what is wrong."""
    if not text or not text.strip():
        return EMPTY

    terms = []
    for token in text.split():
        match = _TERM.match(token)
        if match is None:
            terms.append(Term(None, ":", token))
            continue

        field_token, operator, value = (
            match.group("field"), match.group("op"), match.group("value"))
        if not value:
            raise FilterError(f"'{field_token}{operator}' is missing a value.")

        field = resolve_field(field_token, headers)
        if operator in (">", "<", ">=", "<=") and _as_number(value) is None \
                and not _looks_like_a_date_or_time(value):
            raise FilterError(
                f"'{value}' is not a number or a date, so '{field} {operator}' "
                f"cannot be compared.")
        terms.append(Term(field, operator, value))
    return Query(terms)

_CZECH_DATE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")
_DATE_OR_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}:\d{2}$|^\d{1,2}\.\d{1,2}\.\d{4}$")


def _looks_like_a_date_or_time(value: str) -> bool:
    return bool(_DATE_OR_TIME.match(value.strip()))


def _as_iso_if_a_date(value: str) -> str:
    """A Czech date as the ISO string the row holds, else unchanged."""
    stripped = value.strip()
    return as_stored_date(stripped) if _CZECH_DATE.match(stripped) else value
