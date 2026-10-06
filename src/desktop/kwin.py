import json
import logging
import os

from src.desktop import files
from src.desktop.session import KWIN, session_call

log = logging.getLogger(__name__)

PLUGIN_NAME = "traker-strict-break"
HOME_PLUGIN_NAME = "traker-window-home"


def _release_path(script_path):
    """Return the undo script's path, beside the script it undoes."""
    root, extension = os.path.splitext(script_path)
    return f"{root}-release{extension or '.js'}"


_SHARED = """
    var target = __APP_ID__;
    var wallPrefix = __WALL__;
    var wallOutputs = __WALLS__;

    function windows() {
        if (typeof workspace.windowList === "function") return workspace.windowList();
        if (typeof workspace.clientList === "function") return workspace.clientList();
        return [];
    }

    function appId(w) {
        if (!w) return "";
        return String(w.resourceClass || w.resourceName || "").toLowerCase();
    }

    function isPopup(w) {
        try { if (w.popupWindow === true) return true; } catch (e) {}
        try { if (w.tooltip === true) return true; } catch (e) {}
        return false;
    }

    function isBreak(w) {
        if (target === "" || appId(w).indexOf(target) === -1) return false;
        return !isPopup(w);
    }

    function isWall(w) {
        if (!isBreak(w)) return false;
        if (wallPrefix === "") return true;
        try { return String(w.caption || "").indexOf(wallPrefix) === 0; } catch (e) {}
        return false;
    }

    function call(w, name, argument) {
        try {
            if (typeof w[name] === "function") { w[name](argument); return true; }
        } catch (e) {}
        return false;
    }

    function connect(signal, handler) {
        try { if (signal && typeof signal.connect === "function") signal.connect(handler); }
        catch (e) {}
    }

    function outputs() {
        try {
            if (workspace.screens && workspace.screens.length !== undefined)
                return workspace.screens;
        } catch (e) {}
        return [];
    }

    function outputNamed(name) {
        if (!name) return null;
        var all = outputs();
        for (var i = 0; i < all.length; i++) {
            try { if (String(all[i].name || "") === name) return all[i]; } catch (e) {}
        }
        return null;
    }

    function onOutput(w, output) {
        try {
            var box = w.frameGeometry, area = output.geometry;
            if (box && area && box.width !== undefined && area.width !== undefined) {
                var x = box.x + box.width / 2;
                var y = box.y + box.height / 2;
                return x >= area.x && x < area.x + area.width
                    && y >= area.y && y < area.y + area.height;
            }
        } catch (e) {}
        try { if (w.output !== undefined && w.output !== null) return w.output === output; } catch (e) {}
        return false;
    }

    function outputOf(w) {
        var all = outputs();
        for (var i = 0; i < all.length; i++) {
            if (onOutput(w, all[i])) return String(all[i].name || i);
        }
        try { return "(" + w.frameGeometry.x + "," + w.frameGeometry.y + ")"; } catch (e) {}
        return "(absent)";
    }

    function placeOn(w, output) {
        if (!output || onOutput(w, output)) return;

        try {
            if (typeof workspace.sendClientToScreen === "function") {
                workspace.sendClientToScreen(w, output);
                if (onOutput(w, output)) return;
            }
        } catch (e) {}

        try { w.output = output; } catch (e) {}
        if (onOutput(w, output)) return;

        try {
            var full = w.fullScreen === true;
            if (full) w.fullScreen = false;
            w.frameGeometry = output.geometry;
            if (full) w.fullScreen = true;
        } catch (e) {}
    }
"""

