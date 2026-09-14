import logging

from flask import Blueprint, g, jsonify, request

from server.auth import require_auth
from server.db_session import get_db
from server.events import event_broadcaster
from server.payload import BadValue, read_payload
from server.validation import checked_payload, validate_column_value

log = logging.getLogger(__name__)

chores_bp = Blueprint("chores", __name__)

CHORE_COLUMNS = ("name", "period_days", "anchor", "grace_days", "notes", "active")

_BOARD_SQL = """
    SELECT c.id, c.name, c.period_days, c.anchor, c.grace_days, c.notes,
           c.active,
           (SELECT MAX(date) FROM chore_completions WHERE chore_id = c.id)
               AS last_done,
           (SELECT COUNT(*) FROM chore_completions WHERE chore_id = c.id)
               AS done_count
    FROM chores c
    ORDER BY c.name COLLATE NOCASE
"""


def _chore_by_name(conn, name):
    """Return the chore a member typed, or a refusal naming it."""
    if not isinstance(name, str) or not name.strip():
        raise BadValue("Name a chore to mark done.")
    row = conn.execute(
        "SELECT id, name FROM chores WHERE name = ? COLLATE NOCASE",
        (name.strip(),)).fetchone()
    if row is None:
        raise BadValue(f"There is no chore called '{name}'.")
    return row


@chores_bp.route("", methods=["GET"])
@require_auth
def get_chores():
    """Return every chore with its last completion."""
    conn = get_db()
    return jsonify([dict(row) for row in conn.execute(_BOARD_SQL)])


@chores_bp.route("", methods=["POST"])
@require_auth
def add_chore():
    """Define a recurring chore."""
    payload = read_payload("name", "period_days", "anchor")
    conn = get_db()
    values = checked_payload(conn, "chores", payload, CHORE_COLUMNS)

    name = str(values.get("name", "")).strip()
    if not name:
        raise BadValue("A chore needs a name.")
    values["name"] = name

    columns = sorted(values)
    conn.execute(
        f"INSERT INTO chores ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})",
        [values[column] for column in columns])
    conn.commit()

    event_broadcaster.broadcast("catalog_updated", {"action": "chore", "name": name})
    return jsonify({"status": "success", "name": name}), 201


@chores_bp.route("/done", methods=["POST"])
@require_auth
def complete_chore():
    """Record one chore as done on one day."""
    payload = read_payload("name", "date")
    conn = get_db()
    chore = _chore_by_name(conn, payload["name"])
    values = checked_payload(conn, "chore_completions", payload, ("date",))

    already = conn.execute(
        "SELECT id FROM chore_completions WHERE chore_id = ? AND date = ?",
        (chore["id"], values["date"])).fetchone()
    if already is None:
        conn.execute(
            "INSERT INTO chore_completions (chore_id, date, done_by) "
            "VALUES (?, ?, ?)", (chore["id"], values["date"], g.username))
        conn.commit()

    event_broadcaster.broadcast(
        "catalog_updated", {"action": "chore_done", "name": chore["name"]})
    return jsonify({"status": "success", "name": chore["name"],
                    "date": values["date"], "repeated": already is not None})


@chores_bp.route("/completions", methods=["GET"])
@require_auth
def get_completions():
    """Return the shared history, most recent first, optionally bounded."""
    since = request.args.get("since")
    clause, params = "", ()
    if since:
        validate_column_value("date", since)
        clause, params = " WHERE d.date >= ?", (since,)

    conn = get_db()
    rows = conn.execute(
        "SELECT d.id, d.date, c.name, d.done_by "
        "FROM chore_completions d JOIN chores c ON c.id = d.chore_id"
        f"{clause} ORDER BY d.date DESC, d.id DESC", params)
    return jsonify([list(row) for row in rows])
