from collections import namedtuple

from src.database.rows import PlannedMovementRow
from src.domain import plans

TODAY = "2026-10-02"

Plan = namedtuple("Plan", "id name start_date")
Movement = namedtuple("Movement", "id position name sets target_low target_high "
                                  "weight_kg rpe tempo notes")
Logged = namedtuple("Logged", "name set1 set2 set3 set4 set5 weight_kg")

Prescribed = namedtuple("Prescribed", "date name sets target_low target_high "
                                      "weight_kg metric_type")
Session = namedtuple("Session", "date name")


def movement(sets=3, low=8, high=12, weight=20.0, name="DB RDL"):
    return Movement(1, 0, name, sets, low, high, weight, 8.0, "3/3", None)


def prescribed(date=TODAY, name="DB RDL", sets=3, low=8, high=12, weight=20.0,
               metric="Reps"):
    return Prescribed(date, name, sets, low, high, weight, metric)


def logged(*reps, weight=20.0, name="DB RDL"):
    padded = list(reps) + [0] * (5 - len(reps))
    return Logged(name, *padded, weight)


class TestWhetherASessionHappened:
    def test_a_day_with_an_exercise_logged_is_done(self):
        assert plans.status("2026-09-30", {"2026-09-30"}, TODAY) == plans.DONE

    def test_todays_session_is_not_missed_before_the_day_is_over(self):
        assert plans.status(TODAY, set(), TODAY) == plans.TODAY

    def test_todays_session_reads_as_done_once_something_is_logged(self):
        assert plans.status(TODAY, {TODAY}, TODAY) == plans.DONE

    def test_a_past_day_with_nothing_logged_is_missed(self):
        assert plans.status("2026-09-30", set(), TODAY) == plans.MISSED

    def test_a_future_day_is_only_ahead(self):
        assert plans.status("2026-10-09", set(), TODAY) == plans.AHEAD

    def test_any_training_that_day_counts(self):
        assert plans.status("2026-09-30", {"2026-09-30"}, TODAY) == plans.DONE


class TestAdherence:
    DATES = ["2026-09-28", "2026-09-29", "2026-10-01", TODAY, "2026-10-05"]

    def test_only_sessions_due_are_counted(self):
        assert plans.adherence(self.DATES, {"2026-09-28"}, TODAY) == (1, 4)

    def test_a_plan_not_started_yet_is_neither_kept_nor_broken(self):
        assert plans.adherence(["2026-11-01"], set(), TODAY) == (0, 0)

    def test_every_due_session_logged_is_a_full_score(self):
        assert plans.adherence(self.DATES, set(self.DATES), TODAY) == (4, 4)


class TestStreak:
    def test_it_counts_back_from_the_last_session_due(self):
        assert plans.week_streak(
            ["2026-09-28", "2026-09-29", "2026-10-01"],
            {"2026-09-29", "2026-10-01"}, TODAY) == 2

    def test_a_missed_session_ends_it(self):
        assert plans.week_streak(
            ["2026-09-28", "2026-09-29", "2026-10-01"],
            {"2026-09-28"}, TODAY) == 0

    def test_today_unlogged_does_not_break_a_streak_yet(self):
        assert plans.week_streak(
            ["2026-09-29", "2026-10-01", TODAY], {"2026-09-29", "2026-10-01"},
            TODAY) == 2

    def test_today_logged_extends_it(self):
        assert plans.week_streak(
            ["2026-10-01", TODAY], {"2026-10-01", TODAY}, TODAY) == 2


class TestWhichCycleIsTheCurrentOne:
    def test_the_one_that_has_started(self):
        catalogue = [Plan(2, "Cycle 2", "2027-02-01"), Plan(1, "Cycle 1", "2026-09-14")]
        assert plans.current_plan(catalogue, TODAY).id == 1

    def test_the_next_one_when_none_has_started(self):
        catalogue = [Plan(2, "Cycle 2", "2027-02-01")]
        assert plans.current_plan(catalogue, TODAY).id == 2

    def test_nothing_at_all_when_there_are_no_cycles(self):
        assert plans.current_plan([], TODAY) is None


class TestHowAPrescriptionReads:
    def test_a_range_is_written_with_both_ends(self):
        assert plans.scheme_text(3, 8, 12) == "3x8-12"

    def test_a_fixed_target_is_written_once(self):
        assert plans.scheme_text(3, 30, 30, "Seconds") == "3x30 s"

    def test_a_seconds_movement_says_so(self):
        assert plans.target_text(30, 45, "Seconds") == "30-45 s"

    def test_a_whole_number_keeps_no_decimal_point(self):
        assert plans.target_text(8, 12) == "8-12"

    def test_a_movement_with_no_range_says_how_many_sets(self):
        assert plans.scheme_text(3, 0, 0) == "3 sets"

    def test_a_range_with_no_top_is_its_bottom(self):
        assert plans.scheme_text(3, 8, 0) == "3x8"

    def test_a_movement_with_neither_sets_nor_range_says_nothing(self):
        assert plans.scheme_text(0, 0, 0) == ""

    def test_a_movement_line_drops_the_target_it_never_had(self):
        assert plans.target_text(None, None) == ""