_SCRIPT = """// Traker: keep a strict break where the member is.
(function () {""" + _SHARED + """
    var wanted = __CAPTION__;
    var refuseSwitch = __REFUSE__;
    var holding = false;
    var adjusting = false;

    function ours() { return windows().filter(isBreak); }

    function onEveryDesktop(w) {
        try { return w.onAllDesktops === true; } catch (e) {}
        return false;
    }

    function onEveryActivity(w) {
        try { return w.activities === undefined || w.activities.length === 0; } catch (e) {}
        return true;
    }

    function captionKey(w) {
        var caption = String(w.caption || "");
        if (wallOutputs[caption] !== undefined) return caption;
        var deduped = caption.replace(/ <[0-9]+>$/, "");
        return wallOutputs[deduped] !== undefined ? deduped : caption;
    }

    function describe(w, name) {
        try {
            if (typeof w[name] === "undefined") return "(absent)";
            return String(w[name]);
        } catch (e) {}
        return "(refused)";
    }

    function frontWindow(mine) {
        var i;
        if (wanted !== "") {
            for (i = 0; i < mine.length; i++) {
                if (String(mine[i].caption || "") === wanted) return mine[i];
            }
        }
        for (i = 0; i < mine.length; i++) {
            if (isWall(mine[i])) return mine[i];
        }
        for (i = 0; i < mine.length; i++) {
            if (mine[i].wantsInput !== false) return mine[i];
        }
        return mine[0];
    }

    function placeOnItsOutput(w) {
        placeOn(w, outputNamed(wallOutputs[captionKey(w)]));
    }

    function follow(w) {
        if (!onEveryDesktop(w)) {
            try { w.desktops = [workspace.currentDesktop]; } catch (e) {}
            try { w.desktop = workspace.currentDesktop; } catch (e) {}
        }
        if (!onEveryActivity(w)) {
            call(w, "setOnActivities", [workspace.currentActivity]);
            try { w.activities = [workspace.currentActivity]; } catch (e) {}
        }
    }

    function take(w) {
        follow(w);
        if (!isWall(w)) return;
        try { w.keepAbove = true; } catch (e) {}
        try { if (w.minimized) w.minimized = false; } catch (e) {}
        placeOnItsOutput(w);
    }

    var reported = [];

    function reportOnce(w) {
        if (reported.indexOf(w) !== -1) return;
        reported.push(w);
        print("traker: holding '" + String(w.caption || "") + "'"
              + " class=" + describe(w, "resourceName")
              + " popup=" + describe(w, "popupWindow")
              + " wall=" + isWall(w)
              + " wanted=" + (wallOutputs[captionKey(w)] || "(any)")
              + " on=" + outputOf(w)
              + " everyDesktop=" + onEveryDesktop(w)
              + " everyActivity=" + onEveryActivity(w)
              + " keepAbove=" + describe(w, "keepAbove")
              + " minimized=" + describe(w, "minimized"));
    }

    function apply(w) {
        if (adjusting || !isBreak(w)) return;
        adjusting = true;
        try { take(w); } finally { adjusting = false; }
        reportOnce(w);
    }

    function raise(w) {
        try {
            if (typeof workspace.raiseWindow === "function") workspace.raiseWindow(w);
        } catch (e) {}
    }

    function activate(w) {
        try {
            if (typeof workspace.activeWindow !== "undefined") workspace.activeWindow = w;
            else workspace.activeClient = w;
        } catch (e) {}
        raise(w);
    }

    function hold() {
        if (holding) return;
        holding = true;
        try {
            var mine = ours();
            for (var i = 0; i < mine.length; i++) apply(mine[i]);
            if (mine.length === 0) return;

            var front = frontWindow(mine);
            for (var n = 0; n < mine.length; n++) {
                if (isWall(mine[n]) && mine[n] !== front) raise(mine[n]);
            }
            raise(front);

            var current = typeof workspace.activeWindow !== "undefined"
                ? workspace.activeWindow : workspace.activeClient;
            if (current && isWall(current)) return;
            activate(front);
        } finally {
            holding = false;
        }
    }

    var held = {};
    var restoring = false;
    var said = {};

    function refuse(what) {
        if (!refuseSwitch || restoring || !(what in held)) return;
        try { if (workspace[what] === held[what]) return; } catch (e) { return; }
        restoring = true;
        try { workspace[what] = held[what]; } catch (e) {}
        restoring = false;
        if (!said[what]) {
            said[what] = true;
            var back = false;
            try { back = workspace[what] === held[what]; } catch (e) {}
            print("traker: refusing " + what + " changes during a break, back=" + back);
        }
    }

    function switched(what) {
        return function () { refuse(what); hold(); };
    }

    function watch(w) {
        connect(w.minimizedChanged, function () { apply(w); });
        connect(w.keepAboveChanged, function () { apply(w); });
        connect(w.desktopsChanged || w.desktopChanged, function () { apply(w); });
        connect(w.activitiesChanged, function () { apply(w); });
        connect(w.outputChanged || w.screenChanged, function () { apply(w); });
    }

    function onAdded(w) {
        if (!isBreak(w)) return;
        apply(w);
        watch(w);
    }

    connect(workspace.windowAdded || workspace.clientAdded, onAdded);
    connect(workspace.windowActivated || workspace.clientActivated, hold);
    connect(workspace.currentDesktopChanged, switched("currentDesktop"));
    connect(workspace.currentActivityChanged, switched("currentActivity"));
    connect(workspace.screensChanged, hold);
    connect(workspace.numberScreensChanged, hold);

    var present = windows();
    for (var n = 0; n < present.length; n++) {
        if (isBreak(present[n])) watch(present[n]);
    }
    try { held.currentDesktop = workspace.currentDesktop; } catch (e) {}
    try { held.currentActivity = workspace.currentActivity; } catch (e) {}
    hold();
    print("traker: strict break holding app id '" + target + "'");
})();
"""

