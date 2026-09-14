import sqlite3

import pytest

from server.database import db_service


@pytest.fixture
def opened_connections(flask_app, monkeypatch):
    opened = []
    real = db_service.get_connection

    def spy():
        conn = real()
        opened.append(conn)
        return conn

    monkeypatch.setattr(db_service, "get_connection", spy)
    return opened


def is_closed(conn) -> bool:
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


class TestOneConnectionPerRequest:
    def test_authentication_and_the_route_share_one_connection(
        self, member_a, seeded_catalog, opened_connections
    ):
        member_a.get("/api/logs/food")

        assert len(opened_connections) == 1, "require_auth shares the request's"

    def test_a_write_also_costs_one_connection(
        self, member_a, seeded_catalog, opened_connections
    ):
        member_a.post("/api/logs/food", json={
            "date": "2026-09-05", "meal_type": "Breakfast",
            "food_name": "Rolled Oats", "servings": 1.0,
        })

        assert len(opened_connections) == 1

    def test_a_rejected_token_opens_at_most_one(self, flask_app, opened_connections):
        flask_app.test_client().get("/api/logs/food", headers={"Authorization": "Bearer nope"})

        assert len(opened_connections) == 1

    def test_an_unauthenticated_call_opens_none(self, anon, opened_connections):
        anon.get("/api/logs/food")

        assert opened_connections == [], "no token, no lookup"


class TestTheConnectionIsAlwaysClosed:
    def test_a_successful_request_closes_it(self, member_a, seeded_catalog, opened_connections):
        member_a.get("/api/logs/food")

        (conn,) = opened_connections
        assert is_closed(conn)

    def test_a_refused_write_closes_it(self, member_a, seeded_catalog, opened_connections):
        response = member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Overhead Press",
            "set1": 7, "set2": 0, "set3": 0, "set4": 0, "set5": 0,
            "weight_kg": 30.0, "rpe": 15.0,
        })

        assert response.status_code == 400
        (conn,) = opened_connections
        assert is_closed(conn)

    def test_a_malformed_payload_is_answered_and_still_closes_it(
        self, member_a, opened_connections
    ):
        response = member_a.post("/api/logs/food", json={"date": "2026-09-05"})

        assert response.status_code == 400
        assert "food_name" in response.get_json()["error"]
        (conn,) = opened_connections
        assert is_closed(conn)

    def test_an_unhandled_route_exception_still_closes_it(
        self, flask_app, member_a, opened_connections
    ):
        from server.auth import require_auth
        from server.db_session import get_db

        @flask_app.route("/api/test-only/explode")
        @require_auth
        def explode():
            get_db()
            raise RuntimeError("boom")

        response = member_a.get("/api/test-only/explode")

        assert response.status_code == 500
        (conn,) = opened_connections
        assert is_closed(conn)

    def test_the_event_stream_does_not_sit_on_a_connection(
        self, member_a, opened_connections
    ):
        response = member_a.get("/api/events")

        try:
            (conn,) = opened_connections
            assert is_closed(conn), "released before the long-lived response"
        finally:
            response.close()


class TestConstraintViolationsAreReported:
    @pytest.mark.parametrize("endpoint, payload", [
        ("food", {"date": "2026-09-05", "meal_type": "Brunch",
                  "food_name": "Rolled Oats", "servings": 1.0}),
        ("exercise", {"date": "2026-09-05", "ex_name": "Overhead Press",
                      "set1": 7, "set2": 0, "set3": 0, "set4": 0, "set5": 0,
                      "weight_kg": 30.0, "rpe": 15.0}),
        ("mobility", {"date": "2026-09-05", "mob_name": "Hip Opener",
                      "duration_mins": -5.0}),
    ])
    def test_a_log_write_answers_with_the_constraint(
        self, seeded_catalog, member_a, endpoint, payload
    ):
        response = member_a.post(f"/api/logs/{endpoint}", json=payload)

        assert response.status_code == 400
        assert "CHECK constraint" in response.get_json()["error"]

    def test_a_duplicate_catalog_name_still_answers_with_the_reason(
        self, seeded_catalog, member_a
    ):
        response = member_a.post("/api/catalog/beverage", json={
            "name": "Black Coffee", "caffeine_mg": 80.0, "antioxidants_mg": 200.0,
        })

        assert response.status_code == 400
        assert "UNIQUE constraint" in response.get_json()["error"]

    def test_the_refused_row_is_not_stored(self, seeded_catalog, member_a):
        member_a.post("/api/logs/exercise", json={
            "date": "2026-09-05", "ex_name": "Overhead Press",
            "set1": 7, "set2": 0, "set3": 0, "set4": 0, "set5": 0,
            "weight_kg": 30.0, "rpe": 15.0,
        })

        assert member_a.get("/api/logs/exercise").get_json() == []
