import pathlib

import pytest
import requests
from PyQt6.QtGui import QGuiApplication

import src.database.rows as rows
import src.gui.sync_listener as sync_listener
import src.gui.views.pomodoro_view as pomodoro_view
from tests.row_shapes import catalog_rows


class _FrozenClock:
    def __init__(self, millis):
        self._millis = millis

    def currentMSecsSinceEpoch(self):
        return self._millis


def advance(view, milliseconds):
    now = pomodoro_view.QDateTime.currentMSecsSinceEpoch()
    view.last_frame_timestamp = now - milliseconds
    frozen = _FrozenClock(now)
    original = pomodoro_view.QDateTime
    pomodoro_view.QDateTime = frozen
    try:
        view._engine_loop()
    finally:
        pomodoro_view.QDateTime = original


class RecordingDb:
    def __init__(self, foods=(), beverages=(), exercises=(), supplements=(), mobility=()):
        self.foods = list(foods)
        self.beverages = list(beverages)
        self.exercises = list(exercises)
        self.supplements = list(supplements)
        self.mobility = list(mobility)
        self.calls = []
        self.settings = {}
        self.setting_reads = []
        self.setting_batches = []
        self.invalidations = []
        self.result = (True, "Success")
        self.since_asked = []
        self.meal_sets = {}
        self.sets = {}

    def get_all_foods(self):
        return catalog_rows(self.foods, rows.FoodItemRow)

    def get_all_beverages(self):
        return catalog_rows(self.beverages, rows.BeverageItemRow)

    def get_all_exercises(self):
        return catalog_rows(self.exercises, rows.ExerciseItemRow)

    def get_all_supplements(self):
        return catalog_rows(self.supplements, rows.SupplementItemRow)

    def get_all_mobility(self):
        return catalog_rows(self.mobility, rows.MobilityItemRow)

    def get_all_exercise_names(self):
        return list(self.exercises)

    def _defined_sets(self, domain):
        if domain == "food" and getattr(self, "meal_sets", None):
            return self.meal_sets
        return getattr(self, "sets", {}).get(domain, {})

    def get_sets(self, domain):
        from src.database.rows import SetComponentRow, WorkoutComponentRow

        shape = WorkoutComponentRow if domain == "exercise" else SetComponentRow
        empty = [None] * (len(shape._fields) - 3)
        rows, next_id = [], 1
        for set_name, components in self._defined_sets(domain).items():
            if not components:
                rows.append(shape.from_server([None, set_name, None, *empty]))
                continue
            for item_name, amount in components:
                written = amount if isinstance(amount, tuple) else (float(amount),)
                rows.append(shape.from_server([next_id, set_name, item_name, *written]))
                next_id += 1
        return rows

    def get_set_names(self, domain):
        return list(dict.fromkeys(row.set_name for row in self.get_sets(domain)))

    def invalidate(self, domains=None):
        self.invalidations.append(None if domains is None else tuple(domains))

    def get_setting(self, key, default):
        self.setting_reads.append(key)
        return self.settings.get(key, default)

    def get_settings(self, keys, defaults=None):
        keys = list(keys)
        self.setting_reads.extend(keys)
        self.setting_batches.append(tuple(keys))
        fallbacks = defaults or {}
        return {key: self.settings.get(key, fallbacks.get(key, "")) for key in keys}

    def set_setting(self, key, value):
        self.calls.append(("set_setting", (key, value)))
        if self.result[0]:
            self.settings[key] = value
        return self.result

    def get_pomodoro_daily_summary(self):
        return []

    def get_pomodoro_dsi_overrides(self):
        return {}

    def get_pomodoro_heartbeats_for_day(self, date):
        return {}

    def get_pomodoro_events_for_day(self, date):
        return []

    def _rows(self, attribute, since=None):
        if since is not None:
            self.since_asked.append((attribute, since))
        rows = list(getattr(self, attribute, []))
        if since is None:
            return rows
        return [row for row in rows if str(row.date) >= since]

    def get_food_logs(self, since=None):
        return self._rows("food_logs", since)

    def get_beverage_logs(self, since=None):
        return self._rows("beverage_logs", since)

    def get_exercise_logs(self, since=None):
        return self._rows("exercise_logs", since)

    def get_supplement_logs(self, since=None):
        return self._rows("supplement_logs", since)

    def get_mobility_logs(self, since=None):
        return self._rows("mobility_logs", since)

    def get_daily_aggregates(self):
        return self._rows("daily_aggregates")

    def get_chores(self):
        return list(getattr(self, "chores", []))

    def get_chore_completions(self, since=None):
        return list(getattr(self, "chore_completions", []))

    def complete_chore(self, payload):
        return self._record("complete_chore", (payload,))

    def get_training_plans(self):
        return list(getattr(self, "training_plans", []))

    def get_plan_sessions(self, plan_id):
        return [row for row in getattr(self, "plan_sessions", [])]

    def get_plan_movements(self, plan_id):
        return [row for row in getattr(self, "plan_movements", [])]

    def get_exercise_history_by_name(self, name):
        return self._rows("exercise_history")

    def get_activity_heatmap_data(self, since=None):
        if since is not None:
            self.since_asked.append(("heatmap_points", since))
        points = dict(getattr(self, "heatmap_points", {}))
        if since is None:
            return points
        return {date: value for date, value in points.items() if date >= since}

    def delete_item_by_name(self, name):
        self.calls.append(("delete_item_by_name", (name,)))
        if self.result[0]:
            return True, f" Removed '{name}' from 1 catalog."
        return self.result

    def _record(self, name, args):
        self.calls.append((name, args))
        return self.result

    def __getattr__(self, name):
        if name.startswith(("add_", "set_", "log_", "clear_", "delete_", "update_")):
            return lambda *args, **kwargs: self._record(name, args)
        raise AttributeError(name)

    def last(self, name):
        for called, args in reversed(self.calls):
            if called == name:
                return args[0] if len(args) == 1 else args
        raise AssertionError(f"{name} was never called; recorded: {[c for c, _ in self.calls]}")

    def called(self, name):
        return any(called == name for called, _ in self.calls)


