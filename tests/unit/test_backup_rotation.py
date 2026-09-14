import os
import logging
import re
import sqlite3
import time

import pytest

import backup


def _redirect_backup_paths(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setattr(backup, "DATA_DIR", str(data))
    monkeypatch.setattr(backup, "DEFAULT_DB_PATH", str(data / "traker_server.db"))
    monkeypatch.setattr(backup, "LEGACY_DB_PATHS",
                            (str(data / "traker.db"), str(data / "tracker.db")))
    monkeypatch.setattr(backup, "BACKUP_DIR", str(tmp_path / "backups"))


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    directory = tmp_path / "backups"
    monkeypatch.setattr(backup, "BACKUP_DIR", str(directory))
    return directory


def _make_db(path, rows=("Rolled Oats",)):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS food_items (name TEXT)")
        conn.executemany("INSERT INTO food_items (name) VALUES (?)", [(r,) for r in rows])
    conn.close()
    return path


def _touch(path, epoch):
    os.utime(path, (epoch, epoch))


class TestSnapshot:
    def test_a_snapshot_is_a_readable_copy_of_the_data(self, tmp_path, backup_dir):
        source = _make_db(tmp_path / "traker_server.db", rows=("Rolled Oats", "Black Coffee"))

        backup.execute_safe_backup(str(source))

        (snapshot,) = list(backup_dir.glob("*.db"))
        conn = sqlite3.connect(snapshot)
        names = [row[0] for row in conn.execute("SELECT name FROM food_items ORDER BY name")]
        conn.close()
        assert names == ["Black Coffee", "Rolled Oats"]

    def test_the_snapshot_uses_sqlite_backup_rather_than_a_file_copy(self, tmp_path, backup_dir):
        source = tmp_path / "traker_server.db"
        conn = sqlite3.connect(source)
        conn.execute("PRAGMA journal_mode = WAL")
        with conn:
            conn.execute("CREATE TABLE food_items (name TEXT)")
            conn.execute("INSERT INTO food_items VALUES ('Written to the WAL')")

        backup.execute_safe_backup(str(source))
        conn.close()

        (snapshot,) = list(backup_dir.glob("*.db"))
        copied = sqlite3.connect(snapshot)
        assert copied.execute("SELECT name FROM food_items").fetchall() == [("Written to the WAL",)]
        copied.close()

    def test_the_snapshot_name_carries_the_source_name_and_a_timestamp(self, tmp_path, backup_dir):
        source = _make_db(tmp_path / "traker_server.db")

        backup.execute_safe_backup(str(source))

        (snapshot,) = list(backup_dir.glob("*.db"))
        assert re.fullmatch(r"traker_server_backup_\d{8}_\d{6}\.db", snapshot.name), snapshot.name

    def test_a_missing_database_is_reported_and_not_fatal(self, tmp_path, monkeypatch, caplog):
        _redirect_backup_paths(monkeypatch, tmp_path)

        with caplog.at_level(logging.WARNING, logger="backup"):
            backup.execute_safe_backup(str(tmp_path / "absent.db"))

        assert "No database to snapshot" in caplog.text
        assert not (tmp_path / "backups").exists(), "nothing should be written"

    def test_the_legacy_database_name_is_still_snapshotted(self, tmp_path, monkeypatch):
        _redirect_backup_paths(monkeypatch, tmp_path)
        _make_db(tmp_path / "data" / "traker.db")

        backup.execute_safe_backup()

        (snapshot,) = list((tmp_path / "backups").glob("*.db"))
        assert snapshot.name.startswith("traker_backup_")


class TestRotation:
    def test_the_oldest_snapshots_are_removed_once_the_cap_is_reached(self, backup_dir, caplog):
        backup_dir.mkdir(parents=True)
        for index in range(5):
            snapshot = backup_dir / f"traker_server_backup_{index}.db"
            snapshot.write_bytes(b"")
            _touch(snapshot, time.time() - (100 - index))

        with caplog.at_level(logging.INFO, logger="backup"):
            backup.manage_backup_rotation(max_backups=3)

        surviving = sorted(path.name for path in backup_dir.glob("*.db"))
        assert surviving == [
            "traker_server_backup_2.db",
            "traker_server_backup_3.db",
            "traker_server_backup_4.db",
        ]
        assert "Rotated out" in caplog.text, "removals must be reported"

    def test_staying_under_the_cap_removes_nothing(self, backup_dir):
        backup_dir.mkdir(parents=True)
        for index in range(3):
            (backup_dir / f"snapshot_{index}.db").write_bytes(b"")

        backup.manage_backup_rotation(max_backups=30)

        assert len(list(backup_dir.glob("*.db"))) == 3

    def test_non_database_files_are_left_alone(self, backup_dir):
        backup_dir.mkdir(parents=True)
        for index in range(4):
            snapshot = backup_dir / f"snapshot_{index}.db"
            snapshot.write_bytes(b"")
            _touch(snapshot, time.time() - (10 - index))
        (backup_dir / "README.txt").write_text("keep me")

        backup.manage_backup_rotation(max_backups=1)

        assert (backup_dir / "README.txt").exists()
        assert [p.name for p in backup_dir.glob("*.db")] == ["snapshot_3.db"]

    def test_the_default_cap_is_thirty(self, backup_dir):
        backup_dir.mkdir(parents=True)
        for index in range(35):
            snapshot = backup_dir / f"snapshot_{index:02d}.db"
            snapshot.write_bytes(b"")
            _touch(snapshot, time.time() - (100 - index))

        backup.manage_backup_rotation()

        assert len(list(backup_dir.glob("*.db"))) == 30
