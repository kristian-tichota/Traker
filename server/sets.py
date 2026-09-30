from dataclasses import dataclass

_AMOUNT = ("amount",)

_SCHEME = ("set1", "set2", "set3", "set4", "set5", "weight_kg", "rpe")


@dataclass(frozen=True)
class SetSpec:
    """One domain's named sets: where their parts come from and go to."""

    domain: str
    catalog_table: str
    components_table: str
    item_column: str
    log_table: str
    log_item_column: str
    amount_columns: tuple
    log_amount_columns: tuple
    unit: str
    word: str
    scaled: bool = True

    @property
    def has_single_amount(self) -> bool:
        return self.amount_columns == _AMOUNT

_SPECS = (
    SetSpec("food", "food_items", "food_set_components", "food_item_id",
            "food_logs", "food_item_id", _AMOUNT, ("grams",), "g", "meal set"),
    SetSpec("beverage", "beverage_items", "beverage_set_components", "beverage_item_id",
            "beverage_logs", "beverage_item_id", _AMOUNT, ("servings",),
            "servings", "drink set"),
    SetSpec("supplement", "supplement_items", "supplement_set_components",
            "supplement_item_id", "supplement_logs", "supplement_item_id",
            _AMOUNT, ("servings",), "servings", "stack"),
    SetSpec("mobility", "mobility_items", "mobility_set_components", "mobility_item_id",
            "mobility_logs", "mobility_item_id", _AMOUNT, ("duration_mins",),
            "min", "routine set"),
    SetSpec("exercise", "exercise_items", "exercise_set_components", "exercise_item_id",
            "exercise_logs", "exercise_item_id", _SCHEME, _SCHEME, "", "workout",
            scaled=False),
)

SET_SPECS = {spec.domain: spec for spec in _SPECS}
SET_DOMAINS = tuple(SET_SPECS)


def spec_for(domain: str):
    """Return the registration for domain, or None where it has no sets."""
    return SET_SPECS.get(domain)


def find(conn, domain: str, name: str):
    """Return the item_sets row this domain calls name, or None."""
    return conn.execute(
        "SELECT id, name, domain FROM item_sets "
        "WHERE domain = ? AND name = ? COLLATE NOCASE", (domain, name)
    ).fetchone()


def expansion(conn, spec: SetSpec, set_id: int, multiplier: float):
    """Return what logging this set writes: (item_id, item name, {column: value}) each."""
    scale = float(multiplier) if spec.scaled else 1.0
    amounts = ", ".join(f"c.{column}" for column in spec.amount_columns)
    components = conn.execute(
        f"""SELECT i.id, i.name, {amounts}
            FROM {spec.components_table} c
            JOIN {spec.catalog_table} i ON i.id = c.{spec.item_column}
            WHERE c.set_id = ?
            ORDER BY i.name COLLATE NOCASE""", (set_id,))
    return [(item_id, item_name, {target: value * scale for target, value
                                  in zip(spec.log_amount_columns, values)})
            for item_id, item_name, *values in components]


def every_set_using(conn, item_name: str):
    """Return (spec, [set names]) for every domain the name is a component of."""
    found = []
    for spec in _SPECS:
        names = [row["name"] for row in conn.execute(
            f"""SELECT DISTINCT s.name FROM item_sets s
                JOIN {spec.components_table} c ON c.set_id = s.id
                JOIN {spec.catalog_table} i ON i.id = c.{spec.item_column}
                WHERE s.domain = ? AND i.name = ? COLLATE NOCASE
                ORDER BY s.name""", (spec.domain, item_name))]
        if names:
            found.append((spec, names))
    return found


def listing(conn, spec: SetSpec):
    """Return every set of one domain, as one row per component."""
    amounts = ", ".join(f"c.{column}" for column in spec.amount_columns)
    return conn.execute(
        f"""SELECT c.id, s.name, i.name, {amounts}
            FROM item_sets s
            LEFT JOIN {spec.components_table} c ON c.set_id = s.id
            LEFT JOIN {spec.catalog_table} i ON i.id = c.{spec.item_column}
            WHERE s.domain = ?
            ORDER BY s.name COLLATE NOCASE, i.name COLLATE NOCASE""",
        (spec.domain,)
    ).fetchall()
