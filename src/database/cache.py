import logging
import threading

log = logging.getLogger(__name__)


class LedgerCache:
    """Reads already answered, keyed by (domain, since)."""

    UNBOUNDED = None

    def __init__(self):
        self._entries = {}
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, domain, since=None):
        """Return rows for this read, or None where nothing here answers it."""
        with self._lock:
            exact = self._entries.get((domain, since))
            if exact is not None:
                self.hits += 1
                return list(exact)

            if since is not None:
                whole = self._entries.get((domain, self.UNBOUNDED))
                if whole is not None:
                    self.hits += 1
                    return [row for row in whole if _within(row, since)]

            self.misses += 1
            return None

    def put(self, domain, since, rows):
        with self._lock:
            self._entries[(domain, since)] = list(rows)
        return rows

    def drop(self, domains):
        """Forget every entry for these domains, bounded and unbounded alike."""
        wanted = {domains} if isinstance(domains, str) else set(domains)
        if not wanted:
            return 0
        with self._lock:
            doomed = [key for key in self._entries if key[0] in wanted]
            for key in doomed:
                del self._entries[key]
        if doomed:
            log.debug("Dropped %d cached read(s) for %s", len(doomed), sorted(wanted))
        return len(doomed)

    def clear(self):
        """Forget every cached read."""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
        return count

    def cached_domains(self):
        with self._lock:
            return {key[0] for key in self._entries}

    def __len__(self):
        with self._lock:
            return len(self._entries)


def _row_date(row):
    """Return the date a log row carries, as the API stores it, or None."""
    value = getattr(row, "date", None)
    if value is None:
        try:
            value = row[1]
        except (IndexError, TypeError, KeyError):
            return None
    return None if value is None else str(value)


def _within(row, since):
    """Report whether a row belongs in a read bounded at since."""
    date = _row_date(row)
    return True if date is None else date >= since

_PATH_DOMAINS = ("food", "beverage", "exercise", "supplement", "mobility")


def domain_for_path(path: str):
    """Return the domains a write to path changes, or None where unknown."""
    path = (path or "").split("?", 1)[0].strip("/")
    parts = path.split("/")
    if len(parts) < 2 or parts[0] != "api":
        return None
    section = parts[1]

    if section == "settings":
        return NOTHING_CHANGED
    if section == "pomodoro":
        return "pomodoro"
    if section == "chores":
        return "chore"
    if section == "plans":
        return ("plan", "exercise") if parts[-1] == "log" else "plan"
    if section in ("logs", "catalog") and len(parts) >= 3:
        third = parts[2]
        if third in _PATH_DOMAINS:
            return third
        if third == "sets" and len(parts) >= 4 and parts[3] in _PATH_DOMAINS:
            return parts[3]
        from src.gui.domains import domain_of_table

        return domain_of_table(third)
    return None


class _NothingChanged:
    """Sentinel: this write touched no household data, so drop nothing."""

    def __repr__(self):
        return "NOTHING_CHANGED"

    def __bool__(self):
        return False

NOTHING_CHANGED = _NothingChanged()
