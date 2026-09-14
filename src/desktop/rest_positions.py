import json
import logging
import os

from src.domain.media import Place

log = logging.getLogger(__name__)

DEFAULT_PATH = os.path.expanduser("~/.config/traker/rest-positions.json")

KEEP = 100


def read(path=None) -> dict:
    """Return every remembered place, keyed by path."""
    try:
        with open(path or DEFAULT_PATH, encoding="utf-8") as f:
            stored = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning("Could not read %s: %s", path or DEFAULT_PATH, e)
        return {}
    if not isinstance(stored, dict):
        return {}
    places = ((str(k), _place(v)) for k, v in stored.items())
    return {key: place for key, place in places if place is not None}


def _place(value):
    """Return one entry as a place, or None where the value is unusable."""
    at = _number(value)
    if at is not None:
        return Place(int(at), 0)
    if isinstance(value, dict):
        at, of = _number(value.get("at")), _number(value.get("of"))
        if at is not None:
            return Place(int(at), max(0, int(of or 0)))
    return None


def _number(value):
    """Return value where it is a number, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def position_for(item, path=None) -> int:
    """Return where to resume item: milliseconds for a video, a page for a PDF."""
    return place_for(item, path).at


def place_for(item, path=None) -> Place:
    """Return how far through item the member got, for a readout not a seek."""
    return read(path).get(str(item), Place())


def remember(item, position, path=None, duration=0) -> None:
    """Store where item was left, and how long it is."""
    key = str(item)
    stored = read(path)
    stored.pop(key, None)
    if int(position or 0) > 0:
        stored[key] = Place(int(position), max(0, int(duration or 0)))

    target = path or DEFAULT_PATH
    trimmed = list(stored.items())[-KEEP:]
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump({item: {"at": place.at, "of": place.of}
                       for item, place in trimmed}, f, indent=1, sort_keys=False)
    except OSError as e:
        log.warning("Could not remember where %s stopped: %s", key, e)


def beside(queue_path) -> str:
    """Return the positions file that belongs with this member's queue."""
    folder = os.path.dirname(str(queue_path or "").strip() or DEFAULT_PATH)
    return os.path.join(folder or ".", os.path.basename(DEFAULT_PATH))
