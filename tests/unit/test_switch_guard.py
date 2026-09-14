import pytest

from src.desktop.switch_guard import (ACTIVITIES_PATH, ACTIVITIES_SERVICE,
                                      DESKTOPS, DESKTOPS_PATH, KWIN,
                                      PROPERTIES, SwitchGuard)

pytestmark = pytest.mark.exact


class Session:
    def __init__(self, desktop="desktop-one", activity="activity-one",
                 refuse=(), writable=True):
        self.desktop = desktop
        self.activity = activity
        self.refuse = set(refuse)
        self.writable = writable
        self.calls = []
        self.listening = []

    def __call__(self, service, path, interface, method, *args):
        self.calls.append((path, method) + tuple(str(a) for a in args))
        if interface in self.refuse or path in self.refuse:
            return False, None
        if method == "Get":
            wanted = args[-1]
            if wanted == "current":
                return (True, self.desktop) if self.desktop else (False, None)
            if wanted == "currentDesktop":
                return (True, self.desktop) if self.desktop else (False, None)
            return False, None
        if method == "CurrentActivity":
            return (True, self.activity) if self.activity else (True, "")
        if method in ("Set", "SetCurrentActivity", "setCurrentDesktop"):
            return (True, None) if self.writable else (False, None)
        return True, None

    def listen(self, service, path, interface, signal, slot):
        self.listening.append((signal, slot))
        return True

    def deafen(self, service, path, interface, signal, slot):
        self.listening = [row for row in self.listening if row[0] != signal]
        return True

    @property
    def signals(self):
        return [signal for signal, _slot in self.listening]

    def wrote(self, method):
        return [call for call in self.calls if call[1] == method]


def guard_on(session):
    return SwitchGuard(caller=session, subscriber=session.listen,
                       unsubscriber=session.deafen)


class TestWhatItHoldsOnTo:
    def test_it_remembers_the_desktop_and_the_activity(self):
        session = Session()
        guard = guard_on(session)

        assert guard.hold() is True
        assert guard.held_desktop == "desktop-one"
        assert guard.held_activity == "activity-one"

    def test_it_reads_them_through_the_managers_own_interfaces(self):
        session = Session()

        guard_on(session).hold()

        assert (DESKTOPS_PATH, "Get", DESKTOPS, "current") in session.calls
        assert (ACTIVITIES_PATH, "CurrentActivity") in session.calls

    def test_it_listens_for_both_kinds_of_move(self):
        session = Session()

        guard_on(session).hold()

        assert session.signals == ["currentChanged", "CurrentActivityChanged"]

    def test_letting_go_stops_listening_and_forgets(self):
        session = Session()
        guard = guard_on(session)
        guard.hold()

        guard.release()

        assert session.signals == []
        assert guard.holding is False
        assert guard.held_desktop is None

    def test_holding_twice_does_not_listen_twice(self):
        session = Session()
        guard = guard_on(session)

        guard.hold()
        guard.hold()

        assert session.signals == ["currentChanged", "CurrentActivityChanged"]


class TestPuttingItBack:
    @pytest.fixture
    def held(self):
        session = Session()
        guard = guard_on(session)
        guard.hold()
        return guard, session

    def test_a_desktop_change_is_written_straight_back(self, held):
        guard, session = held

        guard._desktop_changed("desktop-two")

        written = session.wrote("Set")
        assert written
        assert written[0][:4] == (DESKTOPS_PATH, "Set", DESKTOPS, "current")
        assert guard.refusals == 1

    def test_an_activity_change_is_too(self, held):
        guard, session = held

        guard._activity_changed("activity-two")

        assert session.wrote("SetCurrentActivity")[0][2] == "activity-one"
        assert guard.refusals == 1

    def test_the_one_we_are_already_on_is_left_alone(self, held):
        guard, session = held

        guard._desktop_changed("desktop-one")
        guard._activity_changed("activity-one")

        assert session.wrote("Set") == []
        assert session.wrote("SetCurrentActivity") == []
        assert guard.refusals == 0

    def test_our_own_write_does_not_answer_itself(self, held):
        guard, session = held
        seen = []

        def write_and_report_back(service, path, interface, method, *args):
            answer = session(service, path, interface, method, *args)
            if method == "Set":
                seen.append(method)
                guard._desktop_changed("desktop-two")
            return answer

        guard._call = write_and_report_back
        guard._desktop_changed("desktop-two")

        assert seen == ["Set"]
        assert guard.refusals == 1

    def test_nothing_is_written_when_it_is_not_holding(self):
        session = Session()
        guard = guard_on(session)

        guard._desktop_changed("desktop-two")

        assert session.calls == []

    def test_a_write_that_did_not_land_says_so(self, caplog):
        session = Session(writable=False)
        guard = guard_on(session)
        guard.hold()

        with caplog.at_level("WARNING"):
            guard._desktop_changed("desktop-two")

        assert "following rather than holding" in caplog.text


class TestASessionThatAnswersDifferently:
    def test_one_with_no_activities_still_refuses_the_desktop(self):
        session = Session(activity="")
        guard = guard_on(session)

        assert guard.hold() is True
        assert guard.held_activity is None
        assert session.signals == ["currentChanged"]

    def test_one_that_answers_for_neither_holds_nothing(self):
        session = Session(refuse={DESKTOPS_PATH, ACTIVITIES_PATH, "/KWin"})
        guard = guard_on(session)

        assert guard.hold() is False
        assert guard.holding is False
        assert session.signals == []

    def test_the_kwin_5_spelling_is_answered_too(self):
        session = Session(desktop=3, refuse={DESKTOPS_PATH})
        guard = guard_on(session)

        assert guard.hold() is True
        assert guard.held_desktop == 3

        guard._desktop_changed(4)

        assert session.wrote("setCurrentDesktop")[0][2] == "3"

    def test_a_property_wrapped_in_a_variant_is_unwrapped(self):
        from src.desktop.session import _unwrap

        class Wrapped:
            def variant(self):
                return "desktop-one"

        assert _unwrap(Wrapped()) == "desktop-one"
        assert _unwrap("desktop-one") == "desktop-one"


class TestItCanActuallyBeSubscribed:
    @pytest.fixture
    def guard(self, qapp):
        return SwitchGuard()

    def test_it_is_a_qobject(self, guard):
        from PyQt6.QtCore import QObject

        assert isinstance(guard, QObject)

    @pytest.mark.parametrize("slot", ["_desktop_changed", "_activity_changed"])
    def test_both_handlers_are_slots_the_bus_can_reach(self, guard, slot):
        meta = guard.metaObject()

        assert meta.indexOfSlot(f"{slot}(QString)") >= 0, slot
        assert meta.indexOfSlot(f"{slot}()") >= 0, slot


class TestWhatItReachesFor:
    def test_the_desktop_manager_and_the_activity_manager(self):
        assert KWIN == "org.kde.KWin"
        assert DESKTOPS_PATH == "/VirtualDesktopManager"
        assert ACTIVITIES_SERVICE == "org.kde.ActivityManager"
        assert PROPERTIES == "org.freedesktop.DBus.Properties"

    def test_and_it_needs_no_script_to_be_loaded(self):
        session = Session()

        guard_on(session).hold()

        assert not [call for call in session.calls if "Script" in call[1]]
