import logging

log = logging.getLogger(__name__)

CALL_TIMEOUT_MS = 1000

KWIN = "org.kde.KWin"
KWIN_PATH = "/KWin"

ACTIVITIES_SERVICE = "org.kde.ActivityManager"
ACTIVITIES_PATH = "/ActivityManager/Activities"
ACTIVITIES = "org.kde.ActivityManager.Activities"


def _unwrap(answer):
    """Return what a property read answered."""
    inner = getattr(answer, "variant", None)
    return inner() if callable(inner) else answer


def _method(service, path, interface, method, args):
    """Return the session bus, or None without one, and one method call for it."""
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage

    bus = QDBusConnection.sessionBus()
    message = QDBusMessage.createMethodCall(service, path, interface, method)
    message.setArguments(list(args))
    return (bus if bus.isConnected() else None), message


def session_call(service, path, interface, method, *args):
    from PyQt6.QtDBus import QDBus, QDBusMessage

    bus, message = _method(service, path, interface, method, args)
    if bus is None:
        return False, None

    reply = bus.call(message, QDBus.CallMode.Block, CALL_TIMEOUT_MS)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        log.debug("%s.%s refused: %s", interface, method, reply.errorMessage())
        return False, None

    answered = reply.arguments()
    return True, (_unwrap(answered[0]) if answered else None)


def session_send(service, path, interface, method, *args) -> bool:
    """Hand one method to the bus and forget it."""
    bus, message = _method(service, path, interface, method, args)
    return bus is not None and bool(bus.send(message))
