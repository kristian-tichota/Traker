import logging
import os

from src.desktop import kde_config
from src.desktop.session import (ACTIVITIES, ACTIVITIES_PATH, ACTIVITIES_SERVICE, KWIN,
                                 KWIN_PATH, session_call, session_send)

log = logging.getLogger(__name__)

REST_GROUP = "traker-rest"
WINDOW_GROUP = "traker-window"
GENERAL = "General"

FORCE_TEMPORARILY = 6
EXACT_MATCH = 1
SUBSTRING_MATCH = 2

EVERYWHERE = ""

DEFAULT_PATH = os.path.join(kde_config.CONFIG_DIR, "kwinrulesrc")


def _rule_names(general):
    """Return the ordered group names of the rules this file already has."""
    named = kde_config.read(general, "rules")
    if named is not None:
        return [n for n in (part.strip() for part in named.split(",")) if n]
    try:
        count = int(kde_config.read(general, "count") or 0)
    except ValueError:
        return []
    return [str(i) for i in range(1, count + 1)]


def _list(general, names):
    """Write the ordered rule names into [General]."""
    kde_config.set_key(general, "rules", ",".join(names))
    kde_config.set_key(general, "count", str(len(names)))


def written(text, group, keys):
    """Insert one rule first and keep every other line."""
    sections = [(n, lines) for n, lines in kde_config.split(text) if n != group]
    general = kde_config.group_or_new(sections, GENERAL)
    _list(general, [group] + [n for n in _rule_names(general) if n != group])
    sections.append((group, [f"[{group}]\n"] + [f"{key}={value}\n" for key, value in keys]))
    return kde_config.join(sections)


def removed(text, *groups):
    """Return text with none of the groups in it."""
    sections = [(n, lines) for n, lines in kde_config.split(text) if n not in groups]
    for name, lines in sections:
        if name == GENERAL:
            _list(lines, [n for n in _rule_names(lines) if n not in groups])
    return kde_config.join(sections)


def rest_keys(title_prefix, everywhere=True):
    """Build the keys that put every wall in front, immune to a member's rule."""
    keys = [
        ("Description", "Traker: a rest break's walls, in front of every screen"),
        ("title", title_prefix),
        ("titlematch", SUBSTRING_MATCH),
    ]
    if everywhere:
        keys += [
            ("desktops", EVERYWHERE),
            ("desktopsrule", FORCE_TEMPORARILY),
            ("activity", EVERYWHERE),
            ("activityrule", FORCE_TEMPORARILY),
        ]
    return keys + [
        ("fullscreen", "true"),
        ("fullscreenrule", FORCE_TEMPORARILY),
        ("above", "true"),
        ("aboverule", FORCE_TEMPORARILY),
        ("minimize", "false"),
        ("minimizerule", FORCE_TEMPORARILY),
    ]


def window_keys(caption, desktop_id=None, activity_id=None):
    """Build the keys placing the application's own window, by whichever resolved."""
    keys = [
        ("Description", "Traker: where the application's own window belongs"),
        ("title", caption),
        ("titlematch", EXACT_MATCH),
    ]
    if desktop_id:
        keys += [("desktops", desktop_id), ("desktopsrule", FORCE_TEMPORARILY)]
    if activity_id:
        keys += [("activity", activity_id), ("activityrule", FORCE_TEMPORARILY)]
    return keys


def desktop_id(which, path=None):
    """Return the id of a virtual desktop, named by position or by name."""
    lines = kde_config.group(
        kde_config.text(path or kde_config.KWINRC_PATH) or "", "Desktops")
    try:
        count = int(kde_config.read(lines, "Number") or 1)
    except ValueError:
        count = 1

    wanted = str(which).strip().casefold()
    for position in range(1, count + 1):
        name = kde_config.read(lines, f"Name_{position}") or f"Desktop {position}"
        if wanted in (str(position), name.casefold()):
            return kde_config.read(lines, f"Id_{position}") or None
    return None


def activity_id(name, caller=None):
    """Return the id of an activity, named by name or given as its own id."""
    call = caller or session_call
    reached, ids = call(ACTIVITIES_SERVICE, ACTIVITIES_PATH, ACTIVITIES,
                        "ListActivities")
    if not reached or not ids:
        return None

    wanted = str(name).strip()
    ids = [str(one) for one in ids]
    if wanted in ids:
        return wanted

    folded = wanted.casefold()
    for one in ids:
        reached, answered = call(ACTIVITIES_SERVICE, ACTIVITIES_PATH,
                                 ACTIVITIES, "ActivityName", one)
        if reached and str(answered or "").strip().casefold() == folded:
            return one
    return None


