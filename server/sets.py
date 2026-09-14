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
    def amount_column(self) -> str:
        """The single amount column, for the four domains that have one."""
        return self.amount_columns[0]

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
    """The registration for domain, or None if it has no sets."""
    return SET_SPECS.get(domain)


def spec_of_catalog(catalog_table: str):
    """The set registration whose components name items in this catalog."""
    for spec in _SPECS:
        if spec.catalog_table == catalog_table:
            return spec
    return None


def find(conn, domain: str, name: str):
    """The item_sets row this domain calls name, or None."""
    return conn.execute(
        "SELECT id, name, domain FROM item_sets "
        "WHERE domain = ? AND name = ? COLLATE NOCASE", (domain, name)
    ).fetchone()


def components_of(conn, spec: SetSpec, set_id: int):
    """One row per component: the item's name, then its amount columns."""
    amounts = ", ".join(f"c.{column}" for column in spec.amount_columns)
    return conn.execute(
        f"""SELECT i.name AS item_name, i.id AS item_id, {amounts}
            FROM {spec.components_table} c
            JOIN {spec.catalog_table} i ON i.id = c.{spec.item_column}
            WHERE c.set_id = ?
            ORDER BY i.name COLLATE NOCASE""", (set_id,)
    ).fetchall()


def expansion(conn, spec: SetSpec, set_id: int, multiplier: float):
    """What logging this set writes: one (item_id, {log column: value}) each."""
    scale = float(multiplier) if spec.scaled else 1.0
    expanded = []
    for component in components_of(conn, spec, set_id):
        values = {}
        for source, target in zip(spec.amount_columns, spec.log_amount_columns):
            value = component[source]
            values[target] = None if value is None else value * scale
        expanded.append((component["item_id"], component["item_name"], values))
    return expanded


def sets_using(conn, catalog_table: str, item_name: str):
    """The names of the sets that would be left with a hole without this item."""
    spec = spec_of_catalog(catalog_table)
    if spec is None:
        return []
    return [row["name"] for row in conn.execute(
        f"""SELECT DISTINCT s.name FROM item_sets s
            JOIN {spec.components_table} c ON c.set_id = s.id
            JOIN {spec.catalog_table} i ON i.id = c.{spec.item_column}
            WHERE s.domain = ? AND i.name = ? COLLATE NOCASE
            ORDER BY s.name""", (spec.domain, item_name))]


def every_set_using(conn, item_name: str):
    """(word, [set names]) for every domain a name is a component of."""
    found = []
    for spec in _SPECS:
        names = sets_using(conn, spec.catalog_table, item_name)
        if names:
            found.append((spec, names))
    return found


def listing(conn, spec: SetSpec):
    """Every set of one domain, as one row per component."""
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
