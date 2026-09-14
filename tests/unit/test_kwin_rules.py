import pytest

from src.desktop.kwin_rules import (EXACT_MATCH, FORCE_TEMPORARILY, REST_GROUP,
                                   SUBSTRING_MATCH, WINDOW_GROUP, RestRule,
                                   WindowHome, activity_id, desktop_id, prune,
                                   removed, rest_keys, window_keys, written)

pytestmark = pytest.mark.exact


def wall_rule(text):
    return written(text, REST_GROUP, rest_keys("Traker rest"))


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


class Compositor:
    def __init__(self, takes=True):
        self.takes = takes
        self.reconfigures = 0

    def __call__(self):
        self.reconfigures += 1
        return self.takes


@pytest.fixture
def rules_file(tmp_path):
    return tmp_path / "kwinrulesrc"


class TestWhatItWrites:
    def test_it_forces_every_desktop_and_activity_temporarily(self):
        rule = entries(wall_rule(""), REST_GROUP)
        assert rule["desktops"] == ""
        assert rule["activity"] == ""
        assert rule["desktopsrule"] == str(FORCE_TEMPORARILY)
        assert rule["activityrule"] == str(FORCE_TEMPORARILY)

    def test_it_matches_the_wall_title_and_not_the_application_window(self):
        rule = entries(wall_rule(""), REST_GROUP)
        assert rule["title"] == "Traker rest"
        assert rule["titlematch"] == str(SUBSTRING_MATCH)
        assert "Traker rest — DP-1".count(rule["title"]) == 1
        assert rule["title"] not in "Traker"

    def test_a_wall_is_in_front_and_whole_and_cannot_be_minimised(self):
        rule = entries(wall_rule(""), REST_GROUP)
        assert rule["above"] == "true"
        assert rule["fullscreen"] == "true"
        assert rule["minimize"] == "false"
        assert rule["aboverule"] == str(FORCE_TEMPORARILY)

    def test_it_says_whose_rule_it_is(self):
        assert "Traker" in entries(wall_rule(""), REST_GROUP)["Description"]

    def test_it_is_listed_first_so_a_members_own_rule_cannot_win(self):
        before = "[General]\ncount=2\nrules=mine,theirs\n\n[mine]\ndesktops=a\n"
        after = wall_rule(before)
        assert entries(after, "General")["rules"] == f"{REST_GROUP},mine,theirs"
        assert entries(after, "General")["count"] == "3"


class TestAndNothingElseMoves:
    def test_it_keeps_a_members_own_rules(self):
        before = ("[General]\ncount=1\nrules=6f1a\n\n"
                  "[6f1a]\nDescription=Konsole\nwmclass=konsole\n"
                  "desktops=d1\ndesktopsrule=2\n")
        after = wall_rule(before)
        assert entries(after, "6f1a") == entries(before, "6f1a")
        assert "[6f1a]" in after

    def test_it_keeps_the_groups_kconfig_spells_with_two_brackets(self):
        before = "[$Version]\nupdate_info=kwin.upd:replace-scalein\n"
        assert before in wall_rule(before)

    def test_it_materialises_a_legacy_count_rather_than_deleting_it(self):
        before = "[General]\ncount=2\n\n[1]\nwmclass=a\n\n[2]\nwmclass=b\n"
        after = wall_rule(before)
        assert entries(after, "General")["rules"] == f"{REST_GROUP},1,2"
        assert entries(after, "General")["count"] == "3"

    def test_a_second_break_does_not_stack_a_second_rule(self):
        once = wall_rule("")
        assert wall_rule(once) == once

    def test_a_file_with_no_general_group_gets_one_without_gluing_it_on(self):
        before = "[6f1a]\nwmclass=konsole"
        after = wall_rule(before)
        assert entries(after, "6f1a")["wmclass"] == "konsole"
        assert entries(after, "General")["rules"] == REST_GROUP

    def test_a_hand_edited_file_with_no_last_newline_is_not_run_together(self):
        before = "[General]\ncount=1\nrules=6f1a\n\n[6f1a]\nwmclass=konsole"
        after = wall_rule(before)
        assert entries(after, "6f1a")["wmclass"] == "konsole"
        assert f"konsole\n[{REST_GROUP}]" in after


class TestTakingItBackOut:
    def test_it_leaves_the_file_as_it_found_it(self):
        before = ("[General]\ncount=1\nrules=6f1a\n\n"
                  "[6f1a]\nDescription=Konsole\nwmclass=konsole\n")
        assert removed(wall_rule(before), REST_GROUP) == before

    def test_a_file_with_no_rule_in_it_is_not_touched(self):
        before = "[General]\ncount=1\nrules=6f1a\n\n[6f1a]\nwmclass=konsole\n"
        assert removed(before, REST_GROUP) == before

    def test_it_empties_the_list_of_a_file_that_had_only_ours(self):
        after = removed(wall_rule(""), REST_GROUP)
        assert entries(after, "General")["rules"] == ""
        assert entries(after, "General")["count"] == "0"
        assert REST_GROUP not in after


