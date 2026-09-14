import datetime

import pytest

from src.desktop import kde_config
from src.desktop.night_filter import (EFFECT, EFFECT_GROUP, ENABLED_KEY,
                                      MONOCHROME, PLUGINS_GROUP, NightFilter,
                                      wanted_at)
from src.domain.clock import within_window

pytestmark = pytest.mark.gui

GREY_PROFILE = """
[grayscale]
enabled = true
from = "20:00"
to = "06:00"
"""

THEIRS = """[Plugins]
blurEnabled=false
slideEnabled=true

[Effect-colorblindnesscorrection]
Intensity=0.4

[Xwayland]
Scale=1
"""


class Caller:
    def __init__(self, reachable=True):
        self.calls = []
        self.reachable = reachable
        self.loads = True

    def __call__(self, service, path, interface, method, *args):
        self.calls.append((method,) + args)
        if not self.reachable:
            return False, None
        return True, (self.loads if method == "loadEffect" else None)

    @property
    def methods(self):
        return [call[0] for call in self.calls]


def at(clock_time):
    hour, minute = (int(part) for part in clock_time.split(":"))
    return datetime.datetime(2026, 9, 12, hour, minute)


@pytest.fixture
def kwinrc(tmp_path, monkeypatch):
    path = tmp_path / "kwinrc"
    monkeypatch.setattr(kde_config, "KWINRC_PATH", str(path))
    return path


def entries(text, group):
    found, wanted = {}, False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            wanted = stripped[1:-1] == group
            continue
        if wanted:
            name, separator, value = line.partition("=")
            if separator:
                found[name.strip()] = value.strip()
    return found


def a_filter(qapp, caller=None, clock_time="21:00"):
    return NightFilter(caller=caller or Caller(), clock=lambda: at(clock_time))


class TestWhichHoursAreGrey:
    def test_inside_the_hours(self, write_profile):
        assert wanted_at(write_profile(GREY_PROFILE), at("21:30")) is True

    def test_outside_them(self, write_profile):
        assert wanted_at(write_profile(GREY_PROFILE), at("14:00")) is False

    def test_they_wrap_past_midnight(self, write_profile):
        profile = write_profile(GREY_PROFILE)

        assert wanted_at(profile, at("23:59")) is True
        assert wanted_at(profile, at("00:01")) is True
        assert wanted_at(profile, at("05:59")) is True

    def test_the_ends_belong_to_the_hours_and_to_the_day(self, write_profile):
        profile = write_profile(GREY_PROFILE)

        assert wanted_at(profile, at("20:00")) is True
        assert wanted_at(profile, at("06:00")) is False

    def test_it_is_the_rule_the_schedule_wraps_by(self):
        assert within_window(23 * 60, 20 * 60, 6 * 60) is True
        assert within_window(7 * 60, 20 * 60, 6 * 60) is False

    def test_off_is_off_whatever_the_hour_is(self, write_profile):
        profile = write_profile(GREY_PROFILE.replace("true", "false"))

        assert wanted_at(profile, at("21:30")) is False

    def test_a_generated_profile_names_the_hours_and_applies_nothing(self, user_profile):
        assert user_profile.get_metric("grayscale", "from") == "20:00"
        assert user_profile.get_metric("grayscale", "to") == "06:00"
        assert wanted_at(user_profile, at("21:30")) is False

    def test_an_hour_that_will_not_parse_costs_the_filter_and_says_so(
            self, write_profile, caplog):
        profile = write_profile(GREY_PROFILE.replace('"20:00"', '"eight"'))

        with caplog.at_level("WARNING"):
            assert wanted_at(profile, at("21:30")) is False
        assert "HH:MM" in caplog.text


class TestWhatKWinIsAskedFor:
    def test_going_grey_loads_the_effect_and_makes_it_current(self, qapp, kwinrc):
        caller = Caller()

        a_filter(qapp, caller).apply(True)

        assert caller.methods == ["loadEffect", "reconfigureEffect"]
        assert all(call[1] == EFFECT for call in caller.calls)

    def test_giving_it_back_unloads_it(self, qapp, kwinrc):
        caller = Caller()

        a_filter(qapp, caller).apply(False)

        assert caller.methods == ["unloadEffect"]

    def test_a_session_with_no_kwin_is_not_an_error(self, qapp, kwinrc):
        caller = Caller(reachable=False)

        assert a_filter(qapp, caller).apply(True) is False

    def test_a_compositor_that_will_not_load_it_says_so(self, qapp, kwinrc, caplog):
        caller = Caller()
        caller.loads = False

        with caplog.at_level("WARNING"):
            assert a_filter(qapp, caller).apply(True) is False

        assert caller.methods == ["loadEffect"]
        assert EFFECT in caplog.text


