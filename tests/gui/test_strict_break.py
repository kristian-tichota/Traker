import json
import pathlib
import re

import pytest
from PyQt6.QtCore import QDateTime, QEvent, QRect, Qt, QThreadPool
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget

import src.gui.views.pomodoro_view as pomodoro_view
from src.config import PALETTE
from src.desktop.activities import VIDEO, BreakActivity
from src.gui.views.pomodoro_view import RELEASE_KEY, PomodoroView, StrictOverlay
from tests.gui.conftest import advance

pytestmark = [pytest.mark.gui, pytest.mark.exact, pytest.mark.accessibility]


class FakeShell(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Traker")


@pytest.fixture
def timer(qapp, app_id, strict_timer, recording_db):
    view = PomodoroView(recording_db, tray_icon=None)
    view.refresh_timer.stop()
    view.stress_calendar.anim_timer.stop()
    view.last_logged_minute = -1
    yield view
    view.shutdown()
    QThreadPool.globalInstance().waitForDone(2000)
    view.deleteLater()


@pytest.fixture
def shelled(qapp, app_id, strict_timer, recording_db):
    shell = FakeShell()
    view = PomodoroView(recording_db, tray_icon=None)
    view.setParent(shell)
    view.refresh_timer.stop()
    view.stress_calendar.anim_timer.stop()
    view.last_logged_minute = -1
    yield view, shell
    view.shutdown()
    QThreadPool.globalInstance().waitForDone(2000)
    shell.deleteLater()


def hold_for(view, seconds):
    view.begin_hold()
    view._hold_started_ms = QDateTime.currentMSecsSinceEpoch() - int(seconds * 1000)
    view._hold_tick()


def enter_strict_break(view):
    view._skip_phase()
    assert view._strict_break_is_holding()


def send_key(view, key, event_type=QEvent.Type.KeyPress):
    QApplication.sendEvent(view, QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier))


def two_screens(view):
    screen = QApplication.primaryScreen()
    view.screens_to_cover = lambda: [screen, screen]


def font_size_of(widget) -> int:
    return int(re.search(r"font-size: (\d+)px", widget.styleSheet()).group(1))


def corner_colour(widget) -> str:
    return widget.grab().toImage().pixelColor(2, 2).name()


def start_recording(recording_db):
    QThreadPool.globalInstance().waitForDone(2000)
    recording_db.calls.clear()


class TestHoldingEveryDesktop:
    def test_a_strict_break_asks_kwin_to_hold_it(self, timer, desktop_session):
        enter_strict_break(timer)

        assert desktop_session.kwin_methods() == ["unloadScript", "loadScript", "start"]
        assert timer.kwin_pin.engaged is True

    def test_the_script_holds_this_application_and_nothing_else(self, timer, desktop_session, app_id):
        enter_strict_break(timer)

        path = desktop_session.kwin_calls[1][1]
        assert f'var target = "{app_id}";' in open(path).read()

    def test_the_app_id_is_the_desktop_entry_the_launch_declares(self, app_id):
        from src.desktop.kwin import default_app_id

        assert default_app_id() == "Traker"

    def test_the_break_running_out_gives_every_desktop_back(self, timer):
        enter_strict_break(timer)

        advance(timer, timer.break_ms + 1000)

        assert timer.waiting_for_work_start is True
        assert timer.overlays
        assert timer.kwin_pin.engaged is False

    def test_starting_focus_leaves_them_given_back(self, timer):
        enter_strict_break(timer)
        advance(timer, timer.break_ms + 1000)

        timer._toggle_timer()

        assert timer.kwin_pin.engaged is False
        assert timer._strict_engaged is False

    def test_shutdown_gives_every_desktop_back(self, timer, desktop_session):
        enter_strict_break(timer)

        timer.shutdown()

        assert timer.kwin_pin.engaged is False
        assert desktop_session.kwin_methods()[-1] == "unloadScript"

    def test_a_session_without_kwin_still_takes_the_screens(self, timer, desktop_session):
        desktop_session.kwin_reachable = False

        enter_strict_break(timer)

        assert timer.kwin_pin.engaged is False
        assert timer._strict_engaged is True


