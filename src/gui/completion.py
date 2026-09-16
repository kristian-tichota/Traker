import os
import unicodedata
from dataclasses import dataclass

PREFIX, SUBSTRING, SUBSEQUENCE = 0, 1, 2


def normalize(text: str) -> str:
    """Fold a name to the form matching compares: no diacritics, no capitals."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def nocase_fold(text: str) -> str:
    """Fold a name the way the server's COLLATE NOCASE lookup does."""
    return "".join(ch.lower() if "A" <= ch <= "Z" else ch for ch in text)


def is_subsequence(needle: str, haystack: str) -> bool:
    """Report whether the characters of needle appear in haystack, in order."""
    position = 0
    for char in needle:
        found = haystack.find(char, position)
        if found < 0:
            return False
        position = found + 1
    return True


def _score(typed_norm: str, name: str):
    """Rank one candidate, or return None where it does not match."""
    name_norm = normalize(name)
    if name_norm.startswith(typed_norm):
        quality, offset = PREFIX, 0
    else:
        offset = name_norm.find(typed_norm)
        if offset >= 0:
            quality = SUBSTRING
        elif is_subsequence(typed_norm, name_norm):
            quality, offset = SUBSEQUENCE, 0
        else:
            return None
    return quality, offset, len(name), name


def best_match(typed: str, names) -> str | None:
    """Return the catalog name that best answers the typed text, or None."""
    typed_norm = normalize(typed)
    if not typed_norm:
        return None
    scored = [score for score in (_score(typed_norm, name) for name in names) if score]
    return min(scored)[-1] if scored else None


def ranked_matches(typed: str, names, prefer=None) -> list:
    """Return every name that answers typed, best answer first."""
    typed_norm = normalize(typed)
    keys = []
    for position, name in enumerate(names):
        preferred = 0 if prefer is not None and prefer(name) else 1
        if not typed_norm:
            keys.append((PREFIX, preferred, 0, position, name))
            continue
        scored = _score(typed_norm, name)
        if scored is None:
            continue
        quality, offset, length, tiebreak = scored
        keys.append((quality, preferred, offset, length, tiebreak))
    return [key[-1] for key in sorted(keys)]


def completion_tail(typed: str, name: str) -> str | None:
    """Return the characters to append, or None where that would break lookup."""
    if nocase_fold(name[:len(typed)]) != nocase_fold(typed):
        return None
    return name[len(typed):]

DIRECTORY, FILE = "directory", "file"

NO_SUCH_DIRECTORY, UNREADABLE = "no such directory", "cannot be read"


@dataclass(frozen=True)
class PathChoice:
    """One thing Tab could write into a path argument."""

    written: str
    name: str
    kind: str


@dataclass(frozen=True)
class PathListing:
    """The directory a path fragment leads to, and what could complete it there."""

    directory: str
    choices: tuple = ()
    total: int = 0
    problem: str = ""


def where(head: str) -> str:
    """Return the directory head names, absolute, with the home folder as ~."""
    absolute = os.path.abspath(os.path.expanduser(head) or ".")
    home = os.path.expanduser("~")
    if absolute == home or absolute.startswith(home + os.sep):
        absolute = "~" + absolute[len(home):]
    return absolute.rstrip(os.sep) + os.sep


def _entries(directory: str, typed: str) -> list:
    """Return (name, is_dir) for every entry a shell would list for typed."""
    hidden_wanted = typed.startswith(".")
    with os.scandir(directory) as scanned:
        listed = [(entry.name, entry.is_dir()) for entry in scanned
                  if hidden_wanted or not entry.name.startswith(".")]
    return sorted(listed, key=lambda entry: entry[0].lower())


def list_paths(fragment: str, words=None) -> PathListing:
    """Return what could complete fragment: entries of its directory, and words."""
    head, typed = os.path.split(fragment)
    if not head and typed == "~":
        return PathListing(where("~"), (PathChoice("~/", "~/", DIRECTORY),), 1)

    directory = where(head)
    try:
        entries = _entries(os.path.expanduser(head) or ".", typed)
    except (FileNotFoundError, NotADirectoryError):
        return PathListing(directory, problem=NO_SUCH_DIRECTORY)
    except OSError:
        return PathListing(directory, problem=UNREADABLE)

    kinds = dict(words or {}) if not head else {}
    if typed in (".", ".."):
        kinds.setdefault(typed, DIRECTORY)
    for name, is_dir in entries:
        kinds.setdefault(name, DIRECTORY if is_dir else FILE)

    typed_norm = normalize(typed)
    choices = tuple(
        PathChoice(os.path.join(head, name) + (os.sep if kind == DIRECTORY else ""),
                   name + (os.sep if kind == DIRECTORY else ""), kind)
        for name, kind in kinds.items() if normalize(name).startswith(typed_norm))
    return PathListing(directory, choices, len(entries))


def human_size(size: float) -> str:
    """Format a byte count as 999 B, 12.5 KB, 1.2 GB."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.4g} {unit}"
        size /= 1024


def describe_path(choice: PathChoice) -> str:
    """Return the right-hand column for a choice: its size, or what it is."""
    if choice.kind != FILE:
        return choice.kind
    try:
        return human_size(os.stat(os.path.expanduser(choice.written)).st_size)
    except OSError:
        return FILE
