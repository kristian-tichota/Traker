import datetime

from src.domain.clock import ISO_DATE

DONE = "done"
TODAY = "today"
AHEAD = "ahead"
MISSED = "missed"

STATUSES = (DONE, TODAY, AHEAD, MISSED)


def today_iso() -> str:
    return datetime.date.today().strftime(ISO_DATE)


def parse_iso(value):
    """value as a date, or None if it is not an ISO one."""
    try:
        return datetime.datetime.strptime(str(value), ISO_DATE).date()
    except (TypeError, ValueError):
        return None


def current_plan(catalogue, today: str = None):
    """The cycle to show and to log from: the one today falls in, else newest."""
    if not catalogue:
        return None
    today = today or today_iso()
    started = [plan for plan in catalogue if plan.start_date <= today]
    return started[0] if started else catalogue[0]


def status(session_date: str, logged_dates, today: str = None) -> str:
    """Whether the session on session_date happened, is due, or was missed."""
    today = today or today_iso()
    if session_date in logged_dates:
        return DONE
    if session_date == today:
        return TODAY
    return AHEAD if session_date > today else MISSED


def adherence(session_dates, logged_dates, today: str = None) -> tuple:
    """(done, due) over every session up to and including today."""
    today = today or today_iso()
    due = [date for date in session_dates if date <= today]
    return sum(1 for date in due if date in logged_dates), len(due)


def week_streak(session_dates, logged_dates, today: str = None) -> int:
    """How many sessions in a row were logged, counting back from the last due."""
    today = today or today_iso()
    due = sorted(date for date in session_dates if date <= today)
    streak = 0
    for date in reversed(due):
        if date not in logged_dates:
            if date == today and streak == 0:
                continue
            break
        streak += 1
    return streak


def session_on(sessions, date_iso: str):
    """The session planned for date_iso, or None."""
    for session in sessions:
        if session.date == date_iso:
            return session
    return None


def movements_on(movements, date_iso: str) -> list:
    """The movements prescribed for date_iso, in the order given."""
    return [movement for movement in movements if movement.date == date_iso]


def prescribed_day(sessions, movements, date_iso: str) -> tuple:
    """(session, movements) for one day, or (None, [])."""
    session = session_on(sessions, date_iso)
    if session is None:
        return None, []
    return session, movements_on(movements, date_iso)


def movement_text(movement) -> str:
    """One movement as a single line: Overhead Press · 3x8-12 · 16.5 kg."""
    scheme = scheme_text(movement.sets, movement.target_low,
                         movement.target_high, movement.metric_type)
    load = float(movement.weight_kg or 0)
    said = [movement.name or "—", scheme]
    if load:
        said.append(f"{_number(load)} kg")
    return " · ".join(part for part in said if part)


def target_text(low, high, metric: str = None) -> str:
    """A movement's rep or second range as the member reads it: 8-12."""
    unit = " s" if (metric or "").lower().startswith("second") else ""
    bottom, top = _quantity(low), _quantity(high)
    if not bottom and not top:
        return ""
    if not top or top == bottom:
        return f"{_number(bottom or top)}{unit}"
    return f"{_number(bottom)}-{_number(top)}{unit}"


def scheme_text(sets, low, high, metric: str = None) -> str:
    """The whole prescription for one movement: 3x8-12."""
    target = target_text(low, high, metric)
    count = int(sets or 0)
    if not count:
        return target
    return f"{count}x{target}" if target else f"{count} sets"


def logged_sets(log_row) -> list:
    """The non-zero sets of one exercise log row, in order."""
    values = [getattr(log_row, f"set{n}", 0) or 0 for n in range(1, 6)]
    while values and not values[-1]:
        values.pop()
    return values


def logged_text(log_row) -> str:
    """What was actually done, as 10/10/9 @ 22.5, or a blank."""
    if log_row is None:
        return ""
    done = "/".join(_number(value) for value in logged_sets(log_row))
    weight = float(getattr(log_row, "weight_kg", 0) or 0)
    return f"{done} @ {_number(weight)}" if weight else done


def verdict(movement, log_row) -> str:
    """Whether the logged sets met the prescription: hit, under, or ""."""
    if log_row is None:
        return ""
    done = logged_sets(log_row)
    if not done:
        return ""
    low = float(movement.target_low or 0)
    wanted_sets = int(movement.sets or 0)
    heavy_enough = float(getattr(log_row, "weight_kg", 0) or 0) >= float(
        movement.weight_kg or 0)
    complete = len(done) >= wanted_sets and all(float(value) >= low for value in done)
    return "hit" if (complete and heavy_enough) else "under"


def logs_by_exercise(log_rows) -> dict:
    """One day's exercise logs, keyed by the movement's folded name."""
    found = {}
    for row in log_rows:
        key = (getattr(row, "name", None) or "").strip().lower()
        if key and key not in found:
            found[key] = row
    return found


def _quantity(value) -> float:
    """value as a number, or 0.0 where it is not one."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _number(value) -> str:
    """A quantity without a trailing .0 it never had."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"
