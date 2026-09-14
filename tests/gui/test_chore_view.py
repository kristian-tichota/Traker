import datetime

import pytest
from PyQt6.QtCore import QThreadPool

from src.database import rows
from src.domain import chores
from src.gui.views.chore_view import (BOARD_HEADERS, HISTORY_HEADERS,
                                      STANDING_WORDS, ChoreView)
from src.gui.views.pomodoro_view import read_chores

pytestmark = pytest.mark.gui

TODAY = datetime.date.today()


def chore(name, anchor_offset=0, ident=1, period=7, grace=None, last_done=None,
          active=1, notes=None, done_count=0):
    anchor = (TODAY + datetime.timedelta(days=anchor_offset)).isoformat()
    return rows.ChoreRow.from_server({
        "id": ident, "name": name, "period_days": period, "anchor": anchor,
        "grace_days": grace, "notes": notes, "active": active,
        "last_done": last_done, "done_count": done_count})


def completion(ident, date, name, by="member_a"):
    return rows.ChoreDoneRow.from_server([ident, date, name, by])


@pytest.fixture
def with_chores(recording_db):
    recording_db.chores = [
        chore("Vacuum", -3, ident=1),
        chore("Bins", 0, ident=2, grace=1, done_count=4),
        chore("Descale", 20, ident=3, period=30, notes="the kettle"),
        chore("Paused", -9, ident=4, active=0),
    ]
    recording_db.chore_completions = [
        completion(1, TODAY.isoformat(), "Bins"),
        completion(2, "2026-09-01", "Vacuum", by="member_b"),
    ]
    return recording_db


@pytest.fixture
def view(qapp, with_chores, settled):
    made = ChoreView(with_chores)
    made.refresh()
    settled()
    yield made
    made.shutdown()
    QThreadPool.globalInstance().waitForDone(2000)
    made.deleteLater()


def cell(view, table_idx, row, header):
    model = view._table_models[table_idx]
    return model.display_text(row, model._headers.index(header))


def column(view, table_idx, header):
    model = view._table_models[table_idx]
    return [cell(view, table_idx, row, header)
            for row in range(model.rowCount())]


class TestTheBoard:
    def test_it_lists_the_chores_worst_first(self, view):
        assert column(view, 0, "Chore") == ["Vacuum", "Bins", "Descale"]

    def test_a_paused_chore_is_off_it(self, view):
        assert "Paused" not in column(view, 0, "Chore")

    def test_it_says_where_each_one_stands(self, view):
        assert column(view, 0, "Standing") == ["OVERDUE", "TODAY", ""]

    def test_a_derived_grace_is_shown_rather_than_left_blank(self, view):
        assert cell(view, 0, 0, "Grace (days)") == "2"
        assert cell(view, 0, 1, "Grace (days)") == "1"

    def test_a_chore_never_done_says_so_rather_than_showing_a_date(self, view):
        assert cell(view, 0, 0, "Last Done") == "—"

    def test_a_weekly_chore_says_the_weekday_of_its_own_anchor(self, view):
        for row in view._table_models[0]._rows:
            if row.period_days % chores.DAYS_IN_WEEK:
                continue
            weekday = datetime.date.fromisoformat(row.anchor).weekday()
            assert row.lands_on == chores.WEEKDAYS[weekday]

    def test_a_cadence_that_is_not_whole_weeks_says_it_drifts(self, view):
        (row,) = [r for r in view._table_models[0]._rows if r.name == "Descale"]

        assert row.period_days == 30 and row.lands_on == chores.DRIFTS

    def test_the_column_answers_for_every_row(self, view):
        assert all(column(view, 0, "Lands On"))

    def test_the_dates_are_shown_in_czech(self, view):
        expected = (TODAY + datetime.timedelta(days=-3)).strftime("%d.%m.%Y")
        assert cell(view, 0, 0, "Anchor") == expected

    def test_the_dates_are_held_as_iso_so_a_sort_is_chronological(self, view):
        overdue = (TODAY + datetime.timedelta(days=-3)).isoformat()
        held = view._table_models[0]._rows[0]

        assert held.anchor == overdue
        assert held.next_due == overdue


class TestWhatMayBeTypedInto:
    def test_the_cadence_and_the_name_are_editable(self, view):
        editable = {BOARD_HEADERS[index] for index in view.editable_columns(0)}

        assert {"Chore", "Every (days)", "Grace (days)", "Anchor"} <= editable

    def test_nothing_derived_is_editable(self, view):
        editable = {BOARD_HEADERS[index] for index in view.editable_columns(0)}

        assert not editable & {"Last Done", "Next Due", "Standing", "Done"}

    def test_an_edited_anchor_is_sent_as_iso(self, view, settled, with_chores):
        view.on_cell_edited(0, 1, "Anchor", "11.09.2026")
        settled()

        assert ("chores", 1, "Anchor", "2026-09-11") == with_chores.calls[-1][1][:4]

    def test_only_the_date_of_a_completion_may_be_corrected(self, view):
        editable = {HISTORY_HEADERS[index] for index in view.editable_columns(1)}

        assert editable == {"Date"}


class TestTheHistory:
    def test_it_says_who_did_it(self, view):
        assert column(view, 1, "By") == ["member_a", "member_b"]

    def test_it_names_the_chore_rather_than_its_id(self, view):
        assert column(view, 1, "Chore") == ["Bins", "Vacuum"]


class TestOneDueDateOnBothSurfaces:
    def test_the_tab_and_the_break_panel_agree_on_what_is_due(self, view,
                                                              with_chores):
        on_the_tab = {row.name: row.next_due
                      for row in view._table_models[0]._rows}
        on_the_wall = {entry.name: entry.due_iso
                       for entry in read_chores(with_chores)}

        assert on_the_wall
        for name, due in on_the_wall.items():
            assert on_the_tab[name] == due

    def test_the_two_describe_a_standing_with_the_same_words(self, view,
                                                             with_chores):
        for entry in read_chores(with_chores):
            (row,) = [r for r in view._table_models[0]._rows
                      if r.name == entry.name]
            assert row.standing == STANDING_WORDS[entry.standing]

    def test_every_standing_the_domain_can_answer_has_a_word_here(self):
        assert set(STANDING_WORDS) == set(chores.STANDINGS)


class TestItSurvivesAnEmptyStore:
    def test_a_household_with_no_chores_draws_an_empty_board(
            self, qapp, recording_db, settled):
        recording_db.chores = []
        recording_db.chore_completions = []
        made = ChoreView(recording_db)
        made.refresh()
        settled()

        assert made._table_models[0].rowCount() == 0
        made.shutdown()
        QThreadPool.globalInstance().waitForDone(2000)
        made.deleteLater()