def _reconfigure() -> bool:
    """Ask KWin to re-read its rules."""
    return session_send(KWIN, KWIN_PATH, KWIN, "reconfigure")


def _restore(path, was, existed) -> bool:
    """Put the file back exactly as it was, or back to not being there."""
    if existed:
        return kde_config.store(path, was)
    try:
        os.remove(path)
    except OSError as e:
        log.warning("Could not remove %s: %s", path, e)
        return False
    return True


def carried(group=None, path=None) -> bool:
    """Report whether the file currently holds one of this application's rules."""
    carries = kde_config.text(path or DEFAULT_PATH) or ""
    wanted = [group] if group else [REST_GROUP, WINDOW_GROUP]
    return any(f"[{one}]" in carries for one in wanted)


def prune(groups=(REST_GROUP, WINDOW_GROUP), path=None, reconfigure=None) -> bool:
    """Remove this application's rules, whatever left them there."""
    path = path or DEFAULT_PATH
    before = kde_config.text(path)
    if before is None:
        return False
    after = removed(before, *groups)
    if after == before:
        return True
    if not kde_config.store(path, after):
        return False
    return bool((reconfigure or _reconfigure)())


class TemporaryRule:
    """One ForceTemporarily group in kwinrulesrc, while it is held."""

    group = ""

    def __init__(self, path=None, reconfigure=None):
        self._path = path or DEFAULT_PATH
        self._reconfigure = reconfigure or _reconfigure
        self.holding = False

    def keys(self):
        """Return the rule's own keys, or () where there is nothing to say."""
        raise NotImplementedError

    def hold(self) -> bool:
        keys = self.keys()
        if not keys:
            return False

        before = kde_config.text(self._path)
        if before is None:
            return False
        existed = os.path.exists(self._path)
        if not kde_config.store(self._path, written(before, self.group, keys)):
            return False

        if not self._reconfigure():
            log.debug("No session to read a window rule from %s.", self._path)
            _restore(self._path, before, existed)
            return False

        self.holding = True
        self.say()
        return True

    def release(self) -> bool:
        if not self.holding:
            return True
        self.holding = False
        return prune((self.group,), self._path, self._reconfigure)

    def say(self):
        """Log one journal line naming what was asked for."""


class RestRule(TemporaryRule):
    """A break's walls, in front of every screen and on every desktop."""

    group = REST_GROUP

    def __init__(self, title_prefix, path=None, reconfigure=None):
        super().__init__(path, reconfigure)
        self._prefix = str(title_prefix or "")
        self.everywhere = True

    def keys(self):
        if not self._prefix:
            log.debug("No wall title to match a rule on: a break holds "
                      "whatever the compositor carries.")
            return ()
        return rest_keys(self._prefix, self.everywhere)

    def hold(self) -> bool:
        self.everywhere = True
        return super().hold()

    def stand_down(self) -> bool:
        """Give the desktops back, leaving the walls in front of their screens."""
        if not self.holding:
            return False
        self.everywhere = False
        if super().hold():
            return True
        self.everywhere = True
        return False

    def say(self):
        log.info("A break's walls are forced in front of every screen%s by a "
                 "window rule in %s.",
                 " and onto every desktop and activity" if self.everywhere else "",
                 self._path)


class WindowHome(TemporaryRule):
    """The application's own window, on the desktop and activity it belongs on."""

    group = WINDOW_GROUP

    def __init__(self, caption, desktop=None, activity=None, path=None,
                 reconfigure=None, kwinrc=None, caller=None):
        super().__init__(path, reconfigure)
        self._caption = str(caption or "")
        self._desktop = str(desktop or "").strip()
        self._activity = str(activity or "").strip()
        self._kwinrc = kwinrc
        self._caller = caller

    def keys(self):
        if not self._caption or not (self._desktop or self._activity):
            return ()

        desktop = activity = None
        if self._desktop:
            desktop = desktop_id(self._desktop, self._kwinrc)
            if not desktop:
                log.warning("No virtual desktop is called %r on this session, "
                            "so the window is not placed on one.", self._desktop)
        if self._activity:
            activity = activity_id(self._activity, self._caller)
            if not activity:
                log.warning("No activity is called %r on this session, so the "
                            "window is not placed on one.", self._activity)

        if not (desktop or activity):
            return ()
        return window_keys(self._caption, desktop, activity)

    def say(self):
        log.info("Traker's window is forced onto %s by a window rule in %s.",
                 " / ".join(p for p in (self._desktop, self._activity) if p),
                 self._path)
