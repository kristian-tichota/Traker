import logging

import pytest

from src.database import DatabaseClient


@pytest.fixture
def offline_client(offline_requests, profile_path):
    return DatabaseClient(base_url="http://traker.test", token="irrelevant")


class TestReadsWhileTheServiceIsDown:
    @pytest.mark.parametrize(
        "method",
        ["get_all_foods", "get_all_beverages", "get_all_exercises",
         "get_all_supplements", "get_all_mobility", "get_all_exercise_names",
         "get_food_logs", "get_beverage_logs", "get_exercise_logs",
         "get_supplement_logs", "get_mobility_logs", "get_pomodoro_daily_summary"],
    )
    def test_a_read_returns_empty_rather_than_raising(self, offline_client, method):
        assert getattr(offline_client, method)() == []

    def test_a_keyed_read_returns_an_empty_mapping(self, offline_client):
        assert offline_client.get_pomodoro_heartbeats_for_day("2026-09-05") == {}
        assert offline_client.get_pomodoro_dsi_overrides() == {}

    def test_a_setting_falls_back_to_the_callers_default(self, offline_client):
        assert offline_client.get_setting("food_graph_period", "1 Day (Raw)") == "1 Day (Raw)"

    def test_the_failure_is_logged_once_per_call_not_per_row(self, offline_client, caplog):
        with caplog.at_level(logging.WARNING, logger="src.database"):
            offline_client.get_food_logs()

        assert len(caplog.records) == 1
        assert "/api/logs/food" in caplog.text

    def test_derived_reads_survive_an_empty_response(self, offline_client):
        assert offline_client.get_exercise_logs() == []
        assert offline_client.get_beverage_logs() == []
        assert offline_client.get_daily_aggregates() == []


class TestWritesWhileTheServiceIsDown:
    def test_a_write_reports_the_failure_instead_of_raising(self, offline_client):
        success, message = offline_client.add_food_log({
            "date": "2026-09-05", "meal_type": "Breakfast",
            "food_name": "Rolled Oats", "servings": 1.0,
        })

        assert success is False
        assert "household service is not running" in message

    def test_a_delete_reports_the_failure(self, offline_client):
        success, message = offline_client.delete_item_by_name("Rolled Oats")

        assert success is False
        assert message

    def test_an_inline_edit_reports_the_failure(self, offline_client):
        success, message = offline_client.update_record(
            "food_logs", 1, "Servings", "2.0", {"Servings": "servings"}
        )

        assert success is False
        assert message


class TestClientShape:
    def test_the_client_holds_no_database_connection(self, offline_client):
        assert not hasattr(offline_client, "conn")
        assert not hasattr(offline_client, "cursor")

    def test_the_bearer_token_is_sent_on_every_call(self, profile_path):
        client = DatabaseClient(base_url="http://traker.test", token="a-token")
        assert client.headers["Authorization"] == "Bearer a-token"
        assert client.headers["Content-Type"] == "application/json"

    def test_a_trailing_slash_on_the_base_url_is_normalised(self, profile_path):
        assert DatabaseClient(base_url="http://traker.test/").base_url == "http://traker.test"

    def test_clearing_an_override_reports_an_unreachable_service(self, offline_client):
        success, message = offline_client.clear_pomodoro_dsi_override("2026-09-05")

        assert success is False
        assert "not running" in message


class TestCredentialResolution:
    @staticmethod
    def _reload(monkeypatch, env, profile_text, tmp_path):
        import src.config
        import src.profile

        profile = tmp_path / "user_profile.toml"
        if profile_text is not None:
            profile.write_text(profile_text, encoding="utf-8")
        monkeypatch.setattr(src.profile, "PROFILE_PATH", str(profile))
        for key in ("TRAKER_SERVER_URL", "TRAKER_API_TOKEN"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return src.config._load_server_creds()

    def test_the_environment_wins(self, monkeypatch, tmp_path):
        url, token = self._reload(
            monkeypatch,
            {"TRAKER_SERVER_URL": "http://env:1", "TRAKER_API_TOKEN": "env-token"},
            '[server]\nurl = "http://profile:2"\ntoken = "profile-token"\n',
            tmp_path,
        )
        assert (url, token) == ("http://env:1", "env-token")

    def test_the_profile_is_used_when_the_environment_is_silent(self, monkeypatch, tmp_path):
        url, token = self._reload(
            monkeypatch, {},
            '[server]\nurl = "http://profile:2"\ntoken = "profile-token"\n',
            tmp_path,
        )
        assert (url, token) == ("http://profile:2", "profile-token")

    def test_the_built_in_local_default_is_the_last_resort(self, monkeypatch, tmp_path):
        url, _ = self._reload(monkeypatch, {}, None, tmp_path)

        assert url == "http://127.0.0.1:6035"

    def test_no_token_is_built_in(self, monkeypatch, tmp_path):
        _, token = self._reload(monkeypatch, {}, None, tmp_path)

        assert token == "", "a shipped token would authenticate every install as the same member"

    def test_an_unreadable_profile_falls_through_to_the_default(self, monkeypatch, tmp_path, caplog):
        with caplog.at_level(logging.WARNING, logger="src.config"):
            url, _ = self._reload(monkeypatch, {}, "not [[ valid toml", tmp_path)

        assert url == "http://127.0.0.1:6035"
        assert "Could not parse server settings" in caplog.text


class TestUnreachableIsDistinguishableFromEmpty:
    def test_a_fresh_client_assumes_the_service_is_up(self, profile_path):
        assert DatabaseClient(base_url="http://traker.test", token="t").connection.online

    def test_a_failed_read_records_the_reason(self, offline_client):
        assert offline_client.get_food_logs() == []

        assert offline_client.connection.online is False
        assert "household service is not running" in offline_client.connection.last_error

    def test_an_empty_but_answered_read_leaves_the_client_online(self, db_client):
        assert db_client.get_food_logs() == []

        assert db_client.connection.online is True
        assert db_client.connection.last_error is None

    def test_a_failed_write_records_the_reason(self, offline_client):
        offline_client.add_food_log({"date": "2026-09-05", "meal_type": "Breakfast",
                                     "food_name": "Rolled Oats", "servings": 1.0})

        assert offline_client.connection.online is False

    def test_the_change_is_announced_once_per_flip_not_per_call(self, offline_client):
        announced = []
        offline_client.connection.on_change = lambda online, reason: announced.append(online)

        offline_client.get_food_logs()
        offline_client.get_beverage_logs()
        offline_client.get_mobility_logs()

        assert announced == [False], "three failed reads, one status change"

    def test_coming_back_is_announced_too(self, db_client, monkeypatch):
        import requests

        announced = []
        db_client.connection.on_change = lambda online, reason: announced.append(online)

        working_get = requests.get
        monkeypatch.setattr(requests, "get", _refusing)
        db_client.get_food_logs()
        monkeypatch.setattr(requests, "get", working_get)
        db_client.get_food_logs()

        assert announced == [False, True]


def _refusing(*args, **kwargs):
    import requests

    raise requests.ConnectionError("household service is not running")
