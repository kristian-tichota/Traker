import logging
import os

log = logging.getLogger(__name__)

CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
KWINRC_PATH = os.path.join(CONFIG_DIR, "kwinrc")


def split(text):
    """Split the file into [(group, lines)], with None above the first group."""
    sections = [(None, [])]
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            sections.append((stripped[1:-1], [line]))
        else:
            sections[-1][1].append(line)
    return sections


def join(sections):
    return "".join("".join(lines) for _, lines in sections)


def read(lines, key):
    for line in lines:
        name, separator, value = line.partition("=")
        if separator and name.strip() == key:
            return value.strip()
    return None


def set_key(lines, key, value):
    """Write one key in a group, keeping the group's trailing blank line."""
    for i, line in enumerate(lines):
        name, separator, _ = line.partition("=")
        if separator and name.strip() == key:
            lines[i] = f"{key}={value}\n"
            return
    at = len(lines)
    while at > 1 and not lines[at - 1].strip():
        at -= 1
    lines.insert(at, f"{key}={value}\n")


def group(text, name):
    """Return the lines of one group, or none where there is no such group."""
    for found, lines in split(text):
        if found == name:
            return lines
    return []


def group_or_new(sections, name):
    """Return the lines of one group, appending an empty one where absent."""
    for found, lines in sections:
        if found == name:
            return lines
    lines = [f"[{name}]\n"]
    sections.append((name, lines))
    return lines


def with_keys(text, group_name, keys):
    """Return text with keys set in group_name and nothing else touched."""
    sections = split(text)
    last = sections[-1][1]
    if last and not last[-1].endswith("\n"):
        last[-1] += "\n"
    lines = group_or_new(sections, group_name)
    for key, value in keys:
        set_key(lines, key, value)
    return join(sections)


def text(path):
    """Read a file's text, "" where absent and None where unreadable."""
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        log.warning("Could not read %s: %s", path, e)
        return None


def store(path, text_to_write) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text_to_write)
    except OSError as e:
        log.warning("Could not write %s: %s. Nothing of Traker's reaches the "
                    "compositor's configuration this session.", path, e)
        return False
    return True
