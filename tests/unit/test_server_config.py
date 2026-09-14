import os
import stat
import tomllib

import pytest

import server.config as config

TWO_MEMBERS = """[[members]]
username = "alice"
token = "alice-token"

[[members]]
username = "bob"
token = "bob-token"
"""


@pytest.fixture
def at(tmp_path, monkeypatch):
    """Resolve the settings against a config file of your own, and nothing else."""
    path = tmp_path / "server.toml"

    def _resolve(text=None, **env):
        if text is not None:
            path.write_text(text, encoding="utf-8")
        monkeypatch.setenv("TRAKER_SERVER_CONFIG", str(path))
        for key in ("TRAKER_SERVER_HOST", "TRAKER_SERVER_PORT", "TRAKER_DB_PATH"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return config._resolve(), path

    return _resolve


class TestMembers:
    def test_every_configured_member_is_known_by_their_token(self, at):
        (_, _, _, _, tokens), _ = at(TWO_MEMBERS)

        assert tokens == {"alice-token": "alice", "bob-token": "bob"}

    def test_no_config_file_means_no_members_rather_than_an_invented_one(self, at):
        (_, _, _, _, tokens), _ = at()

        assert tokens == {}

    def test_a_member_named_twice_is_only_one_member(self, at):
        (_, _, _, _, tokens), _ = at(
            '[[members]]\nusername = "alice"\ntoken = "first"\n'
            '[[members]]\nusername = "Alice"\ntoken = "second"\n')

        assert list(tokens.values()) == ["alice"]

    def test_a_member_with_no_username_is_ignored(self, at):
        (_, _, _, _, tokens), _ = at('[[members]]\ntoken = "orphan"\n')

        assert tokens == {}


class TestMintingAToken:
    def test_a_member_without_a_token_is_given_one(self, at):
        (_, _, _, _, tokens), _ = at('[[members]]\nusername = "alice"\n')

        assert list(tokens.values()) == ["alice"]
        assert len(next(iter(tokens))) >= 16

    def test_the_minted_token_is_written_back(self, at):
        (_, _, _, _, tokens), path = at('[[members]]\nusername = "alice"\n')

        written = tomllib.loads(path.read_text(encoding="utf-8"))
        assert written["members"][0]["token"] == next(iter(tokens))

    def test_the_next_start_reuses_it_rather_than_minting_again(self, at):
        (_, _, _, _, first), _ = at('[[members]]\nusername = "alice"\n')
        (_, _, _, _, second), _ = at()

        assert first == second

    def test_the_file_it_writes_is_readable_only_by_its_owner(self, at):
        _, path = at('[[members]]\nusername = "alice"\n')

        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_an_environment_override_is_not_baked_into_the_file(self, at):
        _, path = at('[server]\nhost = "127.0.0.1"\n[[members]]\nusername = "alice"\n',
                     TRAKER_SERVER_HOST="0.0.0.0")

        written = tomllib.loads(path.read_text(encoding="utf-8"))
        assert written["server"]["host"] == "127.0.0.1", (
            "an override belongs to the process that set it, not to the file")


class TestSettings:
    def test_the_service_stays_on_this_machine_unless_told_otherwise(self, at):
        (_, host, port, _, _), _ = at(TWO_MEMBERS)

        assert (host, port) == ("127.0.0.1", 6035)

    def test_the_file_says_where_to_listen(self, at):
        (_, host, port, _, _), _ = at('[server]\nhost = "0.0.0.0"\nport = 7000\n')

        assert (host, port) == ("0.0.0.0", 7000)

    @pytest.mark.parametrize("variable, value, index", [
        ("TRAKER_SERVER_HOST", "0.0.0.0", 1),
        ("TRAKER_SERVER_PORT", "7100", 2),
    ])
    def test_the_environment_beats_the_file(self, at, variable, value, index):
        resolved, _ = at('[server]\nhost = "10.0.0.9"\nport = 6035\n', **{variable: value})

        assert str(resolved[index]) == value

    def test_an_unreadable_port_falls_back_rather_than_refusing_to_start(self, at):
        (_, _, port, _, _), _ = at('[server]\nport = "six thousand"\n')

        assert port == 6035

    def test_a_relative_database_path_resolves_against_the_repository(self, at):
        (_, _, _, db_path, _), _ = at('[server]\ndb_path = "data/other.db"\n')

        assert os.path.isabs(db_path)
        assert os.path.normpath(db_path).endswith(os.path.join("data", "other.db"))

    def test_the_environment_beats_the_file_about_the_database(self, at, tmp_path):
        (_, _, _, db_path, _), _ = at(TWO_MEMBERS, TRAKER_DB_PATH=str(tmp_path / "env.db"))

        assert db_path == str(tmp_path / "env.db")

    def test_unparseable_settings_leave_the_service_without_members(self, at, caplog):
        with caplog.at_level("WARNING", logger="server.config"):
            (_, _, _, _, tokens), _ = at("this is not [[[ toml")

        assert tokens == {}
        assert "Could not parse" in caplog.text