class TestHoldingOneForABreak:
    def test_it_writes_the_rule_and_asks_kwin_to_read_it(self, rules_file):
        kwin = Compositor()
        rule = RestRule("Traker rest", path=str(rules_file), reconfigure=kwin)

        assert rule.hold() is True
        assert rule.holding is True
        assert kwin.reconfigures == 1
        assert entries(rules_file.read_text(), REST_GROUP)["title"] == "Traker rest"

    def test_it_creates_a_file_a_session_has_never_had(self, rules_file):
        rule = RestRule("Traker rest", path=str(rules_file),
                        reconfigure=Compositor())
        rule.hold()
        assert rules_file.exists()
        assert entries(rules_file.read_text(), "General")["rules"] == REST_GROUP

    def test_a_session_with_nobody_to_tell_is_left_without_the_file(self, rules_file):
        kwin = Compositor(takes=False)
        rule = RestRule("Traker rest", path=str(rules_file), reconfigure=kwin)

        assert rule.hold() is False
        assert rule.holding is False
        assert not rules_file.exists()

    def test_a_session_with_nobody_to_tell_keeps_the_file_it_had(self, rules_file):
        before = "[General]\ncount=1\nrules=6f1a\n\n[6f1a]\nwmclass=konsole\n"
        rules_file.write_text(before)
        rule = RestRule("Traker rest", path=str(rules_file),
                        reconfigure=Compositor(takes=False))

        assert rule.hold() is False
        assert rules_file.read_text() == before

    def test_a_break_with_no_wall_title_holds_nothing(self, rules_file):
        kwin = Compositor()
        assert RestRule("", path=str(rules_file), reconfigure=kwin).hold() is False
        assert kwin.reconfigures == 0
        assert not rules_file.exists()

    def test_it_gives_the_file_back_at_the_end_of_a_break(self, rules_file):
        before = "[General]\ncount=1\nrules=6f1a\n\n[6f1a]\nwmclass=konsole\n"
        rules_file.write_text(before)
        kwin = Compositor()
        rule = RestRule("Traker rest", path=str(rules_file), reconfigure=kwin)

        rule.hold()
        assert rule.release() is True
        assert rule.holding is False
        assert rules_file.read_text() == before
        assert kwin.reconfigures == 2

    def test_releasing_a_rule_kwin_already_discarded_writes_nothing(self, rules_file):
        kwin = Compositor()
        rule = RestRule("Traker rest", path=str(rules_file), reconfigure=kwin)
        rule.hold()
        rules_file.write_text("[General]\ncount=0\nrules=\n")

        assert rule.release() is True
        assert kwin.reconfigures == 1

    def test_it_holds_nothing_where_the_file_cannot_be_written(self, tmp_path):
        kwin = Compositor()
        (tmp_path / "kwinrulesrc").mkdir()
        rule = RestRule("Traker rest", path=str(tmp_path / "kwinrulesrc"),
                        reconfigure=kwin)

        assert rule.hold() is False
        assert rule.holding is False
        assert kwin.reconfigures == 0


class TestStandingDownWhenTheBreakRunsOut:
    def test_the_desktops_go_back_and_the_walls_stay_in_front(self, rules_file):
        kwin = Compositor()
        rule = RestRule("Traker rest", path=str(rules_file), reconfigure=kwin)
        rule.hold()

        assert rule.stand_down() is True

        standing = entries(rules_file.read_text(), REST_GROUP)
        assert "desktopsrule" not in standing
        assert "activityrule" not in standing
        assert standing["above"] == "true"
        assert standing["fullscreen"] == "true"
        assert rule.holding is True
        assert rule.everywhere is False
        assert kwin.reconfigures == 2

    def test_it_is_still_one_rule_and_still_ahead_of_a_members_own(self, rules_file):
        rules_file.write_text("[General]\ncount=1\nrules=mine\n\n[mine]\ndesktops=a\n")
        rule = RestRule("Traker rest", path=str(rules_file), reconfigure=Compositor())
        rule.hold()

        rule.stand_down()

        assert entries(rules_file.read_text(), "General")["rules"] == f"{REST_GROUP},mine"
        assert rules_file.read_text().count(f"[{REST_GROUP}]") == 1

    def test_what_is_left_still_comes_out_whole(self, rules_file):
        before = "[General]\ncount=1\nrules=6f1a\n\n[6f1a]\nwmclass=konsole\n"
        rules_file.write_text(before)
        rule = RestRule("Traker rest", path=str(rules_file), reconfigure=Compositor())
        rule.hold()
        rule.stand_down()

        assert rule.release() is True
        assert rules_file.read_text() == before

    def test_a_rule_that_was_never_held_stands_down_to_nothing(self, rules_file):
        kwin = Compositor()
        rule = RestRule("Traker rest", path=str(rules_file), reconfigure=kwin)

        assert rule.stand_down() is False
        assert kwin.reconfigures == 0
        assert not rules_file.exists()

    def test_the_next_break_puts_them_everywhere_again(self, rules_file):
        rule = RestRule("Traker rest", path=str(rules_file), reconfigure=Compositor())
        rule.hold()
        rule.stand_down()
        rule.release()

        rule.hold()

        assert rule.everywhere is True
        assert entries(rules_file.read_text(), REST_GROUP)["desktopsrule"] == \
            str(FORCE_TEMPORARILY)


