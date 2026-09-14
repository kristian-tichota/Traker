import json
import logging
import time
import threading
import requests
from requests import RequestException
from PyQt6.QtCore import QObject, pyqtSignal
from src.config import SERVER_URL, API_TOKEN

log = logging.getLogger(__name__)


class SyncBridge(QObject):
    catalog_updated = pyqtSignal(dict)


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
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Cache-Control": "no-cache",
        }
        url = f"{self.base_url}/api/events"

        while self._is_running:
            try:
                self._session = requests.Session()
                with self._session.get(url, headers=headers, stream=True, timeout=(5.0, 30.0)) as response:
                    if response.status_code != 200:
                        self._interruptible_sleep(2.0)
                        continue

                    for line in response.iter_lines(decode_unicode=True):
                        if not self._is_running:
                            return
                        if line and line.startswith("data: "):
                            raw_payload = line[6:].strip()
                            try:
                                payload = json.loads(raw_payload)
                                if payload.get("event") == "catalog_updated":
                                    self.bridge.catalog_updated.emit(payload.get("data", {}))
                            except json.JSONDecodeError:
                                log.debug("Ignoring an unparseable sync payload: %r", raw_payload)
            except RequestException as e:
                log.debug("Sync stream dropped, reconnecting: %s", e)
            finally:
                if self._session:
                    try:
                        self._session.close()
                    except RequestException as e:
                        log.debug("Closing the sync session raised: %s", e)
                    self._session = None

            if not self._is_running:
                break
            self._interruptible_sleep(2.0)

    def _interruptible_sleep(self, duration: float):
        end_time = time.monotonic() + duration
        while self._is_running and time.monotonic() < end_time:
            time.sleep(0.05)

    def stop(self, timeout: float = 1.0):
        """Stop listening; nothing this listener emits reaches the window after."""
        self._is_running = False
        try:
            self.bridge.catalog_updated.disconnect()
        except TypeError:
            pass

        sess = self._session
        if sess is not None:
            try:
                sess.close()
            except RequestException as e:
                log.debug("Closing the sync session on shutdown raised: %s", e)

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
            if thread.is_alive():
                log.debug("The sync listener is still unwinding; it is a daemon "
                          "thread and its bridge is already disconnected")
        self._thread = None