_RELEASE_SCRIPT = """// Traker: give back what a strict break held.
(function () {""" + _SHARED + """
    var wallsStillStand = __STANDING__;

    function giveBack(w) {
        if (!(wallsStillStand && isWall(w))) { try { w.keepAbove = false; } catch (e) {} }
        call(w, "setOnAllDesktops", false);
        try { w.onAllDesktops = false; } catch (e) {}
        try {
            if (typeof workspace.currentDesktop === "object" && workspace.currentDesktop !== null)
                w.desktops = [workspace.currentDesktop];
            else
                w.desktop = workspace.currentDesktop;
        } catch (e) {}
        call(w, "setOnActivities", [workspace.currentActivity]);
        try { w.activities = [workspace.currentActivity]; } catch (e) {}
    }

    var all = windows();
    var given = 0;
    for (var i = 0; i < all.length; i++) {
        if (isBreak(all[i])) { giveBack(all[i]); given += 1; }
    }
    print("traker: strict break gave back " + given + " window(s)");
})();
"""

_HOME_SCRIPT = """// Traker: keep the application's own window on one output.
(function () {""" + _SHARED + """
    var wanted = __OUTPUT__;
    var caption = __CAPTION__;

    var adjusting = false;
    var watched = [];
    var failures = 0;
    var GIVE_UP = 5;

    function isHome(w) {
        if (!isBreak(w)) return false;
        try { return String(w.caption || "").replace(/ <[0-9]+>$/, "") === caption; }
        catch (e) {}
        return false;
    }

    function place(w, why) {
        if (adjusting || !isHome(w)) return;
        var output = outputNamed(wanted);
        if (!output) return;
        if (onOutput(w, output)) { failures = 0; return; }
        if (failures >= GIVE_UP) return;

        adjusting = true;
        try { placeOn(w, output); } finally { adjusting = false; }

        if (onOutput(w, output)) {
            failures = 0;
        } else if (++failures >= GIVE_UP) {
            print("traker: window home gave up moving '" + caption + "' to "
                  + wanted + "; it is on " + outputOf(w));
        }
        print("traker: window home '" + String(w.caption || "") + "' " + why
              + " wanted=" + wanted + " on=" + outputOf(w));
    }

    function settle(w, why) {
        try { if (w.move === true || w.resize === true) return; } catch (e) {}
        place(w, why);
    }

    function watch(w) {
        if (!isHome(w) || watched.indexOf(w) !== -1) return;
        watched.push(w);
        place(w, "opened");

        connect(w.interactiveMoveResizeFinished, function () { place(w, "dragged"); });
        connect(w.moveResizedChanged, function () { settle(w, "moved"); });
        connect(w.frameGeometryChanged, function () { settle(w, "resized"); });
        connect(w.outputChanged || w.screenChanged, function () { place(w, "output"); });
        connect(w.fullScreenChanged, function () { place(w, "fullscreen"); });
    }

    var mine = windows();
    for (var i = 0; i < mine.length; i++) watch(mine[i]);

    connect(workspace.windowAdded, watch);
    connect(workspace.screensChanged, function () {
        failures = 0;
        for (var j = 0; j < watched.length; j++) place(watched[j], "screens");
    });

    print("traker: window home is watching for '" + caption + "' on " + wanted);
})();
"""


def default_app_id():
    """Return what KWin will have called this application's windows."""
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtGui import QGuiApplication

    entry = QGuiApplication.desktopFileName() or ""
    if entry.endswith(".desktop"):
        entry = entry[:-len(".desktop")]
    return entry or QCoreApplication.applicationName() or ""


def _fill(template, app_id, focus_caption="", wall_prefix="",
          wall_outputs=None, refuse_switch=False, output="", standing=False):
    """Substitute the session names into one script source."""
    return (template
            .replace("__APP_ID__", json.dumps(str(app_id).lower()))
            .replace("__CAPTION__", json.dumps(str(focus_caption or "")))
            .replace("__WALL__", json.dumps(str(wall_prefix or "")))
            .replace("__WALLS__", json.dumps(dict(wall_outputs or {})))
            .replace("__REFUSE__", "true" if refuse_switch else "false")
            .replace("__OUTPUT__", json.dumps(str(output or "")))
            .replace("__STANDING__", "true" if standing else "false"))


def script_source(app_id, focus_caption="", wall_prefix="", wall_outputs=None,
                  refuse_switch=False):
    """Build the script KWin is asked to run, carrying this session's names."""
    return _fill(_SCRIPT, app_id, focus_caption, wall_prefix, wall_outputs,
                 refuse_switch)


