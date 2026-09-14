import datetime
import logging
import os
import sqlite3
from contextlib import closing

log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

DEFAULT_DB_PATH = os.path.join(DATA_DIR, "traker_server.db")

LEGACY_DB_PATHS = (
    os.path.join(DATA_DIR, "traker.db"),
    os.path.join(DATA_DIR, "tracker.db"),
)

BACKUP_DIR = os.path.join(DATA_DIR, "backups")


def resolve_db_path(preferred: str = None):
    """The live database to snapshot, or None when there is not one yet."""
    candidates = (preferred,) if preferred else ()
    for candidate in candidates + (DEFAULT_DB_PATH,) + LEGACY_DB_PATHS:
        if os.path.exists(candidate):
            return candidate
    return None


def execute_safe_backup(db_path: str = None):
    """Snapshot the live database into BACKUP_DIR, then rotate."""
    db_path = resolve_db_path(db_path)
    if db_path is None:
        log.warning("No database to snapshot yet (looked in %s)", DATA_DIR)
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    db_base = os.path.splitext(os.path.basename(db_path))[0]
    backup_filename = f"{db_base}_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    try:
        with closing(sqlite3.connect(db_path)) as src_conn, \
                closing(sqlite3.connect(backup_path)) as dst_conn:
            with dst_conn:
                src_conn.backup(dst_conn)
    except (sqlite3.Error, OSError) as e:
        log.error("Backup failed: %s", e)
        return

    log.info("Wrote backup %s", backup_path)
    manage_backup_rotation()


def manage_backup_rotation(max_backups=30):
    backups = sorted(
        [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.endswith(".db")],
        key=os.path.getmtime
    )
    while len(backups) > max_backups:
        oldest = backups.pop(0)
        os.remove(oldest)
        log.info("Rotated out the oldest backup: %s", oldest)


if __name__ == "__main__":
    execute_safe_backup()
