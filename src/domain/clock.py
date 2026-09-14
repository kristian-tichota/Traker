import datetime
from functools import lru_cache

ISO_DATE = "%Y-%m-%d"

DISPLAY_DATE = "%d.%m.%Y"


@lru_cache(maxsize=4096)
def as_displayed_date(value, default=None):
    """Render "2026-09-05" as "05.09.2026"."""
    try:
        parsed = datetime.datetime.strptime(str(value), ISO_DATE)
    except (TypeError, ValueError):
        return str(value) if default is None else default
    return parsed.strftime(DISPLAY_DATE)


@lru_cache(maxsize=4096)
def as_stored_date(value, default=None):
    """Render "05.09.2026" as "2026-09-05"."""
    try:
        parsed = datetime.datetime.strptime(str(value).strip(), DISPLAY_DATE)
    except (TypeError, ValueError):
        return str(value) if default is None else default
    return parsed.strftime(ISO_DATE)


def within_window(at, start, end) -> bool:
    """Report whether at falls in start-end, all of them minutes of a day."""
    if start == end:
        return False
    if start < end:
        return start <= at < end
    return at >= start or at < end


def minutes_of_day(text, default=None):
    """Return minutes since midnight for "HH:MM", or default."""
    try:
        hours, minutes = (int(part) for part in str(text).strip().split(":"))
    except (AttributeError, TypeError, ValueError):
        return default
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        return default
    return hours * 60 + minutes


def minutes_covered(began, ended) -> list:
    """Return each stored minute a span covers, as (date, minute of day)."""
    edge = began.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    covered = []
    while edge <= ended:
        covered.append((edge.date().isoformat(), edge.hour * 60 + edge.minute))
        edge += datetime.timedelta(minutes=1)
    return covered
