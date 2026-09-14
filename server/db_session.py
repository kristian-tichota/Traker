import sqlite3

from flask import g

from server.database import db_service

_G_ATTR = "_db_conn"


def get_db() -> sqlite3.Connection:
    """The connection for this request, opened on first use."""
    conn = getattr(g, _G_ATTR, None)
    if conn is None:
        conn = db_service.get_connection()
        setattr(g, _G_ATTR, conn)
    return conn


def release_db(_exception=None) -> None:
    """Close the request's connection if one was opened."""
    conn = g.pop(_G_ATTR, None)
    if conn is not None:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(release_db)
