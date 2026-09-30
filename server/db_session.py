import sqlite3

from flask import g

from server.database import db_service

_G_ATTR = "_db_conn"


def get_db() -> sqlite3.Connection:
    """Return the connection for this request, opened on first use."""
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


def rows(sql: str, params=()) -> list:
    """Return every row sql answers, each as a list."""
    return [list(row) for row in get_db().execute(sql, params)]


def named(table: str, name: str, columns: str = "id"):
    """Return the row of table called name, however it is capitalised, or None."""
    return get_db().execute(
        f"SELECT {columns} FROM {table} WHERE name = ? COLLATE NOCASE", (name,)).fetchone()


def insert(table: str, values: list) -> int:
    """Write one row per dict of values, all sharing keys; return the last id."""
    columns = list(values[0])
    sql = (f"INSERT INTO {table} ({', '.join(columns)}) "
           f"VALUES ({', '.join('?' * len(columns))})")
    cursor = get_db().cursor()
    for row in values:
        cursor.execute(sql, tuple(row.values()))
    return cursor.lastrowid