class TestForcingTheWallsOntoEveryDesktop:
    def test_a_break_writes_the_rule_and_has_kwin_read_it(self, timer, desktop_session):
        enter_strict_break(timer)

        rule = desktop_session.rules_text()
        assert "[traker-rest]" in rule
        assert f"title={pomodoro_view.WALL_CAPTION}\n" in rule
        assert desktop_session.reconfigures == 1
        assert timer.rest_rule.holding is True

    def test_it_is_in_force_before_the_first_wall_opens(self, timer, desktop_session):
        seen = []
        wall = pomodoro_view.StrictOverlay

        def note(*args, **kwargs):
            seen.append(desktop_session.reconfigures)
            return wall(*args, **kwargs)

        pomodoro_view.StrictOverlay = note
        try:
            enter_strict_break(timer)
        finally:
            pomodoro_view.StrictOverlay = wall

        assert seen and all(count == 1 for count in seen)

    def test_a_rule_kwin_never_discarded_is_gone_by_the_next_launch(
            self, qapp, app_id, strict_timer, recording_db, desktop_session):
        from src.desktop import kwin_rules

        pathlib.Path(desktop_session.rules_path).write_text(
            kwin_rules.written("", kwin_rules.REST_GROUP,
                               kwin_rules.rest_keys(pomodoro_view.WALL_CAPTION)),
            encoding="utf-8")

        view = PomodoroView(recording_db, tray_icon=None)
        view.refresh_timer.stop()
        view.stress_calendar.anim_timer.stop()
        try:
            assert "[traker-rest]" not in desktop_session.rules_text()
        finally:
            view.shutdown()
            QThreadPool.globalInstance().waitForDone(2000)
            view.deleteLater()

    def test_a_session_that_never_had_one_is_not_written_to(
            self, qapp, app_id, strict_timer, recording_db, desktop_session):
        view = PomodoroView(recording_db, tray_icon=None)
        view.refresh_timer.stop()
        view.stress_calendar.anim_timer.stop()
        try:
            assert not pathlib.Path(desktop_session.rules_path).exists()
            assert desktop_session.reconfigures == 0
        finally:
            view.shutdown()
            QThreadPool.globalInstance().waitForDone(2000)
            view.deleteLater()

    def test_the_break_running_out_gives_the_desktops_back_and_not_the_front(
            self, timer, desktop_session):
        enter_strict_break(timer)

        advance(timer, timer.break_ms + 1000)

        assert timer.rest_rule.holding is True
        assert timer.rest_rule.everywhere is False
        assert "[traker-rest]" in desktop_session.rules_text()

    def test_starting_focus_takes_it_back_out(self, timer, desktop_session):
        enter_strict_break(timer)
        advance(timer, timer.break_ms + 1000)

        send_key(timer, RELEASE_KEY)

        assert timer.rest_rule.holding is False
        assert "[traker-rest]" not in desktop_session.rules_text()

    def test_a_profile_that_would_rather_not_have_one(self, qapp, app_id,
                                                      strict_timer, recording_db,
                                                      desktop_session):
        written = strict_timer.read_text(encoding="utf-8")
        assert "pin_with_rule = true" in written, "the template no longer says this"
        strict_timer.write_text(
            written.replace("pin_with_rule = true", "pin_with_rule = false"),
            encoding="utf-8")
        import src.profile as profile_module
        profile_module.reload_profile()

        view = PomodoroView(recording_db, tray_icon=None)
        view.refresh_timer.stop()
        view.stress_calendar.anim_timer.stop()
        try:
            assert view.rest_rule is None
            enter_strict_break(view)
            assert desktop_session.rules_text() == ""
            assert view._strict_engaged is True
        finally:
            view.shutdown()
            QThreadPool.globalInstance().waitForDone(2000)
            view.deleteLater()


class TestWhichScreenTheBreakTakes:
    def test_it_is_the_screen_this_window_is_on(self, timer):
        elsewhere = object()
        timer.windowHandle = lambda: type("Handle", (), {"screen": lambda _: elsewhere})()

        assert timer._member_screen() is elsewhere

    def test_a_window_no_compositor_has_placed_yet_falls_back(self, timer):
        timer.windowHandle = lambda: None

        assert timer._member_screen() == QApplication.primaryScreen()

    def test_every_screen_is_walled(self, shelled):
        view, _shell = shelled
        two_screens(view)

        enter_strict_break(view)

        assert len(view.overlays) == 2
        assert all(wall.isWindow() for wall in view.overlays)

    def test_what_it_shows_is_on_the_primary_one(self, shelled):
        view, _shell = shelled
        two_screens(view)

        enter_strict_break(view)

        assert view._media_host is view._wall_for(QApplication.primaryScreen())
        assert view._media_host.media is view.media_surface

    def test_the_focus_starts_on_the_wall_the_member_is_at(self, shelled,
                                                           desktop_session):
        view, _shell = shelled
        two_screens(view)

        enter_strict_break(view)

        loaded = [call for call in desktop_session.kwin_calls
                  if call[0] == "loadScript"]
        assert loaded
        source = open(loaded[0][1], encoding="utf-8").read()
        wanted = view._wall_for(view._screen_taken).windowTitle()

        assert f"var wanted = {json.dumps(wanted)};" in source
        assert wanted != view.window().windowTitle()

    def test_the_break_keeps_the_screen_it_took(self, shelled):
        view, _shell = shelled
        enter_strict_break(view)
        taken = view._screen_taken

        view._member_screen = lambda: object()
        view._redraw_break_surfaces()

        assert view._screen_taken is taken

    def test_the_next_break_asks_again(self, shelled):
        view, _shell = shelled
        enter_strict_break(view)

        view._clear_overlays()

        assert view._screen_taken is None


