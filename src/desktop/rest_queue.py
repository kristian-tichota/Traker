import logging
import os

log = logging.getLogger(__name__)

DEFAULT_PATH = os.path.expanduser("~/.config/traker/rest-queue.m3u")

HEADER = ("# Traker: what to watch on the next break, newest last.\n"
          "# One path per line; a line starting with # is ignored. Append with\n"
          "# ':rest <path>' in Traker, or with anything else that can write a\n"
          "# file. Nothing here is opened until its key is pressed on a break.\n")


def path_for(profile) -> str:
    """Return this member's queue file, from [strict_break.queue] path."""
    written = str((profile.get_metric("strict_break", "queue", {}) or {})
                  .get("path") or "").strip()
    return os.path.expanduser(written) if written else DEFAULT_PATH


def describe(entries) -> str:
    """Format the queue as one status-bar line: 1 a.mp4 · 2 b.mp4."""
    if not entries:
        return "empty."
    return " · ".join(f"{index} {label(entry)}"
                      for index, entry in enumerate(entries, start=1))


def read(path=None) -> list:
    """Return the queued paths, in the order they were added."""
    try:
        with open(path or DEFAULT_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return []
    except OSError as e:
        log.warning("Could not read the break queue %s: %s", path or DEFAULT_PATH, e)
        return []

    return [line.strip() for line in lines
            if line.strip() and not line.lstrip().startswith("#")]


def append(entry, path=None) -> list:
    wanted = os.path.expanduser(str(entry or "").strip())
    if not wanted:
        raise ValueError("Nothing to queue.")

    queued = read(path)
    if wanted in queued:
        return queued
    return write(queued + [wanted], path)


def remove(position, path=None) -> list:
    """Drop the entry at position, counted from 1 as the surface shows it."""
    queued = read(path)
    index = int(position) - 1
    if index < 0 or index >= len(queued):
        raise ValueError(f"There is no {position} in the queue.")
    return write(queued[:index] + queued[index + 1:], path)


def clear(path=None) -> list:
    """Empty the queue, keeping the file and its header."""
    return write([], path)


def write(entries, path=None) -> list:
    target = path or DEFAULT_PATH
    body = "".join(f"{entry}\n" for entry in entries)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(HEADER + body)
    except OSError as e:
        raise ValueError(f"Could not write the break queue: {e}") from e
    return list(entries)


def label(entry) -> str:
    """Return how one queued path reads on a break surface: its own name."""
    return os.path.basename(str(entry).rstrip("/")) or str(entry)
