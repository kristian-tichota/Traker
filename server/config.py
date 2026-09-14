import json
import logging
import os
import secrets
import tomllib

log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/traker/server.toml")
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "..", "data", "traker_server.db")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6035

TOKEN_BYTES = 16

TEMPLATE = """# Traker household service.
#
# Every value here is optional except the members: the service refuses to start
# until at least one is named. Leave a member's token out and one is minted on
# the next start, written back here, and logged once so it can be pasted into
# that member's client profile.
#
# TRAKER_SERVER_CONFIG points at this file; TRAKER_SERVER_HOST,
# TRAKER_SERVER_PORT and TRAKER_DB_PATH override the three settings below.

[server]
# 127.0.0.1 keeps the service on this machine. A household whose clients run on
# other machines sets 0.0.0.0, and should only do so behind a trusted network.
host = "127.0.0.1"
port = 6035
# Relative paths resolve against the repository root.
db_path = "data/traker_server.db"

# One block per member. They share the catalog and keep separate logs.
# [[members]]
# username = "alice"
"""


def config_path() -> str:
    """Return the file the service reads its settings from."""
    return os.environ.get("TRAKER_SERVER_CONFIG") or DEFAULT_CONFIG_PATH


def write_template(path: str) -> bool:
    """Write a commented starting point at path, unless one is already there."""
    if os.path.exists(path):
        return False
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEMPLATE)
    except OSError as e:
        log.error("Could not write %s: %s", path, e)
        return False
    os.chmod(path, 0o600)
    return True


def _read(path: str) -> dict:
    """Return the parsed settings, or nothing where the file is missing or broken."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except OSError as e:
        log.warning("Could not read %s: %s", path, e)
    except tomllib.TOMLDecodeError as e:
        log.warning("Could not parse %s: %s", path, e)
    return {}


def _members(entries, path):
    """Return every named member with a token, and whether a token was minted."""
    members, minted, seen = [], False, set()
    for entry in entries if isinstance(entries, list) else []:
        username = str(entry.get("username", "")).strip() if isinstance(entry, dict) else ""
        if not username:
            log.warning("Ignoring a member with no username in %s", path)
            continue
        if username.casefold() in seen:
            log.warning("Ignoring a second member called %s in %s", username, path)
            continue
        seen.add(username.casefold())

        token = str(entry.get("token", "")).strip()
        if not token:
            token = secrets.token_urlsafe(TOKEN_BYTES)
            minted = True
            log.warning("Minted an access token for %s: %s", username, token)
        members.append((username, token))
    return members, minted


def _persist(path: str, raw: dict, members) -> None:
    """Write the settings back with the minted tokens, excluding the environment."""
    lines = []
    server = raw.get("server", {})
    if isinstance(server, dict) and server:
        lines.append("[server]")
        lines += [f"{key} = {json.dumps(value)}"
                  for key, value in server.items()
                  if isinstance(value, (str, int, float, bool))]
        lines.append("")
    for username, token in members:
        lines += ["[[members]]",
                  f"username = {json.dumps(username)}",
                  f"token = {json.dumps(token)}",
                  ""]

    temporary = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(temporary, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as e:
        log.error("Minted a token but could not write it to %s: %s — it is lost on the "
                  "next restart", path, e)
        return
    log.warning("Rewrote %s with the minted tokens; any comments in it are gone", path)


def _resolve():
    path = config_path()
    raw = _read(path)
    server = raw.get("server", {})
    if not isinstance(server, dict):
        server = {}

    host = os.environ.get("TRAKER_SERVER_HOST") or server.get("host") or DEFAULT_HOST
    try:
        port = int(os.environ.get("TRAKER_SERVER_PORT") or server.get("port") or DEFAULT_PORT)
    except (TypeError, ValueError):
        log.warning("Ignoring an unreadable port, falling back to %s", DEFAULT_PORT)
        port = DEFAULT_PORT

    db_path = os.environ.get("TRAKER_DB_PATH") or server.get("db_path") or DEFAULT_DB_PATH
    db_path = os.path.expanduser(str(db_path))
    if not os.path.isabs(db_path):
        db_path = os.path.join(BASE_DIR, "..", db_path)

    members, minted = _members(raw.get("members", []), path)
    if minted:
        _persist(path, raw, members)

    return path, str(host), port, db_path, {token: username for username, token in members}


CONFIG_PATH, HOST, PORT, DB_PATH, USER_TOKENS = _resolve()
