import logging

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
                             QWidget)

from src.config import PALETTE
from src.database.rows import PlannedMovementRow
from src.domain import plans
from src.domain.clock import as_displayed_date
from src.gui.views.base import BaseManagedView

log = logging.getLogger(__name__)

MOVEMENT_HEADERS = ["#", "Exercise", "Sets", "From", "To", "Load (kg)", "RPE",
                    "Tempo", "Logged", "Result", "Note"]

MOVEMENT_COLUMNS = {"#": "position", "Exercise": "exercise_item_id",
                    "Sets": "sets", "From": "target_low", "To": "target_high",
                    "Load (kg)": "weight_kg", "RPE": "rpe", "Tempo": "tempo",
                    "Note": "notes"}

STATUS_COLOURS = {
    plans.DONE: "green",
    plans.TODAY: "blue",
    plans.MISSED: "orange",
    plans.AHEAD: "base1",
}

WEEKDAY_INITIALS = ("M", "T", "W", "T", "F", "S", "S")

CELL_PX, PITCH_PX = 13, 18
WEEK_LABEL_PX, BLOCK_LABEL_PX = 30, 74
HEADER_PX, LEGEND_PX = 16, 36

GRID_PX = WEEK_LABEL_PX + 7 * PITCH_PX + BLOCK_LABEL_PX

LEGEND = ((plans.DONE, "done"), (plans.TODAY, "today"),
          (plans.AHEAD, "ahead"), (plans.MISSED, "missed"))


