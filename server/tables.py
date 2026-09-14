import math

from dataclasses import dataclass
from typing import FrozenSet, Optional

from server.payload import BadValue
from server.sets import SET_SPECS


@dataclass(frozen=True)
class TableSpec:
    name: str
    is_catalog: bool
    mutable_columns: FrozenSet[str]
    row_editable: bool = True
    non_negative: FrozenSet[str] = frozenset()
    has_name: bool = True
    exclusive: tuple = ()


def _spec(name, is_catalog, columns, row_editable=True, non_negative=(),
          has_name=True, exclusive=()):
    return TableSpec(name=name, is_catalog=is_catalog,
                     mutable_columns=frozenset(columns),
                     row_editable=row_editable,
                     non_negative=frozenset(non_negative),
                     has_name=has_name,
                     exclusive=tuple(frozenset(group) for group in exclusive))

CATALOG_DOMAINS = {
    "food": "food_items",
    "beverage": "beverage_items",
    "exercise": "exercise_items",
    "supplement": "supplement_items",
    "mobility": "mobility_items",
}

_REGISTRY = {
    spec.name: spec
    for spec in (
        _spec("food_items", True, {
            "name", "category", "energy", "fat_total", "fat_saturated",
            "carbs_total", "carbs_sugars", "fibre", "protein", "salt", "serving_size",
        }),
        _spec("beverage_items", True, {"name", "caffeine_mg", "antioxidants_mg"}),
        _spec("exercise_items", True, {
            "name", "muscle_group", "movement_pattern", "secondary_muscles",
            "plane_of_motion", "joint_mechanics", "equipment_type",
            "unilateral_bilateral", "metric_type",
        }),
        _spec("supplement_items", True, {
            "name", "b12_mcg", "iodine_mcg", "creatine_g", "d3_iu", "k2_mcg",
            "dha_mg", "epa_mg", "calcium_mg", "magnesium_mg", "zinc_mg",
            "c_mg", "l_theanine_mg",
        }, non_negative={
            "b12_mcg", "iodine_mcg", "creatine_g", "d3_iu", "k2_mcg", "dha_mg",
            "epa_mg", "calcium_mg", "magnesium_mg", "zinc_mg", "c_mg", "l_theanine_mg",
        }),
        _spec("mobility_items", True, {"name", "mets", "notes"}),

        _spec("item_sets", True, {"name"}),
        *(_spec(spec.components_table, True,
                {spec.item_column, *spec.amount_columns},
                non_negative=set(spec.amount_columns), has_name=False)
          for spec in SET_SPECS.values()),

        _spec("chores", True,
              {"name", "period_days", "anchor", "grace_days", "notes", "active"},
              non_negative={"period_days", "grace_days"}),
        _spec("chore_completions", True, {"date"}, has_name=False),

        _spec("food_logs", False,
              {"date", "meal_type", "food_item_id", "servings", "grams"},
              non_negative={"servings", "grams"},
              exclusive=(("servings", "grams"),)),
        _spec("beverage_logs", False, {"date", "time", "beverage_item_id", "servings"}),
        _spec("exercise_logs", False, {
            "date", "exercise_item_id", "set1", "set2", "set3", "set4", "set5",
            "weight_kg", "rpe",
        }, non_negative={"set1", "set2", "set3", "set4", "set5", "weight_kg"}),
        _spec("supplement_logs", False, {"date", "supplement_item_id", "servings"}),
        _spec("mobility_logs", False, {"date", "mobility_item_id", "duration_mins"}),

        _spec("pomodoro_heartbeats", False,
              {"date", "minute_of_day", "second", "state", "mode"},
              row_editable=False, non_negative={"minute_of_day", "second"}),
        _spec("pomodoro_events", False, {"timestamp", "event_type", "amount_ms"},
              row_editable=False, non_negative={"amount_ms"}),
        _spec("pomodoro_dsi_overrides", False, {"date", "override_dsi"},
              row_editable=False, non_negative={"override_dsi"}),
        _spec("training_plans", False, {"name", "start_date", "weeks", "notes"},
              non_negative={"weeks"}),
        _spec("plan_sessions", False, {"date", "week", "name", "block", "notes"},
              non_negative={"week"}),
        _spec("plan_movements", False, {
            "exercise_item_id", "position", "sets", "target_low", "target_high",
            "weight_kg", "rpe", "tempo", "grouping", "notes",
        }, non_negative={"position", "sets", "target_low", "target_high",
                         "weight_kg", "rpe"}, has_name=False),
        _spec("user_settings", False, {"key", "value"}, row_editable=False),
    )
}

CATALOG_TABLES = frozenset(s.name for s in _REGISTRY.values() if s.is_catalog)
NAMED_CATALOG_TABLES = frozenset(
    s.name for s in _REGISTRY.values() if s.is_catalog and s.has_name
)
USER_LOG_TABLES = frozenset(
    s.name for s in _REGISTRY.values() if not s.is_catalog and s.row_editable
)


def get_spec(table_name: str) -> Optional[TableSpec]:
    """Return the registration for table_name, or None where it is not exposed."""
    return _REGISTRY.get(table_name)


def mutable_columns(table_name: str) -> FrozenSet[str]:
    spec = get_spec(table_name)
    return spec.mutable_columns if spec else frozenset()


def non_negative_columns(table_name: str) -> FrozenSet[str]:
    spec = get_spec(table_name)
    return spec.non_negative if spec else frozenset()


def exclusive_partners(table_name: str, column: str) -> FrozenSet[str]:
    """Return the columns a write to column must empty, or nothing."""
    spec = get_spec(table_name)
    if spec is None:
        return frozenset()
    for group in spec.exclusive:
        if column in group:
            return frozenset(group) - {column}
    return frozenset()

_DECLARED_TYPES = {"TEXT": str, "REAL": float, "INTEGER": int}

_type_cache = {}


def column_type(conn, table_name: str, column: str):
    """Return the declared Python type of column, from PRAGMA table_info."""
    types = _type_cache.get(table_name)
    if types is None:
        types = {
            row["name"]: _DECLARED_TYPES.get((row["type"] or "").upper())
            for row in conn.execute(f"PRAGMA table_info({table_name})")
        }
        _type_cache[table_name] = types
    return types.get(column)


def coerce_value(conn, table_name: str, column: str, value):
    """Convert an inbound value to the column's declared type."""
    if isinstance(value, (dict, list)):
        raise BadValue(f"{column} takes a single value, not a {type(value).__name__}")
    target = column_type(conn, table_name, column)
    if target is None or value is None:
        return value
    if target is str:
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise BadValue(f"'{value}' is not a number, but {column} stores one")
    if not math.isfinite(number):
        # float() takes "inf" and "1e400"; SQLite stores them and every later sum is infinite.
        raise BadValue(f"'{value}' is not a finite number, but {column} stores one")
    return int(number) if target is int else number


def reset_type_cache() -> None:
    """Forget the cached PRAGMA reads."""
    _type_cache.clear()
