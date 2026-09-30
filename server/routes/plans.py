from flask import Blueprint, g

from server.auth import require_auth
from server.db_session import get_db, insert, named, rows
from server.payload import BadValue, read_payload
from server.validation import checked_columns, checked_payload

plans_bp = Blueprint("plans", __name__)

LEDGER_SETS = 5

MOVEMENT_COLUMNS = ("position", "sets", "target_low", "target_high",
                    "weight_kg", "rpe", "tempo", "grouping", "notes")


def _require_owned_plan(plan_id: int):
    """Refuse a plan id this member does not hold."""
    if get_db().execute("SELECT 1 FROM training_plans WHERE id = ? AND user_id = ?",
                        (plan_id, g.user_id)).fetchone() is None:
        raise BadValue(f"No training plan {plan_id} for this member.")


def _exercise_id(name):
    """Return the catalog id for a movement name, or a refusal naming it."""
    if not isinstance(name, str):
        raise BadValue(
            f"A movement name must be text, not a {type(name).__name__}.")
    row = named("exercise_items", name)
    if row is None:
        raise BadValue(f"Exercise '{name}' is not in the catalog.")
    return row["id"]


def _checked_movements(conn, entries):
    """Return entries as (exercise_item_id, checked columns), or a refusal."""
    prepared = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise BadValue("Each movement must be an object.")
        name = entry.get("exercise")
        item_id = _exercise_id(name)
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

    session_id = insert("plan_sessions", [{"user_id": g.user_id, "plan_id": plan_id, **values}])
    for item_id, checked in prepared:
        insert("plan_movements", [{"user_id": g.user_id, "session_id": session_id,
                                   "exercise_item_id": item_id, **checked}])
    return len(prepared)


@plans_bp.route("", methods=["GET"])
@require_auth
def get_plans():
    """Return this member's cycles, newest start first."""
    return rows("SELECT id, name, start_date, weeks, notes FROM training_plans "
                "WHERE user_id = ? ORDER BY start_date DESC, id DESC", (g.user_id,))


@plans_bp.route("/<int:plan_id>/sessions", methods=["GET"])
@require_auth
def get_plan_sessions(plan_id):
    """Return every session of one cycle, in calendar order."""
    _require_owned_plan(plan_id)
    return rows("SELECT id, date, week, name, block, notes FROM plan_sessions "
                "WHERE plan_id = ? ORDER BY date, id", (plan_id,))


@plans_bp.route("/<int:plan_id>/movements", methods=["GET"])
@require_auth
def get_plan_movements(plan_id):
    """Return every movement of one cycle, each carrying its session date."""
    _require_owned_plan(plan_id)
    return rows("""
        SELECT m.id, s.date, s.name, m.position, e.name, m.sets,
               m.target_low, m.target_high, m.weight_kg, m.rpe,
               m.tempo, m.grouping, m.notes, e.metric_type
        FROM plan_movements m
        JOIN plan_sessions s ON m.session_id = s.id
        LEFT JOIN exercise_items e ON m.exercise_item_id = e.id
        WHERE s.plan_id = ?
        ORDER BY s.date, m.position, m.id
    """, (plan_id,))


@plans_bp.route("", methods=["POST"])
@require_auth
def add_plan():
    """Define a cycle, optionally with every session and movement in it."""
    d = read_payload("name", "start_date", "weeks")
    conn = get_db()
    values = checked_payload(conn, "training_plans", d,
                             ("name", "start_date", "weeks", "notes"))

    sessions = d.get("sessions") or []
    if not isinstance(sessions, list):
        raise BadValue("'sessions' must be a list.")

    with conn:
        plan_id = insert("training_plans", [{"user_id": g.user_id, **values}])
        written = sum(_insert_session(conn, plan_id, entry) for entry in sessions)

    return {"status": "success", "plan_id": plan_id,
            "sessions": len(sessions), "movements": written}


@plans_bp.route("/<int:plan_id>/log", methods=["POST"])
@require_auth
def log_planned_session(plan_id):
    """Write the session prescribed for one date into the exercise ledger."""
    d = read_payload("date")
    _require_owned_plan(plan_id)
    conn = get_db()
    date = checked_payload(conn, "plan_sessions", d, ("date",))["date"]

    session = conn.execute(
        "SELECT id, name FROM plan_sessions WHERE plan_id = ? AND date = ?",
        (plan_id, date)).fetchone()
    if session is None:
        raise BadValue(f"Nothing is planned for {date}.")

    movements = conn.execute(
        "SELECT exercise_item_id, sets, target_low, weight_kg, rpe FROM plan_movements "
        "WHERE session_id = ? ORDER BY position, id", (session["id"],)).fetchall()
    if not movements:
        raise BadValue(f"'{session['name']}' has no movements to log.")

    orphaned = [row for row in movements if row["exercise_item_id"] is None]
    if orphaned:
        raise BadValue(
            f"'{session['name']}' has {len(orphaned)} movement(s) whose "
            f"exercise is no longer in the catalog. Repair the plan first.")

    prepared = [
        {"user_id": g.user_id, "exercise_item_id": row["exercise_item_id"],
         **checked_columns(conn, "exercise_logs", {
             "date": date, "weight_kg": row["weight_kg"], "rpe": row["rpe"],
             **{f"set{n}": (row["target_low"] if n <= row["sets"] else 0)
                for n in range(1, LEDGER_SETS + 1)}})}
        for row in movements]
    with conn:
        insert("exercise_logs", prepared)

    return {"status": "success", "rows": len(prepared), "session": session["name"]}