def home_source(app_id, caption, output):
    """Build the script that keeps the application's own window on one output."""
    return _fill(_HOME_SCRIPT, app_id, focus_caption=caption, output=output)


def release_source(app_id, wall_prefix="", standing=False):
    """Build the undo, naming the same application, leaving a standing wall in front."""
    return _fill(_RELEASE_SCRIPT, app_id, wall_prefix=wall_prefix,
                 standing=standing)


def _session_caller(method, *args):
    return session_call(KWIN, "/Scripting", "org.kde.kwin.Scripting", method, *args)


def _start(call, source, path, plugin):
    """Write one script, load it and start it: (started, what KWin answered)."""
    try:
        files.write(path, source)
    except OSError as e:
        return False, f"could not write {path}: {e}"

    reached, script_id = call("loadScript", path, plugin)
    if not reached:
        return False, f"KWin refused loadScript for {path}"
    if isinstance(script_id, int) and script_id < 0:
        return False, (f"KWin answered {script_id} for loadScript, which means "
                       f"a script called {plugin!r} is already loaded")

    if not call("start")[0]:
        call("unloadScript", plugin)
        return False, "KWin loaded the script and refused to start it"
    return True, f"loaded as {plugin} (id {script_id})"


def _reported(started, why) -> bool:
    log.log(logging.INFO if started else logging.WARNING, "KWin script: %s", why)
    return started


def unload_script(plugin=PLUGIN_NAME, caller=None) -> bool:
    """Unload one script, reporting whether KWin answered at all."""
    return (caller or _session_caller)("unloadScript", plugin)[0]


release_stale_hold = unload_script


def run_script(source, path, plugin=PLUGIN_NAME, caller=None):
    """Unload a stale script of the same name, then write, load and start this one."""
    call = caller or _session_caller
    if not unload_script(plugin, call):
        return False, ("no org.kde.kwin.Scripting on this session: KWin did "
                       "not answer unloadScript at all")
    return _start(call, source, path, plugin)


class WindowScreen:
    """Keeps the application's own window on one named output, for the session."""

    def __init__(self, app_id, caption, output, caller=None, script_path=None):
        self.app_id = str(app_id or "")
        self.caption = str(caption or "")
        self.output = str(output or "").strip()
        self._call = caller or _session_caller
        self.script_path = script_path or files.cache_path("window-home.js")
        self.engaged = False

    def engage(self) -> bool:
        if not self.release():
            log.debug("No KWin scripting interface: the window stays on "
                      "whatever output the compositor gave it.")
            return False
        if not (self.app_id and self.caption and self.output):
            return False
        self.engaged = _reported(*_start(
            self._call, home_source(self.app_id, self.caption, self.output),
            self.script_path, HOME_PLUGIN_NAME))
        return self.engaged

    def release(self) -> bool:
        """Unload the script, a crashed run's too, reporting whether KWin answered."""
        self.engaged = False
        return unload_script(HOME_PLUGIN_NAME, self._call)


class KWinPin:
    """Holds a strict break's windows in front, and where the member is, for its length."""

    def __init__(self, app_id, caller=None, script_path=None, focus_caption="",
                 wall_prefix="", wall_outputs=None, refuse_switch=False):
        self.app_id = app_id
        self.focus_caption = str(focus_caption or "")
        self.wall_prefix = str(wall_prefix or "")
        self.wall_outputs = dict(wall_outputs or {})
        self.refuse_switch = bool(refuse_switch)
        self._call = caller or _session_caller
        self.script_path = script_path or files.cache_path("strict-break.js")
        self.release_path = _release_path(self.script_path)
        self.engaged = False

    def engage(self, focus_caption=None, wall_outputs=None) -> bool:
        if focus_caption is not None:
            self.focus_caption = str(focus_caption)
        if wall_outputs is not None:
            self.wall_outputs = dict(wall_outputs)

        self.engaged = False
        if not self.app_id:
            log.debug("No app id to hold: not asking KWin for anything.")
            return False
        if not unload_script(PLUGIN_NAME, self._call):
            log.debug("No KWin scripting interface: no script holds the break.")
            return False

        self.engaged = _reported(*_start(
            self._call, script_source(self.app_id, self.focus_caption, self.wall_prefix,
                                      self.wall_outputs, self.refuse_switch),
            self.script_path, PLUGIN_NAME))
        return self.engaged

    def release(self, standing=False) -> bool:
        """Unload the script, then run the undo once, leaving a standing wall in front."""
        self.engaged = False
        answered = unload_script(PLUGIN_NAME, self._call)
        if answered and self.app_id and _reported(*_start(
                self._call, release_source(self.app_id, self.wall_prefix, standing),
                self.release_path, PLUGIN_NAME)):
            unload_script(PLUGIN_NAME, self._call)
        return answered
