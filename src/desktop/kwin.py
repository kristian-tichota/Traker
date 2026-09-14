import json
import logging
import os

log = logging.getLogger(__name__)

SERVICE = "org.kde.KWin"
OBJECT = "/Scripting"
INTERFACE = "org.kde.kwin.Scripting"

PLUGIN_NAME = "traker-strict-break"


def _default_script_path():
    """A real on-disk path for the script, outliving the call."""
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache, "traker", "strict-break.js")


def _home_script_path():
    """Beside the break's, for the same reason: KWin reads a script off disk."""
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache, "traker", "window-home.js")


def _release_path(script_path):
    """The undo script's path, beside the script it undoes."""
    root, extension = os.path.splitext(script_path)
    return f"{root}-release{extension or '.js'}"

_SHARED = """
    var target = "__APP_ID__";
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

    function allDesktops() {
        try {
            var all = workspace.desktops;
            if (all && all.length) return all;
        } catch (e) {}
        return null;
    }

    function allActivities() {
        try {
            var all = workspace.activities;
            if (all && all.length) return all;
        } catch (e) {}
        return null;
    }

    function onEveryDesktop(w) {
        try { if (w.onAllDesktops === true) return true; } catch (e) {}
        try {
            if (typeof w.desktops === "undefined") return false;
            if (w.desktops.length === 0) return true;
            var all = allDesktops();
            return all !== null && w.desktops.length >= all.length;
        } catch (e) {}
        return false;
    }

    function onEveryActivity(w) {
        try {
            if (typeof w.activities === "undefined") return true;
            if (w.activities.length === 0) return true;
            var all = allActivities();
            return all !== null && w.activities.length >= all.length;
        } catch (e) {}
        return true;
    }

    function captionKey(w) {
        var caption = String(w.caption || "");
        if (wallOutputs[caption] !== undefined) return caption;
        var deduped = caption.replace(/ <[0-9]+>$/, "");
        return wallOutputs[deduped] !== undefined ? deduped : caption;
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

    function sameBox(one, two) {
        try {
            return one && two && one.x === two.x && one.y === two.y
                   && one.width === two.width && one.height === two.height;
        } catch (e) {}
        return false;
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

    function describe(w, name) {
        try {
            if (typeof w[name] === "undefined") return "(absent)";
            return String(w[name]);
        } catch (e) {}
        return "(refused)";
    }
"""

_SCRIPT = """// Traker: keep a strict break where the member is.
(function () {""" + _SHARED + """
    var wanted = __CAPTION__;
    var refuseSwitch = __REFUSE__;
    var holding = false;
    var adjusting = false;

    function active() {
        if (typeof workspace.activeWindow !== "undefined") return workspace.activeWindow;
        return workspace.activeClient;
    }

    function ours() { return windows().filter(isBreak); }

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

    function holdEverywhere(w) {
        if (!onEveryDesktop(w)) call(w, "setOnAllDesktops", true);
        if (!onEveryDesktop(w)) { try { w.onAllDesktops = true; } catch (e) {} }
        if (!onEveryDesktop(w)) { try { w.desktops = []; } catch (e) {} }
        if (!onEveryDesktop(w)) {
            var desktops = allDesktops();
            if (desktops !== null) { try { w.desktops = desktops; } catch (e) {} }
        }

        if (!onEveryActivity(w)) call(w, "setOnAllActivities", true);
        if (!onEveryActivity(w)) call(w, "setOnActivities", []);
        if (!onEveryActivity(w)) { try { w.activities = []; } catch (e) {} }
        if (!onEveryActivity(w)) {
            var activities = allActivities();
            if (activities !== null) { try { w.activities = activities; } catch (e) {} }
        }
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
        holdEverywhere(w);
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
        var desktops = allDesktops();
        var activities = allActivities();
        print("traker: holding '" + String(w.caption || "") + "'"
              + " class=" + describe(w, "resourceName")
              + " popup=" + describe(w, "popupWindow")
              + " wall=" + isWall(w)
              + " of=" + (desktops === null ? "?" : desktops.length) + "desktops/"
              + (activities === null ? "?" : activities.length) + "activities"
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
        if (!w) return;
        try {
            if (typeof workspace.activeWindow !== "undefined") workspace.activeWindow = w;
            else workspace.activeClient = w;
        } catch (e) {}
        try {
            if (typeof workspace.raiseWindow === "function") workspace.raiseWindow(w);
        } catch (e) {}
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

            var current = active();
            if (current && isWall(current)) return;
            activate(front);
        } finally {
            holding = false;
        }
    }

    var heldDesktop = null;
    var heldActivity = null;
    var restoring = false;

    function remember() {
        try { heldDesktop = workspace.currentDesktop; } catch (e) {}
        try { heldActivity = workspace.currentActivity; } catch (e) {}
    }

    var said = {};

    function refuse(what, held) {
        if (!refuseSwitch || restoring || held === null) return false;
        var now = null;
        try { now = workspace[what]; } catch (e) { return false; }
        if (now === held) return false;
        restoring = true;
        try { workspace[what] = held; } catch (e) {}
        restoring = false;
        if (!said[what]) {
            said[what] = true;
            var back = false;
            try { back = workspace[what] === held; } catch (e) {}
            print("traker: refusing " + what + " changes during a break, back=" + back);
        }
        return true;
    }

    function onDesktopChanged() {
        refuse("currentDesktop", heldDesktop);
        hold();
    }

    function onActivityChanged() {
        refuse("currentActivity", heldActivity);
        hold();
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

    function connect(signal, handler) {
        if (signal && typeof signal.connect === "function") signal.connect(handler);
    }

    connect(workspace.windowAdded || workspace.clientAdded, onAdded);
    connect(workspace.windowActivated || workspace.clientActivated, hold);
    connect(workspace.currentDesktopChanged, onDesktopChanged);
    connect(workspace.currentActivityChanged, onActivityChanged);
    connect(workspace.screensChanged, hold);
    connect(workspace.numberScreensChanged, hold);

    var present = windows();
    for (var n = 0; n < present.length; n++) {
        if (isBreak(present[n])) watch(present[n]);
    }
    remember();
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

HOME_PLUGIN_NAME = "traker-window-home"

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

    function connect(signal, handler) {
        try { if (signal && typeof signal.connect === "function") signal.connect(handler); }
        catch (e) {}
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
    """What KWin will have called this application's windows."""
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtGui import QGuiApplication

    entry = QGuiApplication.desktopFileName() or ""
    if entry.endswith(".desktop"):
        entry = entry[:-len(".desktop")]
    return entry or QCoreApplication.applicationName() or ""


