from flask import Blueprint, jsonify, g

from server.auth import require_auth
from server.db_session import get_db
from server.payload import read_payload
from server.validation import checked_payload, validate_column_value

pomodoro_bp = Blueprint("pomodoro", __name__)


@pomodoro_bp.route("/daily-summary", methods=["GET"])
@require_auth
def get_pomodoro_daily_summary():
    q = """SELECT date,
                  SUM(CASE WHEN state = 'focus' THEN 1 ELSE 0 END) as focus_mins,
                  SUM(CASE WHEN state = 'rest' THEN 1 ELSE 0 END) as rest_mins,
                  SUM(CASE WHEN state = 'focus_overtime' THEN 1 ELSE 0 END) as focus_ot,
                  SUM(CASE WHEN state = 'rest_overtime' THEN 1 ELSE 0 END) as rest_ot
           FROM pomodoro_heartbeats
           -- 'localtime': the client writes its dates in local time, and a
           -- bare date('now') is SQLite's UTC. Comparing the two dropped or
           -- kept a day's summary depending on the hour the tab was opened.
           WHERE user_id = ? AND date >= date('now', 'localtime', '-30 days')
           GROUP BY date ORDER BY date ASC"""
    conn = get_db()
    rows = conn.execute(q, (g.user_id,)).fetchall()
    return jsonify([list(r) for r in rows])


@pomodoro_bp.route("/heartbeats/<date_str>", methods=["GET"])
@require_auth
def get_pomodoro_heartbeats(date_str):
    validate_column_value("date", date_str)
    q = "SELECT minute_of_day, second, state, mode FROM pomodoro_heartbeats WHERE user_id = ? AND date = ?"
    conn = get_db()
    rows = conn.execute(q, (g.user_id, date_str)).fetchall()
    return jsonify([list(r) for r in rows])


@pomodoro_bp.route("/heartbeat", methods=["POST"])
@require_auth
def log_pomodoro_heartbeat():
    d = read_payload("date", "minute_of_day", "state")
    conn = get_db()
    v = checked_payload(conn, "pomodoro_heartbeats", d,
                        ("date", "minute_of_day", "second", "state", "mode"),
                        defaults={"second": 0, "mode": "Default"})
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO pomodoro_heartbeats (user_id, date, minute_of_day, second, state, mode)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (g.user_id, v["date"], v["minute_of_day"], v["second"], v["state"], v["mode"]))
    return jsonify({"status": "success"})


@pomodoro_bp.route("/events/<date_str>", methods=["GET"])
@require_auth
def get_pomodoro_events(date_str):
    validate_column_value("date", date_str)
    q = "SELECT timestamp, event_type, amount_ms FROM pomodoro_events WHERE user_id = ? AND date(timestamp) = ? ORDER BY timestamp ASC"
    conn = get_db()
    rows = conn.execute(q, (g.user_id, date_str)).fetchall()
    return jsonify([list(r) for r in rows])


@pomodoro_bp.route("/event", methods=["POST"])
@require_auth
def log_pomodoro_event():
    d = read_payload("timestamp", "event_type")
    conn = get_db()
    v = checked_payload(conn, "pomodoro_events", d,
                        ("timestamp", "event_type", "amount_ms"),
                        defaults={"amount_ms": 0})
    with conn:
        conn.execute("""
            INSERT INTO pomodoro_events (user_id, timestamp, event_type, amount_ms)
            VALUES (?, ?, ?, ?)
        """, (g.user_id, v["timestamp"], v["event_type"], v["amount_ms"]))
    return jsonify({"status": "success"})


@pomodoro_bp.route("/dsi-overrides", methods=["GET"])
@require_auth
def get_pomodoro_dsi_overrides():
    conn = get_db()
    rows = conn.execute("SELECT date, override_dsi FROM pomodoro_dsi_overrides WHERE user_id = ?", (g.user_id,)).fetchall()
    return jsonify({r["date"]: r["override_dsi"] for r in rows})


@pomodoro_bp.route("/dsi-override", methods=["POST"])
@require_auth
def set_pomodoro_dsi_override():
    d = read_payload("date", "override_dsi")
    conn = get_db()
    v = checked_payload(conn, "pomodoro_dsi_overrides", d, ("date", "override_dsi"))
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO pomodoro_dsi_overrides (user_id, date, override_dsi)
            VALUES (?, ?, ?)
        """, (g.user_id, v["date"], v["override_dsi"]))
    return jsonify({"status": "success"})


@pomodoro_bp.route("/dsi-override/<date_str>", methods=["DELETE"])
@require_auth
def clear_pomodoro_dsi_override(date_str):
    validate_column_value("date", date_str)

    conn = get_db()
    with conn:
        removed = conn.execute(
            "DELETE FROM pomodoro_dsi_overrides WHERE user_id = ? AND date = ?",
            (g.user_id, date_str),
        ).rowcount

    if not removed:
        return jsonify({"error": f"No stress override on {date_str} to clear."}), 404
    return jsonify({"status": "success"})
