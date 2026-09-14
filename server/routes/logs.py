from flask import Blueprint, jsonify, g, request

from server import sets
from server.auth import require_auth
from server.database import AD_HOC_CATEGORY
from server.db_session import get_db
from server.events import event_broadcaster
from server.payload import BadPayload, BadValue, read_payload
from server.validation import (checked_columns, checked_payload,
                               validate_column_value)

logs_bp = Blueprint("logs", __name__)

FOOD_AMOUNTS = ("servings", "grams")

AD_HOC_SERVING_G = 100.0

_GRAMS = "COALESCE(l.grams, l.servings * f.serving_size)"

_SERVINGS = ("CASE WHEN l.servings IS NOT NULL THEN l.servings "
             "WHEN f.serving_size > 0 THEN l.grams / f.serving_size END")


def _since_clause():
    """Return the optional ?since= bound, as (sql, params)."""
    since = request.args.get("since")
    if not since:
        return "", ()
    validate_column_value("date", since)
    return " AND l.date >= ?", (since,)


def _resolve_item(conn, table: str, name: str, label: str):
    """Return the catalog id for name, or a 400 refusing the name."""
    if not isinstance(name, str):
        return None, (jsonify(
            {"error": f"{label} name must be text, not a {type(name).__name__}."}
        ), 400)
    row = conn.execute(
        f"SELECT id FROM {table} WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if row is None:
        return None, (jsonify({"error": f"{label} '{name}' not found in catalog."}), 400)
    return row["id"], None


def _catalog_id(conn, table: str, name):
    """Return the catalog id for name, or None, deciding nothing."""
    if not isinstance(name, str):
        return None
    row = conn.execute(
        f"SELECT id FROM {table} WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    return row["id"] if row else None


def _unknown_name(spec, name):
    """Return the refusal for a name that is neither an item nor a set."""
    return BadValue(
        f"{spec.domain.capitalize()} '{name}' not found in catalog, and there "
        f"is no {spec.word} by that name either.")


def _insert_log_row(conn, spec, item_id, fixed: dict, values: dict):
    """Write one ordinary log row."""
    columns = [*fixed, spec.log_item_column, *values]
    placeholders = ", ".join("?" * (len(columns) + 1))
    with conn:
        conn.execute(
            f"INSERT INTO {spec.log_table} (user_id, {', '.join(columns)}) "
            f"VALUES ({placeholders})",
            (g.user_id, *fixed.values(), item_id, *values.values()))


def _log_set(conn, spec, set_row, multiplier, fixed: dict):
    """Write one log row per component of a set."""
    expanded = sets.expansion(conn, spec, set_row["id"], multiplier)
    if not expanded:
        raise BadValue(
            f"{spec.word.capitalize()} '{set_row['name']}' has no components yet.")

    rows = []
    for item_id, item_name, amounts in expanded:
        try:
            checked = checked_columns(conn, spec.log_table, amounts)
        except BadValue as bad_amount:
            raise BadValue(
                f"{set_row['name']} x{multiplier:g} is more than {item_name} can "
                f"be logged as: {bad_amount}") from None
        rows.append(checked)

    columns = ["user_id", *fixed, spec.log_item_column, "set_id",
               *spec.log_amount_columns]
    placeholders = ", ".join("?" * len(columns))
    values = [
        (g.user_id, *fixed.values(), item_id, set_row["id"],
         *(checked[column] for column in spec.log_amount_columns))
        for (item_id, _name, _raw), checked in zip(expanded, rows)
    ]
    with conn:
        conn.executemany(
            f"INSERT INTO {spec.log_table} ({', '.join(columns)}) "
            f"VALUES ({placeholders})", values)
    return len(values)


def _log_item_or_set(conn, spec, name, fixed: dict, amount: float):
    """Log amount of name, whichever of the two namespaces holds it."""
    (amount_column,) = spec.log_amount_columns
    item_id = _catalog_id(conn, spec.catalog_table, name)
    if item_id is not None:
        _insert_log_row(conn, spec, item_id, fixed, {amount_column: amount})
        return jsonify({"status": "success", "rows": 1})

    named_set = sets.find(conn, spec.domain, name)
    if named_set is None:
        raise _unknown_name(spec, name)
    written = _log_set(conn, spec, named_set, amount, fixed)
    return jsonify({"status": "success", "rows": written,
                    "set": named_set["name"]})


@logs_bp.route("/food", methods=["GET"])
@require_auth
def get_food_logs():
    since_sql, since_params = _since_clause()
    nutrients = ", ".join(
        f"(f.{column} * {_GRAMS} / 100.0) AS {alias}" for column, alias in (
            ("energy", "cal"), ("protein", "prot"), ("carbs_total", "carb"),
            ("carbs_sugars", "sugar"), ("fat_total", "fat"),
            ("fat_saturated", "sat_fat"), ("salt", "salt"), ("fibre", "fibre"),
        ))
    q = f"""SELECT l.id, l.estimated, l.date, l.meal_type, f.name,
                  {_SERVINGS} AS servings, {_GRAMS} AS grams, s.name AS set_name,
                  {nutrients}
           FROM food_logs l LEFT JOIN food_items f ON l.food_item_id = f.id
           LEFT JOIN item_sets s ON l.set_id = s.id
           WHERE l.user_id = ?{since_sql} ORDER BY l.date DESC, l.id DESC"""
    conn = get_db()
    rows = conn.execute(q, (g.user_id, *since_params)).fetchall()
    return jsonify([list(r) for r in rows])


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

    name = d["food_name"]
    if not isinstance(name, str):
        raise BadValue(f"Food name must be text, not a {type(name).__name__}.")

    spec = sets.spec_for("food")
    fixed = {"date": v["date"], "meal_type": v["meal_type"]}
    item = conn.execute(
        "SELECT id, category FROM food_items WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if item is not None:
        estimated = 1 if (item["category"] or "") == AD_HOC_CATEGORY else 0
        _insert_log_row(conn, spec, item["id"], fixed,
                        {amount: v[amount], "estimated": estimated})
        return jsonify({"status": "success", "rows": 1, "estimated": bool(estimated)})

    meal_set = sets.find(conn, "food", name)
    if meal_set is None:
        raise _unknown_name(spec, name)
    if amount == "grams":
        raise BadValue(
            f"'{meal_set['name']}' is a meal set, so log it as a multiple "
            f"rather than in grams — its ingredients are already in grams.")

    written = _log_set(conn, spec, meal_set, v["servings"], fixed)
    return jsonify({"status": "success", "rows": written,
                    "meal_set": meal_set["name"], "set": meal_set["name"]})


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

    held = conn.execute(
        "SELECT name, category FROM food_items WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if held is not None:
        how = ("log it with :log — it is already an estimate"
               if (held["category"] or "") == AD_HOC_CATEGORY
               else "log it with :log, or give this estimate another name")
        return jsonify({"error": f"'{held['name']}' is already a food, so {how}."}), 409
    if sets.find(conn, "food", name) is not None:
        return jsonify({"error": (
            f"'{name}' is already a meal set, so an estimate by that name "
            f"could not be logged."
        )}), 409

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

    event_broadcaster.broadcast(
        "catalog_updated", {"table": "food_items", "action": "insert", "name": name})
    return jsonify({"status": "success", "rows": 1, "estimated": True,
                    "energy_kcal": energy})


@logs_bp.route("/beverage", methods=["GET"])
@require_auth
def get_beverage_logs():
    since_sql, since_params = _since_clause()
    q = f"""SELECT l.id, l.date, l.time, b.name, s.name AS set_name, l.servings,
                  (b.antioxidants_mg * l.servings) as anti,
                  (b.caffeine_mg * l.servings) as caff
           FROM beverage_logs l LEFT JOIN beverage_items b ON l.beverage_item_id = b.id
           LEFT JOIN item_sets s ON l.set_id = s.id
           WHERE l.user_id = ?{since_sql} ORDER BY l.date DESC, l.time DESC"""
    conn = get_db()
    rows = conn.execute(q, (g.user_id, *since_params)).fetchall()
    return jsonify([list(r) for r in rows])


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
    since_sql, since_params = _since_clause()
    q = f"""SELECT l.id, l.date, e.name, st.name AS set_name, l.set1, l.set2,
                  l.set3, l.set4, l.set5, l.weight_kg, l.rpe, e.muscle_group,
                  e.metric_type
           FROM exercise_logs l LEFT JOIN exercise_items e ON l.exercise_item_id = e.id
           LEFT JOIN item_sets st ON l.set_id = st.id
           WHERE l.user_id = ?{since_sql} ORDER BY l.date DESC, l.id DESC"""
    conn = get_db()
    rows = conn.execute(q, (g.user_id, *since_params)).fetchall()
    return jsonify([list(r) for r in rows])


@logs_bp.route("/exercise", methods=["POST"])
@require_auth
def add_exercise_log():
    d = read_payload("date", "ex_name", "weight_kg", "rpe")
    conn = get_db()
    scheme = sets.spec_for("exercise").log_amount_columns
    v = checked_payload(conn, "exercise_logs", d, ("date",) + scheme,
                        defaults={column: 0 for column in scheme})

    spec = sets.spec_for("exercise")
    item_id = _catalog_id(conn, "exercise_items", d["ex_name"])
    if item_id is None:
        if sets.find(conn, "exercise", d["ex_name"]) is not None:
            raise BadValue(
                f"'{d['ex_name']}' is a workout, which carries its own sets and "
                f"loads. Log it with :wlog.")
        raise _unknown_name(spec, d["ex_name"])

    _insert_log_row(conn, spec, item_id, {"date": v["date"]},
                    {column: v[column] for column in scheme})
    return jsonify({"status": "success", "rows": 1})


@logs_bp.route("/exercise/workout", methods=["POST"])
@require_auth
def add_workout_log():
    """Log every movement of a workout template, as the template describes it."""
    d = read_payload("date", "name")
    conn = get_db()
    v = checked_payload(conn, "exercise_logs", d, ("date",))

    spec = sets.spec_for("exercise")
    workout = sets.find(conn, "exercise", d["name"])
    if workout is None:
        raise BadValue(f"No workout called '{d['name']}'.")
    written = _log_set(conn, spec, workout, 1.0, {"date": v["date"]})
    return jsonify({"status": "success", "rows": written, "set": workout["name"]})


@logs_bp.route("/supplement", methods=["GET"])
@require_auth
def get_supplement_logs():
    since_sql, since_params = _since_clause()
    q = f"""SELECT l.id, l.date, s.name, st.name AS set_name, l.servings,
                  (s.b12_mcg * l.servings), (s.iodine_mcg * l.servings), (s.creatine_g * l.servings),
                  (s.d3_iu * l.servings), (s.k2_mcg * l.servings), (s.dha_mg * l.servings),
                  (s.epa_mg * l.servings), (s.calcium_mg * l.servings), (s.magnesium_mg * l.servings),
                  (s.zinc_mg * l.servings), (s.c_mg * l.servings), (s.l_theanine_mg * l.servings)
           FROM supplement_logs l LEFT JOIN supplement_items s ON l.supplement_item_id = s.id
           LEFT JOIN item_sets st ON l.set_id = st.id
           WHERE l.user_id = ?{since_sql} ORDER BY l.date DESC, l.id DESC"""
    conn = get_db()
    rows = conn.execute(q, (g.user_id, *since_params)).fetchall()
    return jsonify([list(r) for r in rows])


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
    since_sql, since_params = _since_clause()
    q = f"""SELECT l.id, l.date, m.name, s.name AS set_name, l.duration_mins, m.mets
           FROM mobility_logs l LEFT JOIN mobility_items m ON l.mobility_item_id = m.id
           LEFT JOIN item_sets s ON l.set_id = s.id
           WHERE l.user_id = ?{since_sql} ORDER BY l.date DESC, l.id DESC"""
    conn = get_db()
    rows = conn.execute(q, (g.user_id, *since_params)).fetchall()
    return jsonify([list(r) for r in rows])


@logs_bp.route("/mobility", methods=["POST"])
@require_auth
def add_mobility_log():
    d = read_payload("date", "mob_name", "duration_mins")
    conn = get_db()
    v = checked_payload(conn, "mobility_logs", d, ("date", "duration_mins"))
    return _log_item_or_set(conn, sets.spec_for("mobility"), d["mob_name"],
                            {"date": v["date"]}, v["duration_mins"])
