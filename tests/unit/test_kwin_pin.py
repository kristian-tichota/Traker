import pytest

import src.desktop.kwin as kwin
from src.desktop.kwin import (HOME_PLUGIN_NAME, PLUGIN_NAME, KWinPin,
                              WindowScreen, home_source, release_source,
                              release_stale_hold, script_source)


class Caller:
    def __init__(self, reachable=True, load_answer=3):
        self.calls = []
        self.reachable = reachable
        self.answers = {"loadScript": load_answer, "unloadScript": True, "start": None}

    def __call__(self, method, *args):
        self.calls.append((method,) + args)
        if not self.reachable:
            return False, None
        return True, self.answers.get(method)

    @property
    def methods(self):
        return [call[0] for call in self.calls]


@pytest.fixture
def script_path(tmp_path):
    return str(tmp_path / "cache" / "strict-break.js")


class TestTheScript:
    def test_it_holds_this_application_by_app_id(self):
        assert 'var target = "traker";' in script_source("Traker")

    def test_there_is_no_allow_list_to_get_wrong(self):
        source = script_source("traker")

        assert "allowed" not in source
        assert "resourceClass" in source

    def test_it_is_told_what_the_breaks_own_windows_are_called(self):
        source = script_source("traker", wall_prefix="Traker rest")

        assert 'var wallPrefix = "Traker rest";' in source
        assert "function isWall(w)" in source

    def test_the_walls_are_what_is_kept_above_everything(self):
        source = script_source("traker", wall_prefix="Traker rest")

        assert "if (!isWall(w)) return;\n        try { w.keepAbove = true; }" \
            in source.replace("\r\n", "\n")

    def test_the_focus_stands_down_for_a_wall_and_nothing_else(self):
        assert "if (current && isWall(current)) return;" in script_source("traker")

    def test_no_prefix_treats_every_window_of_ours_as_a_wall(self):
        source = script_source("traker")

        assert 'var wallPrefix = "";' in source
        assert 'if (wallPrefix === "") return true;' in source

    def test_the_window_focus_is_pulled_back_to_is_named(self):
        source = script_source("traker", focus_caption="Traker")

        assert 'var wanted = "Traker";' in source
        assert "frontWindow(mine)" in source

    def test_it_skips_a_window_that_wants_no_input(self):
        assert "wantsInput !== false" in script_source("traker")

    def test_a_caption_is_a_members_window_title_and_is_quoted_as_one(self):
        assert 'var wanted = "say \\"this\\"";' in script_source(
            "traker", focus_caption='say "this"')

    def test_no_caption_leaves_the_choice_where_it_was(self):
        assert 'var wanted = "";' in script_source("traker")

    def test_it_answers_a_desktop_and_an_activity_change(self):
        source = script_source("traker")

        assert "currentDesktopChanged" in source
        assert "currentActivityChanged" in source

    def test_it_pins_to_every_desktop_and_every_activity(self):
        source = script_source("traker")

        assert "w.onAllDesktops = true;" in source
        assert "w.desktops = [];" in source
        assert "w.activities = [];" in source


class TestTheUndo:
    def test_it_takes_the_two_properties_back_off(self):
        source = release_source("traker")

        assert "w.keepAbove = false;" in source
        assert "w.onAllDesktops = false;" in source

    def test_it_puts_a_window_where_the_member_is_now(self):
        source = release_source("traker")

        assert "w.desktops = [workspace.currentDesktop];" in source
        assert "w.desktop = workspace.currentDesktop;" in source
        assert "w.activities = [workspace.currentActivity];" in source

    def test_it_names_the_same_application_as_the_hold(self):
        assert 'var target = "traker";' in release_source("Traker")

    def test_a_wall_still_standing_keeps_the_front_it_was_given(self):
        source = release_source("traker", "Traker rest", standing=True)

        assert "var wallsStillStand = true;" in source
        assert 'var wallPrefix = "Traker rest";' in source
        assert "if (!(wallsStillStand && isWall(w))) { try { w.keepAbove = false; }" in source

    def test_and_a_break_with_no_walls_left_gives_that_back_too(self):
        assert "var wallsStillStand = false;" in release_source("traker")

    def test_it_needs_no_caption_of_its_own(self):
        source = release_source("traker")

        assert "__WALL__" not in source and "__CAPTION__" not in source
        assert 'var wallPrefix = "";' in source

    def test_it_touches_nothing_of_the_members(self):
        source = release_source("traker")

        assert "if (isBreak(all[i]))" in source
        assert "allowed" not in source

    def test_it_connects_to_nothing(self):
        assert "connect(" not in release_source("traker")


