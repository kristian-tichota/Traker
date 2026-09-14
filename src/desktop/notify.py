import logging

log = logging.getLogger(__name__)

SERVICE = "org.freedesktop.Notifications"
OBJECT = "/org/freedesktop/Notifications"
INTERFACE = "org.freedesktop.Notifications"

APP_NAME = "Traker"
DESKTOP_ENTRY = "Traker"


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
        APP_NAME, _replaces_nothing(), icon, summary, body,
        _no_actions(), hints, int(timeout_ms),
    ])

    sent = bus.send(message)
    if not sent:
        log.debug("The notification could not be put on the bus.")
    return sent


# PyQt marshals by Python type: a plain int goes out as "i" where Notify's signature says "u".


def _replaces_nothing():
    """Return Notify's replaces_id, a u."""
    from PyQt6.QtCore import QMetaType
    from PyQt6.QtDBus import QDBusArgument

    return QDBusArgument(0, QMetaType.Type.UInt.value)


def _no_actions():
    """Return Notify's actions, an as."""
    from PyQt6.QtCore import QMetaType
    from PyQt6.QtDBus import QDBusArgument

    return QDBusArgument([], QMetaType.Type.QStringList.value)
