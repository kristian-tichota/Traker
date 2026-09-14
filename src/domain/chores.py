import datetime

from src.domain.clock import ISO_DATE

GRACE_CAP_DAYS = 7

GRACE_DIVISOR = 3

OVERDUE, DUE, EARLY, LATER = "overdue", "due", "early", "later"
STANDINGS = (OVERDUE, DUE, EARLY, LATER)

DAYS_IN_WEEK = 7

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

DRIFTS = "drifts"

WORTH_SHOWING = (OVERDUE, DUE, EARLY)


def today_iso() -> str:
    """Today as the store spells it."""
    return datetime.date.today().isoformat()


def as_date(value):
    """An ISO date as a date, or None if it will not read as one."""
    try:
        return datetime.datetime.strptime(str(value).strip(), ISO_DATE).date()
    except (AttributeError, TypeError, ValueError):
        return None


def default_grace(period_days) -> int:
    """How far ahead of its day a chore of this cadence may be done."""
    period = whole(period_days, 1)
    return max(0, min(period // GRACE_DIVISOR, GRACE_CAP_DAYS))


def whole(value, fallback: int) -> int:
    """value as a whole number, or fallback."""
    if isinstance(value, bool) or value is None:
        return fallback
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def grace_of(chore) -> int:
    """A chore's own grace, or the default for its cadence."""
    declared = getattr(chore, "grace_days", None)
    if declared is None:
        return default_grace(getattr(chore, "period_days", 1))
    return max(0, whole(declared, default_grace(getattr(chore, "period_days", 1))))


def lands_on(anchor, period_days) -> str:
    """The weekday this chore always falls on, or DRIFTS."""
    start = as_date(anchor)
    period = max(1, whole(period_days, 1))
    if start is None or period % DAYS_IN_WEEK:
        return DRIFTS
    return WEEKDAYS[start.weekday()]


def next_due(anchor, period_days, grace_days, last_done):
    """The date this chore is next wanted, as a date, or None."""
    start = as_date(anchor)
    if start is None:
        return None

    period = max(1, whole(period_days, 1))
    grace = max(0, whole(grace_days, 0))
    done = as_date(last_done)
    if done is None:
        return start

    cleared = ((done - start).days + grace) // period
    if cleared < 0:
        return start
    return start + datetime.timedelta(days=(cleared + 1) * period)


def standing(due, grace_days, today) -> str:
    """Where a chore due on due stands on today."""
    if due is None:
        return LATER
    ahead = (due - today).days
    if ahead < 0:
        return OVERDUE
    if ahead == 0:
        return DUE
    return EARLY if ahead <= max(0, whole(grace_days, 0)) else LATER


class Standing:
    """One chore, where it stands today, and the words for it."""

    def __init__(self, chore, today):
        self.chore = chore
        self.id = getattr(chore, "id", None)
        self.name = getattr(chore, "name", "") or ""
        self.period_days = max(1, whole(getattr(chore, "period_days", 1), 1))
        self.grace_days = grace_of(chore)
        self.anchor = getattr(chore, "anchor", None)
        self.lands_on = lands_on(self.anchor, self.period_days)
        self.due = next_due(self.anchor, self.period_days,
                            self.grace_days, getattr(chore, "last_done", None))
        self.today = today
        self.standing = standing(self.due, self.grace_days, today)

    @property
    def days_over(self) -> int:
        """Days past due, or 0 for a chore that is not late."""
        if self.due is None or self.due >= self.today:
            return 0
        return (self.today - self.due).days

    @property
    def days_ahead(self) -> int:
        """Days until due, or 0 for one that is due or late."""
        if self.due is None or self.due <= self.today:
            return 0
        return (self.due - self.today).days

    @property
    def due_iso(self):
        return None if self.due is None else self.due.isoformat()

    def said(self) -> str:
        """How late or early this is, in the fewest words that are true."""
        if self.due is None:
            return "no start date"
        if self.standing == OVERDUE:
            days = self.days_over
            return "1 day over" if days == 1 else f"{days} days over"
        if self.standing == DUE:
            return "due today"
        days = self.days_ahead
        return "ok today" if self.standing == EARLY else (
            "in 1 day" if days == 1 else f"in {days} days")

    def __repr__(self):
        return f"<Standing {self.name!r} {self.standing} due={self.due_iso}>"


def board(chores, today=None) -> list:
    """Every chore as a Standing, worst first."""
    day = as_date(today) or datetime.date.today()
    standings = [Standing(chore, day) for chore in chores
                 if _is_active(chore)]
    return sorted(standings, key=_worst_first)


def due_now(chores, today=None) -> list:
    """The chores a break surface offers: overdue, due, or doable early."""
    return [entry for entry in board(chores, today)
            if entry.standing in WORTH_SHOWING]


def _is_active(chore) -> bool:
    """Whether a chore is being kept."""
    value = getattr(chore, "active", 1)
    return True if value is None else bool(value)


def _worst_first(entry):
    """Sort key: standing, then how long it has waited, then the name."""
    return (STANDINGS.index(entry.standing), -entry.days_over,
            entry.days_ahead, entry.name.lower())
