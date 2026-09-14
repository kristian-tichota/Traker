import pathlib
import subprocess
import sys

import pytest
from PyQt6.QtCore import QThreadPool

from src.database import REQUEST_TIMEOUT_S
from src.gui.main_window import MainWindow
from src.gui.views.beverage_view import BeveragesView
from src.gui.views.exercise_view import ExerciseView
from src.gui.views.food_views import FoodView
from src.gui.views.mobility_view import MobilityView
from src.gui.views.supplement_view import SupplementsView
from src.gui.workers import WorkerSignals

pytestmark = pytest.mark.gui


def drain(qapp, timeout_ms=5000):
    QThreadPool.globalInstance().waitForDone(timeout_ms)
    qapp.processEvents()


class TestTheWindowIsBuildable:
    def test_every_registered_tab_is_present(self, window):
        assert window.tabs.count() == len(MainWindow.TAB_REGISTRY)
        assert len(window.views) == len(MainWindow.TAB_REGISTRY)

    def test_each_tab_is_prefixed_with_the_key_that_selects_it(self, window):
        for index in range(window.tabs.count()):
            assert window.tabs.tabText(index).startswith(f"{window.tab_keys[index]}: ")

    def test_the_first_tab_is_refreshed_on_the_way_up(self, window, qapp):
        drain(qapp)

        assert 0 not in window.dirty_tabs


class TestTheProfileTheAppWritesItself:
    EVERYDAY = {"food", "beverages", "exercise", "mobility",
                "food_graphs", "exercise_graphs", "caffeine_graph"}

    def test_an_untouched_default_opens_the_everyday_tabs_and_no_others(
            self, qapp, profile_path, recording_db):
        import src.profile as profile_module

        profile_path.unlink()
        profile_module.UserProfile()
        profile_module.reload_profile()

        built = MainWindow(recording_db)
        try:
            assert set(built.views) == self.EVERYDAY
            assert built.tabs.count() == len(self.EVERYDAY)
        finally:
            built.close()
            drain(qapp)
            built.deleteLater()


class TestAnInstallWithoutTheGraphsExtra:
    GRAPH_TABS = {"food_graphs", "exercise_graphs", "heatmap",
                  "caffeine_graph", "supplement_graphs"}

    def test_the_window_still_builds(self, window_without_graphs):
        assert window_without_graphs.tabs.count() == (
            len(MainWindow.TAB_REGISTRY) - len(self.GRAPH_TABS))

    def test_only_the_graph_tabs_are_missing(self, window_without_graphs):
        every_key = {key for key, *_ in MainWindow.TAB_REGISTRY}

        assert set(window_without_graphs.views) == every_key - self.GRAPH_TABS

    def test_matplotlib_is_not_imported_just_by_opening_the_window(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        probe = ("import sys; sys.path.insert(0, %r); import src.gui.main_window; "
                 "print(sorted({'matplotlib', 'numpy', 'mpv'} & set(sys.modules)))" % str(root))

        said = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                              text=True, env={"QT_QPA_PLATFORM": "offscreen",
                                              "PATH": "/usr/bin:/bin",
                                              "HOME": str(root)}, timeout=120)

        assert said.returncode == 0, said.stderr
        assert said.stdout.strip() == "[]", (
            "an optional dependency is imported at module scope, so a core-only "
            "install can no longer open the window")


class TestWalkingEveryTab:
    def test_every_tab_can_be_visited_and_drawn(self, window, qapp):
        for index in range(window.tabs.count()):
            window.tabs.setCurrentIndex(index)
            drain(qapp)

        assert window.dirty_tabs == set(), "visiting a tab clears its staleness"

    def test_every_view_survives_a_refresh_with_no_rows(self, window, qapp):
        for view in window.views.values():
            view.refresh()
        drain(qapp)

    def test_a_write_marks_every_tab_stale_and_redraws_the_visible_one(self, window, qapp):
        drain(qapp)
        window.tabs.setCurrentIndex(1)
        drain(qapp)

        window.mark_all_tabs_stale()
        drain(qapp)

        assert window.dirty_tabs == set(range(window.tabs.count())) - {1}


class TestShutdownIsOrderly:
    def test_the_grace_exceeds_the_clients_own_timeout(self):
        assert MainWindow.SHUTDOWN_GRACE_MS > REQUEST_TIMEOUT_S * 1000

    def test_closing_stops_the_live_update_listener(self, window, qapp):
        listener = window.sync_listener

        window.close()
        qapp.processEvents()

        assert window.sync_listener is None
        assert listener._is_running is False
        assert listener._thread is None, "stop() joins it rather than leaving it running"

    def test_closing_stops_every_timer_under_every_view(self, window, qapp):
        from PyQt6.QtCore import QTimer

        window.close()
        qapp.processEvents()

        still_running = [
            timer for view in window.views.values()
            for timer in view.findChildren(QTimer) if timer.isActive()
        ]
        assert still_running == []

    def test_closing_lets_in_flight_work_finish(self, window, qapp):
        for view in window.views.values():
            if hasattr(view, "refresh"):
                view.refresh()

        window.close()
        qapp.processEvents()

        assert QThreadPool.globalInstance().activeThreadCount() == 0

    def test_closing_twice_is_not_an_error(self, window, qapp):
        window.close()
        qapp.processEvents()
        window.close()
        qapp.processEvents()


