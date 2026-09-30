import json
import queue

from flask import Blueprint, Response, g, request, stream_with_context

from server.auth import require_auth
from server.db_session import get_db, release_db
from server.events import event_broadcaster
from server.payload import read_payload
from server.validation import checked_payload

system_bp = Blueprint("system", __name__)


@system_bp.route("/ping", methods=["GET"])
def ping():
    return {"status": "ok"}


@system_bp.route("/events", methods=["GET"])
@require_auth
def stream_events():
    release_db()

    client_queue = event_broadcaster.subscribe(g.user_id)

    def generate_event_stream():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    message = client_queue.get(timeout=15)
                    yield message
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            event_broadcaster.unsubscribe(client_queue)

    response = Response(
        stream_with_context(generate_event_stream()),
        mimetype="text/event-stream"
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@system_bp.route("/settings", methods=["GET"])
@require_auth
def get_settings():
    """Return several of this member's preferences in one round trip."""
    raw = request.args.get("keys", "")
    wanted = [key.strip() for key in raw.split(",") if key.strip()]
    return dict(get_db().execute(
        "SELECT key, value FROM user_settings WHERE user_id = ? "
        "AND key IN (SELECT value FROM json_each(?))", (g.user_id, json.dumps(wanted))).fetchall())


@system_bp.route("/settings/<key>", methods=["GET"])
@require_auth
def get_setting(key):
    row = get_db().execute("SELECT value FROM user_settings WHERE user_id = ? AND key = ?",
                           (g.user_id, key)).fetchone()
    return {"value": row["value"] if row else request.args.get("default", "")}


@system_bp.route("/settings/<key>", methods=["POST"])
@require_auth
def set_setting(key):
    """Store one of this member's view preferences."""
    data = read_payload("value")
    conn = get_db()
    v = checked_payload(conn, "user_settings",
                        {"key": key, "value": str(data["value"])},
                        ("key", "value"))
    with conn:
        conn.execute("""
            INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
        """, (g.user_id, v["key"], v["value"]))
    return {"status": "success"}