def no_idle_answer():
    return None


@pytest.fixture(autouse=True)
def idle_unanswered(monkeypatch):
    """Refuse to answer how long this session has been idle."""
    monkeypatch.setattr(pomodoro_view, "session_idle_ms", no_idle_answer)


@pytest.fixture
def recording_db():
    return RecordingDb(
        foods=["Rolled Oats", "Rolled Oat Bar", "Greek Yoghurt", "Řízek s bramborem"],
        beverages=["Black Coffee", "Green Tea"],
        exercises=["Overhead Press", "Plank", "Bench Press"],
        supplements=["Morning Stack", "Evening Stack"],
        mobility=["Hip Opener"],
    )


TABS_OFF_BY_DEFAULT = ("pomodoro", "supplements", "supplement_graphs",
                       "heatmap", "plans", "chores")


@pytest.fixture(autouse=True)
def all_tabs(profile_path):
    """Switch every tab on, so a window test exercises the whole strip."""
    import src.profile as profile_module

    profile_module.UserProfile()
    written = profile_path.read_text(encoding="utf-8")
    for key in TABS_OFF_BY_DEFAULT:
        assert f"\n{key} = false" in written, f"[windows] no longer switches {key} off"
        written = written.replace(f"\n{key} = false", f"\n{key} = true")
    profile_path.write_text(written, encoding="utf-8")
    profile_module.reload_profile()
    return profile_path


@pytest.fixture
def chores_on_break(profile_path):
    """Build a profile that puts the chore board in a break."""
    import src.profile as profile_module

    profile_module.UserProfile()
    written = profile_path.read_text(encoding="utf-8")
    assert "on_break = false" in written, "the [chores] template no longer says this"
    profile_path.write_text(written.replace("on_break = false", "on_break = true"),
                            encoding="utf-8")
    profile_module.reload_profile()
    return profile_path


@pytest.fixture
def strict_timer(profile_path):
    import src.profile as profile_module

    profile_module.UserProfile()
    written = profile_path.read_text(encoding="utf-8")
    assert "strict = false" in written, "the [timer] template no longer says this"
    profile_path.write_text(written.replace("strict = false", "strict = true"),
                            encoding="utf-8")
    profile_module.reload_profile()
    return profile_path


@pytest.fixture
def settled(qapp):
    from PyQt6.QtCore import QThreadPool

    def _settle(timeout_ms=2000):
        QThreadPool.globalInstance().waitForDone(timeout_ms)
        qapp.processEvents()

    return _settle


class UnreachableSession:
    def get(self, *args, **kwargs):
        raise requests.ConnectionError("household service is not running")

    def close(self):
        pass