def _fill(template, app_id, focus_caption="", wall_prefix="",
          wall_outputs=None, refuse_switch=False, output="", standing=False):
    """One substitution for every script here, so they name one application."""
    return (template
            .replace("__APP_ID__", str(app_id).lower())
            .replace("__CAPTION__", json.dumps(str(focus_caption or "")))
            .replace("__WALL__", json.dumps(str(wall_prefix or "")))
            .replace("__WALLS__", json.dumps(dict(wall_outputs or {})))
            .replace("__REFUSE__", "true" if refuse_switch else "false")
            .replace("__OUTPUT__", json.dumps(str(output or "")))
            .replace("__STANDING__", "true" if standing else "false"))


def script_source(app_id, focus_caption="", wall_prefix="", wall_outputs=None,
                  refuse_switch=False):
    """The script KWin is asked to run, with this session's names in it."""
    return _fill(_SCRIPT, app_id, focus_caption, wall_prefix, wall_outputs,
                 refuse_switch)


def home_source(app_id, caption, output):
    """The script that keeps the application's own window on one output."""
    return _fill(_HOME_SCRIPT, app_id, focus_caption=caption, output=output)


def release_source(app_id, wall_prefix="", standing=False):
    """The undo, naming the same application; a wall still up stays in front."""
    return _fill(_RELEASE_SCRIPT, app_id, wall_prefix=wall_prefix,
                 standing=standing)

CALL_TIMEOUT_MS = 1000


def _session_caller(method, *args):
    """Call one org.kde.kwin.Scripting method."""
    from PyQt6.QtDBus import QDBus, QDBusConnection, QDBusMessage

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False, None

    message = QDBusMessage.createMethodCall(SERVICE, OBJECT, INTERFACE, method)
    if args:
        message.setArguments(list(args))

    reply = bus.call(message, QDBus.CallMode.Block, CALL_TIMEOUT_MS)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        log.debug("KWin refused %s: %s", method, reply.errorMessage())
        return False, None

    answered = reply.arguments()
    return True, (answered[0] if answered else None)


def run_script(source, path, plugin=PLUGIN_NAME, caller=None):
    """Write one script, load it and start it."""
    call = caller or _session_caller
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
    except OSError as e:
        return False, f"could not write {path}: {e}"

    reached, _ = call("unloadScript", plugin)
    if not reached:
        return False, ("no org.kde.kwin.Scripting on this session: KWin did "
                       "not answer unloadScript at all")

    reached, script_id = call("loadScript", path, plugin)
    if not reached:
        return False, f"KWin refused loadScript for {path}"
    if isinstance(script_id, int) and script_id < 0:
        return False, (f"KWin answered {script_id} for loadScript, which means "
                       f"a script called {plugin!r} is already loaded")

    reached, _ = call("start")
    if not reached:
        call("unloadScript", plugin)
        return False, "KWin loaded the script and refused to start it"
    return True, f"loaded as {plugin} (id {script_id})"


def unload_script(plugin=PLUGIN_NAME, caller=None) -> bool:
    """Drop a loaded script by name."""
    reached, _ = (caller or _session_caller)("unloadScript", plugin)
    return reached