class TestTheApplicationWindowIsLeftAlone:
    def test_a_break_does_not_touch_its_flags(self, shelled):
        view, shell = shelled
        before = shell.windowFlags()

        enter_strict_break(view)

        assert shell.windowFlags() == before
        assert not shell.windowFlags() & Qt.WindowType.WindowStaysOnTopHint

    def test_a_wall_covers_the_screen_it_is_on_instead(self, shelled):
        view, _shell = shelled

        enter_strict_break(view)

        assert view._wall_for(view._screen_taken) in view.overlays

    def test_the_walls_are_not_children_of_it(self, shelled):
        view, shell = shelled
        two_screens(view)

        enter_strict_break(view)

        assert all(wall.parent() is None for wall in view.overlays)
        assert shell.findChildren(StrictOverlay) == []

    def test_nothing_is_handed_back_at_the_end_of_one(self, shelled):
        view, shell = shelled
        before = shell.windowFlags()
        enter_strict_break(view)
        advance(view, view.break_ms + 1000)

        view._toggle_timer()

        assert shell.windowFlags() == before
        assert view.overlays == []


class FakeScreen:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name

    def geometry(self):
        return QRect(0, 0, 800, 800)


def named_outputs(view, monkeypatch, *names):
    outputs = [FakeScreen(name) for name in names]
    view.screens_to_cover = lambda: list(outputs)
    monkeypatch.setattr(StrictOverlay, "setScreen", lambda self, screen: None)
    return outputs


class TestWhichOutputShowsTheFile:
    def test_the_named_output_is_the_one_it_uses(self, timer):
        left, right = FakeScreen("DP-2"), FakeScreen("DP-1")
        timer.screens_to_cover = lambda: [left, right]
        timer._media_screen_name = "DP-1"

        assert timer._media_screen() is right

    def test_a_name_no_output_has_falls_back_and_says_so(self, timer, caplog):
        timer.screens_to_cover = lambda: [FakeScreen("DP-2")]
        timer._media_screen_name = "HDMI-A-3"

        with caplog.at_level("WARNING"):
            assert timer._media_screen() == QApplication.primaryScreen()

    def test_unset_it_follows_the_window(self, timer):
        left, right = FakeScreen("DP-2"), FakeScreen("DP-1")
        timer.screens_to_cover = lambda: [left, right]
        timer._media_screen_name = ""
        timer._window_screen_name = "DP-1"

        assert timer._media_screen() is right

    def test_the_break_may_still_name_the_other_screen(self, timer):
        left, right = FakeScreen("DP-2"), FakeScreen("DP-1")
        timer.screens_to_cover = lambda: [left, right]
        timer._media_screen_name = "DP-2"
        timer._window_screen_name = "DP-1"

        assert timer._media_screen() is left

    def test_neither_named_is_still_qts_primary(self, timer):
        timer.screens_to_cover = lambda: [FakeScreen("DP-2")]
        timer._media_screen_name = ""
        timer._window_screen_name = ""

        assert timer._media_screen() == QApplication.primaryScreen()

    def test_a_window_screen_no_output_has_falls_through_too(self, timer, caplog):
        timer.screens_to_cover = lambda: [FakeScreen("DP-2")]
        timer._media_screen_name = ""
        timer._window_screen_name = "HDMI-A-3"

        with caplog.at_level("WARNING"):
            assert timer._media_screen() == QApplication.primaryScreen()

        assert "HDMI-A-3" in caplog.text

    def test_an_empty_setting_keeps_qt_s_answer(self, timer):
        assert timer._media_screen_name == ""
        assert timer._media_screen() == QApplication.primaryScreen()

    def test_the_profile_is_what_says_it(self, qapp, app_id, strict_timer,
                                        recording_db):
        written = strict_timer.read_text(encoding="utf-8")
        assert 'media_screen = ""' in written, "the template no longer says this"
        strict_timer.write_text(
            written.replace('media_screen = ""', 'media_screen = "DP-1"'),
            encoding="utf-8")
        import src.profile as profile_module
        profile_module.reload_profile()

        view = PomodoroView(recording_db, tray_icon=None)
        view.refresh_timer.stop()
        view.stress_calendar.anim_timer.stop()

        assert view._media_screen_name == "DP-1"

        view.shutdown()
        QThreadPool.globalInstance().waitForDone(2000)
        view.deleteLater()

    def test_the_wall_that_shows_it_is_the_one_the_focus_goes_to(self, shelled,
                                                                 desktop_session):
        view, _shell = shelled
        two_screens(view)

        enter_strict_break(view)

        loaded = [call for call in desktop_session.kwin_calls
                  if call[0] == "loadScript"]
        source = open(loaded[0][1], encoding="utf-8").read()
        assert f"var wanted = {json.dumps(view._media_host.windowTitle())};" in source


