#!/usr/bin/env python3

import argparse
import logging
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtDBus import QDBus, QDBusConnection, QDBusMessage

from src.desktop import activities as break_activities
from src.desktop import idle
from src.desktop import notify
from src.desktop import kwin_rules
from src.desktop import rest_positions
from src.desktop import rest_queue
from src.desktop.kwin import (HOME_PLUGIN_NAME, PLUGIN_NAME, KWinPin,
                              run_script, unload_script)
from src.domain import media
from src.profile import UserProfile


def service_is_there(bus, name):
    answer = bus.interface().isServiceRegistered(name)
    return bool(answer.value())


def report_session():
    print("session")
    for variable in ("XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "KDE_SESSION_VERSION"):
        print(f"  {variable:<20} {os.environ.get(variable, '(unset)')}")

    for label, group in (("break walls rule", kwin_rules.REST_GROUP),
                         ("window home rule", kwin_rules.WINDOW_GROUP)):
        carried = kwin_rules.carried(group)
        print(f"  {label:<20} "
              f"{'[' + group + '] in ' + kwin_rules.DEFAULT_PATH if carried else '(none)'}")


def report_idle(profile):
    """Report whether this session answers how long the member has been away."""
    threshold = profile.number("timer", "idle_pause_secs", 300, low=0.0)
    print(f"\nidle time  (the timer stops itself past {threshold:.0f}s)")
    print("  leave the keyboard alone and watch it climb; touch it and watch it drop")
    for _ in range(6):
        away = idle.idle_ms()
        print("  no answer: the clock will keep running during an absence"
              if away is None else f"  {away / 1000:>8.1f} s")
        if away is None:
            return
        time.sleep(1)


def report_window(bus):
    """Report what KWin calls a window, and where it has it."""
    print("\nclick a Traker window...")
    message = QDBusMessage.createMethodCall(
        "org.kde.KWin", "/KWin", "org.kde.KWin", "queryWindowInfo")
    reply = bus.call(message, QDBus.CallMode.Block, 60000)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        print(f"  refused: {reply.errorMessage()}")
        return
    info = reply.arguments()[0] or {}
    for key in ("resourceClass", "resourceName", "caption", "desktopFile"):
        print(f"  {key:<20} {info.get(key, '(absent)')}")
    for key in ("x", "y", "width", "height", "desktops", "activities",
                "fullScreen", "onAllDesktops", "keepAbove", "minimized"):
        print(f"  {key:<20} {info.get(key, '(absent)')}")

PROBE = """
(function () {
    var target = "__APP_ID__";

    function windows() {
        if (typeof workspace.windowList === "function") return workspace.windowList();
        if (typeof workspace.clientList === "function") return workspace.clientList();
        return [];
    }

    function ours(w) {
        var id = String((w && (w.resourceClass || w.resourceName)) || "").toLowerCase();
        return target !== "" && id.indexOf(target) !== -1;
    }

    function has(thing, name) {
        try { return typeof thing[name]; } catch (e) { return "(refused)"; }
    }

    function say(line) { print("traker: probe " + line); }

    function box(geometry) {
        try {
            return geometry.x + "," + geometry.y + " "
                   + geometry.width + "x" + geometry.height;
        } catch (e) { return "(absent)"; }
    }

    function outputs() {
        try {
            if (workspace.screens && workspace.screens.length !== undefined)
                return workspace.screens;
        } catch (e) {}
        return [];
    }

    function outputOf(w) {
        try { if (w.output && w.output.name) return String(w.output.name); } catch (e) {}
        var all = outputs();
        for (var i = 0; i < all.length; i++) {
            try {
                if (box(all[i].geometry) === box(w.frameGeometry)) return String(all[i].name);
            } catch (e) {}
        }
        return "(unknown) at " + box(w.frameGeometry);
    }

    function value(w, name) {
        try {
            if (typeof w[name] === "undefined") return "(absent)";
            var answer = w[name];
            if (answer === null) return "(null)";
            if (answer && answer.length !== undefined && typeof answer !== "string")
                return "[" + answer.length + "]";
            return String(answer);
        } catch (e) { return "(refused)"; }
    }

    function names(thing, label) {
        var found = [];
        try { for (var key in thing) found.push(key); } catch (e) {}
        found.sort();
        say(label + ": " + found.length + " names");
        for (var i = 0; i < found.length; i += 12) {
            say("  " + label + "[" + i + "] " + found.slice(i, i + 12).join(" "));
        }
    }

    function reportOnce() {
        names(workspace, "workspace");
        var all = windows();
        for (var i = 0; i < all.length; i++) {
            if (ours(all[i])) { names(all[i], "window"); break; }
        }
        say("kwin names:"
            + " screens=" + has(workspace, "screens")
            + " activeScreen=" + has(workspace, "activeScreen")
            + " sendClientToScreen=" + has(workspace, "sendClientToScreen")
            + " raiseWindow=" + has(workspace, "raiseWindow")
            + " activeWindow=" + has(workspace, "activeWindow")
            + " windowList=" + has(workspace, "windowList"));

        var all = outputs();
        say("outputs: " + all.length);
        for (var i = 0; i < all.length; i++) {
            say("  output " + i + " name=" + value(all[i], "name")
                + " geometry=" + box(all[i].geometry));
        }
        try {
            say("activeScreen=" + (workspace.activeScreen && workspace.activeScreen.name
                                   ? workspace.activeScreen.name
                                   : String(workspace.activeScreen)));
        } catch (e) { say("activeScreen=(refused)"); }
    }

    function reportWindows(why) {
        var all = windows();
        var mine = [];
        for (var i = 0; i < all.length; i++) if (ours(all[i])) mine.push(all[i]);

        var here = "(absent)";
        try {
            here = (typeof workspace.currentDesktop === "object"
                    && workspace.currentDesktop !== null)
                ? String(workspace.currentDesktop.name) : String(workspace.currentDesktop);
        } catch (e) {}
        var active = "(none)";
        try {
            var it = (typeof workspace.activeWindow !== "undefined")
                ? workspace.activeWindow : workspace.activeClient;
            if (it) active = String(it.caption) + " [" + outputOf(it) + "]";
        } catch (e) {}

        say("--- " + why + ": desktop=" + here
            + " activity=" + String(workspace.currentActivity)
            + " active=" + active
            + " ours=" + mine.length);
        for (var n = 0; n < mine.length; n++) {
            var w = mine[n];
            say("  '" + String(w.caption) + "'"
                + " class=" + value(w, "resourceName")
                + " popup=" + value(w, "popupWindow")
                + " transient=" + value(w, "transient")
                + " on=" + outputOf(w)
                + " keepAbove=" + value(w, "keepAbove")
                + " onAllDesktops=" + value(w, "onAllDesktops")
                + " desktops=" + value(w, "desktops")
                + " activities=" + value(w, "activities")
                + " fullScreen=" + value(w, "fullScreen")
                + " minimized=" + value(w, "minimized")
                + " wantsInput=" + value(w, "wantsInput"));
        }
    }

    function connect(signal, handler) {
        if (signal && typeof signal.connect === "function") signal.connect(handler);
    }

    reportOnce();
    reportWindows("now");
    connect(workspace.currentDesktopChanged, function () { reportWindows("desktop changed"); });
    connect(workspace.currentActivityChanged, function () { reportWindows("activity changed"); });
    connect(workspace.windowActivated || workspace.clientActivated, function (w) {
        reportWindows("activated " + String(w && w.caption));
    });
    connect(workspace.windowAdded || workspace.clientAdded, function (w) {
        if (ours(w)) reportWindows("ours mapped: " + String(w.caption));
    });
    say("watching. switch desktop or activity now.");
})();
"""

PROBE_PLUGIN = "traker-desktop-probe"


def report_interfaces(bus):
    """Report what KWin and the activity manager offer this session."""
    for service, path in (("org.kde.KWin", "/Scripting"),
                          ("org.kde.KWin", "/VirtualDesktopManager"),
                          ("org.kde.ActivityManager", "/ActivityManager/Activities")):
        print(f"\n{service} {path}")
        message = QDBusMessage.createMethodCall(
            service, path, "org.freedesktop.DBus.Introspectable", "Introspect")
        reply = bus.call(message, QDBus.CallMode.Block, 2000)
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            print(f"  absent: {reply.errorMessage()}")
            continue
        xml = reply.arguments()[0] or ""
        for line in xml.splitlines():
            stripped = line.strip()
            if stripped.startswith(("<method", "<property", "<signal")):
                print("  " + stripped.rstrip(">").rstrip("/").strip())


def report_where_we_are(bus):
    """Report the current desktop and activity, as a client reads them."""
    from src.desktop import switch_guard

    print("\nwhere the session reports the member to be")
    guard = switch_guard.SwitchGuard()
    desktop = guard._read_desktop()
    activity = guard._read_activity()
    print(f"  desktop   {desktop if desktop is not None else '(no answer)'}")
    print(f"  activity  {activity if activity is not None else '(no answer)'}")
    print("  a break puts both back while it holds; neither needs a KWin script")


def report_screens(app_id, seconds):
    """Ask this KWin what it answers for, and watch what a switch does."""
    path = os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
        "traker", "desktop-probe.js")
    source = PROBE.replace("__APP_ID__", str(app_id).lower())

    print(f"\nasking KWin what it answers for, as app id '{app_id}'")
    took, why = run_script(source, path, PROBE_PLUGIN)
    print(f"  {why}")
    if not took:
        return

    try:
        print(f"  watching for {seconds:.0f}s. Now, while it runs:")
        print("   - switch virtual desktop and activity with the focus on the")
        print("     *primary* screen, then again with the focus on the other one")
        print("   - start a strict break first to include the walls in the list")
        time.sleep(seconds)
    finally:
        print(f"  unloaded: {unload_script(PROBE_PLUGIN)}")

    print("\nwhat it said (journalctl --user -b -g 'traker: probe'):")
    try:
        said = subprocess.run(
            ["journalctl", "--user", "-b", "-g", "traker: probe", "--no-pager",
             "-o", "cat", "-n", "400"],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  could not read the journal ({e}); read it by hand with:")
        print("  journalctl --user -b -g 'traker: probe'")
        return
    lines = [line for line in said.stdout.splitlines() if "traker: probe" in line]
    if not lines:
        print("  nothing in the journal: this KWin may log elsewhere. Try")
        print("  journalctl --user -u plasma-kwin_wayland -b | grep traker")
        return
    for line in lines:
        print("  " + line.split("traker: probe", 1)[1].strip())


def report_activities(profile):
    """Report what a break would show, in the order of its keys."""
    queue_path = rest_queue.path_for(profile)
    offers = break_activities.queued(rest_queue.read(queue_path)) \
        + break_activities.read(
            profile.get_metric("strict_break", "activities", ()) or ())
    positions = rest_positions.read(rest_positions.beside(queue_path))

    print(f"\nwhat a break could show   (queue: {queue_path})")
    if not offers:
        print("  nothing written down: a break shows its wall and no more")
        return
    for index, activity in enumerate(offers):
        stopped = positions.get(activity.path)
        print(f"  {break_activities.offer_key(index):<6} {activity.name}")
        print(f"         kind    {activity.kind}")
        print(f"         file    {activity.path}")
        print(f"         there   {'yes' if os.path.exists(activity.path) else 'NO -- nothing would show'}")
        if stopped:
            print(f"         stopped {media.how_far(stopped, break_activities.readout_of(activity.kind))}")


def report_media():
    """Report what this machine gives a break player: mpv, decoder and sinks."""
    print("== what a break would play through ==")
    try:
        import mpv
    except (ImportError, OSError) as error:
        print(f"  libmpv                    MISSING -- {error}")
        print("\n  A break will say COULD NOT PLAY on the screen until this is"
              "\n  installed. On Gentoo: media-video/mpv with USE=\"libmpv\".")
        return

    player = mpv.MPV(vo="libmpv", hwdec="auto-safe", input_default_bindings=False,
                     input_vo_keyboard=False, osc=False)
    try:
        print(f"  libmpv                    {player.mpv_version}")
        print(f"  ffmpeg                    {getattr(player, 'ffmpeg_version', '?')}")
        asked = player.hwdec
        print(f"  hwdec asked for           "
              f"{','.join(asked) if isinstance(asked, list) else asked}")
        devices = list(player.audio_device_list or ())
        print(f"  audio devices             {len(devices)}")
        for device in devices:
            name = device.get("name", "")
            print(f"    {name}")
            if device.get("description"):
                print(f"      {device['description']}")
        print("\n  The prefix on each device is the driver mpv would use for it."
              "\n  mpv picks its own, and says which in Traker's log at WARNING"
              "\n  if anything about the choice fails:"
              "\n    TRAKER_LOG_LEVEL=DEBUG uv run python src/main.py")
    finally:
        player.terminate()


def main():
    parser = argparse.ArgumentParser(description="Prove the two things a strict break asks of the desktop, on this session.")
    parser.add_argument("--release", action="store_true",
                        help="unload a leftover strict-break script, give back "
                             "what it held, and stop")
    parser.add_argument("--window", action="store_true",
                        help="ask KWin what it calls a clicked window, and where it has it")
    parser.add_argument("--activities", action="store_true",
                        help="what a break would offer to open, and whether it can")
    parser.add_argument("--media", action="store_true",
                        help="what libmpv, the decoder and the sinks are on "
                             "this machine")
    parser.add_argument("--idle", action="store_true",
                        help="whether this session reports how long the member has "
                             "been away, which is what stops the timer")
    parser.add_argument("--screens", action="store_true",
                        help="what KWin answers for outputs and windows, and what "
                             "a desktop or activity switch does to them")
    parser.add_argument("--engage-secs", type=float, default=8.0,
                        help="how long to hold, leaving time to try an escape (default 8)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG, format="  [%(name)s] %(message)s")

    app = QCoreApplication(sys.argv)
    QCoreApplication.setApplicationName("Traker")

    if args.media:
        report_media()
        return 0

    bus = QDBusConnection.sessionBus()

    if not bus.isConnected():
        print("no session bus: a break here will hold one desktop and say nothing")
        return 1

    profile = UserProfile()
    app_id = profile.get_metric("strict_break", "app_id", "") or "Traker"
    pin = KWinPin(app_id)

    if args.release:
        print(f"unloading {PLUGIN_NAME} and giving back what it held: "
              f"{pin.release()}")
        print(f"taking Traker's window rules out of {kwin_rules.DEFAULT_PATH}: "
              f"{kwin_rules.prune()}")
        print(f"unloading {HOME_PLUGIN_NAME}: "
              f"{unload_script(HOME_PLUGIN_NAME)}")
        return 0

    report_session()

    print("\nservices")
    for name in ("org.kde.KWin", "org.freedesktop.Notifications",
                 "org.freedesktop.ScreenSaver"):
        print(f"  {name:<34} {'there' if service_is_there(bus, name) else 'ABSENT'}")

    if args.idle:
        report_idle(profile)

    if args.window:
        report_window(bus)

    if args.activities:
        report_activities(profile)

    if args.screens:
        report_interfaces(bus)
        report_where_we_are(bus)
        report_screens(app_id, args.engage_secs * 4)
        return 0

    print("\nthe warning (listen)")
    sent = notify.notify(
        "Strict break in 60 s",
        "Traker takes every screen when focus ends. Hold ESC for 10 s to leave one.",
        sound_name=profile.get_metric("strict_break", "sound_name", "dialog-warning"),
        sound_file=profile.get_metric("strict_break", "sound_file", ""),
    )
    print(f"  sent: {sent}   (shown but silent means [strict_break] sound_file is unset)")

    print(f"\nholding for {args.engage_secs:.0f}s as app id '{app_id}'")
    print("  switch desktop or activity now: the Traker window should follow")
    print("  and so should every wall -- the covered screen that stays behind")
    print("  is the escape this is here to catch, not the current one")
    if not pin.engage():
        print("  KWin did not take the script -- a break will hold one desktop only")
        return 1

    print(f"  engaged, script at {pin.script_path}")
    time.sleep(args.engage_secs)
    print(f"  released: {pin.release()}")
    print("\nkwin's own view of the script: journalctl --user -b -g 'traker:'")
    print("  one \'holding <caption>\' line per window of this application,")
    print("  saying what Plasma took: everyDesktop=false is a window only")
    print("  *followed* onto each desktop on a switch, and (absent) is a name")
    print("  it does not answer for at all. In a real break wall=false marks")
    print("  the one window that is not the break: Traker's own, which keeps")
    print("  neither keepAbove nor the focus, because fullscreen and focused")
    print("  outranks kept-above")
    return 0


if __name__ == "__main__":
    sys.exit(main())
