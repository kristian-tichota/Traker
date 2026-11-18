import logging
import os
import re
import tomllib
from typing import NamedTuple

from src.desktop import rest_queue
from src.domain import media

log = logging.getLogger(__name__)

VIDEO = "video"
DOCUMENT = "document"
BOOK = "book"
DECK = "deck"
PAGE = "page"
TERMINAL = "terminal"
SHELF = "shelf"
GALLERY = "gallery"
LISTS = (SHELF, GALLERY)
ANY_DECK = "*"

DEFAULT_LIBRARY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Media")

SHELVED = (".epub", ".pdf", ".mkv", ".mp4", ".webm", ".avi", ".mov", ".m4v", ".wmv",
           ".flv", ".mpg", ".mpeg", ".ts", ".ogv", ".mp3", ".flac", ".m4a", ".ogg",
           ".opus", ".wav")


class BreakActivity(NamedTuple):
    """One thing a break may show: a file, a deck, a page, sessions, a shelf or a gallery."""

    name: str
    path: str
    kind: str
    items: tuple = ()


class Entry(NamedTuple):
    """One line of a folder's list: a folder holding something to show, or a file."""

    name: str
    path: str
    folder: bool


class Item(NamedTuple):
    """One named file of a gallery shelf, opened at page where it names one."""

    name: str
    path: str
    page: int = 0


class Shelf(NamedTuple):
    """One named row of a gallery, holding its items in written order."""

    name: str
    items: tuple


def kind_of(path) -> str:
    """Return DOCUMENT for a PDF, BOOK for an EPUB and VIDEO for anything else."""
    written = str(path).lower()
    if written.endswith(".pdf"):
        return DOCUMENT
    return BOOK if written.endswith(".epub") else VIDEO


def readout_of(kind) -> str:
    """Return the readout that says how far through this kind the member is."""
    return {DOCUMENT: media.PAGES, BOOK: media.SHARE, DECK: media.CARDS}.get(kind, media.TIME)


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


def library_for(profile) -> str:
    """Return this member's media folder, from [strict_break.library] path."""
    written = str(profile.get_metric("strict_break.library", "path", "") or "").strip()
    return os.path.abspath(os.path.expanduser(written)) if written else DEFAULT_LIBRARY


def shelves(folder) -> list:
    """Return one SHELF per subfolder of folder that holds something to show, in name order."""
    entries = _listed(folder)
    loose = tuple(entry.path for entry in entries
                  if _shelved(entry.name) and entry.is_file())
    found = ([BreakActivity(os.path.basename(os.path.normpath(folder)), folder, SHELF, loose)]
             if loose else [])
    for entry in entries:
        if entry.is_dir() and not entry.name.startswith("."):
            items = _shelved_under(entry.path)
            if items:
                found.append(BreakActivity(entry.name, entry.path, SHELF, items))
    return found


def contents(folder) -> list:
    """Return the subfolders holding something to show, then the files to show, in name order."""
    entries = _listed(folder)
    folders = [Entry(entry.name, entry.path, True) for entry in entries
               if not entry.name.startswith(".") and entry.is_dir()
               and next(_shelved_files(entry.path), None) is not None]
    files = [Entry(entry.name, entry.path, False) for entry in entries
             if _shelved(entry.name) and entry.is_file()]
    return folders + files


def resolve(offer, places) -> BreakActivity:
    """Return what an offer opens: a shelf's latest file, or the next once it ended."""
    if offer.kind != SHELF or not offer.items:
        return offer
    latest = next((path for path in reversed(list(places)) if path in offer.items), None)
    chosen = latest or offer.items[0]
    if latest is not None and _ended(latest, places):
        at = offer.items.index(latest)
        rest = offer.items[at + 1:] + offer.items[:at]
        chosen = next((path for path in rest if not _ended(path, places)), latest)
    return BreakActivity(rest_queue.label(chosen), chosen, kind_of(chosen))