class TestTheCompositorIsToldWhereEachWallGoes:
    def script_of(self, desktop_session):
        loaded = [call for call in desktop_session.kwin_calls
                  if call[0] == "loadScript"]
        assert loaded, "KWin was never asked to load anything"
        return open(loaded[0][1], encoding="utf-8").read()

    def test_the_script_is_given_a_map_of_them(self, timer, desktop_session):
        enter_strict_break(timer)

        assert timer.wall_outputs() == {}
        assert "var wallOutputs = " in self.script_of(desktop_session)

    def test_a_wall_is_keyed_by_its_title_and_names_its_output(self, timer, monkeypatch):
        named_outputs(timer, monkeypatch, "DP-1")

        enter_strict_break(timer)

        assert timer.wall_outputs() == {"Traker rest \u2014 DP-1": "DP-1"}

    def test_an_output_with_no_name_is_left_out(self, timer):
        enter_strict_break(timer)

        assert timer.overlays[0].screen_covered.name() == ""
        assert timer.wall_outputs() == {}

    def test_what_it_asks_for_reaches_the_pin(self, timer, desktop_session):
        timer.kwin_pin.wall_outputs = {"stale": "DP-9"}

        enter_strict_break(timer)

        assert timer.kwin_pin.wall_outputs == timer.wall_outputs()

    def test_the_client_no_longer_re_shows_a_wall_the_script_can_move(self, timer):
        enter_strict_break(timer)
        wall = timer.overlays[0]
        wall.covers_its_own_screen = lambda: False
        asked = []
        wall.take_its_screen_again = lambda: asked.append(1)

        timer._redraw_break_surfaces()

        assert timer.kwin_pin.engaged is True
        assert asked == []
        assert wall.stands_corrected is True

    def test_a_session_with_no_script_still_takes_its_screen_back(self, timer):
        timer.kwin_pin = None
        enter_strict_break(timer)
        wall = timer.overlays[0]
        wall.covers_its_own_screen = lambda: False
        asked = []
        wall.take_its_screen_again = lambda: asked.append(1)

        timer._redraw_break_surfaces()

        assert asked == [1]


class TestAMonitorSwitchedOffAndBackOn:
    def test_the_screens_are_watched_while_a_break_has_walls(self, timer):
        enter_strict_break(timer)
        wall = timer.overlays[0]

        QApplication.instance().screenRemoved.emit(wall.screen_covered)

        assert wall.screen_covered is None
        assert timer._screens_settling.isActive() is True

    def test_an_output_that_goes_is_let_go_of_at_once(self, timer, monkeypatch):
        _left, right = named_outputs(timer, monkeypatch, "DP-2", "DP-1")
        enter_strict_break(timer)
        wall = timer._wall_for(right)

        timer._an_output_went(right)

        assert wall.screen_covered is None
        assert wall.output_name == "DP-1"
        assert wall.isVisible() is False

    def test_the_engine_still_asks_every_wall_where_it_is(self, timer, monkeypatch):
        left, right = named_outputs(timer, monkeypatch, "DP-2", "DP-1")
        timer.kwin_pin = None
        enter_strict_break(timer)
        timer._an_output_went(right)

        advance(timer, 1000)

        assert timer.wall_outputs() == {timer._wall_for(left).windowTitle(): "DP-2"}

    def test_a_monitor_that_came_back_is_walled_again(self, timer, monkeypatch):
        left, right = named_outputs(timer, monkeypatch, "DP-2", "DP-1")
        enter_strict_break(timer)
        kept = timer._wall_for(left)

        timer._an_output_went(right)
        timer.screens_to_cover = lambda: [left]
        timer._rewall_for_the_outputs()
        back = FakeScreen("DP-1")
        timer.screens_to_cover = lambda: [left, back]
        timer._rewall_for_the_outputs()

        assert [wall.screen_covered for wall in timer.overlays] == [left, back]
        assert timer._wall_for(left) is kept

    def test_the_compositor_is_told_the_walls_there_are_now(self, timer, monkeypatch,
                                                            desktop_session):
        left, right = named_outputs(timer, monkeypatch, "DP-2", "DP-1")
        enter_strict_break(timer)
        timer._an_output_went(right)
        back = FakeScreen("DP-1")
        timer.screens_to_cover = lambda: [left, back]

        timer._rewall_for_the_outputs()

        assert timer.kwin_pin.wall_outputs == timer.wall_outputs()
        assert sorted(timer.wall_outputs().values()) == ["DP-1", "DP-2"]
        assert desktop_session.kwin_methods().count("loadScript") == 2

    def test_every_monitor_off_is_not_a_break_over(self, timer, monkeypatch):
        left, right = named_outputs(timer, monkeypatch, "DP-2", "DP-1")
        enter_strict_break(timer)

        timer._an_output_went(left)
        timer._an_output_went(right)
        timer.screens_to_cover = lambda: []
        timer._rewall_for_the_outputs()

        assert timer.overlays == []
        assert timer._strict_break_is_holding() is True
        assert timer._filtering_keys is True

        back = FakeScreen("DP-1")
        timer.screens_to_cover = lambda: [back]
        timer._rewall_for_the_outputs()

        assert [wall.screen_covered for wall in timer.overlays] == [back]

    def test_the_focus_is_taken_again_on_a_screen_that_came_back(self, timer, monkeypatch):
        _left, right = named_outputs(timer, monkeypatch, "DP-2", "DP-1")
        enter_strict_break(timer)
        timer._an_output_went(right)
        timer.screens_to_cover = lambda: []
        timer._rewall_for_the_outputs()

        back = FakeScreen("DP-1")
        timer.screens_to_cover = lambda: [back]
        timer._rewall_for_the_outputs()

        assert timer._screen_taken is not None
        assert timer.overlays[0].isVisible() is True

    def test_a_rebuild_with_nothing_to_do_builds_nothing(self, timer, monkeypatch):
        named_outputs(timer, monkeypatch, "DP-2", "DP-1")
        enter_strict_break(timer)
        before = list(timer.overlays)

        timer._rewall_for_the_outputs()

        assert timer.overlays == before

    def test_a_kept_wall_may_be_put_back_once_more(self, timer, monkeypatch):
        left, right = named_outputs(timer, monkeypatch, "DP-2", "DP-1")
        timer.kwin_pin = None
        enter_strict_break(timer)
        kept = timer._wall_for(left)
        assert kept.stands_corrected is True, "it was never put back the first time"
        asked = []
        kept.take_its_screen_again = lambda: asked.append(1)

        timer._an_output_went(right)
        timer.screens_to_cover = lambda: [left, FakeScreen("DP-1")]
        timer._rewall_for_the_outputs()

        assert asked == [1]

    def test_the_outputs_stop_being_watched_with_the_walls(self, timer, monkeypatch):
        named_outputs(timer, monkeypatch, "DP-2", "DP-1")
        enter_strict_break(timer)
        assert timer._watching_outputs is True

        timer._clear_overlays()

        assert timer._watching_outputs is False
        assert timer._screens_settling.isActive() is False


