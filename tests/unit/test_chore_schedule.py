import datetime

import pytest

from src.domain import chores

FRIDAY = "2026-09-11"


def due(last_done, anchor=FRIDAY, period=7, grace=2):
    return chores.next_due(anchor, period, grace, last_done)


def date(iso):
    return datetime.date.fromisoformat(iso)


class Chore:
    def __init__(self, name="Chore", period_days=7, anchor=FRIDAY,
                 grace_days=None, last_done=None, active=1, chore_id=1):
        self.id = chore_id
        self.name = name
        self.period_days = period_days
        self.anchor = anchor
        self.grace_days = grace_days
        self.last_done = last_done
        self.active = active


def test_never_done_is_due_on_its_anchor():
    assert due(None) == date(FRIDAY)


def test_one_day_early_clears_it_and_the_weekday_holds():
    assert due("2026-09-10") == date("2026-09-18")


def test_one_day_late_clears_it_and_the_weekday_still_holds():
    assert due("2026-09-12") == date("2026-09-18")


def test_four_days_early_does_not_clear_it():
    assert due("2026-09-07") == date(FRIDAY)


def test_two_days_late_pulls_the_next_one_in():
    assert due("2026-09-13") == date("2026-09-18")


def test_weeks_late_drops_what_was_missed_rather_than_stacking_it():
    done = "2026-09-30"
    assert due(done) == date("2026-10-09")


@pytest.mark.parametrize("done", [
    "2026-09-05", "2026-09-08", "2026-09-10", FRIDAY, "2026-09-12", "2026-09-20",
])


def test_never_asked_for_again_the_next_day(done):
    assert due(done) > date(done) + datetime.timedelta(days=2)


@pytest.mark.parametrize("period", [1, 2, 3, 7, 14, 30, 90])
def test_the_next_due_is_always_an_occurrence_of_the_cadence(period):
    answer = due("2026-09-19", period=period, grace=0)
    assert (answer - date(FRIDAY)).days % period == 0


def test_a_daily_chore_is_due_again_tomorrow():
    assert due("2026-09-11", period=1, grace=0) == date("2026-09-12")


def test_an_unreadable_anchor_has_no_due_date_rather_than_an_exception():
    assert chores.next_due("not a date", 7, 2, None) is None


def test_a_completion_that_will_not_parse_leaves_the_anchor_standing():
    assert due("yesterday") == date(FRIDAY)


@pytest.mark.parametrize("period,expected", [
    (1, 0), (3, 1), (7, 2), (14, 4), (30, 7), (90, 7),
])


def test_default_grace_scales_with_the_cadence_and_is_capped(period, expected):
    assert chores.default_grace(period) == expected


def test_a_weekly_default_grace_separates_the_members_two_cases():
    grace = chores.default_grace(7)
    assert due("2026-09-10", grace=grace) == date("2026-09-18")
    assert due("2026-09-07", grace=grace) == date(FRIDAY)


def test_a_stored_zero_grace_means_only_on_the_day():
    assert chores.grace_of(Chore(grace_days=0)) == 0
    assert due("2026-09-10", grace=0) == date(FRIDAY)


def test_an_absent_grace_is_derived_rather_than_read_as_zero():
    assert chores.grace_of(Chore(period_days=30, grace_days=None)) == 7


class TestItAlwaysLandsOnTheSameDay:
    @pytest.mark.parametrize("period", [7, 14, 21, 28, 35, 70, 364])
    def test_a_whole_number_of_weeks_keeps_the_anchors_weekday_for_ever(
            self, period):
        anchor = date(FRIDAY)
        landed = set()
        for offset in range(-400, 400):
            done = (anchor + datetime.timedelta(days=offset)).isoformat()
            answer = due(done, period=period,
                         grace=chores.default_grace(period))
            landed.add(answer.weekday())

        assert landed == {anchor.weekday()}

    @pytest.mark.parametrize("period", [3, 10, 30, 31, 45])
    def test_anything_else_walks_off_the_weekday(self, period):
        landed = {due((date(FRIDAY) + datetime.timedelta(days=offset)).isoformat(),
                      period=period, grace=0).weekday()
                  for offset in range(-400, 400)}

        assert len(landed) > 1

    @pytest.mark.parametrize("period,expected", [
        (7, "Fri"), (14, "Fri"), (28, "Fri"), (364, "Fri"),
        (1, chores.DRIFTS), (3, chores.DRIFTS), (30, chores.DRIFTS),
    ])
    def test_lands_on_says_which_day_or_that_there_is_none(self, period, expected):
        assert chores.lands_on(FRIDAY, period) == expected

    def test_it_reads_the_weekday_off_the_anchor_rather_than_off_today(self):
        assert chores.lands_on("2026-09-14", 7) == "Mon"
        assert chores.lands_on("2026-09-13", 14) == "Sun"

    def test_an_unreadable_anchor_keeps_no_day_rather_than_guessing_one(self):
        assert chores.lands_on("Friday", 7) == chores.DRIFTS

    def test_the_standing_carries_it_so_a_surface_need_not_recompute_it(self):
        entry = chores.Standing(Chore(period_days=14), date(FRIDAY))

        assert entry.lands_on == "Fri"

    def test_every_weekday_is_reachable_and_named_once(self):
        days = {chores.lands_on(f"2026-09-{7 + n:02d}", 7) for n in range(7)}

        assert days == set(chores.WEEKDAYS)
        assert len(chores.WEEKDAYS) == chores.DAYS_IN_WEEK


