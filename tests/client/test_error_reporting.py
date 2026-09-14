import pytest
import requests

from src.database import DatabaseClient


class FakeResponse:
    def __init__(self, status_code, text, json_body=None):
        self.status_code = status_code
        self.text = text
        self._json = json_body

    def json(self):
        if self._json is None:
            raise requests.exceptions.JSONDecodeError("Expecting value", self.text, 0)
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


@pytest.fixture
def client_answering(monkeypatch):
    def _build(response):
        import src.database as module

        class FakeRequests:
            HTTPError = requests.HTTPError

            def get(self, *a, **k): return response
            def post(self, *a, **k): return response
            def delete(self, *a, **k): return response
            def patch(self, *a, **k): return response

        monkeypatch.setattr(module, "requests", FakeRequests())
        return DatabaseClient(base_url="http://stub", token="t")

    return _build

UNREADABLE = [
    pytest.param(FakeResponse(500, "<!doctype html><title>500</title>"), id="html-page"),
    pytest.param(FakeResponse(502, ""), id="empty-body"),
    pytest.param(FakeResponse(400, "plain words"), id="plain-text"),
]


class TestAnErrorBodyThatIsNotJson:
    @pytest.mark.parametrize("response", UNREADABLE)
    def test_a_write_returns_a_refusal_rather_than_raising(self, client_answering, response):
        client = client_answering(response)

        success, message = client.add_food_log({"date": "2026-09-05"})

        assert success is False
        assert message

    @pytest.mark.parametrize("response", UNREADABLE)
    def test_an_inline_edit_returns_a_refusal_rather_than_raising(self, client_answering, response):
        client = client_answering(response)

        success, message = client.update_record(
            "food_logs", 1, "Servings", "2", {"Servings": "servings"})

        assert success is False
        assert message

    @pytest.mark.parametrize("response", UNREADABLE)
    def test_a_delete_returns_a_refusal_rather_than_raising(self, client_answering, response):
        client = client_answering(response)

        success, message = client.delete_record("food_logs", 1)

        assert success is False
        assert message

    def test_a_read_degrades_to_empty_rather_than_raising(self, client_answering):
        client = client_answering(FakeResponse(200, "<html>not json</html>"))

        assert client.get_food_logs() == []
        assert client.connection.online is False


class TestBeingToldNoIsNotBeingOffline:
    @pytest.mark.parametrize("status", [400, 401, 404, 500])
    def test_a_refused_read_leaves_the_client_online(self, client_answering, status):
        client = client_answering(FakeResponse(status, "", {"error": "no"}))

        assert client.get_food_logs() == []
        assert client.connection.online is True

    def test_a_refused_read_and_a_refused_write_agree(self, client_answering):
        client = client_answering(FakeResponse(400, "", {"error": "no"}))

        client.add_food_log({"date": "2026-09-05"})
        after_write = client.connection.online
        client.get_food_logs()

        assert (after_write, client.connection.online) == (True, True)

    def test_a_refusal_is_still_a_refusal(self, client_answering):
        client = client_answering(FakeResponse(400, "", {"error": "energy is not a number"}))

        success, message = client.add_food_item({"energy": "12o"})

        assert (success, message) == (False, "energy is not a number")


class TestAReadableRefusalKeepsItsReason:
    def test_the_servers_reason_is_what_the_status_bar_gets(self, client_answering):
        client = client_answering(
            FakeResponse(400, "", {"error": "'12o' is not a number, but energy stores one"}))

        _success, message = client.add_food_item({"energy": "12o"})

        assert message == "'12o' is not a number, but energy stores one"

    def test_a_refused_edit_keeps_its_reason(self, client_answering):
        client = client_answering(FakeResponse(404, "", {"error": "No row 7 of food_logs"}))

        _success, message = client.update_record(
            "food_logs", 7, "Servings", "2", {"Servings": "servings"})

        assert "No row 7" in message
