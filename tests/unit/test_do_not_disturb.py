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


class Owners:
    def __init__(self):
        self.slot = None

    def __call__(self, slot):
        self.slot = slot
        return self


def test_holding_twice_asks_once_and_letting_go_hands_the_cookie_back_once():
    server = NotificationServer()
    quiet = DoNotDisturb(caller=server, watcher=Owners())

    assert quiet.hold() and quiet.hold()
    quiet.release()
    quiet.release()

    assert [call[0] for call in server.calls] == ["Inhibit", "UnInhibit"]
    assert isinstance(server.calls[1][1], QDBusArgument)
    assert quiet.holding is False


def test_a_server_without_inhibitions_holds_nothing_and_is_told_nothing():
    server = NotificationServer(cookie=None)
    quiet = DoNotDisturb(caller=server, watcher=Owners())

    assert quiet.hold() is False
    quiet.release()

    assert [call[0] for call in server.calls] == ["Inhibit"]


def test_a_server_replaced_mid_break_is_asked_again_and_never_handed_the_old_cookie():
    server, owners = NotificationServer(), Owners()
    quiet = DoNotDisturb(caller=server, watcher=owners)
    quiet.hold()

    owners.slot("")
    assert quiet.holding is False
    server.cookie = 1
    owners.slot(":1.9")
    assert quiet.cookie == 1

    quiet.release()
    owners.slot(":1.12")

    assert [call[0] for call in server.calls] == ["Inhibit", "Inhibit", "UnInhibit"]
    assert quiet.holding is False
