import shlex
import subprocess
from typing import NamedTuple

LIST_TIMEOUT_SECS = 15.0

AGO_UNITS = ((86_400, "D"), (3_600, "H"), (60, "MIN"))


class Session(NamedTuple):
    """One live session of a project, as the session program lists it."""

    name: str
    clients: int
    active_at: int
    title: str


class Project(NamedTuple):
    """One project the session program offers, with its live sessions, latest first."""

    path: str
    label: str
    sessions: tuple = ()


def parse(text) -> list:
    """Return the projects of a listing, each with the sessions listed under its path."""
    projects, found = [], {}
    for line in str(text).splitlines():
        fields = line.split("\t")
        if fields[0] == "project" and len(fields) >= 3:
            projects.append(Project(fields[1], fields[2] or fields[1]))
        elif fields[0] == "session" and len(fields) >= 6:
            found.setdefault(fields[1], []).append(
                Session(fields[2], _count(fields[3]), _count(fields[4]),
                        " ".join("\t".join(fields[5:]).split())))
    return [project._replace(sessions=tuple(sorted(found.get(project.path, ()),
                                                   key=lambda session: -session.active_at)))
            for project in projects]


def listing(command) -> list:
    """Run the program's listing and return its projects."""
    done = subprocess.run([*shlex.split(command), "--list"], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=LIST_TIMEOUT_SECS,
                          check=True)
    return parse(done.stdout)


def opening(command, path, session="") -> list:
    """Return the argv running session at path, or a new chat without one."""
    return [*shlex.split(command), "--open", str(path), *([session] if session else [])]


def ago(secs) -> str:
    """Format a time since in its largest whole unit: "NOW", "12 MIN AGO", "3 H AGO"."""
    secs = max(0, int(secs))
    for size, unit in AGO_UNITS:
        if secs >= size:
            return f"{secs // size} {unit} AGO"
    return "NOW"


def described(session, now) -> str:
    """Return what a session's row notes: whether a client shows it, and its last activity."""
    when = ago(now - session.active_at)
    return f"ATTACHED · {when}" if session.clients else when


def _count(written) -> int:
    try:
        return max(0, int(written))
    except ValueError:
        return 0
