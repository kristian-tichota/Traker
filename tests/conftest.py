import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["QT_QPA_PLATFORM"] = os.environ.get("TRAKER_TEST_QT_PLATFORM", "offscreen")
os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="traker-mpl-"))

_SANDBOX = Path(tempfile.mkdtemp(prefix="traker-tests-"))
(_SANDBOX / "server.toml").write_text(
    """[[members]]
username = "member-a"
token = "test-token-member-a"

[[members]]
username = "member-b"
token = "test-token-member-b"
""", encoding="utf-8")
os.environ["TRAKER_SERVER_CONFIG"] = str(_SANDBOX / "server.toml")

import src.profile  # noqa: E402  (must follow the sys.path edit)

src.profile.PROFILE_PATH = str(_SANDBOX / "user_profile.toml")

import server.config  # noqa: E402

server.config.DB_PATH = str(_SANDBOX / "traker_server.db")

import src.desktop.rest_queue  # noqa: E402

src.desktop.rest_queue.DEFAULT_PATH = str(_SANDBOX / "rest-queue.m3u")

import src.desktop.kwin_rules  # noqa: E402
import src.desktop.kde_config  # noqa: E402

src.desktop.kwin_rules.DEFAULT_PATH = str(_SANDBOX / "kwinrulesrc")
src.desktop.kde_config.KWINRC_PATH = str(_SANDBOX / "kwinrc")

from server.config import USER_TOKENS  # noqa: E402

_SEEDED = list(USER_TOKENS.items())
MEMBER_A_TOKEN, MEMBER_A_NAME = _SEEDED[0]
MEMBER_B_TOKEN, MEMBER_B_NAME = _SEEDED[1]


@pytest.fixture
def profile_path(tmp_path, monkeypatch):
    path = tmp_path / "user_profile.toml"
    monkeypatch.setattr(src.profile, "PROFILE_PATH", str(path))
    return path


@pytest.fixture
def user_profile(profile_path):
    return src.profile.UserProfile()


@pytest.fixture
def write_profile(profile_path):
    def _write(toml_text: str):
        profile_path.write_text(toml_text, encoding="utf-8")
        return src.profile.UserProfile()

    return _write


@pytest.fixture
def server_db(tmp_path, monkeypatch):
    from server.database import db_service
    from server.tables import reset_type_cache

    monkeypatch.setattr(db_service, "db_path", str(tmp_path / "traker_server.db"))
    db_service.init_db()
    reset_type_cache()
    return db_service


@pytest.fixture
def flask_app(server_db):
    from server.app import create_app

    app = create_app()
    return app


class MemberApi:
    def __init__(self, client, token, username):
        self._client = client
        self.token = token
        self.username = username
        self.headers = {"Authorization": f"Bearer {token}"}

    def get(self, path, **kwargs):
        return self._client.get(path, headers=self.headers, **kwargs)

    def post(self, path, **kwargs):
        return self._client.post(path, headers=self.headers, **kwargs)

    def patch(self, path, **kwargs):
        return self._client.patch(path, headers=self.headers, **kwargs)

    def delete(self, path, **kwargs):
        return self._client.delete(path, headers=self.headers, **kwargs)


@pytest.fixture
def anon(flask_app):
    return flask_app.test_client()


@pytest.fixture
def member_a(flask_app):
    return MemberApi(flask_app.test_client(), MEMBER_A_TOKEN, MEMBER_A_NAME)


@pytest.fixture
def member_b(flask_app):
    return MemberApi(flask_app.test_client(), MEMBER_B_TOKEN, MEMBER_B_NAME)

OATS = {
    "name": "Rolled Oats", "category": "Carbs", "energy": 380.0,
    "fat_total": 7.0, "fat_saturated": 1.2, "carbs_total": 60.0,
    "carbs_sugars": 1.0, "fibre": 10.0, "protein": 13.0,
    "salt": 0.0, "serving_size": 50.0,
}
BLACK_COFFEE = {"name": "Black Coffee", "caffeine_mg": 80.0, "antioxidants_mg": 200.0}
OVERHEAD_PRESS = {
    "name": "Overhead Press", "muscle_group": "Shoulders", "movement_pattern": "Push",
    "secondary_muscles": "Triceps", "plane_of_motion": "Frontal", "joint_mechanics": "Compound",
    "equipment_type": "Dumbbell", "unilateral_bilateral": "Bilateral", "metric_type": "Reps",
}
PLANK = dict(OVERHEAD_PRESS, name="Plank", muscle_group="Core", metric_type="Seconds")
MORNING_STACK = {"name": "Morning Stack", "b12_mcg": 500.0, "creatine_g": 5.0, "zinc_mg": 15.0}
HIP_OPENER = {"name": "Hip Opener", "mets": 3.0, "notes": "Daily"}


@pytest.fixture
def seeded_catalog(member_a):
    member_a.post("/api/catalog/food", json=OATS)
    member_a.post("/api/catalog/beverage", json=BLACK_COFFEE)
    member_a.post("/api/catalog/exercise", json=OVERHEAD_PRESS)
    member_a.post("/api/catalog/exercise", json=PLANK)
    member_a.post("/api/catalog/supplement", json=MORNING_STACK)
    member_a.post("/api/catalog/mobility", json=HIP_OPENER)
    return member_a


class _BridgedResponse:
    def __init__(self, werkzeug_response):
        self.status_code = werkzeug_response.status_code
        self.text = werkzeug_response.get_data(as_text=True)

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} for bridged request")


@pytest.fixture
def bridge_requests(flask_app, monkeypatch):
    import requests

    test_client = flask_app.test_client()

    def _path(url):
        return urlsplit(url).path

    def fake_get(url, headers=None, params=None, timeout=None, **kwargs):
        return _BridgedResponse(
            test_client.get(_path(url), headers=headers or {}, query_string=params or {})
        )

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        return _BridgedResponse(
            test_client.post(_path(url), headers=headers or {}, json=json if json is not None else {})
        )

    def fake_patch(url, headers=None, json=None, timeout=None, **kwargs):
        return _BridgedResponse(
            test_client.patch(_path(url), headers=headers or {}, json=json if json is not None else {})
        )

    def fake_delete(url, headers=None, timeout=None, **kwargs):
        return _BridgedResponse(test_client.delete(_path(url), headers=headers or {}))

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "patch", fake_patch)
    monkeypatch.setattr(requests, "delete", fake_delete)
    return test_client


@pytest.fixture
def offline_requests(monkeypatch):
    import requests

    def _refuse(*args, **kwargs):
        raise requests.ConnectionError("household service is not running")

    for verb in ("get", "post", "patch", "delete"):
        monkeypatch.setattr(requests, verb, _refuse)


@pytest.fixture
def db_client(bridge_requests, profile_path):
    from src.database import DatabaseClient

    return DatabaseClient(base_url="http://traker.test", token=MEMBER_A_TOKEN)


@pytest.fixture
def db_client_b(bridge_requests, profile_path):
    from src.database import DatabaseClient

    return DatabaseClient(base_url="http://traker.test", token=MEMBER_B_TOKEN)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()