class TestWhatIsWrittenToKwinrc:
    def test_the_mode_the_intensity_and_the_plugin(self, qapp, kwinrc):
        a_filter(qapp).apply(True, intensity=0.8)

        written = kwinrc.read_text(encoding="utf-8")
        assert entries(written, EFFECT_GROUP) == {"Mode": str(MONOCHROME),
                                                  "Intensity": "0.8"}
        assert entries(written, PLUGINS_GROUP)[ENABLED_KEY] == "true"

    def test_giving_the_colour_back_leaves_the_mode_alone(self, qapp, kwinrc):
        kwinrc.write_text(THEIRS, encoding="utf-8")

        a_filter(qapp).apply(False)

        written = kwinrc.read_text(encoding="utf-8")
        assert entries(written, EFFECT_GROUP) == {"Intensity": "0.4"}
        assert entries(written, PLUGINS_GROUP)[ENABLED_KEY] == "false"

    def test_nothing_else_in_the_file_moves(self, qapp, kwinrc):
        kwinrc.write_text(THEIRS, encoding="utf-8")

        a_filter(qapp).apply(True)

        written = kwinrc.read_text(encoding="utf-8")
        assert entries(written, PLUGINS_GROUP)["blurEnabled"] == "false"
        assert entries(written, PLUGINS_GROUP)["slideEnabled"] == "true"
        assert entries(written, "Xwayland") == {"Scale": "1"}

    def test_a_session_with_no_file_yet_gets_one(self, qapp, kwinrc):
        a_filter(qapp).apply(True)

        assert entries(kwinrc.read_text(encoding="utf-8"),
                       PLUGINS_GROUP)[ENABLED_KEY] == "true"


class TestFollowingTheClock:
    def test_a_launch_inside_the_hours_does_not_wait_for_the_next_one(
            self, qapp, kwinrc, write_profile):
        write_profile(GREY_PROFILE)
        caller = Caller()

        a_filter(qapp, caller, "21:30").begin()

        assert caller.methods == ["loadEffect", "reconfigureEffect"]

    def test_a_launch_outside_them_gives_the_colour_back(
            self, qapp, kwinrc, write_profile):
        write_profile(GREY_PROFILE)
        caller = Caller()

        a_filter(qapp, caller, "14:00").begin()

        assert caller.methods == ["unloadEffect"]

    def test_the_compositor_hears_about_a_boundary_and_not_a_minute(
            self, qapp, kwinrc, write_profile):
        write_profile(GREY_PROFILE)
        caller = Caller()
        night = a_filter(qapp, caller, "21:30")

        night.follow_the_clock()
        night.follow_the_clock()
        night.follow_the_clock()

        assert caller.methods == ["loadEffect", "reconfigureEffect"]

    def test_crossing_out_of_them_gives_the_colour_back(
            self, qapp, kwinrc, write_profile):
        write_profile(GREY_PROFILE)
        caller = Caller()
        hand = ["21:30"]
        night = NightFilter(caller=caller, clock=lambda: at(hand[0]))

        night.follow_the_clock()
        hand[0] = "06:30"
        night.follow_the_clock()

        assert caller.methods == ["loadEffect", "reconfigureEffect",
                                         "unloadEffect"]

    def test_a_profile_that_never_asked_touches_nothing(
            self, qapp, kwinrc, user_profile):
        kwinrc.write_text(THEIRS, encoding="utf-8")
        caller = Caller()

        a_filter(qapp, caller, "21:30").begin()

        assert caller.methods == []
        assert kwinrc.read_text(encoding="utf-8") == THEIRS

    def test_turning_it_on_outside_the_hours_still_waits_for_them(
            self, qapp, kwinrc, write_profile):
        write_profile(GREY_PROFILE.replace("true", "false"))
        caller = Caller()
        night = a_filter(qapp, caller, "14:00")
        night.follow_the_clock()

        write_profile(GREY_PROFILE)
        night.follow_the_clock()

        assert caller.methods == []

    def test_switching_it_off_mid_evening_is_answered_within_the_minute(
            self, qapp, kwinrc, write_profile, profile_path):
        write_profile(GREY_PROFILE)
        caller = Caller()
        night = a_filter(qapp, caller, "21:30")
        night.follow_the_clock()

        profile_path.write_text(GREY_PROFILE.replace("true", "false"),
                                encoding="utf-8")
        night.follow_the_clock()

        assert caller.methods[-1] == "unloadEffect"

    def test_a_refused_call_is_tried_again_at_the_next_tick(
            self, qapp, kwinrc, write_profile):
        write_profile(GREY_PROFILE)
        caller = Caller(reachable=False)
        night = a_filter(qapp, caller, "21:30")

        night.follow_the_clock()
        caller.reachable = True
        night.follow_the_clock()

        assert caller.methods == ["loadEffect", "loadEffect",
                                         "reconfigureEffect"]

    def test_closing_traker_leaves_the_screens_as_they_are(
            self, qapp, kwinrc, write_profile):
        write_profile(GREY_PROFILE)
        caller = Caller()
        night = a_filter(qapp, caller, "21:30")
        night.begin()

        night.stop()

        assert "unloadEffect" not in caller.methods