class TestAMistypedShortcutIsNotAWayOut:
    def test_a_break_starts_refusing_switches_itself(self, timer, desktop_session):
        enter_strict_break(timer)

        assert timer.switch_guard.holding is True
        assert desktop_session.subscriptions == ["currentChanged",
                                                 "CurrentActivityChanged"]

    def test_and_a_switch_during_one_is_written_straight_back(self, timer,
                                                              desktop_session):
        enter_strict_break(timer)

        timer.switch_guard._desktop_changed("desktop-two")

        assert "Set" in desktop_session.guard_methods
        assert timer.switch_guard.refusals == 1

    def test_giving_the_screens_back_stops_refusing(self, timer, desktop_session):
        enter_strict_break(timer)

        timer._release_strict_break()

        assert timer.switch_guard.holding is False
        assert desktop_session.subscriptions == []

    def test_and_so_does_the_break_running_out(self, timer, desktop_session):
        enter_strict_break(timer)

        advance(timer, timer.break_ms + 1000)

        assert timer.switch_guard.holding is False
        assert desktop_session.subscriptions == []

    def test_it_is_not_asked_for_outside_a_break(self, timer, desktop_session):
        assert timer.switch_guard.holding is False
        assert desktop_session.guard_calls == []

    def test_a_break_asks_for_it_by_default(self, timer, desktop_session):
        enter_strict_break(timer)

        loaded = [call for call in desktop_session.kwin_calls
                  if call[0] == "loadScript"]
        source = open(loaded[0][1], encoding="utf-8").read()
        assert timer._refuse_switch is True
        assert "var refuseSwitch = true;" in source

    def test_the_profile_can_switch_it_off(self, qapp, app_id, strict_timer,
                                           recording_db):
        written = strict_timer.read_text(encoding="utf-8")
        assert "refuse_switch = true" in written, "the template no longer says this"
        strict_timer.write_text(
            written.replace("refuse_switch = true", "refuse_switch = false"),
            encoding="utf-8")
        import src.profile as profile_module
        profile_module.reload_profile()

        view = PomodoroView(recording_db, tray_icon=None)
        view.refresh_timer.stop()
        view.stress_calendar.anim_timer.stop()

        assert view._refuse_switch is False
        assert view.kwin_pin.refuse_switch is False

        view.shutdown()
        QThreadPool.globalInstance().waitForDone(2000)
        view.deleteLater()


class TestAWallRefusesToBeClosed:
    def test_closing_one_does_nothing_while_the_break_holds(self, timer):
        enter_strict_break(timer)
        wall = timer.overlays[0]

        wall.close()

        assert wall.isVisible() is True
        assert wall.let_go is False
        assert timer._strict_break_is_holding() is True

    def test_the_break_letting_go_is_what_closes_it(self, timer):
        enter_strict_break(timer)
        wall = timer.overlays[0]

        timer._clear_overlays()

        assert wall.let_go is True
        assert wall.isVisible() is False

    def test_and_it_closes_once_the_screens_are_given_back(self, timer):
        wall = StrictOverlay(timer, QApplication.primaryScreen())
        wall.show()

        wall.close()

        assert wall.isVisible() is False


class TestTheWindowRefusesToQuitMidBreak:
    def test_closing_it_is_ignored_while_a_break_holds(self, strict_window, settled):
        window = strict_window
        view = window.views["pomodoro"]
        view.refresh_timer.stop()
        settled()
        enter_strict_break(view)

        window.close()

        assert window.sync_listener is not None
        assert view._strict_break_is_holding() is True
        assert view.overlays

    def test_and_taken_once_the_screens_are_given_back(self, strict_window, settled):
        window = strict_window
        view = window.views["pomodoro"]
        view.refresh_timer.stop()
        settled()
        enter_strict_break(view)
        view._release_strict_break()

        window.close()

        assert window.sync_listener is None