class TestTheCrashClass:
    @pytest.mark.parametrize(
        "view_class, receiver_name",
        [
            (ExerciseView, "_populate_first_table"),
            (MobilityView, "_populate_second_table"),
            (SupplementsView, "_populate_first_table"),
            (BeveragesView, "_populate_second_table"),
            (FoodView, "_populate_first_table"),
        ],
        ids=lambda value: getattr(value, "__name__", value),
    )
    def test_a_result_landing_after_teardown_reaches_nothing(
        self, qapp, profile_path, recording_db, view_class, receiver_name
    ):
        from PyQt6 import sip

        view = view_class(recording_db)
        signals = WorkerSignals()
        signals.result.connect(getattr(view, receiver_name))

        sip.delete(view)
        signals.result.emit([(1, "2026-09-05", "Anything")])

        qapp.processEvents()

    def test_every_worker_receiver_in_the_gui_is_a_named_callable(self):
        import ast
        import pathlib

        offenders = []
        for path in sorted(pathlib.Path("src/gui").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", getattr(node.func, "id", None))
                if name not in ("fetch", "run_in_background"):
                    continue
                receiver_at = 1 if name == "fetch" else 2
                args = node.args
                if len(args) > receiver_at and isinstance(args[receiver_at], ast.Lambda):
                    offenders.append(f"{path}:{args[receiver_at].lineno}")

        assert offenders == []


class TestTheWindowClaimsItsDesktop:
    def test_a_profile_naming_nothing_touches_no_configuration(
            self, window, desktop_session):
        assert window.window_home.holding is False
        assert desktop_session.rules_text() == ""

    def test_a_named_screen_is_asked_for_by_name(
            self, qapp, profile_path, recording_db, desktop_session, monkeypatch):
        import src.profile as profile_module
        from src.desktop.kwin import HOME_PLUGIN_NAME

        profile_module.UserProfile()
        written = profile_path.read_text(encoding="utf-8")
        assert 'screen = ""' in written, "the [window] template no longer says this"
        profile_path.write_text(written.replace('screen = ""', 'screen = "DP-1"'),
                                encoding="utf-8")
        profile_module.reload_profile()

        built = MainWindow(recording_db)
        try:
            loaded = [c for c in desktop_session.kwin_calls
                      if c[0] == "loadScript" and c[2] == HOME_PLUGIN_NAME]
            assert len(loaded) == 1
            source = open(loaded[0][1], encoding="utf-8").read()
            assert 'var wanted = "DP-1";' in source
            assert built.window_screen.engaged is True

            built.close()
            assert built.window_screen.engaged is False
        finally:
            drain(qapp)
            built.deleteLater()

    def test_a_profile_naming_no_screen_asks_for_no_script(
            self, window, desktop_session):
        from src.desktop.kwin import HOME_PLUGIN_NAME

        assert window.window_screen.engaged is False
        assert not [c for c in desktop_session.kwin_calls
                    if c[0] == "loadScript" and c[2] == HOME_PLUGIN_NAME]

    def test_a_named_desktop_and_activity_are_forced(
            self, qapp, profile_path, recording_db, desktop_session, monkeypatch):
        import src.profile as profile_module
        from src.desktop import kwin_rules

        pathlib.Path(desktop_session.kwinrc_path).write_text(
            "[Desktops]\nId_5=d-five\nNumber=6\n", encoding="utf-8")
        profile_module.UserProfile()
        written = profile_path.read_text(encoding="utf-8")
        assert 'desktop = ""' in written, "the [window] template no longer says this"
        profile_path.write_text(
            written.replace('desktop = ""', 'desktop = "Desktop 5"')
                   .replace('activity = ""', 'activity = "Personal"'),
            encoding="utf-8")
        profile_module.reload_profile()

        built = MainWindow(recording_db)
        try:
            rule = desktop_session.rules_text()
            assert f"[{kwin_rules.WINDOW_GROUP}]" in rule
            assert "desktops=d-five\n" in rule
            assert "activity=activity-one\n" in rule
            assert f"titlematch={kwin_rules.EXACT_MATCH}\n" in rule
            assert "title=Traker\n" in rule

            built.close()
            assert kwin_rules.WINDOW_GROUP not in desktop_session.rules_text()
        finally:
            drain(qapp)
            built.deleteLater()
