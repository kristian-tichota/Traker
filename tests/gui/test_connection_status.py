import pytest

from src.database import ConnectionStatus
from src.gui.main_window import MainWindow


class FakeStatusBar:
    def __init__(self):
        self.message = ""

    def setText(self, value):
        self.message = value


class FakePulser:
    def __init__(self):
        self.colours = []

    def pulse(self, colour):
        self.colours.append(colour)


class FakeCommandLine:
    def __init__(self):
        self.cache_invalidations = 0

    def invalidate_catalog_cache(self):
        self.cache_invalidations += 1


class _RecordingCache:
    def __init__(self, log):
        self._log = log

    def invalidate(self, domains=None):
        self._log.append("all reads" if domains is None else tuple(domains))


class WindowStandIn:
    _on_connection_changed = MainWindow._on_connection_changed
    _invalidate_reads = MainWindow._invalidate_reads

    def __init__(self):
        self.status_bar = FakeStatusBar()
        self.status_pulser = FakePulser()
        self.command_line = FakeCommandLine()
        self.dirty_tabs = set()
        self.invalidated = []
        self.db = _RecordingCache(self.invalidated)

    def mark_all_tabs_stale(self):
        self.invalidated.append("all tabs")


@pytest.fixture
def window():
    return WindowStandIn()


class TestTheStatusLine:
    def test_going_offline_says_why_the_tables_are_empty(self, window):
        window._on_connection_changed(False, "Connection refused")

        assert "unreachable" in window.status_bar.message
        assert "not because there is nothing logged" in window.status_bar.message
        assert "Connection refused" in window.status_bar.message

    def test_coming_back_says_so(self, window):
        window._on_connection_changed(True, "")

        assert "reachable again" in window.status_bar.message

    def test_each_state_pulses(self, window):
        window._on_connection_changed(False, "boom")
        window._on_connection_changed(True, "")

        assert len(window.status_pulser.colours) == 2
        assert window.status_pulser.colours[0] != window.status_pulser.colours[1]


class TestTheClientDrivesIt:
    def test_a_status_flip_reaches_the_window(self, window):
        status = ConnectionStatus()
        status.on_change = window._on_connection_changed

        status.record_failure("household service is not running")

        assert "unreachable" in window.status_bar.message

        status.record_success()

        assert "reachable again" in window.status_bar.message

    def test_coming_back_refills_the_completion_cache(self, window):
        status = ConnectionStatus()
        status.on_change = window._on_connection_changed
        status.record_failure("household service is not running")

        status.record_success()

        assert window.command_line.cache_invalidations == 1

    def test_a_service_already_down_at_startup_is_still_announced(self, window):
        status = ConnectionStatus()
        status.record_failure("Connection refused")

        status.on_change = window._on_connection_changed
        if not status.online:
            window._on_connection_changed(False, status.last_error)

        assert "unreachable" in window.status_bar.message