class TestPauseAndSkipAreRefused:
    def test_pause_does_not_release_the_screens(self, timer, recording_db):
        enter_strict_break(timer)
        start_recording(recording_db)

        timer._toggle_timer()

        assert timer.is_running is True
        assert timer._strict_engaged is True
        assert not recording_db.called("log_pomodoro_event")

    def test_skip_does_not_end_the_break(self, timer, recording_db):
        enter_strict_break(timer)
        phase = timer.current_phase
        start_recording(recording_db)

        timer._skip_phase()

        assert timer.current_phase == phase
        assert not recording_db.called("log_pomodoro_event")

    def test_the_buttons_say_they_are_refused(self, timer):
        enter_strict_break(timer)

        assert timer.btn_play.isEnabled() is False
        assert timer.btn_skip.isEnabled() is False
        assert timer.lbl_release_hint.isHidden() is False

    def test_a_break_that_has_run_out_gives_both_back(self, timer):
        enter_strict_break(timer)

        advance(timer, timer.break_ms + 1000)

        assert timer.btn_play.isEnabled() is True
        assert timer.btn_skip.isEnabled() is True
        assert timer.lbl_release_hint.isHidden() is True
        assert timer._strict_engaged is True

    def test_a_break_that_holds_no_screens_refuses_nothing(self, qapp, app_id,
                                                          profile_path,
                                                          recording_db):
        relaxed = PomodoroView(recording_db, tray_icon=None)
        relaxed.refresh_timer.stop()
        relaxed.stress_calendar.anim_timer.stop()

        relaxed._toggle_timer()
        relaxed._skip_phase()

        assert relaxed.strict_mode is False
        assert relaxed._strict_engaged is False
        assert relaxed.btn_play.isEnabled() is True

        relaxed.shutdown()
        QThreadPool.globalInstance().waitForDone(2000)
        relaxed.deleteLater()


class TestTheOneExit:
    def test_holding_the_key_long_enough_abandons_the_break(self, timer):
        enter_strict_break(timer)

        hold_for(timer, timer.release_hold_secs)

        assert timer.current_phase == "work"
        assert timer.waiting_for_work_start is True
        assert timer.is_running is False
        assert timer._strict_engaged is False
        assert timer.kwin_pin.engaged is False

    def test_it_is_recorded_as_a_debt_under_its_own_name(self, timer, recording_db):
        enter_strict_break(timer)
        timer.time_left_ms = 300_000
        start_recording(recording_db)

        hold_for(timer, timer.release_hold_secs)

        QThreadPool.globalInstance().waitForDone(2000)
        event = recording_db.last("log_pomodoro_event")
        assert event["event_type"] == "overridden_break"
        assert event["amount_ms"] == 300_000

    def test_a_hold_that_is_let_go_of_early_costs_nothing(self, timer, recording_db):
        enter_strict_break(timer)
        start_recording(recording_db)

        hold_for(timer, timer.release_hold_secs - 2)

        assert timer._strict_engaged is True
        assert timer.is_running is True
        assert not recording_db.called("log_pomodoro_event")

    def test_the_ring_shows_how_much_of_the_hold_is_paid(self, timer):
        enter_strict_break(timer)

        hold_for(timer, timer.release_hold_secs / 2)

        assert timer.hold_ring.isHidden() is False
        assert 0.4 < timer.hold_ring.fraction < 0.6

    def test_letting_go_takes_the_ring_away(self, timer):
        enter_strict_break(timer)
        hold_for(timer, 1)

        timer.cancel_hold()

        assert timer.hold_ring.isHidden() is True
        assert timer._hold_timer.isActive() is False

    def test_the_key_starts_the_hold_wherever_it_arrives(self, timer):
        enter_strict_break(timer)

        send_key(timer, RELEASE_KEY)

        assert timer._hold_timer.isActive() is True

    def test_releasing_the_key_stops_the_hold(self, timer):
        enter_strict_break(timer)
        send_key(timer, RELEASE_KEY)

        send_key(timer, RELEASE_KEY, QEvent.Type.KeyRelease)

        assert timer._hold_timer.isActive() is False

    def test_the_key_is_left_alone_when_no_break_holds_the_screens(self, timer):
        send_key(timer, RELEASE_KEY)

        assert timer._hold_timer.isActive() is False

    def test_a_hold_cannot_survive_the_break_it_was_leaving(self, timer, recording_db):
        enter_strict_break(timer)
        timer.begin_hold()
        start_recording(recording_db)

        advance(timer, timer.break_ms + 1000)
        hold_for(timer, timer.release_hold_secs)

        assert not recording_db.called("log_pomodoro_event")


