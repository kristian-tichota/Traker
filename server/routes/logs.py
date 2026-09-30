from flask import Blueprint, g

from server import sets
from server.auth import require_auth
from server.database import AD_HOC_CATEGORY
from server.db_session import get_db, insert, named, rows
from server.events import catalog_updated
from server.payload import BadPayload, BadValue, Conflict, read_payload
from server.tables import SUPPLEMENT_DOSES
from server.validation import checked_columns, checked_payload, since_date

logs_bp = Blueprint("logs", __name__)

FOOD_AMOUNTS = ("servings", "grams")

AD_HOC_SERVING_G = 100.0

_GRAMS = "COALESCE(l.grams, l.servings * i.serving_size)"

_SERVINGS = ("CASE WHEN l.servings IS NOT NULL THEN l.servings "
             "WHEN i.serving_size > 0 THEN l.grams / i.serving_size END")

_FOOD_COLUMNS = (
    f"l.id, l.estimated, l.date, l.meal_type, i.name, {_SERVINGS}, {_GRAMS}, s.name, "
    + ", ".join(f"i.{nutrient} * {_GRAMS} / 100.0" for nutrient in (
        "energy", "protein", "carbs_total", "carbs_sugars", "fat_total", "fat_saturated",
        "salt", "fibre")))


def _ledger(domain: str, columns: str, order: str = "l.date DESC, l.id DESC") -> list:
    """Return this member's rows of one domain's log, from the optional ?since= on."""
    spec = sets.spec_for(domain)
    return rows(f"SELECT {columns} FROM {spec.log_table} l "
                f"LEFT JOIN {spec.catalog_table} i ON l.{spec.log_item_column} = i.id "
                f"LEFT JOIN item_sets s ON l.set_id = s.id "
                f"WHERE l.user_id = ? AND l.date >= ? ORDER BY {order}",
                (g.user_id, since_date()))


def _name(spec, name):
    """Return the item or set name a log write carries, once it is text."""
    if not isinstance(name, str):
        raise BadValue(
            f"{spec.domain.capitalize()} name must be text, not a {type(name).__name__}.")
    return name


def _unknown_name(spec, name):
    """Return the refusal for a name that is neither an item nor a set."""
    return BadValue(
        f"{spec.domain.capitalize()} '{name}' not found in catalog, and there "
        f"is no {spec.word} by that name either.")


def _log_item(conn, spec, item_id, fixed: dict, values: dict):
    """Write one ordinary log row."""
    with conn:
        insert(spec.log_table, [{"user_id": g.user_id, **fixed,
                                 spec.log_item_column: item_id, **values}])


def _log_set(conn, spec, set_row, multiplier, fixed: dict) -> int:
    """Write one log row per component of a set, and return how many."""
    expanded = sets.expansion(conn, spec, set_row["id"], multiplier)
    if not expanded:
        raise BadValue(
            f"{spec.word.capitalize()} '{set_row['name']}' has no components yet.")

    written = []
    for item_id, item_name, amounts in expanded:
        try:
            checked = checked_columns(conn, spec.log_table, amounts)
        except BadValue as bad_amount:
            raise BadValue(
                f"{set_row['name']} x{multiplier:g} is more than {item_name} can "
                f"be logged as: {bad_amount}") from None
        written.append({"user_id": g.user_id, **fixed, spec.log_item_column: item_id,
                        "set_id": set_row["id"], **checked})
    with conn:
        insert(spec.log_table, written)
    return len(written)


def _log_item_or_set(conn, spec, name, fixed: dict, amount: float):
    """Log amount of name, whichever of the two namespaces holds it."""
    name = _name(spec, name)
    item = named(spec.catalog_table, name)
    if item is not None:
        (amount_column,) = spec.log_amount_columns
        _log_item(conn, spec, item["id"], fixed, {amount_column: amount})
        return {"status": "success", "rows": 1}

    named_set = sets.find(conn, spec.domain, name)
    if named_set is None:
        raise _unknown_name(spec, name)
    written = _log_set(conn, spec, named_set, amount, fixed)
    return {"status": "success", "rows": written, "set": named_set["name"]}