class TestOneDaysPrescription:
    def test_the_session_on_a_day(self):
        sessions = [Session(TODAY, "Upper A"), Session("2026-10-03", "Lower A")]

        assert plans.session_on(sessions, TODAY).name == "Upper A"
        assert plans.session_on(sessions, "2026-11-01") is None

    def test_only_that_days_movements(self):
        movements = [prescribed(name="DB RDL"), prescribed("2026-10-03", "Row"),
                     prescribed(name="Plank")]

        assert [m.name for m in plans.movements_on(movements, TODAY)] == [
            "DB RDL", "Plank"]

    def test_the_order_the_service_answered_in_is_kept(self):
        movements = [prescribed(name="Plank"), prescribed(name="DB RDL")]

        assert [m.name for m in plans.movements_on(movements, TODAY)] == [
            "Plank", "DB RDL"]

    def test_a_day_with_nothing_on_it_answers_nothing(self):
        assert plans.prescribed_day([], [prescribed()], TODAY) == (None, [])

    def test_the_session_and_its_movements_come_together(self):
        session, movements = plans.prescribed_day(
            [Session(TODAY, "Upper A")], [prescribed(), prescribed("2026-10-03")],
            TODAY)

        assert (session.name, len(movements)) == ("Upper A", 1)

    def test_a_movement_reads_as_one_line(self):
        assert plans.movement_text(prescribed()) == "DB RDL · 3x8-12 · 20 kg"

    def test_a_bodyweight_movement_names_no_load(self):
        assert plans.movement_text(prescribed(name="Plank", weight=0,
                                              low=30, high=45,
                                              metric="Seconds")) == \
            "Plank · 3x30-45 s"

    def test_an_orphaned_movement_still_reads(self):
        assert plans.movement_text(prescribed(name=None)) == "— · 3x8-12 · 20 kg"


class TestWhatWasActuallyLogged:
    def test_trailing_empty_sets_are_absence_not_zeroes(self):
        assert plans.logged_sets(logged(10, 10, 9)) == [10, 10, 9]

    def test_the_ledger_row_reads_as_sets_at_a_load(self):
        assert plans.logged_text(logged(10, 10, 9, weight=22.5)) == "10/10/9 @ 22.5"

    def test_a_bodyweight_movement_reports_no_load(self):
        assert plans.logged_text(logged(30, 30, 30, weight=0)) == "30/30/30"

    def test_an_unlogged_movement_reads_as_blank(self):
        assert plans.logged_text(None) == ""

    def test_the_first_row_of_a_repeated_movement_wins(self):
        first, second = logged(10, 10, 10), logged(5, 5, 5)
        assert plans.logs_by_exercise([first, second])["db rdl"] is first

    def test_a_movement_is_matched_however_it_was_capitalised(self):
        assert "db rdl" in plans.logs_by_exercise([logged(8, name="DB RDL")])


class TestWhetherThePrescriptionWasMet:
    def test_every_set_at_the_bottom_of_the_range_is_a_hit(self):
        assert plans.verdict(movement(), logged(8, 8, 8)) == "hit"

    def test_a_set_short_of_the_range_is_under(self):
        assert plans.verdict(movement(), logged(12, 12, 6)) == "under"

    def test_one_set_too_few_is_under(self):
        assert plans.verdict(movement(sets=3), logged(8, 8)) == "under"

    def test_a_lighter_load_is_under_however_many_reps(self):
        assert plans.verdict(movement(weight=20.0),
                             logged(12, 12, 12, weight=16.5)) == "under"

    def test_a_heavier_load_is_still_a_hit(self):
        assert plans.verdict(movement(weight=20.0),
                             logged(8, 8, 8, weight=22.5)) == "hit"

    def test_an_unlogged_movement_gets_no_verdict(self):
        assert plans.verdict(movement(), None) == ""


class TestTheJoinedRow:
    def test_it_carries_the_prescription_and_the_ledgers_answer(self):
        row = PlannedMovementRow.of(movement(), logged(10, 10, 9, weight=22.5))
        assert (row.logged, row.result) == ("10/10/9 @ 22.5", "hit")

    def test_an_unlogged_movement_leaves_both_blank(self):
        row = PlannedMovementRow.of(movement(), None)
        assert (row.logged, row.result) == ("", "")

    def test_its_field_order_is_the_tabs_column_order(self):
        from src.gui.views.plan_view import MOVEMENT_HEADERS

        assert len(PlannedMovementRow._fields) - 1 == len(MOVEMENT_HEADERS)


class TestParsingADate:
    def test_an_iso_date_becomes_a_date(self):
        assert plans.parse_iso("2026-10-02").weekday() == 4

    def test_anything_else_is_none_rather_than_an_exception(self):
        assert plans.parse_iso("02.10.2026") is None
        assert plans.parse_iso(None) is None
