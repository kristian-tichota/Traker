import json
import logging
import queue
import threading

log = logging.getLogger(__name__)


class EventBroadcaster:
    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def broadcast(self, event_type: str, payload: dict):
        data = json.dumps({"event": event_type, "data": payload})
        msg = f"data: {data}\n\n"
        with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    log.warning(
                        "Dropped a %s event: a subscriber's queue is full (%d waiting)",
                        event_type, q.qsize(),
                    )

event_broadcaster = EventBroadcaster()
