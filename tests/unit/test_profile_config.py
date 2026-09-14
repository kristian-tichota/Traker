import datetime
import types

import pytest

from src.config import PALETTE
from src.profile import (DEFAULT_SUPPLEMENT_TARGETS, UserProfile,
                         get_qt_key)


class TestGeneratedDocument:
    def test_a_missing_profile_is_generated_on_first_use(self, profile_path):
        assert not profile_path.exists()
        UserProfile()
        assert profile_path.exists()

    @pytest.mark.parametrize(
        "section",
        ["windows", "biometrics", "goals", "timer", "strict_break", "keybinds",
         "schedule", "regime_colors", "exercise_goals", "supplement_targets"],
    )
    def test_every_section_the_app_reads_is_present(self, user_profile, section):
        assert section in user_profile.data, f"generated profile is missing [{section}]"

    def test_an_unreadable_profile_leaves_the_app_running(self, profile_path):
        profile_path.write_text("this is not = valid toml [[[", encoding="utf-8")
        profile = UserProfile()
        assert profile.data == {}
        assert profile.calculate_bmr() == pytest.approx(1730.0)

    def test_generated_profile_declares_a_weight_goal(self, user_profile):
        assert user_profile.data["goals"]["goal_type"] == "maintain_weight"
        assert user_profile.goal_type() == "maintain_weight"

    def test_generated_profile_declares_where_the_service_is(self, user_profile):
        from src.config import LOCAL_SERVER_URL

        assert user_profile.data["server"]["url"] == LOCAL_SERVER_URL

    def test_generated_profile_carries_no_token_of_its_own(self, user_profile):
        assert user_profile.data["server"]["token"] == ""

    def test_every_default_the_app_reads_is_written_down(self, user_profile):
        from src import profile as profile_module

        goals = user_profile.data["goals"]
        assert goals["daily_adjustment_kcal"] == profile_module.DEFAULT_DAILY_ADJUSTMENT_KCAL
        assert goals["tick_markers"] == profile_module.DEFAULT_TICK_MARKERS
        assert goals["activity_level"] == profile_module.DEFAULT_ACTIVITY_LEVEL
        assert goals["neat_tax_percent"] == profile_module.DEFAULT_NEAT_TAX_PERCENT


class TestEnabledWindows:
    MINIMUM = {"food", "beverages", "exercise", "mobility",
               "food_graphs", "exercise_graphs", "caffeine_graph"}
    REST = {"pomodoro", "supplements", "supplement_graphs", "heatmap", "plans", "chores"}

    def test_a_generated_profile_enables_the_everyday_views_only(self, user_profile):
        windows = user_profile.data["windows"]
        assert {key for key, on in windows.items() if on} == self.MINIMUM

    def test_the_rest_are_written_down_as_off_rather_than_left_out(self, user_profile):
        windows = user_profile.data["windows"]
        assert {key for key, on in windows.items() if not on} == self.REST

    def test_the_template_names_every_tab_the_window_can_build(self, user_profile):
        """Check every tab the window can build is named in the template."""
        from src.gui.main_window import MainWindow

        registry = {key for key, *_ in MainWindow.TAB_REGISTRY}
        assert set(user_profile.data["windows"]) == registry
        assert self.MINIMUM | self.REST == registry

    def test_a_tab_can_be_switched_off(self, write_profile):
        profile = write_profile("[windows]\npomodoro = false\n")
        assert profile.is_window_enabled("pomodoro") is False

    def test_an_unknown_tab_key_defaults_to_enabled(self, user_profile):
        assert user_profile.is_window_enabled("sleep_tracking") is True
        assert user_profile.is_window_enabled("sleep_tracking", default=False) is False


class TestAProfileWrittenBeforeATabMerge:
    def test_both_halves_off_leaves_the_merged_tab_off(self, write_profile):
        profile = write_profile("[windows]\nfood_logs = false\nfood_db = false\n")
        assert profile.is_window_enabled("food") is False

    def test_either_half_on_keeps_the_merged_tab(self, write_profile):
        profile = write_profile("[windows]\nfood_logs = false\nfood_db = true\n")
        assert profile.is_window_enabled("food") is True

    def test_one_half_named_alone_is_enough(self, write_profile):
        profile = write_profile("[windows]\nfood_logs = false\n")
        assert profile.is_window_enabled("food") is False

    def test_the_merged_key_wins_when_both_are_present(self, write_profile):
        profile = write_profile("[windows]\nfood = true\nfood_logs = false\n")
        assert profile.is_window_enabled("food") is True

    def test_a_profile_naming_neither_falls_back_to_the_default(self, write_profile):
        profile = write_profile("[windows]\npomodoro = true\n")
        assert profile.is_window_enabled("food") is True


