import datetime

import pytest
from PyQt6.QtCore import QEvent, Qt, QThreadPool
from PyQt6.QtGui import QGuiApplication, QKeyEvent
from PyQt6.QtWidgets import QLineEdit

from src.database import rows
from src.gui.components.chore_panel import DONE_MARK, ChorePanel, chore_key
from src.gui.views.pomodoro_view import PomodoroView, read_chores
from tests.gui.conftest import advance

pytestmark = [pytest.mark.gui, pytest.mark.accessibility]

TODAY = datetime.date.today()


def chore(name, anchor_offset=0, ident=1, period=7, grace=None, last_done=None,
          active=1):
    anchor = (TODAY + datetime.timedelta(days=anchor_offset)).isoformat()
    return rows.ChoreRow.from_server({
        "id": ident, "name": name, "period_days": period, "anchor": anchor,
        "grace_days": grace, "notes": None, "active": active,
        "last_done": last_done, "done_count": 0})


class Offline:
    online = False
    reason = "household service is not running"


@pytest.fixture
def app_id(qapp):
    previous = QGuiApplication.desktopFileName()
    QGuiApplication.setDesktopFileName("Traker.desktop")
    yield "traker"
    QGuiApplication.setDesktopFileName(previous)


@pytest.fixture
def with_chores(recording_db):
    recording_db.chores = [
        chore("Vacuum", -3, ident=1),
        chore("Bins", 0, ident=2),
        chore("Water plants", 1, ident=3, grace=2),
        chore("Descale", 20, ident=4, period=30),
    ]
    return recording_db


@pytest.fixture
def timer(qapp, app_id, strict_timer, chores_on_break, with_chores):
    view = PomodoroView(with_chores, tray_icon=None)
    view.refresh_timer.stop()
    view.stress_calendar.anim_timer.stop()
    view.last_logged_minute = -1
    yield view
    view.shutdown()
    QThreadPool.globalInstance().waitForDone(2000)
    view.deleteLater()


def enter_strict_break(view):
    view._skip_phase()
    assert view._strict_break_is_holding()


def press(view, key, watched=None):
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    return view.eventFilter(watched if watched is not None else view, event)


class TestWhatABreakLists:
    def test_it_lists_what_is_due_and_what_is_late(self, timer, settled):
        enter_strict_break(timer)
        settled()

        said = " ".join(timer.chores_panel.lines())
        assert "Vacuum" in said and "Bins" in said

    def test_a_chore_that_is_weeks_away_is_left_off(self, timer, settled):
        enter_strict_break(timer)
        settled()

        assert "Descale" not in " ".join(timer.chores_panel.lines())

    def test_one_that_can_be_done_early_is_offered_and_says_so(
            self, timer, settled):
        enter_strict_break(timer)
        settled()

        (line,) = [l for l in timer.chores_panel.lines() if "Water plants" in l]
        assert "ok today" in line

    def test_the_worst_one_is_first_and_says_how_late_it_is(self, timer, settled):
        enter_strict_break(timer)
        settled()

        assert "Vacuum" in timer.chores_panel.lines()[1]
        assert "3 days over" in timer.chores_panel.lines()[1]

    def test_a_day_with_nothing_due_shows_no_panel_at_all(
            self, timer, settled, with_chores):
        with_chores.chores = [chore("Descale", 20, period=30)]
        enter_strict_break(timer)
        settled()

        assert timer.chores_panel.lines() == ["CHORES TODAY"]
        assert not timer.chores_panel.isVisible()

    def test_a_read_that_did_not_arrive_shows_nothing(
            self, timer, settled, with_chores):
        with_chores.connection = Offline()
        enter_strict_break(timer)
        settled()

        assert timer._chores == []

    def test_every_covered_screen_says_the_same_thing(self, timer, settled):
        enter_strict_break(timer)
        settled()

        for overlay in timer.overlays:
            assert overlay.chores.lines() == timer.chores_panel.lines()

    def test_no_frame_of_the_break_reads_it(self, timer, settled, with_chores):
        enter_strict_break(timer)
        settled()
        reads = []
        real = with_chores.get_chores

        def counted():
            reads.append(1)
            return real()

        with_chores.get_chores = counted
        for _ in range(20):
            timer._redraw_break_surfaces()
        settled()

        assert reads == []

    def test_beginning_a_break_reads_it(self, timer, settled, with_chores):
        reads = []
        real = with_chores.get_chores

        def counted():
            reads.append(1)
            return real()

        with_chores.get_chores = counted
        enter_strict_break(timer)
        settled()

        assert reads and timer._chores

    def test_a_re_read_never_blanks_the_panel_it_is_replacing(
            self, timer, settled):
        enter_strict_break(timer)
        settled()
        before = timer.chores_panel.lines()

        timer._read_chores()
        assert timer.chores_panel.lines() == before
        settled()
        assert timer.chores_panel.lines() == before

    def test_it_stays_until_focus_starts(self, timer, settled):
        enter_strict_break(timer)
        settled()
        listed = timer.chores_panel.lines()
        assert listed

        advance(timer, timer.break_ms + 1000)

        assert timer.overlays
        assert timer.chores_panel.lines() == listed
        assert all(wall.chores.lines() == listed for wall in timer.overlays)

    def test_it_is_gone_once_the_screens_are_given_back(self, timer, settled):
        enter_strict_break(timer)
        settled()
        timer._clear_overlays()
        settled()

        assert timer._chores == []
        assert not timer.chores_panel.isVisible()


