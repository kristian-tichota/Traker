import json
import logging
import time
import threading

import requests
from requests import RequestException
from PyQt6.QtCore import QObject, pyqtSignal

from src.config import SERVER_URL, API_TOKEN

log = logging.getLogger(__name__)

RETRY_S = 2.0


class SyncBridge(QObject):
    catalog_updated = pyqtSignal(dict)


def catalog_update(line: str):
    """Return the payload a catalog_updated frame carries, or None for any other line."""
    if not line or not line.startswith("data: "):
        return None
    try:
        frame = json.loads(line[6:])
    except json.JSONDecodeError:
        log.debug("Ignoring an unparseable sync payload: %r", line)
        return None
    if not isinstance(frame, dict) or frame.get("event") != "catalog_updated":
        return None
    data = frame.get("data")
    return data if isinstance(data, dict) else {}


class SyncListener:
    """The household's live catalog updates, consumed on a daemon thread."""

    def __init__(self, db=None):
        self.bridge = SyncBridge()
        self.catalog_updated = self.bridge.catalog_updated
        self.base_url = (getattr(db, "base_url", None) or SERVER_URL).rstrip("/")
        self.token = getattr(db, "token", None) or API_TOKEN
        self._is_running = True
        self._session = None
        self._thread = None

    def start(self):
        self._is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="SyncListener")
        self._thread.start()

    def _run(self):
        headers = {"Authorization": f"Bearer {self.token}", "Cache-Control": "no-cache"}
        url = f"{self.base_url}/api/events"

        while self._is_running:
            self._session = requests.Session()
            try:
                with self._session.get(url, headers=headers, stream=True,
                                       timeout=(5.0, 30.0)) as response:
                    if response.status_code == 200:
                        for line in response.iter_lines(decode_unicode=True):
                            if not self._is_running:
                                return
                            data = catalog_update(line)
                            if data is not None:
                                self.bridge.catalog_updated.emit(data)
            except RequestException as e:
                log.debug("Sync stream dropped, reconnecting: %s", e)
            finally:
                self._session.close()
                self._session = None
            self._interruptible_sleep(RETRY_S)

    def _interruptible_sleep(self, duration: float):
        end_time = time.monotonic() + duration
        while self._is_running and time.monotonic() < end_time:
            time.sleep(0.05)

    def stop(self, timeout: float = 1.0):
        """Stop listening, after which nothing this listener emits reaches the window."""
        self._is_running = False
        try:
            self.bridge.catalog_updated.disconnect()
        except TypeError:
            pass

        session = self._session
        if session is not None:
            session.close()

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
            if thread.is_alive():
                log.debug("The sync listener is still unwinding; it is a daemon "
                          "thread and its bridge is already disconnected")
        self._thread = None