def test_standing_names_where_a_chore_is_today():
    assert chores.standing(date("2026-09-09"), 2, date(FRIDAY)) == chores.OVERDUE
    assert chores.standing(date(FRIDAY), 2, date(FRIDAY)) == chores.DUE
    assert chores.standing(date("2026-09-12"), 2, date(FRIDAY)) == chores.EARLY
    assert chores.standing(date("2026-09-20"), 2, date(FRIDAY)) == chores.LATER


def test_early_is_exactly_the_window_in_which_doing_it_clears_the_occasion():
    anchor, period, grace = FRIDAY, 7, 2
    for ahead in range(0, 6):
        day = date(FRIDAY) - datetime.timedelta(days=ahead)
        early = chores.standing(date(FRIDAY), grace, day) in (
            chores.DUE, chores.EARLY)
        cleared = chores.next_due(anchor, period, grace, day.isoformat()) \
            > date(FRIDAY)
        assert early == cleared, day


def test_days_over_and_the_words_for_it():
    entry = chores.Standing(Chore(last_done=None), date("2026-09-14"))
    assert entry.standing == chores.OVERDUE
    assert entry.days_over == 3
    assert entry.said() == "3 days over"


def test_one_day_over_is_said_in_the_singular():
    entry = chores.Standing(Chore(last_done=None), date("2026-09-12"))
    assert entry.said() == "1 day over"


def test_a_chore_doable_today_says_so_rather_than_naming_a_date():
    entry = chores.Standing(Chore(last_done=None), date("2026-09-10"))
    assert entry.standing == chores.EARLY
    assert entry.said() == "ok today"


def test_the_board_is_worst_first():
    made = [
        Chore("Fresh", anchor="2026-09-25", chore_id=1),
        Chore("Late", anchor="2026-09-01", chore_id=2),
        Chore("Today", anchor=FRIDAY, chore_id=3),
        Chore("Later", anchor="2026-09-12", chore_id=4),
    ]
    names = [entry.name for entry in chores.board(made, FRIDAY)]
    assert names == ["Late", "Today", "Later", "Fresh"]


def test_two_chores_equally_late_keep_a_stable_order():
    made = [Chore("Zinc", anchor="2026-09-01", chore_id=1),
            Chore("Apple", anchor="2026-09-01", chore_id=2)]
    assert [e.name for e in chores.board(made, FRIDAY)] == ["Apple", "Zinc"]
    assert [e.name for e in chores.board(made[::-1], FRIDAY)] == ["Apple", "Zinc"]


def test_a_paused_chore_is_off_the_board_entirely():
    made = [Chore("Paused", active=0), Chore("Kept", chore_id=2)]
    assert [entry.name for entry in chores.board(made, FRIDAY)] == ["Kept"]


def test_a_row_from_before_active_existed_is_still_wanted():
    class Old:
        id, name, period_days, anchor = 1, "Old", 7, FRIDAY
        grace_days = last_done = None

    assert [entry.name for entry in chores.board([Old()], FRIDAY)] == ["Old"]


def test_due_now_offers_the_three_standings_a_break_can_act_on():
    made = [
        Chore("Late", anchor="2026-09-01", chore_id=1),
        Chore("Today", anchor=FRIDAY, chore_id=2),
        Chore("Early", anchor="2026-09-12", chore_id=3),
        Chore("Next week", anchor="2026-09-18", chore_id=4),
    ]
    offered = [entry.name for entry in chores.due_now(made, FRIDAY)]
    assert offered == ["Late", "Today", "Early"]


def test_ticking_a_chore_takes_it_off_the_break_list():
    made = [Chore("Vacuum", anchor=FRIDAY)]
    assert [e.name for e in chores.due_now(made, FRIDAY)] == ["Vacuum"]

    made[0].last_done = FRIDAY
    assert chores.due_now(made, FRIDAY) == []