class TestTickingOneOff:
    def test_the_letter_beside_a_chore_ticks_it(self, timer, settled):
        enter_strict_break(timer)
        settled()

        assert press(timer, Qt.Key.Key_A) is True
        settled()

        assert ("complete_chore", ({"name": "Vacuum",
                                    "date": TODAY.isoformat()},)) in timer.db.calls

    def test_it_ticks_during_the_minutes_away_from_the_screen_too(
            self, timer, settled):
        enter_strict_break(timer)
        settled()

        assert timer.opens_in_ms() > 0
        assert press(timer, Qt.Key.Key_A) is True
        settled()

        assert timer.db.calls[-1][1][0]["name"] == "Vacuum"

    def test_the_second_letter_ticks_the_second_chore(self, timer, settled):
        enter_strict_break(timer)
        settled()
        press(timer, Qt.Key.Key_B)
        settled()

        assert timer.db.calls[-1][1][0]["name"] == "Bins"

    def test_the_row_is_struck_through_on_the_keystroke(self, timer, settled):
        enter_strict_break(timer)
        settled()
        press(timer, Qt.Key.Key_A)

        assert timer.chores_panel.is_done(1)
        assert DONE_MARK in timer.chores_panel.lines()[1]

    def test_every_covered_screen_strikes_the_same_row_through(
            self, timer, settled):
        enter_strict_break(timer)
        settled()
        press(timer, Qt.Key.Key_A)

        for overlay in timer.overlays:
            assert overlay.chores.is_done(1)

    def test_a_click_ticks_it_too(self, timer, settled):
        enter_strict_break(timer)
        settled()
        timer.chores_panel.chore_ticked.emit(2)
        settled()

        assert timer.db.calls[-1][1][0]["name"] == "Bins"

    def test_it_says_which_subject_changed_so_the_tab_refreshes(
            self, timer, settled):
        changed = []
        timer.data_changed.connect(changed.append)
        enter_strict_break(timer)
        settled()
        press(timer, Qt.Key.Key_A)
        settled()

        assert changed == ["chore"]

    def test_a_refused_tick_says_so_and_does_not_claim_the_chore_is_done(
            self, timer, settled, with_chores):
        said = []
        timer.status_message.connect(said.append)
        with_chores.result = (False, "There is no chore called 'Vacuum'.")
        enter_strict_break(timer)
        settled()
        press(timer, Qt.Key.Key_A)
        settled()
        settled()

        assert any("not recorded" in message for message in said)
        assert not timer.chores_panel.is_done(1)

    def test_a_letter_with_no_chore_behind_it_is_left_alone(self, timer, settled):
        enter_strict_break(timer)
        settled()

        assert press(timer, Qt.Key.Key_Z) is False

    def test_a_letter_typed_into_a_field_is_left_alone(self, timer, settled):
        enter_strict_break(timer)
        settled()
        field = QLineEdit()

        assert press(timer, Qt.Key.Key_A, watched=field) is False
        assert not any(call[0] == "complete_chore" for call in timer.db.calls)
        field.deleteLater()

    def test_no_key_ticks_anything_outside_a_break(self, timer, settled):
        assert press(timer, Qt.Key.Key_A) is False
        assert not any(call[0] == "complete_chore" for call in timer.db.calls)


class TestTheTwoKeyRangesDoNotCollide:
    def test_a_chore_never_takes_a_digit(self, timer, settled):
        enter_strict_break(timer)
        settled()

        for offset in range(9):
            assert timer._chore_for(Qt.Key.Key_1 + offset) is None

    def test_an_offer_never_takes_a_letter(self, timer, settled):
        enter_strict_break(timer)
        settled()

        for offset in range(26):
            assert timer._activity_for(Qt.Key.Key_A + offset) is None

    def test_the_key_shown_is_the_key_answered(self, timer, settled):
        enter_strict_break(timer)
        settled()

        for index, entry in enumerate(timer._chores):
            shown = chore_key(index)
            answered = timer._chore_for(Qt.Key.Key_A + index)
            assert shown in timer.chores_panel.lines()[index + 1]
            assert answered is entry


class TestTheReadItself:
    def test_it_answers_the_domain_standings_worst_first(self, with_chores):
        entries = read_chores(with_chores)

        assert [entry.name for entry in entries] == [
            "Vacuum", "Bins", "Water plants"]

    def test_a_paused_chore_is_never_offered(self, with_chores):
        with_chores.chores = [chore("Paused", -3, active=0)]

        assert read_chores(with_chores) == []


class TestThePanelAlone:
    def test_it_hides_itself_when_there_is_nothing_due(self, qapp):
        panel = ChorePanel()
        panel.set_entries([])

        assert not panel.isVisible()
        panel.deleteLater()

    def test_a_key_past_the_end_answers_nothing(self, qapp):
        panel = ChorePanel()

        assert panel.chore_at(0) is None
        assert panel.chore_at(99) is None
        panel.deleteLater()