def _built_window(qapp, recording_db, monkeypatch):
    from src.gui.main_window import MainWindow

    monkeypatch.setattr(sync_listener.requests, "Session", UnreachableSession)

    built = MainWindow(recording_db)
    yield built

    timer = built.views.get("pomodoro")
    if timer is not None and timer.holds_the_screens():
        timer._clear_overlays()

    if built.isVisible() or built.sync_listener is not None:
        built.close()
    qapp.processEvents()
    built.deleteLater()
    qapp.processEvents()


@pytest.fixture(autouse=True)
def app_id(qapp):
    previous = QGuiApplication.desktopFileName()
    QGuiApplication.setDesktopFileName("Traker.desktop")
    yield "traker"
    QGuiApplication.setDesktopFileName(previous)


@pytest.fixture
def window(qapp, profile_path, recording_db, monkeypatch):
    yield from _built_window(qapp, recording_db, monkeypatch)


@pytest.fixture
def strict_window(qapp, strict_timer, recording_db, monkeypatch):
    yield from _built_window(qapp, recording_db, monkeypatch)


@pytest.fixture
def window_without_graphs(qapp, profile_path, recording_db, monkeypatch):
    """Build a window as if the graphs extra were not installed."""
    import src.gui.main_window as main_window

    real = main_window.import_module

    def refuse(name, *args, **kwargs):
        if name.startswith("src.gui.graphs."):
            raise ImportError("No module named 'matplotlib'")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(main_window, "import_module", refuse)
    yield from _built_window(qapp, recording_db, monkeypatch)


class RecordingSession:
    def __init__(self):
        self.kwin_calls = []
        self.notifications = []
        self.answers = {"loadScript": 3, "unloadScript": True, "start": None}
        self.guard_calls = []
        self.subscriptions = []
        self.desktop = "desktop-one"
        self.activity = "activity-one"
        self.kwin_reachable = True
        self.reconfigures = 0
        self.rules_path = None
        self.kwinrc_path = None
        self.activity_names = {"activity-one": "Personal",
                               "activity-two": "Work"}

    def kwin(self, method, *args):
        self.kwin_calls.append((method,) + args)
        if not self.kwin_reachable:
            return False, None
        return True, self.answers.get(method)

    def notify(self, summary, body, **hints):
        self.notifications.append((summary, body, hints))
        return True

    def reconfigure(self):
        self.reconfigures += 1
        return self.kwin_reachable

    def activities(self, service, path, interface, method, *args):
        self.guard_calls.append((path, method) + tuple(str(a) for a in args))
        if not self.kwin_reachable:
            return False, None
        if method == "ListActivities":
            return True, list(self.activity_names)
        if method == "ActivityName":
            return True, self.activity_names.get(str(args[0]), "")
        return True, None

    def rules_text(self):
        path = pathlib.Path(self.rules_path)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def kwin_methods(self):
        return [call[0] for call in self.kwin_calls]

    def guard(self, service, path, interface, method, *args):
        self.guard_calls.append((method,) + tuple(str(a) for a in args))
        if method == "Get" and args[-1:] == ("current",):
            return True, self.desktop
        if method == "CurrentActivity":
            return True, self.activity
        return True, None

    def listen(self, service, path, interface, signal, slot):
        self.subscriptions.append(signal)
        return True

    def deafen(self, service, path, interface, signal, slot):
        self.subscriptions.remove(signal) if signal in self.subscriptions else None
        return True

    @property
    def guard_methods(self):
        return [call[0] for call in self.guard_calls]


@pytest.fixture(autouse=True)
def desktop_session(monkeypatch, tmp_path):
    recorded = RecordingSession()
    monkeypatch.setattr("src.desktop.kwin._session_caller", recorded.kwin)
    monkeypatch.setattr("src.desktop.notify.notify", recorded.notify)
    recorded.rules_path = str(tmp_path / "kwinrulesrc")
    recorded.kwinrc_path = str(tmp_path / "kwinrc")
    monkeypatch.setattr("src.desktop.kwin_rules.DEFAULT_PATH", recorded.rules_path)
    monkeypatch.setattr("src.desktop.kde_config.KWINRC_PATH", recorded.kwinrc_path)
    monkeypatch.setattr("src.desktop.kwin_rules._reconfigure", recorded.reconfigure)
    monkeypatch.setattr("src.desktop.kwin_rules.session_call", recorded.activities)
    monkeypatch.setattr("src.desktop.switch_guard._session_call", recorded.guard)
    monkeypatch.setattr("src.desktop.switch_guard._subscribe", recorded.listen)
    monkeypatch.setattr("src.desktop.switch_guard._unsubscribe", recorded.deafen)
    return recorded
