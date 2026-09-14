import pytest

from tests.conftest import (MEMBER_A_NAME, MEMBER_A_TOKEN,
                            MEMBER_B_NAME, MEMBER_B_TOKEN)

PROTECTED = [
    ("get", "/api/catalog/food"),
    ("get", "/api/logs/food"),
    ("get", "/api/logs/exercise"),
    ("get", "/api/pomodoro/daily-summary"),
    ("get", "/api/settings/food_graph_period"),
    ("get", "/api/events"),
]


class TestTokenChecks:
    @pytest.mark.parametrize("verb, path", PROTECTED)
    def test_a_request_without_a_token_is_unauthenticated(self, anon, verb, path):
        response = getattr(anon, verb)(path)
        assert response.status_code == 401
        assert "token" in response.get_json()["error"].lower()

    @pytest.mark.parametrize("verb, path", PROTECTED)
    def test_a_request_with_an_unknown_token_is_unauthorised(self, anon, verb, path):
        response = getattr(anon, verb)(path, headers={"Authorization": "Bearer not-a-member"})
        assert response.status_code == 403

    def test_an_empty_bearer_value_is_treated_as_missing(self, anon):
        assert anon.get("/api/logs/food", headers={"Authorization": "Bearer   "}).status_code == 401

    def test_a_token_may_arrive_as_an_api_key_header(self, anon):
        assert anon.get("/api/logs/food", headers={"X-API-Key": MEMBER_A_TOKEN}).status_code == 200

    def test_the_liveness_probe_needs_no_token(self, anon):
        response = anon.get("/api/ping")
        assert response.status_code == 200
        assert response.get_json() == {"status": "ok"}


class TestSeeding:
    def test_both_members_are_seeded_from_the_pre_shared_tokens(self, server_db):
        conn = server_db.get_connection()
        rows = conn.execute("SELECT username, api_token FROM users ORDER BY id").fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[0]["username"] == MEMBER_A_NAME
        assert rows[0]["api_token"] == MEMBER_A_TOKEN

    def test_re_running_the_schema_build_does_not_duplicate_members(self, server_db):
        server_db.init_db()
        server_db.init_db()

        conn = server_db.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        assert count == 2

    def test_the_two_members_are_distinct_identities(self, member_a, member_b):
        assert member_a.token != member_b.token
        assert member_a.username != member_b.username


class TestConnectionPragmas:
    def test_write_ahead_logging_is_on(self, server_db):
        conn = server_db.get_connection()
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        conn.close()

    def test_foreign_keys_are_enforced(self, server_db):
        conn = server_db.get_connection()
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        conn.close()


class TestRotatingAToken:
    def test_a_rotated_token_replaces_the_old_one_in_place(self, server_db, monkeypatch):
        import server.database

        before = {r["username"]: r["id"] for r in _users(server_db)}
        monkeypatch.setitem(server.database.USER_TOKENS, "A-FRESHLY-ROTATED-TOKEN", MEMBER_A_NAME)
        monkeypatch.delitem(server.database.USER_TOKENS, MEMBER_A_TOKEN)

        server_db.init_db()

        rows = {r["username"]: (r["id"], r["api_token"]) for r in _users(server_db)}
        assert rows[MEMBER_A_NAME][1] == "A-FRESHLY-ROTATED-TOKEN"
        assert rows[MEMBER_A_NAME][0] == before[MEMBER_A_NAME], (
            "every log references users.id with ON DELETE CASCADE, so the row is "
            "updated in place and never replaced"
        )

    def test_the_other_member_is_untouched(self, server_db, monkeypatch):
        import server.database

        monkeypatch.setitem(server.database.USER_TOKENS, "A-FRESHLY-ROTATED-TOKEN", MEMBER_A_NAME)
        monkeypatch.delitem(server.database.USER_TOKENS, MEMBER_A_TOKEN)
        server_db.init_db()

        rows = {r["username"]: r["api_token"] for r in _users(server_db)}
        assert rows[MEMBER_B_NAME] == MEMBER_B_TOKEN

    def test_seeding_the_same_tokens_again_changes_nothing(self, server_db):
        before = [(r["id"], r["username"], r["api_token"]) for r in _users(server_db)]

        server_db.init_db()

        assert [(r["id"], r["username"], r["api_token"]) for r in _users(server_db)] == before


def _users(server_db):
    conn = server_db.get_connection()
    try:
        return conn.execute("SELECT id, username, api_token FROM users ORDER BY id").fetchall()
    finally:
        conn.close()
