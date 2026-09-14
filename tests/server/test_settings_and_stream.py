import json

import pytest


class TestSettings:
    def test_an_unset_key_returns_the_callers_default(self, member_a):
        response = member_a.get("/api/settings/food_graph_period",
                                query_string={"default": "7 Days (Weekly Average)"})

        assert response.get_json() == {"value": "7 Days (Weekly Average)"}

    def test_an_unset_key_with_no_default_returns_empty(self, member_a):
        assert member_a.get("/api/settings/food_graph_period").get_json() == {"value": ""}

    def test_a_stored_value_wins_over_the_default(self, member_a):
        member_a.post("/api/settings/food_graph_period", json={"value": "1 Day (Raw)"})

        response = member_a.get("/api/settings/food_graph_period",
                                query_string={"default": "7 Days (Weekly Average)"})
        assert response.get_json() == {"value": "1 Day (Raw)"}

    def test_writing_a_key_twice_replaces_it(self, member_a):
        member_a.post("/api/settings/ex_graph_layout_dims", json={"value": "2x2"})
        member_a.post("/api/settings/ex_graph_layout_dims", json={"value": "3x3"})

        assert member_a.get("/api/settings/ex_graph_layout_dims").get_json()["value"] == "3x3"

    def test_values_are_stored_as_text(self, member_a):
        member_a.post("/api/settings/ex_graph_slot_1", json={"value": 7})

        assert member_a.get("/api/settings/ex_graph_slot_1").get_json()["value"] == "7"

    def test_keys_are_independent(self, member_a):
        member_a.post("/api/settings/ex_graph_slot_1", json={"value": "Overhead Press"})
        member_a.post("/api/settings/ex_graph_slot_2", json={"value": "Plank"})

        assert member_a.get("/api/settings/ex_graph_slot_1").get_json()["value"] == "Overhead Press"
        assert member_a.get("/api/settings/ex_graph_slot_2").get_json()["value"] == "Plank"


class TestEventStream:
    @pytest.fixture
    def stream(self, member_a):
        response = member_a.get("/api/events", buffered=False)
        yield response
        response.close()

    def test_the_stream_announces_itself_as_server_sent_events(self, stream):
        assert stream.status_code == 200
        assert stream.mimetype == "text/event-stream"
        assert stream.headers["Cache-Control"] == "no-cache"
        assert stream.headers["X-Accel-Buffering"] == "no", "proxies must not buffer the stream"

    def test_the_first_frame_is_a_connected_comment(self, stream):
        assert next(stream.response) == b": connected\n\n"

    def test_a_catalog_change_arrives_on_the_stream(self, stream, member_a):
        from tests.conftest import OATS

        next(stream.response)

        member_a.post("/api/catalog/food", json=OATS)

        frame = next(stream.response).decode()
        assert json.loads(frame[len("data: "):]) == {
            "event": "catalog_updated",
            "data": {"domain": "food", "table": "food_items", "action": "insert"},
        }

    def test_a_subscriber_is_registered_for_the_life_of_the_request(self, stream):
        from server.events import event_broadcaster

        next(stream.response)
        assert len(event_broadcaster._subscribers) >= 1

