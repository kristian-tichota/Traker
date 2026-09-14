import importlib
import socket
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "scripts"))

from tests.conftest import MEMBER_A_TOKEN  # noqa: E402

SEED_SCALE = 2.0
SEED_DAYS = 250


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="session")
def seeded_db_path(tmp_path_factory):
    seed_dev_db = importlib.import_module("seed_dev_db")
    path = tmp_path_factory.mktemp("perf") / "seeded.db"
    counts = seed_dev_db.seed(str(path), SEED_SCALE, SEED_DAYS, seed_value=20260906,
                              quiet=True)
    return str(path), counts


@pytest.fixture(scope="session")
def live_server(seeded_db_path):
    from werkzeug.serving import make_server

    from server.database import db_service
    from server.tables import reset_type_cache

    path, counts = seeded_db_path
    original = db_service.db_path
    db_service.db_path = path
    reset_type_cache()

    from server.app import create_app

    port = _free_port()
    httpd = make_server("127.0.0.1", port, create_app(), threaded=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", counts
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        db_service.db_path = original
        reset_type_cache()


@pytest.fixture
def live_client(live_server, profile_path):
    from src.database import DatabaseClient

    base_url, _counts = live_server
    return DatabaseClient(base_url=base_url, token=MEMBER_A_TOKEN)


@pytest.fixture
def ledger_counts(live_server):
    _base_url, counts = live_server
    return counts


@pytest.fixture
def settled(qapp):
    from PyQt6.QtCore import QThreadPool

    def _settle(timeout_ms=15000):
        QThreadPool.globalInstance().waitForDone(timeout_ms)
        qapp.processEvents()

    return _settle
