import logging

from PyQt6.QtCore import QObject, pyqtSlot

from src.desktop.session import (ACTIVITIES, ACTIVITIES_PATH, ACTIVITIES_SERVICE, KWIN,
                                 KWIN_PATH, session_call)

log = logging.getLogger(__name__)

DESKTOPS_PATH = "/VirtualDesktopManager"
DESKTOPS = "org.kde.KWin.VirtualDesktopManager"

PROPERTIES = "org.freedesktop.DBus.Properties"

DESKTOP_CHANGED = (KWIN, DESKTOPS_PATH, DESKTOPS, "currentChanged")
ACTIVITY_CHANGED = (ACTIVITIES_SERVICE, ACTIVITIES_PATH, ACTIVITIES, "CurrentActivityChanged")

_session_call = session_call


def _subscribe(service, path, interface, signal, slot) -> bool:
    from PyQt6.QtDBus import QDBusConnection

    bus = QDBusConnection.sessionBus()
    return bus.isConnected() and bool(bus.connect(service, path, interface, signal, slot))


def _unsubscribe(service, path, interface, signal, slot) -> bool:
    from PyQt6.QtDBus import QDBusConnection

    bus = QDBusConnection.sessionBus()
    return bus.isConnected() and bool(bus.disconnect(service, path, interface, signal, slot))


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
        self.holding = False
        self._restoring = False
        self.refusals = 0

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
            listening |= self._subscribe(*DESKTOP_CHANGED, self._desktop_changed)
        if self.held_activity is not None:
            listening |= self._subscribe(*ACTIVITY_CHANGED, self._activity_changed)

        self.holding = bool(listening)
        if self.holding:
            log.info("A strict break is refusing desktop and activity changes.")
        return self.holding

    def release(self):
        """Stop reversing switches."""
        if self.holding and self.held_desktop is not None:
            self._unsubscribe(*DESKTOP_CHANGED, self._desktop_changed)
        if self.holding and self.held_activity is not None:
            self._unsubscribe(*ACTIVITY_CHANGED, self._activity_changed)
        self.holding = False
        self.held_desktop = None
        self.held_activity = None
        self.refusals = 0

    @pyqtSlot()
    @pyqtSlot(str)
    def _desktop_changed(self, which=None):
        """Handle KWin reporting a desktop change."""
        self._put_back(which, self.held_desktop, self._write_desktop, "desktop")

    @pyqtSlot()
    @pyqtSlot(str)
    def _activity_changed(self, which=None):
        """Handle the activity manager reporting an activity change."""
        self._put_back(which, self.held_activity, self._write_activity, "activity")

    def _put_back(self, which, where, write, what):
        if not self.holding or self._restoring or where is None:
            return
        if which is not None and str(which) == str(where):
            return
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
                                     KWIN, "currentDesktop")
        return answer if reached else None

    def _write_desktop(self, where) -> bool:
        from PyQt6.QtDBus import QDBusVariant

        if isinstance(where, str):
            reached, _ = self._call(KWIN, DESKTOPS_PATH, PROPERTIES, "Set",
                                    DESKTOPS, "current", QDBusVariant(where))
            if reached:
                return True
        reached, _ = self._call(KWIN, KWIN_PATH, KWIN, "setCurrentDesktop", where)
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
