import json
import queue
import threading

from server.events import EventBroadcaster


def _drain(subscriber):
    messages = []
    while True:
        try:
            messages.append(subscriber.get_nowait())
        except queue.Empty:
            return messages


class TestBroadcast:
    def test_every_subscriber_receives_the_event(self):
        broadcaster = EventBroadcaster()
        one, two = broadcaster.subscribe(), broadcaster.subscribe()

        broadcaster.broadcast("catalog_updated", {"domain": "food", "action": "insert"})

        for subscriber in (one, two):
            (message,) = _drain(subscriber)
            assert message.startswith("data: ")
            assert message.endswith("\n\n"), "SSE frames must be terminated by a blank line"
            assert json.loads(message[len("data: "):]) == {
                "event": "catalog_updated",
                "data": {"domain": "food", "action": "insert"},
            }

    def test_broadcasting_with_nobody_listening_is_harmless(self):
        EventBroadcaster().broadcast("catalog_updated", {"action": "delete"})

    def test_an_unsubscribed_queue_stops_receiving(self):
        broadcaster = EventBroadcaster()
        subscriber = broadcaster.subscribe()
        broadcaster.unsubscribe(subscriber)

        broadcaster.broadcast("catalog_updated", {})

        assert _drain(subscriber) == []

    def test_unsubscribing_twice_is_harmless(self):
        broadcaster = EventBroadcaster()
        subscriber = broadcaster.subscribe()
        broadcaster.unsubscribe(subscriber)
        broadcaster.unsubscribe(subscriber)

    def test_a_stalled_subscriber_does_not_block_the_others(self):
        broadcaster = EventBroadcaster()
        stalled, healthy = broadcaster.subscribe(), broadcaster.subscribe()

        for _ in range(150):
            broadcaster.broadcast("catalog_updated", {})

        assert stalled.full()
        assert len(_drain(healthy)) == 100

    def test_subscribing_from_several_threads_is_safe(self):
        broadcaster = EventBroadcaster()
        subscribers = []

        def join():
            subscribers.append(broadcaster.subscribe())

        threads = [threading.Thread(target=join) for _ in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        broadcaster.broadcast("catalog_updated", {"action": "insert"})
        assert all(len(_drain(subscriber)) == 1 for subscriber in subscribers)
        assert len(subscribers) == 16