class TestRunningOneScript:
    def test_it_clears_a_stale_script_of_the_same_name_first(self, script_path):
        caller = Caller()

        took, why = kwin.run_script("// x", script_path, "traker-probe",
                                    caller=caller)

        assert took is True
        assert caller.methods == ["unloadScript", "loadScript", "start"]
        assert "traker-probe" in why

    def test_a_kwin_that_is_not_there_says_so(self, script_path):
        took, why = kwin.run_script("// x", script_path, "traker-probe",
                                    caller=Caller(reachable=False))

        assert took is False
        assert "did not answer" in why

    def test_a_name_already_loaded_says_that(self, script_path):
        caller = Caller(load_answer=-1)

        took, why = kwin.run_script("// x", script_path, "traker-probe",
                                    caller=caller)

        assert took is False
        assert "already loaded" in why

    def test_a_script_it_would_not_start_is_unloaded_again(self, script_path):
        caller = Caller()
        caller.answers["start"] = None

        def refuse_start(method, *args):
            caller.calls.append((method,) + args)
            if method == "start":
                return False, None
            return True, caller.answers.get(method)

        took, why = kwin.run_script("// x", script_path, "traker-probe",
                                    caller=refuse_start)

        assert took is False
        assert "refused to start" in why
        assert [m for m, *_ in caller.calls].count("unloadScript") == 2

    def test_a_path_it_cannot_write_is_not_a_kwin_problem(self, tmp_path):
        blocked = tmp_path / "blocked"
        blocked.write_text("not a directory", encoding="utf-8")

        took, why = kwin.run_script("// x", str(blocked / "x.js"), caller=Caller())

        assert took is False
        assert "could not write" in why


class TestEngaging:
    def test_it_clears_a_stale_script_before_loading_its_own(self, script_path):
        caller = Caller()

        assert KWinPin("traker", caller=caller, script_path=script_path).engage() is True
        assert caller.methods == ["unloadScript", "loadScript", "start"]

    def test_the_script_is_written_where_kwin_is_told_to_read_it(self, script_path):
        caller = Caller()

        KWinPin("traker", caller=caller, script_path=script_path).engage()

        assert caller.calls[1] == ("loadScript", script_path, PLUGIN_NAME)
        assert 'var target = "traker";' in open(script_path).read()

    def test_engaging_again_asks_for_the_same_thing(self, script_path):
        caller = Caller()
        pin = KWinPin("traker", caller=caller, script_path=script_path)
        pin.engage()
        caller.calls.clear()

        assert pin.engage() is True
        assert caller.methods == ["unloadScript", "loadScript", "start"]

    def test_a_session_without_kwin_engages_nothing(self, script_path):
        import os

        caller = Caller(reachable=False)
        pin = KWinPin("traker", caller=caller, script_path=script_path)

        assert pin.engage() is False
        assert pin.engaged is False
        assert not os.path.exists(script_path)
        assert caller.methods == ["unloadScript"]

    def test_a_refused_load_does_not_count_as_engaged(self, script_path):
        caller = Caller(load_answer=-1)
        pin = KWinPin("traker", caller=caller, script_path=script_path)

        assert pin.engage() is False
        assert pin.engaged is False

    def test_a_re_engage_that_fails_leaves_nothing_claiming_to_be_loaded(
            self, script_path):
        caller = Caller()
        pin = KWinPin("traker", caller=caller, script_path=script_path)
        pin.engage()
        caller.answers["loadScript"] = -1

        assert pin.engage() is False
        assert pin.engaged is False

    def test_an_engage_that_names_nothing_leaves_the_script_as_it_was(self, script_path):
        caller = Caller()
        pin = KWinPin("traker", caller=caller,
                      script_path=script_path, focus_caption="Traker")

        pin.engage()

        assert 'var wanted = "Traker";' in open(script_path).read()

    def test_without_an_app_id_it_asks_for_nothing(self, script_path):
        caller = Caller()
        pin = KWinPin("", caller=caller, script_path=script_path)

        assert pin.engage() is False
        assert caller.calls == []


class TestALaunchAfterACrash:
    def test_the_launch_unloads_what_the_last_run_left(self, monkeypatch):
        caller = Caller()
        monkeypatch.setattr(kwin, "_session_caller", caller)

        assert release_stale_hold() is True
        assert caller.calls == [("unloadScript", PLUGIN_NAME)]

    def test_a_session_without_kwin_is_not_a_failed_launch(self, monkeypatch):
        monkeypatch.setattr(kwin, "_session_caller", Caller(reachable=False))

        assert release_stale_hold() is False


