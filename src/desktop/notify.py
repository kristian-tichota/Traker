import logging

from src.desktop.session import session_call

log = logging.getLogger(__name__)

SERVICE = "org.freedesktop.Notifications"
OBJECT = "/org/freedesktop/Notifications"
INTERFACE = "org.freedesktop.Notifications"

APP_NAME = "Traker"
DESKTOP_ENTRY = "Traker"

HOLD_REASON = "strict break"

_session_call = session_call


def notify(summary, body, *, timeout_ms=15000,
           sound_name="dialog-warning", sound_file="", icon="clock"):
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        log.debug("No session bus: nothing to warn on.")
        return False

    hints = {"desktop-entry": DESKTOP_ENTRY}
    if sound_name:
        hints["sound-name"] = sound_name
    if sound_file:
        hints["sound-file"] = sound_file

    message = QDBusMessage.createMethodCall(SERVICE, OBJECT, INTERFACE, "Notify")
    message.setArguments([
        APP_NAME, _unsigned(0), icon, summary, body,
        _no_actions(), hints, int(timeout_ms),
    ])

    sent = bus.send(message)
    if not sent:
        log.debug("The notification could not be put on the bus.")
    return sent


class DoNotDisturb:
    """Holds the session's Do Not Disturb as an inhibition of the notification server."""

    def __init__(self, caller=None):
        self._call = caller or _session_call
        self.cookie = None

    @property
    def holding(self) -> bool:
        return self.cookie is not None

    def hold(self) -> bool:
        """Ask the notification server to hold every notification back."""
        if self.cookie is not None:
            return True
        reached, cookie = self._call(SERVICE, OBJECT, INTERFACE, "Inhibit",
                                     DESKTOP_ENTRY, HOLD_REASON, {})
        if not reached or not cookie:
            log.info("%s takes no inhibition: notifications still arrive "
                     "during a break.", SERVICE)
            return False
        self.cookie = int(cookie)
        log.info("A strict break is holding notifications back.")
        return True

    def release(self):
        """Let notifications through again."""
        if self.cookie is None:
            return
        cookie, self.cookie = self.cookie, None
        reached, _ = self._call(SERVICE, OBJECT, INTERFACE, "UnInhibit",
                                _unsigned(cookie))
        if not reached:
            log.warning("%s did not end its inhibition; notifications stay "
                        "held back until Traker exits.", SERVICE)


# Workaround: PyQt marshals a plain int as "i" where the interface declares "u".
def _unsigned(value):
    """Return value as a D-Bus u."""
    from PyQt6.QtCore import QMetaType
    from PyQt6.QtDBus import QDBusArgument

    return QDBusArgument(int(value), QMetaType.Type.UInt.value)


def _no_actions():
    """Return Notify's actions, an as."""
    from PyQt6.QtCore import QMetaType
    from PyQt6.QtDBus import QDBusArgument

    return QDBusArgument([], QMetaType.Type.QStringList.value)
