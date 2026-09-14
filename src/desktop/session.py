import logging

log = logging.getLogger(__name__)

CALL_TIMEOUT_MS = 1000


def _unwrap(answer):
    """What a property read actually answered."""
    inner = getattr(answer, "variant", None)
    return inner() if callable(inner) else answer


def session_call(service, path, interface, method, *args):
    """Call one method."""
    from PyQt6.QtDBus import QDBus, QDBusConnection, QDBusMessage

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False, None

    message = QDBusMessage.createMethodCall(service, path, interface, method)
    if args:
        message.setArguments(list(args))

    reply = bus.call(message, QDBus.CallMode.Block, CALL_TIMEOUT_MS)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        log.debug("%s.%s refused: %s", interface, method, reply.errorMessage())
        return False, None

    answered = reply.arguments()
    return True, (_unwrap(answered[0]) if answered else None)


def session_send(service, path, interface, method, *args) -> bool:
    """Hand one method to the bus and forget it."""
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False

    message = QDBusMessage.createMethodCall(service, path, interface, method)
    if args:
        message.setArguments(list(args))
    return bool(bus.send(message))