class TestWhatACrashLeavesBehind:
    def test_prune_takes_out_a_rule_no_process_remembers(self, rules_file):
        rules_file.write_text(wall_rule(""))
        kwin = Compositor()

        assert prune((REST_GROUP,), str(rules_file), kwin) is True
        assert REST_GROUP not in rules_file.read_text()
        assert kwin.reconfigures == 1

    def test_prune_on_a_clean_session_asks_kwin_for_nothing(self, rules_file):
        rules_file.write_text("[General]\ncount=0\nrules=\n")
        kwin = Compositor()

        assert prune((REST_GROUP,), str(rules_file), kwin) is True
        assert kwin.reconfigures == 0

    def test_prune_answers_for_a_session_that_never_had_the_file(self, tmp_path):
        kwin = Compositor()
        assert prune((REST_GROUP,), str(tmp_path / "nothing-here"), kwin) is True
        assert kwin.reconfigures == 0


def test_the_suite_never_writes_the_real_rules_file():
    from src.desktop import kwin_rules

    assert kwin_rules.DEFAULT_PATH.endswith("kwinrulesrc")
    assert "traker-tests-" in kwin_rules.DEFAULT_PATH

KWINRC = """[Desktops]
Id_1=d-one
Id_2=d-two
Id_5=d-five
Name_2=Reading
Number=6
Rows=2

[Windows]
Placement=Centered
"""


class Activities:
    def __init__(self, names=None, reachable=True):
        self.names = names if names is not None else {"a-one": "Personal",
                                                      "a-two": "Work"}
        self.reachable = reachable
        self.calls = []

    def __call__(self, service, path, interface, method, *args):
        self.calls.append((method,) + tuple(str(a) for a in args))
        if not self.reachable:
            return False, None
        if method == "ListActivities":
            return True, list(self.names)
        if method == "ActivityName":
            return True, self.names.get(str(args[0]), "")
        return True, None


@pytest.fixture
def kwinrc(tmp_path):
    path = tmp_path / "kwinrc"
    path.write_text(KWINRC)
    return str(path)


class TestNamingADesktop:
    def test_a_position_answers_with_its_id(self, kwinrc):
        assert desktop_id(5, kwinrc) == "d-five"
        assert desktop_id("5", kwinrc) == "d-five"

    def test_kwins_own_default_name_is_understood(self, kwinrc):
        assert desktop_id("Desktop 5", kwinrc) == "d-five"

    def test_a_renamed_desktop_answers_to_its_name(self, kwinrc):
        assert desktop_id("Reading", kwinrc) == "d-two"

    def test_a_name_this_session_does_not_have_answers_nothing(self, kwinrc):
        assert desktop_id("Desktop 9", kwinrc) is None
        assert desktop_id("Nonsense", kwinrc) is None

    def test_the_case_of_a_label_read_off_a_pager_does_not_matter(self, kwinrc):
        assert desktop_id("desktop 5", kwinrc) == "d-five"
        assert desktop_id("READING", kwinrc) == "d-two"

    def test_a_desktop_with_no_id_yet_answers_nothing_rather_than_empty(self, kwinrc):
        assert desktop_id(3, kwinrc) is None

    def test_a_session_with_no_kwinrc_answers_nothing(self, tmp_path):
        assert desktop_id(5, str(tmp_path / "not-here")) is None


class TestNamingAnActivity:
    def test_a_name_answers_with_its_id(self):
        assert activity_id("Personal", Activities()) == "a-one"

    def test_an_id_is_passed_straight_through(self):
        assert activity_id("a-two", Activities()) == "a-two"

    def test_a_name_this_session_does_not_have_answers_nothing(self):
        assert activity_id("Gardening", Activities()) is None

    def test_the_case_of_a_name_does_not_matter(self):
        assert activity_id("personal", Activities()) == "a-one"

    def test_a_session_with_no_activity_manager_answers_nothing(self):
        assert activity_id("Personal", Activities(reachable=False)) is None


