import logging
import threading

log = logging.getLogger(__name__)


class LedgerCache:
    """Reads already answered, keyed by (domain, since)."""

    def __init__(self):
        self._entries = {}
        self._drops = {}
        self._clears = 0
        self._lock = threading.RLock()
        self.hits = 0

    def get(self, domain, since=None):
        """Return rows for this read, or None where nothing here answers it."""
        with self._lock:
            exact = self._entries.get((domain, since))
            if exact is not None:
                self.hits += 1
                return list(exact)
            whole = None if since is None else self._entries.get((domain, None))
            if whole is None:
                return None
            self.hits += 1
            return [row for row in whole
                    if getattr(row, "date", None) is None or row.date >= since]

    def generation(self, domain):
        """Return a token that changes whenever domain is dropped or the cache cleared."""
        with self._lock:
            return self._clears + self._drops.get(domain, 0)

    def put(self, domain, since, rows, generation=None):
        """Remember rows, unless domain was dropped after generation was taken."""
        with self._lock:
            if generation is None or generation == self.generation(domain):
                self._entries[(domain, since)] = list(rows)

    def drop(self, domains):
        """Forget every entry for these domains, bounded and unbounded alike."""
        wanted = {domains} if isinstance(domains, str) else set(domains)
        with self._lock:
            for domain in wanted:
                self._drops[domain] = self._drops.get(domain, 0) + 1
            doomed = [key for key in self._entries if key[0] in wanted]
            for key in doomed:
                del self._entries[key]
        if doomed:
            log.debug("Dropped %d cached read(s) for %s", len(doomed), sorted(wanted))

    def clear(self):
        """Forget every cached read."""
        with self._lock:
            self._clears += 1
            self._entries.clear()

    def cached_domains(self):
        with self._lock:
            return {key[0] for key in self._entries}

    def __len__(self):
        with self._lock:
            return len(self._entries)


_PATH_DOMAINS = ("food", "beverage", "exercise", "supplement", "mobility")

_SECTION_DOMAINS = {"settings": (), "pomodoro": "pomodoro", "chores": "chore",
                    "plans": "plan"}


def domain_for_path(path: str):
    """Return the domains a write to path changes, or None where unknown."""
    parts = (path or "").split("?", 1)[0].strip("/").split("/")
    if len(parts) < 2 or parts[0] != "api":
        return None
    section, rest = parts[1], parts[2:]
    if section == "plans" and rest[-1:] == ["log"]:
        return ("plan", "exercise")
    if section in _SECTION_DOMAINS:
        return _SECTION_DOMAINS[section]
    if section not in ("logs", "catalog") or not rest:
        return None
    subject = rest[1] if rest[0] == "sets" and len(rest) > 1 else rest[0]
    if subject in _PATH_DOMAINS:
        return subject
    from src.gui.domains import domain_of_table

    return domain_of_table(subject)