def release_stale_hold() -> bool:
    """Drop a script a killed client left behind."""
    reached, _ = _session_caller("unloadScript", PLUGIN_NAME)
    return reached


class WindowScreen:
    """Keeps the application's own window on one named output, for the session."""

    def __init__(self, app_id, caption, output, caller=None, script_path=None):
        self.app_id = str(app_id or "")
        self.caption = str(caption or "")
        self.output = str(output or "").strip()
        self._call = caller or _session_caller
        self.script_path = script_path or _home_script_path()
        self._engaged = False

    @property
    def engaged(self) -> bool:
        return self._engaged

    def engage(self) -> bool:
        """Load the script."""
        # A script KWin loaded for a client that has died stays loaded; this also probes for KWin.
        reached, _ = self._call("unloadScript", HOME_PLUGIN_NAME)
        self._engaged = False
        if not reached:
            log.debug("No KWin scripting interface: the window stays on "
                      "whatever output the compositor gave it.")
            return False

        if not (self.app_id and self.caption and self.output):
            return False

        source = home_source(self.app_id, self.caption, self.output)
        try:
            os.makedirs(os.path.dirname(self.script_path), exist_ok=True)
            with open(self.script_path, "w", encoding="utf-8") as f:
                f.write(source)
        except OSError as e:
            log.warning("Could not write %s: %s", self.script_path, e)
            return False

        reached, script_id = self._call("loadScript", self.script_path,
                                        HOME_PLUGIN_NAME)
        if not reached:
            return False
        if isinstance(script_id, int) and script_id < 0:
            log.warning("KWin would not load %s.", self.script_path)
            return False

        reached, _ = self._call("start")
        if not reached:
            self._call("unloadScript", HOME_PLUGIN_NAME)
            return False

        self._engaged = True
        log.info("KWin is keeping Traker's window on %s.", self.output)
        return True

    def release(self) -> bool:
        """Unload it."""
        reached, _ = self._call("unloadScript", HOME_PLUGIN_NAME)
        self._engaged = False
        return reached


class KWinPin:
    """Holds a strict break on every desktop and activity, for its length."""

    def __init__(self, app_id, caller=None, script_path=None, focus_caption="",
                 wall_prefix="", wall_outputs=None, refuse_switch=False):
        self.app_id = app_id
        self.focus_caption = str(focus_caption or "")
        self.wall_prefix = str(wall_prefix or "")
        self.wall_outputs = dict(wall_outputs or {})
        self.refuse_switch = bool(refuse_switch)
        self._call = caller or _session_caller
        self.script_path = script_path or _default_script_path()
        self.release_path = _release_path(self.script_path)
        self._engaged = False

    @property
    def engaged(self) -> bool:
        return self._engaged

    def engage(self, focus_caption=None, wall_outputs=None) -> bool:
        """Load the script."""
        if focus_caption is not None:
            self.focus_caption = str(focus_caption)
        if wall_outputs is not None:
            self.wall_outputs = dict(wall_outputs)

        if not self.app_id:
            log.debug("No app id to hold: not asking KWin for anything.")
            return False

        if not self._unload():
            log.debug("No KWin scripting interface: the break holds one desktop only.")
            return False

        self._engaged = False

        if not self._write(self.script_path,
                           script_source(self.app_id, self.focus_caption,
                                         self.wall_prefix, self.wall_outputs,
                                         self.refuse_switch)):
            return False

        reached, script_id = self._call("loadScript", self.script_path, PLUGIN_NAME)
        if not reached:
            return False
        if isinstance(script_id, int) and script_id < 0:
            log.warning("KWin would not load %s.", self.script_path)
            return False

        reached, _ = self._call("start")
        if not reached:
            self._unload()
            return False

        self._engaged = True
        log.info("KWin is holding the strict break on every desktop.")
        return True

    def release(self, standing=False) -> bool:
        """Unload the script, then give back what it held."""
        answered = self._unload()
        self._engaged = False
        if answered:
            self._give_back(standing)
        return answered

    def _give_back(self, standing=False) -> bool:
        """Run the undo once, leaving a wall that is still up in front."""
        if not self.app_id:
            return False

        if not self._write(self.release_path,
                           release_source(self.app_id, self.wall_prefix, standing)):
            return False

        reached, script_id = self._call("loadScript", self.release_path, PLUGIN_NAME)
        if not reached:
            return False
        if isinstance(script_id, int) and script_id < 0:
            log.warning("KWin would not load %s: a window it held keeps the "
                        "properties the break gave it.", self.release_path)
            return False

        reached, _ = self._call("start")
        self._unload()
        return reached

    def _unload(self) -> bool:
        """Whether KWin was reached."""
        reached, _ = self._call("unloadScript", PLUGIN_NAME)
        return reached

    def _write(self, path, source) -> bool:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(source)
        except OSError as e:
            log.warning("Could not write the strict-break script %s: %s", path, e)
            return False
        return True
