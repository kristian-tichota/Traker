from flask import Blueprint, g

from server.auth import require_auth
from server.db_session import get_db, insert, named, rows
from server.events import catalog_updated
from server.payload import BadValue, read_payload
from server.validation import checked_payload, since_date

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


def _chore_by_name(name):
    """Return the chore a member typed, or a refusal naming it."""
    if not isinstance(name, str) or not name.strip():
        raise BadValue("Name a chore to mark done.")
    row = named("chores", name.strip(), "id, name")
    if row is None:
        raise BadValue(f"There is no chore called '{name}'.")
    return row


@chores_bp.route("", methods=["GET"])
@require_auth
def get_chores():
    """Return every chore with its last completion."""
    return [dict(row) for row in get_db().execute(_BOARD_SQL)]


@chores_bp.route("", methods=["POST"])
@require_auth
def add_chore():
    """Define a recurring chore."""
    payload = read_payload("name", "period_days", "anchor")
    conn = get_db()
    values = checked_payload(conn, "chores", payload, CHORE_COLUMNS)

    name = values["name"] = values["name"].strip()

    with conn:
        insert("chores", [values])

    catalog_updated(table="chores", action="chore", name=name)
    return {"status": "success", "name": name}, 201


@chores_bp.route("/done", methods=["POST"])
@require_auth
def complete_chore():
    """Record one chore as done on one day."""
    payload = read_payload("name", "date")
    conn = get_db()
    chore = _chore_by_name(payload["name"])
    values = checked_payload(conn, "chore_completions", payload, ("date",))

    with conn:
        repeated = not conn.execute(
            "INSERT INTO chore_completions (chore_id, date, done_by) "
            "SELECT :chore, :date, :by WHERE NOT EXISTS (SELECT 1 FROM chore_completions "
            "WHERE chore_id = :chore AND date = :date)",
            {"chore": chore["id"], "date": values["date"], "by": g.username}).rowcount

    if not repeated:
        catalog_updated(table="chore_completions", action="chore_done", name=chore["name"])
    return {"status": "success", "name": chore["name"], "date": values["date"],
            "repeated": repeated}


@chores_bp.route("/completions", methods=["GET"])
@require_auth
def get_completions():
    """Return the shared history, most recent first, optionally bounded."""
    return rows("SELECT d.id, d.date, c.name, d.done_by "
                "FROM chore_completions d JOIN chores c ON c.id = d.chore_id "
                "WHERE d.date >= ? ORDER BY d.date DESC, d.id DESC", (since_date(),))
