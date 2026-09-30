import json
import logging
import queue
import threading

from flask import g

log = logging.getLogger(__name__)


class EventBroadcaster:
    def __init__(self):
        self._subscribers = {}
        self._lock = threading.Lock()

    def subscribe(self, member=None) -> queue.Queue:
        """Return a queue of every event, each marked own where member caused it."""
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers[q] = member
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            self._subscribers.pop(q, None)

    def broadcast(self, event_type: str, payload: dict, origin=None):
        with self._lock:
            for q, member in self._subscribers.items():
                data = dict(payload, own=origin is not None and member == origin)
                try:
                    q.put_nowait(f"data: {json.dumps({'event': event_type, 'data': data})}\n\n")
                except queue.Full:
                    log.warning(
                        "Dropped a %s event: a subscriber's queue is full (%d waiting)",
                        event_type, q.qsize(),
                    )


event_broadcaster = EventBroadcaster()


def catalog_updated(**data):
    """Tell every stream the shared catalog changed, and which member changed it."""
    event_broadcaster.broadcast("catalog_updated", data, origin=g.user_id)
