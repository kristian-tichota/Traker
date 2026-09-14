from functools import wraps
from flask import request, jsonify, g
from server.db_session import get_db


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if auth_header[:7].lower() == "bearer ":
            auth_header = auth_header[7:]
        token = auth_header.strip() or request.headers.get("X-API-Key", "").strip()

        if not token:
            return jsonify({"error": "Missing authentication token"}), 401

        user = get_db().execute(
            "SELECT id, username FROM users WHERE api_token = ?", (token,)
        ).fetchone()

        if not user:
            return jsonify({"error": "Invalid API token"}), 403

        g.user_id = user["id"]
        g.username = user["username"]
        return f(*args, **kwargs)
    return decorated
