import datetime

from flask import request

from server.payload import BadValue
from server.tables import coerce_value, mutable_columns, non_negative_columns


def _iso_date(value):
    return datetime.datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def _clock_time(value):
    return datetime.datetime.strptime(value, "%H:%M").strftime("%H:%M")


def _iso_moment(value):
    """Match an ISO-8601 moment, as datetime.isoformat() writes one."""
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.time() == datetime.time.min and len(value.strip()) <= 10:
        raise ValueError("a date alone carries no moment")
    return value


def _named(value):
    if not value.strip():
        raise ValueError("a name cannot be blank")
    return value


_CHECKS = {
    "name": (_named, "a name"),
    "date": (_iso_date, "a date as YYYY-MM-DD"),
    "anchor": (_iso_date, "a date as YYYY-MM-DD"),
    "time": (_clock_time, "a time as HH:MM"),
    "timestamp": (_iso_moment, "an ISO-8601 moment such as 2026-09-05T14:30:00"),
}


def canonical_value(column: str, value):
    """Return value in the spelling column stores, or raise BadValue."""
    if column not in _CHECKS or value is None:
        return value
    check, expected = _CHECKS[column]
    try:
        return check(str(value))
    except ValueError:
        raise BadValue(
            f"'{value}' is not {expected}, which is what {column} stores"
        ) from None


def since_date() -> str:
    """Return the ?since= date bound, or the empty string that bounds nothing."""
    since = request.args.get("since")
    return canonical_value("date", since) if since else ""


def validate_column_bound(table_name: str, column: str, value) -> None:
    """Raise BadValue if value is a negative quantity."""
    if value is None or column not in non_negative_columns(table_name):
        return
    if isinstance(value, (int, float)) and value < 0:
        raise BadValue(f"{column} is a quantity and cannot be negative, got {value}")


def checked_columns(conn, table_name: str, values: dict) -> dict:
    """Return values coerced to the declared types of table_name, then checked."""
    checked = {}
    for column, value in values.items():
        coerced = canonical_value(column, coerce_value(conn, table_name, column, value))
        validate_column_bound(table_name, column, coerced)
        checked[column] = coerced
    return checked


def checked_payload(conn, table_name: str, payload: dict, columns, defaults=None) -> dict:
    """Return the named columns of payload, coerced and checked for table_name."""
    values = dict(defaults or {})
    values.update({column: payload[column] for column in columns if column in payload})
    return checked_columns(conn, table_name, values)


def require_known_columns(table_name: str, values: dict) -> None:
    """Raise BadValue naming any column that is not writable on this table."""
    offending = sorted(set(values) - mutable_columns(table_name))
    if offending:
        raise BadValue(
            "Not writable on %s: %s" % (table_name, ", ".join(offending))
        )