@logs_bp.route("/food", methods=["GET"])
@require_auth
def get_food_logs():
    return _ledger("food", _FOOD_COLUMNS)


def _food_amount(payload) -> str:
    """Return which of servings or grams this write carries."""
    given = [column for column in FOOD_AMOUNTS if payload.get(column) is not None]
    if len(given) == 1:
        return given[0]
    if not given:
        raise BadPayload("Missing required field(s): an amount in servings or grams")
    raise BadPayload("An amount is either servings or grams, not both.")


@logs_bp.route("/food", methods=["POST"])
@require_auth
def add_food_log():
    """Log a food, or a whole meal set, against one meal of one day."""
    d = read_payload("date", "meal_type", "food_name")
    conn = get_db()
    amount = _food_amount(d)
    v = checked_payload(conn, "food_logs", d, ("date", "meal_type", amount))

    spec = sets.spec_for("food")
    name = _name(spec, d["food_name"])
    fixed = {"date": v["date"], "meal_type": v["meal_type"]}
    item = named("food_items", name, "id, category")
    if item is not None:
        estimated = int(item["category"] == AD_HOC_CATEGORY)
        _log_item(conn, spec, item["id"], fixed, {amount: v[amount], "estimated": estimated})
        return {"status": "success", "rows": 1, "estimated": bool(estimated)}

    meal_set = sets.find(conn, "food", name)
    if meal_set is None:
        raise _unknown_name(spec, name)
    if amount == "grams":
        raise BadValue(
            f"'{meal_set['name']}' is a meal set, so log it as a multiple "
            f"rather than in grams — its ingredients are already in grams.")

    written = _log_set(conn, spec, meal_set, v["servings"], fixed)
    return {"status": "success", "rows": written,
            "meal_set": meal_set["name"], "set": meal_set["name"]}


@logs_bp.route("/food/quick", methods=["POST"])
@require_auth
def add_quick_food_log():
    """Log a meal nobody has a label for, as an estimate in calories."""
    d = read_payload("date", "meal_type", "food_name", "energy_kcal")
    conn = get_db()
    name = d["food_name"]
    if not isinstance(name, str) or not name.strip():
        raise BadValue("An estimate needs something to call it.")
    name = name.strip()

    v = checked_payload(conn, "food_logs", d, ("date", "meal_type"))
    energy = checked_payload(
        conn, "food_items", {"energy": d["energy_kcal"]}, ("energy",))["energy"]
    if energy <= 0:
        raise BadValue("An estimate needs more than zero calories.")

    held = named("food_items", name, "name, category")
    if held is not None:
        how = ("log it with :log — it is already an estimate"
               if held["category"] == AD_HOC_CATEGORY
               else "log it with :log, or give this estimate another name")
        raise Conflict(f"'{held['name']}' is already a food, so {how}.")
    if sets.find(conn, "food", name) is not None:
        raise Conflict(f"'{name}' is already a meal set, so an estimate by that name "
                       f"could not be logged.")

    with conn:
        cursor = conn.execute("""
            INSERT INTO food_items
                (name, category, energy, fat_total, fat_saturated, carbs_total,
                 carbs_sugars, fibre, protein, salt, serving_size)
            VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0, ?)
        """, (name, AD_HOC_CATEGORY, energy, AD_HOC_SERVING_G))
        conn.execute("""
            INSERT INTO food_logs
                (user_id, date, meal_type, food_item_id, servings, estimated)
            VALUES (?, ?, ?, ?, 1.0, 1)
        """, (g.user_id, v["date"], v["meal_type"], cursor.lastrowid))

    catalog_updated(table="food_items", action="insert", name=name)
    return {"status": "success", "rows": 1, "estimated": True, "energy_kcal": energy}