class TestReleasing:
    def test_release_unloads_the_script_then_runs_the_undo(self, script_path):
        caller = Caller()
        pin = KWinPin("traker", caller=caller, script_path=script_path)
        pin.engage()
        caller.calls.clear()

        assert pin.release() is True
        assert pin.engaged is False
        assert caller.methods == ["unloadScript", "loadScript", "start", "unloadScript"]
        assert caller.calls[1] == ("loadScript", pin.release_path, PLUGIN_NAME)
        assert "w.keepAbove = false;" in open(pin.release_path).read()

    def test_the_undo_is_written_beside_the_script_it_undoes(self, script_path):
        pin = KWinPin("traker", caller=Caller(), script_path=script_path)

        assert pin.release_path == script_path.replace(".js", "-release.js")

    def test_it_runs_even_where_this_object_never_engaged(self, script_path):
        caller = Caller()

        assert KWinPin("traker", caller=caller,
                       script_path=script_path).release() is True
        assert caller.methods == ["unloadScript", "loadScript", "start", "unloadScript"]

    def test_a_session_without_kwin_is_asked_for_nothing_more(self, script_path):
        caller = Caller(reachable=False)

        assert KWinPin("traker", caller=caller, script_path=script_path).release() is False
        assert caller.methods == ["unloadScript"]

    def test_an_undo_kwin_will_not_load_is_not_a_failed_release(self, script_path):
        caller = Caller(load_answer=-1)
        pin = KWinPin("traker", caller=caller, script_path=script_path)

        assert pin.release() is True
        assert caller.methods == ["unloadScript", "loadScript"]

    def test_without_an_app_id_there_is_nothing_to_give_back(self, script_path):
        caller = Caller()

        assert KWinPin("", caller=caller, script_path=script_path).release() is True
        assert caller.methods == ["unloadScript"]

    def test_a_kwin_that_answers_no_script_was_loaded_is_not_a_failure(self, script_path):
        caller = Caller()
        caller.answers["unloadScript"] = False
        pin = KWinPin("traker", caller=caller, script_path=script_path)

        assert pin.release() is True


class TestKeepingTheWindowOnOneScreen:
    def test_it_loads_a_script_of_its_own(self, tmp_path):
        caller = Caller()
        path = str(tmp_path / "home.js")
        screen = WindowScreen("Traker", "Traker", "DP-1", caller=caller,
                              script_path=path)

        assert screen.engage() is True
        assert screen.engaged is True
        assert caller.methods == ["unloadScript", "loadScript", "start"]
        assert caller.calls[0] == ("unloadScript", HOME_PLUGIN_NAME)
        assert caller.calls[1] == ("loadScript", path, HOME_PLUGIN_NAME)

    def test_the_script_names_the_output_and_the_window(self, tmp_path):
        path = str(tmp_path / "home.js")
        WindowScreen("Traker", "Traker", "DP-1", caller=Caller(),
                     script_path=path).engage()
        source = open(path, encoding="utf-8").read()

        assert 'var wanted = "DP-1";' in source
        assert 'var caption = "Traker";' in source
        assert 'var target = "traker";' in source

    def test_an_empty_key_still_drops_the_last_runs_script(self, tmp_path):
        caller = Caller()
        screen = WindowScreen("Traker", "Traker", "", caller=caller,
                              script_path=str(tmp_path / "home.js"))

        assert screen.engage() is False
        assert caller.methods == ["unloadScript"]

    def test_a_session_with_no_kwin_asks_for_nothing_more(self, tmp_path):
        caller = Caller(reachable=False)
        screen = WindowScreen("Traker", "Traker", "DP-1", caller=caller,
                              script_path=str(tmp_path / "home.js"))

        assert screen.engage() is False
        assert caller.methods == ["unloadScript"]

    def test_a_kwin_that_refuses_the_script_leaves_nothing_loaded(self, tmp_path):
        caller = Caller(load_answer=-1)
        screen = WindowScreen("Traker", "Traker", "DP-1", caller=caller,
                              script_path=str(tmp_path / "home.js"))

        assert screen.engage() is False
        assert screen.engaged is False

    def test_closing_unloads_it(self, tmp_path):
        caller = Caller()
        screen = WindowScreen("Traker", "Traker", "DP-1", caller=caller,
                              script_path=str(tmp_path / "home.js"))
        screen.engage()

        assert screen.release() is True
        assert screen.engaged is False
        assert caller.calls[-1] == ("unloadScript", HOME_PLUGIN_NAME)

    def test_the_two_scripts_do_not_share_a_name(self):
        assert HOME_PLUGIN_NAME != PLUGIN_NAME

    def test_the_source_names_one_application(self):
        assert 'var target = "traker";' in home_source("Traker", "Traker", "DP-1")
