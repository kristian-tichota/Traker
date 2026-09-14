import logging

from flask import Blueprint, g, jsonify

from server.auth import require_auth
from server.db_session import get_db
from server.payload import BadValue, read_payload
from server.validation import checked_columns, checked_payload

log = logging.getLogger(__name__)

plans_bp = Blueprint("plans", __name__)

LEDGER_SETS = 5

MOVEMENT_COLUMNS = ("position", "sets", "target_low", "target_high",
                    "weight_kg", "rpe", "tempo", "grouping", "notes")


def _owned_plan(conn, plan_id: int):
    """The member's plan by id, or the refusal that they have no such plan."""
    row = conn.execute(
        "SELECT id, name, start_date, weeks, notes FROM training_plans "
        "WHERE id = ? AND user_id = ?", (plan_id, g.user_id)).fetchone()
    if row is None:
        raise BadValue(f"No training plan {plan_id} for this member.")
    return row


def _exercise_id(conn, name):
    """The catalog id for a movement name, or a refusal naming it."""
    if not isinstance(name, str):
        raise BadValue(
            f"A movement name must be text, not a {type(name).__name__}.")
    row = conn.execute(
        "SELECT id FROM exercise_items WHERE name = ? COLLATE NOCASE",
        (name,)).fetchone()
    if row is None:
        raise BadValue(f"Exercise '{name}' is not in the catalog.")
    return row["id"]


def _checked_movements(conn, entries):
    """entries as (exercise_item_id, checked columns), or a refusal."""
    prepared = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise BadValue("Each movement must be an object.")
        name = entry.get("exercise")
        item_id = _exercise_id(conn, name)
        given = {column: entry[column] for column in MOVEMENT_COLUMNS
                 if entry.get(column) is not None}
        given.setdefault("position", position + 1)
        try:
            prepared.append((item_id, checked_columns(conn, "plan_movements", given)))
        except BadValue as bad:
            raise BadValue(f"{name}: {bad}") from None
    return prepared