class TestWhenTheBreakRunsOut:
    def test_the_walls_stay_and_say_what_to_press(self, timer):
        enter_strict_break(timer)

        advance(timer, timer.break_ms + 1000)

        wall = timer.overlays[0]
        assert wall.isVisible() is True
        assert wall.label.text().startswith("BREAK OVER\n+")
        assert wall.lbl_hint.text() == f"PRESS {pomodoro_view.RELEASE_KEY_NAME} TO START FOCUS"

    def test_it_counts_the_seconds_since_the_break_ran_out(self, timer):
        enter_strict_break(timer)
        advance(timer, timer.break_ms + 1000)
        wall = timer.overlays[0]

        timer._over_since_ms -= 83_000
        wall.update_display()

        assert wall.label.text() == "BREAK OVER\n+1:23"

    def test_the_sign_is_sized_off_the_screen_but_leaves_the_wall_its_room(self, timer):
        enter_strict_break(timer)
        wall = timer.overlays[0]
        wall.resize(1000, 700)
        quiet = font_size_of(wall.label)

        advance(timer, timer.break_ms + 1000)
        sign = font_size_of(wall.label)
        wall.resize(2000, 1400)

        assert sign > quiet
        assert wall.label.sizeHint().height() < wall.height() // 3
        assert font_size_of(wall.label) > sign

    def test_the_wall_takes_a_frame_that_carries_across_a_room(self, timer):
        enter_strict_break(timer)
        wall = timer.overlays[0]
        wall.resize(400, 300)
        assert corner_colour(wall) != PALETTE["blue"]

        advance(timer, timer.break_ms + 1000)

        assert corner_colour(wall) == PALETTE["blue"]

    def test_one_press_of_that_key_starts_focus(self, timer, recording_db):
        enter_strict_break(timer)
        advance(timer, timer.break_ms + 1000)
        start_recording(recording_db)

        send_key(timer, RELEASE_KEY)

        assert timer.is_running is True
        assert timer.current_phase == "work"
        assert timer.overlays == []
        assert timer._strict_engaged is False
        QThreadPool.globalInstance().waitForDone(2000)
        assert recording_db.last("log_pomodoro_event")["event_type"] == "resumed_focus"

    def test_it_is_a_press_and_not_a_hold(self, timer):
        enter_strict_break(timer)
        advance(timer, timer.break_ms + 1000)

        send_key(timer, RELEASE_KEY)

        assert timer._hold_timer.isActive() is False
        assert timer.hold_ring.isHidden() is True

    def test_a_field_being_typed_into_keeps_its_own_escape(self, timer):
        enter_strict_break(timer)
        advance(timer, timer.break_ms + 1000)
        field = QLineEdit()

        QApplication.sendEvent(field, QKeyEvent(
            QEvent.Type.KeyPress, RELEASE_KEY, Qt.KeyboardModifier.NoModifier))

        assert timer.is_running is False
        assert timer.overlays
        field.deleteLater()

    def test_the_walls_stay_in_front_of_the_screens_they_cover(self, timer):
        enter_strict_break(timer)

        advance(timer, timer.break_ms + 1000)

        assert timer.kwin_pin.engaged is False
        assert "var wallsStillStand = true;" in pathlib.Path(
            timer.kwin_pin.release_path).read_text(encoding="utf-8")

    def test_a_wall_stops_pulling_the_focus_back(self, timer):
        enter_strict_break(timer)
        wall = timer.overlays[0]
        tries = []
        wall.activateWindow = lambda: tries.append(1)

        wall._take_the_screen_back()
        assert tries == [1], "a running break still comes back in front"

        advance(timer, timer.break_ms + 1000)
        wall._take_the_screen_back()

        assert tries == [1]


class TestTheWarningBeforeTheWall:
    def test_it_goes_out_before_a_strict_break_takes_the_screens(self, timer, desktop_session):
        timer._toggle_timer()

        advance(timer, timer.work_ms - int(timer.warn_secs * 1000) + 500)

        assert len(desktop_session.notifications) == 1
        summary, body, _ = desktop_session.notifications[0]
        assert "60" in summary
        assert "30-minute break" in body

    def test_it_names_the_break_that_is_actually_coming(self, timer, desktop_session):
        timer.set_long_break_queued(True)
        timer._toggle_timer()

        advance(timer, timer.work_ms)

        _, body, _ = desktop_session.notifications[0]
        assert "60-minute break" in body

    def test_it_says_how_to_leave_the_break(self, timer, desktop_session):
        timer._toggle_timer()

        advance(timer, timer.work_ms)

        _, body, _ = desktop_session.notifications[0]
        assert "ESC" in body and "10" in body

    def test_it_is_audible(self, timer, desktop_session):
        timer._toggle_timer()

        advance(timer, timer.work_ms)

        assert desktop_session.notifications[0][2]["sound_name"] == "dialog-warning"

    def test_one_warning_per_focus_interval_and_not_one_per_frame(self, timer, desktop_session):
        timer._toggle_timer()

        advance(timer, timer.work_ms - int(timer.warn_secs * 1000) + 500)
        advance(timer, 100)
        advance(timer, 100)

        assert len(desktop_session.notifications) == 1

    def test_the_next_focus_interval_is_warned_of_too(self, timer, desktop_session):
        timer._toggle_timer()
        advance(timer, timer.work_ms)
        hold_for(timer, timer.release_hold_secs)
        timer._toggle_timer()

        advance(timer, timer.work_ms)

        assert len(desktop_session.notifications) == 2

    def test_a_timer_that_takes_no_screens_warns_of_nothing(self, qapp, app_id,
                                                            profile_path,
                                                            recording_db,
                                                            desktop_session):
        relaxed = PomodoroView(recording_db, tray_icon=None)
        relaxed.refresh_timer.stop()
        relaxed.stress_calendar.anim_timer.stop()
        relaxed._toggle_timer()

        advance(relaxed, relaxed.work_ms)

        assert desktop_session.notifications == []

        relaxed.shutdown()
        QThreadPool.globalInstance().waitForDone(2000)
        relaxed.deleteLater()

    def test_the_warning_can_be_switched_off(self, timer, desktop_session):
        timer.warn_secs = 0
        timer._toggle_timer()

        advance(timer, timer.work_ms)

        assert desktop_session.notifications == []


