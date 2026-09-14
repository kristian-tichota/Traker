import logging

from PyQt6.QtCore import QObject, pyqtSlot

from src.desktop.session import session_call

log = logging.getLogger(__name__)

KWIN = "org.kde.KWin"
DESKTOPS_PATH = "/VirtualDesktopManager"
DESKTOPS = "org.kde.KWin.VirtualDesktopManager"
KWIN_PATH = "/KWin"
KWIN_IFACE = "org.kde.KWin"

ACTIVITIES_SERVICE = "org.kde.ActivityManager"
ACTIVITIES_PATH = "/ActivityManager/Activities"
ACTIVITIES = "org.kde.ActivityManager.Activities"

PROPERTIES = "org.freedesktop.DBus.Properties"

_session_call = session_call


def _subscribe(service, path, interface, signal, slot) -> bool:
    from PyQt6.QtDBus import QDBusConnection

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    return bool(bus.connect(service, path, interface, signal, slot))


def _unsubscribe(service, path, interface, signal, slot) -> bool:
    from PyQt6.QtDBus import QDBusConnection

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    return bool(bus.disconnect(service, path, interface, signal, slot))


class SwitchGuard(QObject):
    """Refuses a desktop or activity change for the length of one break."""

    def __init__(self, caller=None, subscriber=None, unsubscriber=None,
                 parent=None):
        super().__init__(parent)
        self._call = caller or _session_call
        self._subscribe = subscriber or _subscribe
        self._unsubscribe = unsubscriber or _unsubscribe
        self.held_desktop = None
        self.held_activity = None
        self._holding = False
        self._restoring = False
        self.refusals = 0

    @property
    def holding(self) -> bool:
        return self._holding

    def hold(self) -> bool:
        """Remember the current desktop and start reversing switches."""
        self.release()

        self.held_desktop = self._read_desktop()
        self.held_activity = self._read_activity()
        if self.held_desktop is None and self.held_activity is None:
            log.debug("Nothing answered for the desktop or the activity: a "
                      "break holds whatever the compositor carries.")
            return False

        listening = False
        if self.held_desktop is not None:
            listening |= self._subscribe(
                KWIN, DESKTOPS_PATH, DESKTOPS, "currentChanged",
                self._desktop_changed)
        if self.held_activity is not None:
            listening |= self._subscribe(
                ACTIVITIES_SERVICE, ACTIVITIES_PATH, ACTIVITIES,
                "CurrentActivityChanged", self._activity_changed)

        self._holding = bool(listening)
        if self._holding:
            log.info("A strict break is refusing desktop and activity changes.")
        return self._holding

    def release(self):
        """Stop reversing switches."""
        if self._holding:
            if self.held_desktop is not None:
                self._unsubscribe(KWIN, DESKTOPS_PATH, DESKTOPS,
                                  "currentChanged", self._desktop_changed)
            if self.held_activity is not None:
                self._unsubscribe(ACTIVITIES_SERVICE, ACTIVITIES_PATH,
                                  ACTIVITIES, "CurrentActivityChanged",
                                  self._activity_changed)
        self._holding = False
        self.held_desktop = None
        self.held_activity = None
        self.refusals = 0

    @pyqtSlot()
    @pyqtSlot(str)
    def _desktop_changed(self, which=None):
        """Handle KWin reporting a desktop change."""
        if not self._holding or self._restoring or self.held_desktop is None:
            return
        if which is not None and str(which) == str(self.held_desktop):
            return
        self._put_back(self._write_desktop, self.held_desktop, "desktop")

    @pyqtSlot()
    @pyqtSlot(str)
    def _activity_changed(self, which=None):
        """Handle the activity manager reporting an activity change."""
        if not self._holding or self._restoring or self.held_activity is None:
            return
        if which is not None and str(which) == str(self.held_activity):
            return
        self._put_back(self._write_activity, self.held_activity, "activity")

    def _put_back(self, write, where, what):
        self._restoring = True
        try:
            took = write(where)
        finally:
            self._restoring = False
        self.refusals += 1
        if took:
            log.info("Refused a %s change during a break: back on %s.",
                     what, where)
        else:
            log.warning("Could not put the %s back during a break; the break "
                        "is following rather than holding.", what)

    def _read_desktop(self):
        """Return the current desktop, as this KWin names one."""
        reached, answer = self._call(KWIN, DESKTOPS_PATH, PROPERTIES, "Get",
                                     DESKTOPS, "current")
        if reached and answer is not None:
            return answer
        reached, answer = self._call(KWIN, KWIN_PATH, PROPERTIES, "Get",
                                     KWIN_IFACE, "currentDesktop")
        return answer if reached else None

    def _write_desktop(self, where) -> bool:
        from PyQt6.QtDBus import QDBusVariant

        if isinstance(where, str):
            reached, _ = self._call(KWIN, DESKTOPS_PATH, PROPERTIES, "Set",
                                    DESKTOPS, "current", QDBusVariant(where))
            if reached:
                return True
        reached, _ = self._call(KWIN, KWIN_PATH, KWIN_IFACE,
                                "setCurrentDesktop", where)
        return reached

    def _read_activity(self):
        """Return the current activity, or None on a session without any."""
        reached, answer = self._call(ACTIVITIES_SERVICE, ACTIVITIES_PATH,
                                     ACTIVITIES, "CurrentActivity")
        return answer if reached and answer else None

    def _write_activity(self, where) -> bool:
        reached, _ = self._call(ACTIVITIES_SERVICE, ACTIVITIES_PATH,
                                ACTIVITIES, "SetCurrentActivity", str(where))
        return reached