def gallery(path) -> list:
    """Return the shelves a gallery file declares, each item's file present, in written order."""
    try:
        with open(path, "rb") as f:
            written = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        log.warning("Could not read the gallery %s: %s", path, e)
        return []
    home = os.path.dirname(os.path.abspath(path))
    found = []
    for position, entry in enumerate(_tables(written.get("shelf")), start=1):
        name = str(entry.get("name") or "").strip() or f"Shelf {position}"
        base = os.path.join(home, os.path.expanduser(str(entry.get("folder") or "")))
        items = tuple(item for item in (_item(base, raw) for raw in _tables(entry.get("items")))
                      if item is not None)
        if items:
            found.append(Shelf(name, items))
    return found


def _tables(value) -> list:
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def _item(base, entry):
    """Return one gallery entry as an Item, or None where it names no file that is there."""
    path = str(entry.get("path") or "").strip()
    if not path:
        return None
    path = os.path.normpath(os.path.join(base, os.path.expanduser(path)))
    if not os.path.isfile(path):
        log.info("The gallery names %s, which is not there: skipped.", path)
        return None
    page = entry.get("page")
    page = page if isinstance(page, int) and not isinstance(page, bool) and page > 0 else 0
    name = str(entry.get("name") or "").strip() or rest_queue.label(path)
    return Item(name, path, page)


def _ended(path, places) -> bool:
    return media.finished(places.get(path, media.Place()), readout_of(kind_of(path)))


def _listed(folder) -> list:
    """Return folder's entries in natural order of name, or none where it cannot be read."""
    try:
        with os.scandir(folder) as scanned:
            return sorted(scanned, key=lambda entry: _natural(entry.name))
    except OSError:
        return []


def _shelved(name) -> bool:
    return not name.startswith(".") and name.lower().endswith(SHELVED)


def _shelved_under(folder) -> tuple:
    """Return every file under folder a shelf can show, in natural order of path."""
    return tuple(sorted(_shelved_files(folder),
                        key=lambda path: _natural(os.path.relpath(path, folder))))


def _shelved_files(folder):
    """Yield every file under folder a shelf can show, walking each real folder once."""
    seen = set()
    for top, folders, files in os.walk(folder, followlinks=True):
        real = os.path.realpath(top)
        if real in seen:
            folders[:] = []
            continue
        seen.add(real)
        folders[:] = [name for name in folders if not name.startswith(".")]
        yield from (os.path.join(top, name) for name in files if _shelved(name))


def _natural(text) -> list:
    """Return a sort key that orders "2" before "10"."""
    return [int(part) if part.isdecimal() else part.casefold()
            for part in re.split(r"(\d+)", str(text))]


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
    deck = str(entry.get("deck") or "").strip()
    url = str(entry.get("url") or "").strip()
    program = str(entry.get("sessions") or "").strip()
    shelves = str(entry.get("gallery") or "").strip()
    if sum(map(bool, (path, deck, url, program, shelves))) > 1:
        log.warning("Break activity %r names more than one of a path, a deck, a url, "
                    "sessions and a gallery: skipped.", name)
        return None
    if shelves:
        return BreakActivity(name, os.path.abspath(os.path.expanduser(shelves)), GALLERY)
    if deck:
        return BreakActivity(name, deck, DECK)
    if url:
        return BreakActivity(name, url, PAGE)
    if program:
        return BreakActivity(name, program, TERMINAL)
    if not path:
        if entry.get("command") is not None or entry.get("app_id") is not None:
            log.warning("Break activity %r still names a command and an app "
                        "id; a break shows the file itself now. Replace both "
                        "with path = \"<the file>\": skipped.", name)
        else:
            log.warning("Break activity %r has no path, deck, url, sessions or gallery: "
                        "skipped.", name)
        return None

    return BreakActivity(name, os.path.expanduser(path), kind_of(path))