class TestTheOneSplit:
    @pytest.mark.exact
    def test_the_generated_document_ships_thirty_thirty(self, user_profile):
        split = user_profile.timer_split()
        assert (split["focus_mins"], split["break_mins"]) == (30, 30)

    @pytest.mark.exact
    def test_and_two_sixty_minute_breaks_a_day(self, user_profile):
        split = user_profile.timer_split()
        assert (split["long_break_mins"], split["long_breaks_per_day"]) == (60, 2)

    def test_the_wall_is_off_until_a_member_asks_for_it(self, user_profile):
        assert user_profile.timer_split()["strict"] is False

    def test_a_member_can_ask_for_it(self, write_profile):
        assert write_profile("[timer]\nstrict = true\n").timer_split()["strict"] is True

    def test_a_profile_that_says_nothing_gets_the_shipped_split(self, write_profile):
        from src import profile as profile_module

        split = write_profile("[biometrics]\nweight_kg = 70.0\n").timer_split()

        assert split["focus_mins"] == profile_module.DEFAULT_FOCUS_MINS
        assert split["break_mins"] == profile_module.DEFAULT_BREAK_MINS

    def test_a_profile_still_declaring_modes_is_not_read_from(self, write_profile, caplog):
        with caplog.at_level("INFO"):
            split = write_profile(
                "[pomodoro_modes.hardcore_gaming]\nwork_mins = 90\n"
                "strict_mode = true\n").timer_split()

        assert split["focus_mins"] == 30
        assert split["strict"] is False, "a mode they had to select is not a wall"
        assert "[pomodoro_modes] is no longer read" in caplog.text

    @pytest.mark.parametrize("written", ["0", "-5", '"half an hour"'])
    def test_a_duration_that_cannot_run_is_clamped(self, write_profile, written):
        profile = write_profile(f"[timer]\nfocus_mins = {written}\n")

        assert profile.timer_split()["focus_mins"] >= 1

    def test_no_long_breaks_at_all_is_a_choice_and_not_a_typo(self, write_profile):
        profile = write_profile("[timer]\nlong_breaks_per_day = 0\n")

        assert profile.timer_split()["long_breaks_per_day"] == 0

    def test_a_long_break_count_that_is_not_a_number_is_the_shipped_one(
        self, write_profile
    ):
        profile = write_profile('[timer]\nlong_breaks_per_day = "twice"\n')

        assert profile.timer_split()["long_breaks_per_day"] == 2


class TestAHandEditedNumber:
    @pytest.mark.parametrize("written", ['"ten"', "true", '"1e400"'])
    def test_a_value_that_is_not_a_number_falls_back_and_says_so(
        self, write_profile, caplog, written
    ):
        profile = write_profile(f"[strict_break]\nrelease_hold_secs = {written}\n")

        with caplog.at_level("WARNING"):
            held = profile.number("strict_break", "release_hold_secs", 10,
                                  low=1.0, high=60.0)

        assert held == 10
        assert "release_hold_secs is not a number" in caplog.text

    def test_a_value_it_can_read_is_the_members_own(self, write_profile):
        profile = write_profile("[strict_break]\nrelease_hold_secs = 4\n")

        assert profile.number("strict_break", "release_hold_secs", 10,
                              low=1.0, high=60.0) == 4.0

    @pytest.mark.parametrize("written, expected", [("0", 1.0), ("900", 60.0)])
    def test_it_is_clamped_to_what_can_be_paid(self, write_profile, written,
                                               expected):
        profile = write_profile(f"[strict_break]\nrelease_hold_secs = {written}\n")

        assert profile.number("strict_break", "release_hold_secs", 10,
                              low=1.0, high=60.0) == expected

    def test_a_missing_section_is_the_default(self, write_profile):
        profile = write_profile("[goals]\nsalt_g = 5.0\n")

        assert profile.number("strict_break", "warn_secs", 60, low=0.0) == 60.0


class TestSupplementTargets:
    def test_the_generated_document_lists_every_tracked_micronutrient(self, user_profile):
        targets = user_profile.get_supplement_targets()
        assert len(targets) == 12
        assert {"key", "name", "target"} <= set(targets[0])

    def test_targets_fall_back_when_the_section_is_missing(self, write_profile):
        profile = write_profile("[biometrics]\nweight_kg = 70.0\n")
        assert len(profile.get_supplement_targets()) == 12

    def test_the_generated_document_and_the_fallback_are_one_list(self, user_profile):
        assert user_profile.get_supplement_targets() == DEFAULT_SUPPLEMENT_TARGETS


class TestGeneratedColours:
    def test_the_regimes_are_coloured_out_of_the_palette(self, user_profile):
        colours = set(user_profile.data["regime_colors"].values())

        assert colours <= set(PALETTE.values())


