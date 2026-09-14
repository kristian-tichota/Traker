import json

import pytest
import requests

import src.gui.sync_listener as sync_listener
from src.gui.sync_listener import SyncListener

pytestmark = pytest.mark.gui


class FakeResponse:
    def __init__(self, lines, status_code=200, on_exhausted=None):
        self.status_code = status_code
        self._lines = list(lines)
        self._on_exhausted = on_exhausted

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line
        if self._on_exhausted:
            self._on_exhausted()


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.attempts = 0
        self.closed = 0
        self.last_headers = None
        self.last_url = None

    def get(self, url, headers=None, stream=False, timeout=None):
        self.attempts += 1
        self.last_url = url
        self.last_headers = headers
        if not self._responses:
            raise requests.ConnectionError("no more stream")
        return self._responses.pop(0)

    def close(self):
        self.closed += 1


@pytest.fixture
def run_listener(qapp, monkeypatch):
    def _run(responses, stop_after_first_stream=True):
        listener = SyncListener()
        received = []
        listener.catalog_updated.connect(received.append)

        queued = []
        for response in responses:
            if stop_after_first_stream and response is responses[-1]:
                response._on_exhausted = lambda: setattr(listener, "_is_running", False)
            queued.append(response)

        session = FakeSession(queued)
        monkeypatch.setattr(sync_listener.requests, "Session", lambda: session)
        monkeypatch.setattr(listener, "_interruptible_sleep", lambda duration: None)

        listener._run()
        return listener, received, session

    return _run


class TestFrameHandling:
    def test_a_catalog_event_reaches_the_ui(self, run_listener):
        frame = json.dumps({"event": "catalog_updated",
                            "data": {"domain": "food", "action": "insert"}})

        _, received, _ = run_listener([FakeResponse([f"data: {frame}"])])

        assert received == [{"domain": "food", "action": "insert"}]

    def test_keepalive_comments_are_ignored(self, run_listener):
        _, received, session = run_listener([FakeResponse(
            [": connected", ": keepalive", ": keepalive", ""]
        )])

        assert received == []
        assert session.attempts == 1, "silence must not trigger a reconnect mid-stream"

    def test_a_malformed_frame_is_skipped(self, run_listener):
        good = json.dumps({"event": "catalog_updated", "data": {"action": "delete"}})

        _, received, _ = run_listener([FakeResponse(
            ["data: {not json at all", f"data: {good}"]
        )])

        assert received == [{"action": "delete"}]

    def test_an_unrelated_event_type_is_ignored(self, run_listener):
        frame = json.dumps({"event": "something_else", "data": {"x": 1}})

        _, received, _ = run_listener([FakeResponse([f"data: {frame}"])])

        assert received == []

    def test_an_event_without_a_payload_still_notifies(self, run_listener):
        frame = json.dumps({"event": "catalog_updated"})

        _, received, _ = run_listener([FakeResponse([f"data: {frame}"])])

        assert received == [{}]

    def test_several_frames_arrive_in_order(self, run_listener):
        frames = [
            json.dumps({"event": "catalog_updated", "data": {"action": action}})
            for action in ("insert", "update", "delete")
        ]

        _, received, _ = run_listener([FakeResponse([f"data: {f}" for f in frames])])

        assert [payload["action"] for payload in received] == ["insert", "update", "delete"]


class TestConnection:
    def test_the_stream_is_requested_with_the_members_token(self, run_listener):
        _, _, session = run_listener([FakeResponse([])])

        assert session.last_url.endswith("/api/events")
        assert session.last_headers["Authorization"].startswith("Bearer ")
        assert session.last_headers["Cache-Control"] == "no-cache"

    def test_a_refused_connection_is_retried_rather_than_abandoned(self, run_listener):
        frame = json.dumps({"event": "catalog_updated", "data": {"action": "insert"}})

        _, received, session = run_listener([
            FakeResponse([], status_code=503),
            FakeResponse([f"data: {frame}"]),
        ])

        assert session.attempts == 2
        assert received == [{"action": "insert"}]

    def test_a_dropped_stream_reconnects_by_itself(self, run_listener):
        frame = json.dumps({"event": "catalog_updated", "data": {"action": "insert"}})

        _, received, session = run_listener([
            FakeResponse([]),
            FakeResponse([f"data: {frame}"]),
        ])

        assert session.attempts == 2
        assert received == [{"action": "insert"}]

    def test_each_attempt_closes_its_session(self, run_listener):
        _, _, session = run_listener([FakeResponse([]), FakeResponse([])])

        assert session.closed == 2


class TestItListensWhereTheClientIsPointed:
    class ClientPointedElsewhere:
        base_url = "http://study-desk.lan:6035"
        token = "the-members-own-token"

    def test_the_stream_is_opened_at_the_clients_address(self, run_listener, monkeypatch):
        listener = SyncListener(self.ClientPointedElsewhere())

        assert listener.base_url == "http://study-desk.lan:6035"
        assert listener.token == "the-members-own-token"

    def test_a_trailing_slash_does_not_double_up(self):
        class Trailing:
            base_url = "http://study-desk.lan:6035/"
            token = "t"

        assert SyncListener(Trailing()).base_url == "http://study-desk.lan:6035"

    def test_without_a_client_it_falls_back_to_the_module_defaults(self):
        from src.config import API_TOKEN, SERVER_URL

        listener = SyncListener()

        assert listener.base_url == SERVER_URL.rstrip("/")
        assert listener.token == API_TOKEN


class TestShutdown:
    def test_stopping_joins_the_thread_it_started(self, qapp, monkeypatch):
        listener = SyncListener()
        monkeypatch.setattr(sync_listener.requests, "Session", lambda: FakeSession([]))
        listener.start()

        listener.stop()

        assert listener._thread is None

    def test_stopping_disconnects_the_bridge(self, qapp, monkeypatch):
        listener = SyncListener()
        received = []
        listener.catalog_updated.connect(received.append)
        monkeypatch.setattr(sync_listener.requests, "Session", lambda: FakeSession([]))
        listener.start()

        listener.stop()
        listener.bridge.catalog_updated.emit({"domain": "food"})
        qapp.processEvents()

        assert received == []

    def test_stopping_releases_the_open_session(self, qapp):
        listener = SyncListener()
        session = FakeSession([])
        listener._session = session

        listener.stop()

        assert listener._is_running is False
        assert session.closed == 1

    def test_stopping_without_a_session_is_harmless(self, qapp):
        listener = SyncListener()

        listener.stop()

        assert listener._is_running is False

    def test_the_worker_thread_is_a_daemon(self, qapp, monkeypatch):
        listener = SyncListener()
        monkeypatch.setattr(listener, "_run", lambda: None)

        listener.start()

        assert listener._thread.daemon is True
        listener._thread.join(timeout=2)

    def test_the_sleep_between_retries_ends_as_soon_as_the_listener_stops(self, qapp):
        import time

        listener = SyncListener()
        listener._is_running = False

        started = time.monotonic()
        listener._interruptible_sleep(30.0)

        assert time.monotonic() - started < 1.0
