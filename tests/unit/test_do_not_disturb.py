import pytest
from PyQt6.QtDBus import QDBusArgument

from src.desktop.notify import DoNotDisturb

pytestmark = pytest.mark.exact


class NotificationServer:
    def __init__(self, cookie=5):
        self.cookie = cookie
        self.calls = []

    def __call__(self, service, path, interface, method, *args):
        self.calls.append((method,) + args)
        if method == "Inhibit":
            return (True, self.cookie) if self.cookie else (False, None)
        return True, None


def test_holding_twice_asks_once_and_letting_go_hands_the_cookie_back_once():
    server = NotificationServer()
    quiet = DoNotDisturb(caller=server)

    assert quiet.hold() and quiet.hold()
    quiet.release()
    quiet.release()

    assert [call[0] for call in server.calls] == ["Inhibit", "UnInhibit"]
    assert isinstance(server.calls[1][1], QDBusArgument)
    assert quiet.holding is False


def test_a_server_without_inhibitions_holds_nothing_and_is_told_nothing():
    server = NotificationServer(cookie=None)
    quiet = DoNotDisturb(caller=server)

    assert quiet.hold() is False
    quiet.release()

    assert [call[0] for call in server.calls] == ["Inhibit"]
