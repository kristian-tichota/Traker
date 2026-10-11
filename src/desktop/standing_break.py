import contextlib
import json
import logging
import os
import time

from src.desktop import files
from src.desktop.activities import BreakActivity

log = logging.getLogger(__name__)

DEFAULT_PATH = os.path.expanduser("~/.config/traker/standing-break.json")

RESUME_WITHIN_MS = 120_000


def beside(queue_path) -> str:
    """Return the saved walls' file that belongs with this member's queue."""
    folder = os.path.dirname(str(queue_path or "").strip() or DEFAULT_PATH)
    return os.path.join(folder or ".", os.path.basename(DEFAULT_PATH))


def save(state, path=None) -> None:
    """Store what the walls stand for, stamped with the moment of saving."""
    try:
        files.write(path or DEFAULT_PATH,
                    json.dumps({**state, "saved_at_ms": now_ms()}, indent=1))
    except OSError as e:
        log.warning("Could not save the standing break: %s", e)


def take(path=None) -> dict | None:
    """Return the walls saved within RESUME_WITHIN_MS with how long ago, forgetting them."""
    path = path or DEFAULT_PATH
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        log.warning("Could not read the standing break %s: %s", path, e)
        return None
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)
    try:
        state = json.loads(text)
        gone_ms = now_ms() - int(state["saved_at_ms"])
    except (ValueError, TypeError, KeyError) as e:
        log.warning("Ignoring the standing break %s: %s", path, e)
        return None
    if not 0 <= gone_ms <= RESUME_WITHIN_MS:
        log.info("Ignoring a standing break saved %d s ago.", gone_ms // 1000)
        return None
    return {**state, "gone_ms": gone_ms}


def activity(written) -> BreakActivity | None:
    """Return the activity a saved list of its fields names, or None."""
    if not isinstance(written, list) or len(written) < 3:
        return None
    name, path, kind, *rest = written
    return BreakActivity(str(name), str(path), str(kind), tuple(rest[0]) if rest else ())


def now_ms() -> int:
    return int(time.time() * 1000)