class TestSchedule:
    @staticmethod
    def _at(monkeypatch, hh_mm, weekday="Monday"):
        import src.profile

        hour, minute = (int(part) for part in hh_mm.split(":"))
        base = datetime.datetime(2026, 9, 7, hour, minute)
        offset = ["Monday", "Tuesday", "Wednesday", "Thursday",
                  "Friday", "Saturday", "Sunday"].index(weekday)
        frozen = base + datetime.timedelta(days=offset)

        class _FrozenDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen

        monkeypatch.setattr(
            src.profile, "datetime",
            types.SimpleNamespace(datetime=_FrozenDateTime, timedelta=datetime.timedelta),
        )

    def test_a_time_inside_a_block_reports_that_regime(self, user_profile, monkeypatch):
        self._at(monkeypatch, "10:00")
        assert user_profile.get_current_regime() == "Work"

    def test_the_end_of_a_block_belongs_to_the_next_one(self, user_profile, monkeypatch):
        self._at(monkeypatch, "14:00")
        assert user_profile.get_current_regime() == "Admin"

    def test_time_outside_every_block_is_unscheduled(self, user_profile, monkeypatch):
        self._at(monkeypatch, "03:00")
        assert user_profile.get_current_regime() == "Unscheduled"

    def test_a_block_wrapping_past_midnight_covers_both_sides(self, write_profile, monkeypatch):
        profile = write_profile('[schedule.default]\n"22:00-06:00" = "Night Shift"\n')
        self._at(monkeypatch, "23:30")
        assert profile.get_current_regime() == "Night Shift"
        self._at(monkeypatch, "02:00")
        assert profile.get_current_regime() == "Night Shift"

    def test_a_named_day_overrides_the_default_schedule(self, write_profile, monkeypatch):
        profile = write_profile(
            '[schedule.default]\n"06:00-14:00" = "Work"\n'
            '[schedule.saturday]\n"06:00-14:00" = "Personal"\n'
        )
        self._at(monkeypatch, "10:00", weekday="Saturday")
        assert profile.get_current_regime() == "Personal"
        self._at(monkeypatch, "10:00", weekday="Monday")
        assert profile.get_current_regime() == "Work"

    def test_a_malformed_time_range_is_skipped_rather_than_fatal(self, write_profile, monkeypatch):
        profile = write_profile(
            '[schedule.default]\n"garbage" = "Nonsense"\n"06:00-14:00" = "Work"\n'
        )
        self._at(monkeypatch, "10:00")
        assert profile.get_current_regime() == "Work"

    def test_regime_colours_come_from_the_profile(self, user_profile):
        assert user_profile.get_regime_color("Personal", "#000000") == "#859900"

    def test_an_unknown_regime_uses_the_supplied_fallback(self, user_profile):
        assert user_profile.get_regime_color("Napping", "#123456") == "#123456"


class TestKeybindResolution:
    @pytest.mark.accessibility
    @pytest.mark.parametrize(
        "configured, attribute",
        [("k", "Key_K"), ("J", "Key_J"), ("esc", "Key_Escape"),
         ("escape", "Key_Escape"), ("enter", "Key_Return"),
         ("return", "Key_Return"), ("tab", "Key_Tab")],
    )
    def test_named_and_literal_keys_resolve(self, qapp, configured, attribute):
        from PyQt6.QtCore import Qt

        assert get_qt_key(configured, Qt.Key.Key_X) == getattr(Qt.Key, attribute)

    @pytest.mark.accessibility
    def test_an_unresolvable_key_falls_back_to_the_default(self, qapp):
        from PyQt6.QtCore import Qt

        assert get_qt_key("not-a-key", Qt.Key.Key_J) == Qt.Key.Key_J


class TestTheDocumentIsParsedOnce:
    def test_two_profiles_share_one_parsed_document(self, profile_path):
        first, second = UserProfile(), UserProfile()

        assert first.data is second.data

    def test_the_file_is_read_once_for_many_constructions(self, profile_path, monkeypatch):
        import builtins

        UserProfile()

        reads = []
        real_open = builtins.open

        def counting_open(path, *args, **kwargs):
            if str(path) == str(profile_path):
                reads.append(path)
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", counting_open)
        for _ in range(10):
            UserProfile()

        assert reads == []

    def test_an_edited_profile_is_picked_up_without_a_restart(self, write_profile, profile_path):
        assert write_profile("[goals]\nsalt_g = 5.0\n").get_metric("goals", "salt_g") == 5.0

        profile_path.write_text("[goals]\nsalt_g = 3.0\n", encoding="utf-8")

        assert UserProfile().get_metric("goals", "salt_g") == 3.0

    def test_reload_re_reads_the_file(self, user_profile, profile_path):
        profile_path.write_text("[goals]\nsalt_g = 9.0\n", encoding="utf-8")

        user_profile.reload()

        assert user_profile.get_metric("goals", "salt_g") == 9.0

    def test_filling_in_a_default_does_not_write_into_the_shared_document(
        self, write_profile
    ):
        profile = write_profile("[timer]\nfocus_mins = 50\n")

        split = profile.timer_split()

        assert (split["focus_mins"], split["break_mins"]) == (50, 30)
        assert "break_mins" not in profile.data["timer"], (
            "the document is shared between instances and must stay as written"
        )