def _insert_session(conn, plan_id: int, entry: dict):
    """Write one session and its movements."""
    if not isinstance(entry, dict):
        raise BadValue("Each session must be an object.")
    for field in ("date", "week", "name"):
        if entry.get(field) is None:
            raise BadValue(f"A session needs a {field}.")

    values = checked_payload(conn, "plan_sessions", entry,
                             ("date", "week", "name", "block", "notes"))
    movements = entry.get("movements") or []
    if not isinstance(movements, list):
        raise BadValue(f"'{entry['name']}' needs its movements as a list.")
    prepared = _checked_movements(conn, movements)

    columns = ["user_id", "plan_id", *values]
    cursor = conn.execute(
        f"INSERT INTO plan_sessions ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' * len(columns))})",
        (g.user_id, plan_id, *values.values()))
    session_id = cursor.lastrowid

    for item_id, checked in prepared:
        columns = ["user_id", "session_id", "exercise_item_id", *checked]
        conn.execute(
            f"INSERT INTO plan_movements ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            (g.user_id, session_id, item_id, *checked.values()))
    return len(prepared)


@plans_bp.route("", methods=["GET"])
@require_auth
def get_plans():
    """This member's cycles, newest start first."""
    conn = get_db()
    rows = conn.execute("""
        SELECT p.id, p.name, p.start_date, p.weeks, p.notes,
               (SELECT COUNT(*) FROM plan_sessions s WHERE s.plan_id = p.id)
        FROM training_plans p WHERE p.user_id = ?
        ORDER BY p.start_date DESC, p.id DESC
    """, (g.user_id,)).fetchall()
    return jsonify([list(r) for r in rows])


@plans_bp.route("/<int:plan_id>/sessions", methods=["GET"])
@require_auth
def get_plan_sessions(plan_id):
    """Every session of one cycle, in calendar order."""
    conn = get_db()
    _owned_plan(conn, plan_id)
    rows = conn.execute("""
        SELECT s.id, s.date, s.week, s.name, s.block, s.notes,
               (SELECT COUNT(*) FROM plan_movements m WHERE m.session_id = s.id)
        FROM plan_sessions s WHERE s.plan_id = ?
        ORDER BY s.date, s.id
    """, (plan_id,)).fetchall()
    return jsonify([list(r) for r in rows])


@plans_bp.route("/<int:plan_id>/movements", methods=["GET"])
@require_auth
def get_plan_movements(plan_id):
    """Every movement of one cycle, carrying the date of the session it is in."""
    conn = get_db()
    _owned_plan(conn, plan_id)
    rows = conn.execute("""
        SELECT m.id, s.date, s.name, m.position, e.name, m.sets,
               m.target_low, m.target_high, m.weight_kg, m.rpe,
               m.tempo, m.grouping, m.notes, e.metric_type
        FROM plan_movements m
        JOIN plan_sessions s ON m.session_id = s.id
        LEFT JOIN exercise_items e ON m.exercise_item_id = e.id
        WHERE s.plan_id = ?
        ORDER BY s.date, m.position, m.id
    """, (plan_id,)).fetchall()
    return jsonify([list(r) for r in rows])


@plans_bp.route("", methods=["POST"])
@require_auth
def add_plan():
    """Define a cycle, optionally with every session and movement in it."""
    d = read_payload("name", "start_date", "weeks")
    conn = get_db()
    values = checked_payload(conn, "training_plans", d,
                             ("name", "start_date", "weeks", "notes"))
    if not str(values["name"]).strip():
        raise BadValue("A training plan needs a name.")

    sessions = d.get("sessions") or []
    if not isinstance(sessions, list):
        raise BadValue("'sessions' must be a list.")

    columns = ["user_id", *values]
    with conn:
        cursor = conn.execute(
            f"INSERT INTO training_plans ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            (g.user_id, *values.values()))
        plan_id = cursor.lastrowid
        written = sum(_insert_session(conn, plan_id, entry) for entry in sessions)

    return jsonify({"status": "success", "plan_id": plan_id,
                    "sessions": len(sessions), "movements": written})


@plans_bp.route("/<int:plan_id>/sessions", methods=["POST"])
@require_auth
def add_plan_session(plan_id):
    """Add one session, with its movements, to an existing cycle."""
    d = read_payload("date", "week", "name")
    conn = get_db()
    _owned_plan(conn, plan_id)
    with conn:
        written = _insert_session(conn, plan_id, d)
    return jsonify({"status": "success", "movements": written})


@plans_bp.route("/<int:plan_id>/log", methods=["POST"])
@require_auth
def log_planned_session(plan_id):
    """Write the session prescribed for one date into the exercise ledger."""
    d = read_payload("date")
    conn = get_db()
    _owned_plan(conn, plan_id)
    date = checked_payload(conn, "plan_sessions", d, ("date",))["date"]

    session = conn.execute(
        "SELECT id, name FROM plan_sessions WHERE plan_id = ? AND date = ?",
        (plan_id, date)).fetchone()
    if session is None:
        raise BadValue(f"Nothing is planned for {date}.")

    movements = conn.execute("""
        SELECT m.exercise_item_id, e.name, m.sets, m.target_low, m.weight_kg, m.rpe
        FROM plan_movements m
        LEFT JOIN exercise_items e ON m.exercise_item_id = e.id
        WHERE m.session_id = ? ORDER BY m.position, m.id
    """, (session["id"],)).fetchall()
    if not movements:
        raise BadValue(f"'{session['name']}' has no movements to log.")

    orphaned = [row for row in movements if row["exercise_item_id"] is None]
    if orphaned:
        raise BadValue(
            f"'{session['name']}' has {len(orphaned)} movement(s) whose "
            f"exercise is no longer in the catalog. Repair the plan first.")

    prepared = []
    for row in movements:
        scheme = {f"set{n}": (row["target_low"] if n <= row["sets"] else 0)
                  for n in range(1, LEDGER_SETS + 1)}
        prepared.append((row["exercise_item_id"], checked_columns(
            conn, "exercise_logs",
            {"date": date, "weight_kg": row["weight_kg"], "rpe": row["rpe"],
             **scheme})))

    columns = ["user_id", "exercise_item_id", "date", "weight_kg", "rpe",
               *(f"set{n}" for n in range(1, LEDGER_SETS + 1))]
    with conn:
        conn.executemany(
            f"INSERT INTO exercise_logs ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            [(g.user_id, item_id, *(checked[column] for column in columns[2:]))
             for item_id, checked in prepared])

    return jsonify({"status": "success", "rows": len(prepared),
                    "session": session["name"]})