class PlanCalendar(QWidget):
    """One cycle as a grid: a row per week, a column per weekday."""

    day_selected = pyqtSignal(str)
    log_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(GRID_PX)
        self.setFixedHeight(HEADER_PX + PITCH_PX + LEGEND_PX)

        self._cells = {}
        self._blocks = {}
        self._logged = set()
        self._weeks = 0
        self._today = plans.today_iso()
        self._selected = ""
        self._cursor = (0, 0)

    def show_plan(self, weeks, sessions, logged_dates, today, selected):
        """Replace everything drawn."""
        self._weeks = max(1, int(weeks or 1))
        self._logged = set(logged_dates)
        self._today = today
        self._selected = selected or ""
        self._cells = {}
        self._blocks = {}

        for session in sessions:
            date = plans.parse_iso(session.date)
            if date is None:
                log.warning("Plan session %s has no usable date: %r",
                            session.id, session.date)
                continue
            row = max(0, int(session.week or 1) - 1)
            clash = self._cells.get((row, date.weekday()))
            if clash is not None:
                log.warning("Plan sessions %s and %s both land on week %d, %s: "
                            "the calendar can show only the later one.",
                            clash.id, session.id, row + 1, session.date)
            self._cells[(row, date.weekday())] = session
            if session.block and row not in self._blocks:
                self._blocks[row] = session.block
            self._weeks = max(self._weeks, row + 1)

        self._cursor = self._cursor_for(self._selected)
        self.setFixedHeight(HEADER_PX + self._weeks * PITCH_PX + LEGEND_PX)
        self.updateGeometry()
        self.update()

    def _cursor_for(self, date_iso):
        for position, session in self._cells.items():
            if session.date == date_iso:
                return position
        return self._cursor if self._cursor[0] < self._weeks else (0, 0)

    def _cell_rect(self, row, column) -> QRectF:
        """The square drawn for one day, inset inside its pitch."""
        inset = (PITCH_PX - CELL_PX) / 2.0
        return QRectF(WEEK_LABEL_PX + column * PITCH_PX + inset,
                      HEADER_PX + row * PITCH_PX + inset, CELL_PX, CELL_PX)

    def sizeHint(self):
        return QSize(GRID_PX, HEADER_PX + self._weeks * PITCH_PX + LEGEND_PX)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(PALETTE["base3"]))

        small = QFont(self.font())
        small.setPointSizeF(max(6.5, small.pointSizeF() - 1.5))
        painter.setFont(small)

        self._paint_weekday_header(painter)
        for row in range(self._weeks):
            self._paint_week(painter, row)
        self._paint_legend(painter)
        painter.end()

    def _paint_weekday_header(self, painter):
        painter.setPen(QPen(QColor(PALETTE["base1"])))
        for column, initial in enumerate(WEEKDAY_INITIALS):
            painter.drawText(
                QRectF(WEEK_LABEL_PX + column * PITCH_PX, 0, PITCH_PX, HEADER_PX),
                Qt.AlignmentFlag.AlignCenter, initial)

    def _paint_week(self, painter, row):
        top = HEADER_PX + row * PITCH_PX
        current = any(session.date == self._today
                      for (week, _day), session in self._cells.items() if week == row)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(
            PALETTE["base00"] if current else PALETTE["base1"])))
        painter.drawText(QRectF(0, top, WEEK_LABEL_PX - 5, PITCH_PX),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         f"W{row + 1}")

        for column in range(7):
            self._paint_cell(painter, row, column)

        block = self._blocks.get(row, "")
        if block:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(PALETTE["base1"])))
            painter.drawText(
                QRectF(WEEK_LABEL_PX + 7 * PITCH_PX + 5, top, BLOCK_LABEL_PX - 6,
                       PITCH_PX),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, block)

    def _paint_cell(self, painter, row, column):
        rect = self._cell_rect(row, column)
        session = self._cells.get((row, column))

        if session is None:
            painter.setBrush(QColor(PALETTE["base1"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect.center(), 1.6, 1.6)
        else:
            self._paint_status(painter, rect,
                               plans.status(session.date, self._logged, self._today))

        if (row, column) == self._cursor:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(PALETTE["violet"]), 1.4))
            painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 3.0, 3.0)

    @staticmethod
    def _paint_status(painter, rect, state):
        """One day's mark."""
        colour = QColor(PALETTE[STATUS_COLOURS[state]])
        if state == plans.AHEAD:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(colour, 1.0))
        else:
            painter.setBrush(colour)
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 2.5, 2.5)

    def _paint_legend(self, painter):
        top = HEADER_PX + self._weeks * PITCH_PX + 5
        dates = [session.date for session in self._cells.values()]
        done, due = plans.adherence(dates, self._logged, self._today)
        streak = plans.week_streak(dates, self._logged, self._today)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(PALETTE["base00"])))
        painter.drawText(QRectF(0, top, GRID_PX, 15),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"{done}/{due} done · streak {streak} · "
                         f"{len(dates)} planned")

        left = 0.0
        for state, label in LEGEND:
            swatch = QRectF(left, top + 20, 7, 7)
            self._paint_status(painter, swatch, state)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(PALETTE["base01"])))
            width = painter.fontMetrics().horizontalAdvance(label)
            painter.drawText(QRectF(left + 11, top + 15, width + 2, 15),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             label)
            left += 11 + width + 8

    def keyPressEvent(self, event):
        key = event.key()
        row, column = self._cursor
        step = {Qt.Key.Key_H: (0, -1), Qt.Key.Key_Left: (0, -1),
                Qt.Key.Key_L: (0, 1), Qt.Key.Key_Right: (0, 1),
                Qt.Key.Key_J: (1, 0), Qt.Key.Key_Down: (1, 0),
                Qt.Key.Key_K: (-1, 0), Qt.Key.Key_Up: (-1, 0)}.get(key)

        if step is not None:
            self._move_cursor(row + step[0], column + step[1])
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            session = self._cells.get(self._cursor)
            if session is not None:
                self.log_requested.emit(session.date)
            return
        super().keyPressEvent(event)

    def _move_cursor(self, row, column):
        row = max(0, min(self._weeks - 1, row))
        column = max(0, min(6, column))
        if (row, column) == self._cursor:
            return
        self._cursor = (row, column)
        self.update()
        session = self._cells.get(self._cursor)
        self.day_selected.emit(session.date if session is not None else "")

    def mousePressEvent(self, event):
        position = event.position()
        row = int((position.y() - HEADER_PX) // PITCH_PX)
        column = int((position.x() - WEEK_LABEL_PX) // PITCH_PX)
        if 0 <= row < self._weeks and 0 <= column < 7:
            self.setFocus()
            self._move_cursor(row, column)


class PlanView(BaseManagedView):
    """The training plan, and how much of it has actually happened."""

    def __init__(self, db):
        super().__init__(db, ["plan_movements"], [MOVEMENT_HEADERS],
                         [MOVEMENT_COLUMNS])

        self.plan = None
        self.sessions = []
        self.movements = []
        self.logs = []
        self.selected_date = ""

        self.calendar = PlanCalendar(self)
        self.calendar.day_selected.connect(self.on_day_selected)
        self.calendar.log_requested.connect(self.on_log_requested)

        self.cycle_label = QLabel("")
        self.cycle_label.setWordWrap(True)
        self.cycle_label.setFixedWidth(GRID_PX)
        self.cycle_label.setStyleSheet(f"color: {PALETTE['base01']}; padding: 2px;")

        left = QVBoxLayout()
        left.addWidget(self.cycle_label)
        left.addWidget(self.calendar)
        left.addStretch(1)

        self.session_label = QLabel("<b>No plan yet</b>")
        detail, self.t_movements = self.build_table_layout("", MOVEMENT_HEADERS, 0)
        self.session_note = QLabel("")
        self.session_note.setWordWrap(True)
        self.session_note.setStyleSheet(f"color: {PALETTE['base01']}; padding: 2px;")

        right = QVBoxLayout()
        right.addWidget(self.session_label)
        right.addLayout(detail)
        right.addWidget(self.session_note)

        layout = QHBoxLayout(self)
        layout.addLayout(left, 0)
        layout.addLayout(right, 1)

    def refresh(self):
        """One worker for the whole tab."""
        self.fetch(self._read_plan, self._apply_plan)

    def _read_plan(self):
        """Everything the tab draws, off the interface thread."""
        catalogue = self.db.get_training_plans()
        if not catalogue:
            return None, [], [], []
        plan = plans.current_plan(catalogue)
        sessions = self.db.get_plan_sessions(plan.id)
        movements = self.db.get_plan_movements(plan.id)
        logs = self.db.get_exercise_logs(since=plan.start_date)
        return plan, sessions, movements, logs

    def _apply_plan(self, payload):
        plan, sessions, movements, logs = payload
        self.plan = plan
        self.sessions = list(sessions)
        self.movements = list(movements)
        self.logs = list(logs)

        if plan is None:
            self.cycle_label.setText(
                "No training plan yet — import one with "
                "<code>scripts/import_training_plan.py</code>")
            self.session_label.setText("<b>No plan yet</b>")
            self.calendar.show_plan(1, [], set(), plans.today_iso(), "")
            self.set_rows(0, [])
            return

        self.cycle_label.setText(
            f"<b>{plan.name}</b> · {as_displayed_date(plan.start_date)} "
            f"· {plan.weeks} weeks")
        self.selected_date = self._date_to_show()
        self.calendar.show_plan(plan.weeks, self.sessions, self._logged_dates(),
                                plans.today_iso(), self.selected_date)
        self._show_session()

    def _logged_dates(self) -> set:
        return {row.date for row in self.logs if row.date}

    def _date_to_show(self) -> str:
        """Which day the detail pane opens on, preserving the member's choice."""
        dates = [session.date for session in self.sessions]
        if self.selected_date in dates:
            return self.selected_date
        today = plans.today_iso()
        if today in dates:
            return today
        ahead = sorted(date for date in dates if date > today)
        return ahead[0] if ahead else (max(dates) if dates else "")

    def on_day_selected(self, date_iso: str):
        """The calendar cursor moved."""
        self.selected_date = date_iso
        self._show_session()

    def _show_session(self):
        session, movements = plans.prescribed_day(
            self.sessions, self.movements, self.selected_date)
        if session is None:
            self.session_label.setText(
                f"<b>{as_displayed_date(self.selected_date) or 'Rest day'}</b>"
                f" — nothing planned")
            self.session_note.setText("")
            self.set_rows(0, [])
            return

        state = plans.status(session.date, self._logged_dates(), plans.today_iso())
        self.session_label.setText(
            f"<b>{as_displayed_date(session.date)} · {session.name}</b>"
            f" — W{session.week} · {session.block or ''} · {state}")

        day_logs = plans.logs_by_exercise(
            [row for row in self.logs if row.date == session.date])
        rows = [
            PlannedMovementRow.of(
                movement, day_logs.get((movement.name or "").strip().lower()))
            for movement in movements
        ]
        self.set_rows(0, rows)
        self.session_note.setText(session.notes or "")

    def on_log_requested(self, date_iso: str):
        """Enter on a planned day: offer the command, do not run it."""
        self.command_requested.emit(f"planlog {as_displayed_date(date_iso)}")
