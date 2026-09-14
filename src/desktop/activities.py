import logging
import os
from typing import NamedTuple

from src.desktop import rest_queue
from src.domain import media

log = logging.getLogger(__name__)

VIDEO = "video"
DOCUMENT = "document"


class BreakActivity(NamedTuple):
    """One thing a break may show."""

    name: str
    path: str
    kind: str


def kind_of(path) -> str:
    """Return DOCUMENT for a PDF and VIDEO for anything else."""
    return DOCUMENT if str(path).lower().endswith(".pdf") else VIDEO


def readout_of(kind) -> str:
    """Return the readout that says how far through this kind the member is."""
    return media.PAGES if kind == DOCUMENT else media.TIME


def offer_key(index) -> str:
    """Return the key to press for the offer at index."""
    if index == 0:
        return "ENTER"
    return str(index + 1) if index < 9 else "—"


def read(entries) -> list:
    """Return the activities the profile declares, in declared order."""
    activities = []
    for position, entry in enumerate(entries or (), start=1):
        activity = _one(entry, position)
        if activity is not None:
            activities.append(activity)
    return activities


def queued(paths) -> list:
    """Return each queued path as an activity, named by its own file name."""
    return [BreakActivity(rest_queue.label(path), os.path.expanduser(str(path)),
                          kind_of(path))
            for path in paths if str(path).strip()]


def _one(entry, position):
    """Return one entry as a BreakActivity, or None with the reason logged."""
    if not isinstance(entry, dict):
        log.warning("Break activity %d is not a table: %r", position, entry)
        return None

    name = str(entry.get("name") or "").strip()
    if not name:
        log.warning("Break activity %d has no name: skipped.", position)
        return None

    path = str(entry.get("path") or "").strip()
    if not path:
        if entry.get("command") is not None or entry.get("app_id") is not None:
            log.warning("Break activity %r still names a command and an app "
                        "id; a break shows the file itself now. Replace both "
                        "with path = \"<the file>\": skipped.", name)
        else:
            log.warning("Break activity %r has no path: skipped.", name)
        return None

    return BreakActivity(name, os.path.expanduser(path), kind_of(path))
