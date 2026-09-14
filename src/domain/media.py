from typing import NamedTuple

TIME, PAGES = "time", "pages"

UNKNOWN = "—"


class Place(NamedTuple):
    """Where something got to, and what that is out of."""

    at: int = 0
    of: int = 0


def away_ms(secs, phase_ms, standard_ms) -> int:
    """Return how long this break waits before it will show anything."""
    away = max(0.0, float(secs or 0)) * 1000
    phase, standard = max(0, int(phase_ms or 0)), max(0, int(standard_ms or 0))
    if standard > 0:
        away *= phase / standard
    return int(min(away, phase))


def opens_in(away, phase_ms, left_ms) -> int:
    """Return what is left of that wait, zero once the break will show one."""
    elapsed = max(0, int(phase_ms or 0)) - max(0, int(left_ms or 0))
    return max(0, int(away or 0) - max(0, elapsed))


def as_elapsed(ms) -> str:
    """Format milliseconds as a position in a file: "26:33", "1:26:35"."""
    total = max(0, int(ms or 0) // 1000)
    hours, rest = divmod(total, 3600)
    mins, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def how_far(place, unit=TIME) -> str:
    """Format "26:33 / 1:26:35" or "42 / 310", or UNKNOWN."""
    at, of = _bounded(place, unit)
    if of <= 0:
        return UNKNOWN
    if unit == PAGES:
        return f"{at} / {of}"
    return f"{as_elapsed(at)} / {as_elapsed(of)}"


def fraction(place, unit=TIME) -> float:
    """Return how much is behind the member, between nothing and all of it."""
    at, of = _bounded(place, unit)
    return at / of if of > 0 else 0.0


def _bounded(place, unit):
    """Return the pair as two bounded numbers, pages counted from one."""
    at, of = (int(place.at or 0), int(place.of or 0)) if place else (0, 0)
    at, of = max(0, at), max(0, of)
    if of <= 0:
        return at, 0
    if unit == PAGES:
        at += 1
    return min(at, of), of