class TestInsideTheRealWindow:
    def test_a_break_leaves_the_window_where_the_member_put_it(self, strict_window,
                                                               settled):
        window = strict_window
        view = window.views["pomodoro"]
        view.refresh_timer.stop()
        settled()
        before = window.windowFlags()
        tab = window.tabs.currentIndex()

        enter_strict_break(view)

        assert window.windowFlags() == before
        assert window.tabs.currentIndex() == tab
        assert view.overlays

    def test_and_takes_the_walls_away_when_focus_starts(self, strict_window, settled):
        window = strict_window
        view = window.views["pomodoro"]
        view.refresh_timer.stop()
        enter_strict_break(view)
        advance(view, view.break_ms + 1000)
        settled()

        view._toggle_timer()

        assert view.overlays == []
        assert view.media_surface is None

    def test_the_release_key_reaches_the_hold_from_the_window(self, strict_window, settled):
        window = strict_window
        view = window.views["pomodoro"]
        view.refresh_timer.stop()
        enter_strict_break(view)
        settled()

        send_key(window, RELEASE_KEY)

        assert view._hold_timer.isActive() is True


class TestTheOverlaySurface:
    def test_it_says_what_to_hold(self, timer):
        overlay = StrictOverlay(timer, QApplication.primaryScreen())

        assert "ESC" in overlay.lbl_hint.text()
        assert "10" in overlay.lbl_hint.text()

    def test_it_counts_the_break_down(self, timer):
        enter_strict_break(timer)
        overlay = StrictOverlay(timer, QApplication.primaryScreen())

        overlay.update_display()

        assert "REST INTERVAL" in overlay.label.text()

    def test_it_shows_the_hold_being_paid(self, timer):
        overlay = StrictOverlay(timer, QApplication.primaryScreen())

        overlay.show_hold(0.5, True)

        assert overlay.hold_ring.isHidden() is False
        assert overlay.hold_ring.fraction == 0.5


class TestEveryWallIsAWindowTheCompositorCanHold:
    def test_a_wall_is_named_apart_from_the_window_it_covers_for(self, timer):
        overlay = StrictOverlay(timer, QApplication.primaryScreen())

        assert overlay.windowTitle() != "Traker"
        assert overlay.windowTitle()

    def test_it_names_the_output_it_covers(self, timer):
        screen = QApplication.primaryScreen()
        overlay = StrictOverlay(timer, screen)

        assert screen.name() in overlay.windowTitle()

    def test_it_is_a_window_of_its_own_and_stays_on_top(self, timer):
        overlay = StrictOverlay(timer, QApplication.primaryScreen())
        flags = overlay.windowFlags()

        assert flags & Qt.WindowType.Window
        assert flags & Qt.WindowType.WindowStaysOnTopHint
        assert flags & Qt.WindowType.FramelessWindowHint
        assert not flags & Qt.WindowType.SubWindow

    def test_a_break_builds_one_toplevel_per_screen(self, shelled):
        view, _shell = shelled
        two_screens(view)

        enter_strict_break(view)

        assert len(view.overlays) == 2
        assert all(wall.parent() is None for wall in view.overlays)
        assert all(wall.isWindow() for wall in view.overlays)
        assert len({wall.windowTitle() for wall in view.overlays}) == 1

    def test_a_wall_the_compositor_moved_names_its_output_again(self, shelled):
        view, _shell = shelled
        enter_strict_break(view)
        wall = view.overlays[0]
        wall.covers_its_own_screen = lambda: False

        view._redraw_break_surfaces()

        assert wall.stands_corrected is True
        assert wall.isWindow()
        assert wall.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert wall.windowFlags() & Qt.WindowType.WindowStaysOnTopHint

    def test_a_wall_that_landed_where_it_was_put_is_left_alone(self, shelled):
        view, _shell = shelled
        enter_strict_break(view)
        wall = view.overlays[0]

        view._redraw_break_surfaces()

        assert wall.stands_corrected is False

    def test_it_asks_once_and_not_once_a_frame(self, shelled):
        view, _shell = shelled
        enter_strict_break(view)
        wall = view.overlays[0]
        wall.covers_its_own_screen = lambda: False
        view._redraw_break_surfaces()

        asked = []
        wall.take_its_screen_again = lambda: asked.append(1)
        view._redraw_break_surfaces()
        view._redraw_break_surfaces()

        assert asked == []

    def test_showing_a_file_does_not_take_a_wall_away_and_back(self, timer, tmp_path):
        enter_strict_break(timer)
        wall = timer._media_host
        before = int(wall.winId())

        timer.media_surface.open(
            BreakActivity("watch", str(tmp_path / "talk.mkv"), VIDEO))
        QApplication.processEvents()

        assert int(wall.winId()) == before

    def test_a_wall_does_not_outlive_the_break_that_built_it(self, shelled):
        view, _shell = shelled
        two_screens(view)
        enter_strict_break(view)
        walls = list(view.overlays)
        assert walls and view.media_surface is not None

        view._clear_overlays()

        assert view.overlays == []
        assert view.media_surface is None
        assert view._media_host is None
        assert all(wall.isHidden() for wall in walls)