@logs_bp.route("/beverage", methods=["GET"])
@require_auth
def get_beverage_logs():
    return _ledger("beverage", "l.id, l.date, l.time, i.name, s.name, l.servings, "
                               "i.antioxidants_mg * l.servings, i.caffeine_mg * l.servings",
                   order="l.date DESC, l.time DESC")


@logs_bp.route("/beverage", methods=["POST"])
@require_auth
def add_beverage_log():
    d = read_payload("date", "time", "bev_name", "servings")
    conn = get_db()
    v = checked_payload(conn, "beverage_logs", d, ("date", "time", "servings"))
    return _log_item_or_set(conn, sets.spec_for("beverage"), d["bev_name"],
                            {"date": v["date"], "time": v["time"]}, v["servings"])


@logs_bp.route("/exercise", methods=["GET"])
@require_auth
def get_exercise_logs():
    return _ledger("exercise", "l.id, l.date, i.name, s.name, l.set1, l.set2, l.set3, "
                               "l.set4, l.set5, l.weight_kg, l.rpe, i.muscle_group, "
                               "i.metric_type")


@logs_bp.route("/exercise", methods=["POST"])
@require_auth
def add_exercise_log():
    d = read_payload("date", "ex_name", "weight_kg", "rpe")
    conn = get_db()
    spec = sets.spec_for("exercise")
    scheme = spec.log_amount_columns
    v = checked_payload(conn, "exercise_logs", d, ("date",) + scheme,
                        defaults=dict.fromkeys(scheme, 0))

    name = _name(spec, d["ex_name"])
    item = named("exercise_items", name)
    if item is None:
        if sets.find(conn, "exercise", name) is not None:
            raise BadValue(
                f"'{name}' is a workout, which carries its own sets and "
                f"loads. Log it with :wlog.")
        raise _unknown_name(spec, name)

    _log_item(conn, spec, item["id"], {"date": v["date"]},
              {column: v[column] for column in scheme})
    return {"status": "success", "rows": 1}


@logs_bp.route("/exercise/workout", methods=["POST"])
@require_auth
def add_workout_log():
    """Log every movement of a workout template, as the template describes it."""
    d = read_payload("date", "name")
    conn = get_db()
    v = checked_payload(conn, "exercise_logs", d, ("date",))

    spec = sets.spec_for("exercise")
    name = _name(spec, d["name"])
    workout = sets.find(conn, "exercise", name)
    if workout is None:
        raise BadValue(f"No workout called '{name}'.")
    written = _log_set(conn, spec, workout, 1.0, {"date": v["date"]})
    return {"status": "success", "rows": written, "set": workout["name"]}


@logs_bp.route("/supplement", methods=["GET"])
@require_auth
def get_supplement_logs():
    return _ledger("supplement", "l.id, l.date, i.name, s.name, l.servings, " + ", ".join(
        f"i.{dose} * l.servings" for dose in SUPPLEMENT_DOSES))


@logs_bp.route("/supplement", methods=["POST"])
@require_auth
def add_supplement_log():
    d = read_payload("date", "supp_name", "servings")
    conn = get_db()
    v = checked_payload(conn, "supplement_logs", d, ("date", "servings"))
    return _log_item_or_set(conn, sets.spec_for("supplement"), d["supp_name"],
                            {"date": v["date"]}, v["servings"])


@logs_bp.route("/mobility", methods=["GET"])
@require_auth
def get_mobility_logs():
    return _ledger("mobility", "l.id, l.date, i.name, s.name, l.duration_mins, i.mets")


@logs_bp.route("/mobility", methods=["POST"])
@require_auth
def add_mobility_log():
    d = read_payload("date", "mob_name", "duration_mins")
    conn = get_db()
    v = checked_payload(conn, "mobility_logs", d, ("date", "duration_mins"))
    return _log_item_or_set(conn, sets.spec_for("mobility"), d["mob_name"],
                            {"date": v["date"]}, v["duration_mins"])