class TestTheWindowsOwnRule:
    def test_it_matches_the_window_exactly_and_so_cannot_reach_a_wall(self):
        rule = dict(window_keys("Traker", "d-five", "a-one"))

        assert rule["title"] == "Traker"
        assert rule["titlematch"] == EXACT_MATCH
        assert rule["desktops"] == "d-five"
        assert rule["activity"] == "a-one"
        assert rule["desktopsrule"] == FORCE_TEMPORARILY
        assert rule["activityrule"] == FORCE_TEMPORARILY

    def test_it_writes_both_dimensions(self, rules_file, kwinrc):
        kwin = Compositor()
        home = WindowHome("Traker", desktop="Desktop 5", activity="Personal",
                          path=str(rules_file), reconfigure=kwin,
                          kwinrc=kwinrc, caller=Activities())

        assert home.hold() is True
        rule = entries(rules_file.read_text(), WINDOW_GROUP)
        assert rule["desktops"] == "d-five"
        assert rule["activity"] == "a-one"
        assert kwin.reconfigures == 1

    def test_a_dimension_that_resolved_alone_is_the_only_one_written(
            self, rules_file, kwinrc):
        home = WindowHome("Traker", desktop="Desktop 5", activity="Gardening",
                          path=str(rules_file), reconfigure=Compositor(),
                          kwinrc=kwinrc, caller=Activities())

        assert home.hold() is True
        rule = entries(rules_file.read_text(), WINDOW_GROUP)
        assert rule["desktops"] == "d-five"
        assert "activity" not in rule
        assert "activityrule" not in rule

    def test_a_profile_naming_nothing_writes_nothing(self, rules_file, kwinrc):
        kwin = Compositor()
        home = WindowHome("Traker", path=str(rules_file), reconfigure=kwin,
                          kwinrc=kwinrc, caller=Activities())

        assert home.hold() is False
        assert not rules_file.exists()
        assert kwin.reconfigures == 0

    def test_two_names_that_resolve_to_nothing_write_nothing(self, rules_file, kwinrc):
        home = WindowHome("Traker", desktop="Desktop 9", activity="Gardening",
                          path=str(rules_file), reconfigure=Compositor(),
                          kwinrc=kwinrc, caller=Activities())

        assert home.hold() is False
        assert not rules_file.exists()

    def test_closing_the_window_gives_the_rule_back(self, rules_file, kwinrc):
        home = WindowHome("Traker", desktop=5, activity="Personal",
                          path=str(rules_file), reconfigure=Compositor(),
                          kwinrc=kwinrc, caller=Activities())
        home.hold()

        assert home.release() is True
        assert WINDOW_GROUP not in rules_file.read_text()


class TestTheTwoRulesTogether:
    def test_a_break_and_the_window_can_both_be_held(self, rules_file, kwinrc):
        home = WindowHome("Traker", desktop=5, activity="Personal",
                          path=str(rules_file), reconfigure=Compositor(),
                          kwinrc=kwinrc, caller=Activities())
        rest = RestRule("Traker rest", path=str(rules_file),
                        reconfigure=Compositor())
        home.hold()
        rest.hold()

        text = rules_file.read_text()
        assert entries(text, WINDOW_GROUP)["desktops"] == "d-five"
        assert entries(text, REST_GROUP)["desktops"] == ""
        assert entries(text, "General")["rules"].split(",")[:2] == [
            REST_GROUP, WINDOW_GROUP]

    def test_the_window_rule_cannot_match_a_wall(self):
        window = dict(window_keys("Traker", "d-five", "a-one"))
        assert window["titlematch"] == EXACT_MATCH
        assert window["title"] != "Traker rest \u2014 DP-1"

    def test_the_break_rule_forces_what_a_foreign_rule_used_to_take_away(self):
        rule = dict(rest_keys("Traker rest"))
        assert rule["fullscreen"] == "true"
        assert rule["above"] == "true"
        assert rule["minimize"] == "false"
        for key in ("fullscreenrule", "aboverule", "minimizerule"):
            assert rule[key] == FORCE_TEMPORARILY

    def test_a_break_leaves_the_windows_rule_where_it_found_it(self, rules_file, kwinrc):
        home = WindowHome("Traker", desktop=5, path=str(rules_file),
                          reconfigure=Compositor(), kwinrc=kwinrc,
                          caller=Activities())
        home.hold()
        before = rules_file.read_text()

        rest = RestRule("Traker rest", path=str(rules_file),
                        reconfigure=Compositor())
        rest.hold()
        rest.release()

        assert rules_file.read_text() == before
