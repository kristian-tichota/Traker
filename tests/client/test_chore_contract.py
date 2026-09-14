import datetime

import pytest

from src.database import DatabaseClient
from src.domain import chores

VACUUM = {"name": "Vacuum", "period_days": 7, "anchor": "2026-09-11"}
BINS = {"name": "Bins", "period_days": 7, "anchor": "2026-09-08",
        "grace_days": 1, "notes": "Tuesday night"}


@pytest.fixture
def offline_client(offline_requests, profile_path):
    return DatabaseClient(base_url="http://traker.test", token="irrelevant")


@pytest.fixture
def board(db_client):
    db_client.add_chore(VACUUM)
    db_client.add_chore(BINS)
    return db_client


def by_name(client):
    return {row.name: row for row in client.get_chores()}


class TestTheWireShape:
    def test_a_chore_arrives_as_a_named_row(self, board):
        row = by_name(board)["Vacuum"]

        assert (row.name, row.period_days, row.anchor) == (
            "Vacuum", 7, "2026-09-11")
        assert (row.grace_days, row.active) == (None, 1)

    def test_it_carries_the_aggregate_the_rule_reads(self, board):
        board.complete_chore({"name": "Vacuum", "date": "2026-09-11"})
        row = by_name(board)["Vacuum"]

        assert (row.last_done, row.done_count) == ("2026-09-11", 1)

    def test_a_completion_names_its_chore_and_who_ticked_it(self, board):
        board.complete_chore({"name": "Bins", "date": "2026-09-08"})

        (row,) = board.get_chore_completions()

        assert (row.date, row.name) == ("2026-09-08", "Bins")
        assert row.done_by

    def test_the_completion_date_is_called_date_so_the_cache_can_bound_it(
            self, board):
        board.complete_chore({"name": "Bins", "date": "2026-09-08"})

        (row,) = board.get_chore_completions()

        assert row.date == "2026-09-08"


class TestTheRuleAgainstWhatCameBack:
    def test_the_weekday_holds_when_it_is_done_a_day_late(self, board):
        board.complete_chore({"name": "Vacuum", "date": "2026-09-12"})
        row = by_name(board)["Vacuum"]

        entry = chores.Standing(row, datetime.date(2026, 9, 13))

        assert entry.due == datetime.date(2026, 9, 18)

    def test_doing_it_four_days_early_leaves_it_standing(self, board):
        board.complete_chore({"name": "Vacuum", "date": "2026-09-07"})
        row = by_name(board)["Vacuum"]

        entry = chores.Standing(row, datetime.date(2026, 9, 7))

        assert entry.due == datetime.date(2026, 9, 11)

    def test_a_chore_never_done_is_due_on_its_anchor(self, board):
        entry = chores.Standing(by_name(board)["Vacuum"],
                                datetime.date(2026, 9, 11))

        assert entry.standing == chores.DUE


class TestTheCache:
    def test_a_second_read_is_answered_without_the_wire(self, board):
        board.cache.clear()
        board.get_chores()
        before = board.cache.hits

        board.get_chores()

        assert board.cache.hits == before + 1

    def test_ticking_one_drops_what_the_board_was_read_from(self, board):
        board.get_chores()
        assert "chore" in board.cache.cached_domains()

        board.complete_chore({"name": "Vacuum", "date": "2026-09-11"})

        assert "chore" not in board.cache.cached_domains()

    def test_defining_one_drops_it_too(self, board):
        board.get_chores()

        board.add_chore({"name": "Descale", "period_days": 30,
                         "anchor": "2026-10-01"})

        assert "chore" not in board.cache.cached_domains()

    def test_a_chore_write_leaves_another_domain_alone(self, board):
        board.get_food_logs()
        assert "food" in board.cache.cached_domains()

        board.complete_chore({"name": "Vacuum", "date": "2026-09-11"})

        assert "food" in board.cache.cached_domains()

    def test_the_board_and_the_history_never_answer_each_other(self, board):
        board.complete_chore({"name": "Vacuum", "date": "2026-09-11"})
        board.get_chores()

        (row,) = board.get_chore_completions()

        assert row.name == "Vacuum" and row.date == "2026-09-11"

    def test_the_history_answers_the_board_no_better(self, board):
        board.complete_chore({"name": "Vacuum", "date": "2026-09-11"})
        board.get_chore_completions()

        assert sorted(row.name for row in board.get_chores()) == ["Bins", "Vacuum"]

    def test_a_bounded_history_read_answers_only_its_window(self, board):
        for day in ("2026-09-04", "2026-09-18"):
            board.complete_chore({"name": "Vacuum", "date": day})
        board.get_chore_completions()

        narrowed = board.get_chore_completions(since="2026-09-10")

        assert [row.date for row in narrowed] == ["2026-09-18"]


class TestRefusals:
    def test_a_chore_nobody_defined_is_refused_with_the_reason(self, board):
        success, message = board.complete_chore(
            {"name": "Hoover", "date": "2026-09-11"})

        assert success is False
        assert "Hoover" in message

    def test_a_duplicate_name_is_refused(self, board):
        success, _message = board.add_chore(VACUUM)

        assert success is False

    def test_an_offline_read_answers_nothing_rather_than_raising(self, offline_client):
        assert offline_client.get_chores() == []
        assert offline_client.get_chore_completions() == []

    def test_an_offline_read_is_not_cached_as_an_empty_board(self, offline_client):
        offline_client.get_chores()

        assert "chore" not in offline_client.cache.cached_domains()
