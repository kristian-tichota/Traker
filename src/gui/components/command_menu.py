from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

from src.config import PALETTE
from src.gui.commands import (belongs_to, candidates_for, command_being_typed,
                              command_word)

MAX_ROWS = 7


@dataclass(frozen=True)
class MenuRow:
    """One line: what could be typed, and what it takes."""
    left: str
    right: str
    selected: bool = False
    accent: str = "base00"


def _command_rows(text: str, domains, selected: int) -> list:
    """Build one row per command the line could still become."""
    candidates = candidates_for(text, domains)
    if not candidates:
        return [MenuRow(command_word(text), "matches no command", accent="red")]
    rows = [MenuRow(command.name, command.usage,
                    selected=(position == selected),
                    accent="green" if belongs_to(command, domains) else "base00")
            for position, command in enumerate(candidates)]
    return _windowed(rows, selected)


def _argument_rows(command, text: str) -> list:
    """Build the command's own line, then one row per argument it takes."""
    asked = command.current_argument(text)
    rows = [MenuRow(param.label,
                    param.expects + (" · may be left out" if param.optional else ""),
                    selected=(position == asked))
            for position, param in enumerate(command.params)]
    heading = MenuRow(command.name, command.usage, accent="green")
    return [heading] + _windowed(rows, 0 if asked is None else asked)


def _windowed(rows: list, focus: int) -> list:
    """Window to at most MAX_ROWS rows around the focus, plus an overflow line."""
    if len(rows) <= MAX_ROWS:
        return rows
    first = min(max(0, focus - MAX_ROWS + 1), len(rows) - MAX_ROWS)
    hidden = len(rows) - (first + MAX_ROWS)
    shown = rows[first:first + MAX_ROWS]
    if hidden:
        shown = shown + [MenuRow("", f"+{hidden} more", accent="base1")]
    return shown


def rows_for(text: str, domains=(), selected: int = 0) -> list:
    """Build the menu content for what has been typed."""
    command = command_being_typed(text)
    if command is not None:
        return _argument_rows(command, text)
    return _command_rows(text, domains, selected)


class CommandMenu(QWidget):
    """The rows above the command bar, re-rendered on every keystroke."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.setStyleSheet(f"background-color: {PALETTE['base3']};")
        self._labels = self._build_rows()

    def _build_rows(self) -> list:
        """Build one row of three labels each, once, for re-use."""
        grid = QGridLayout(self)
        grid.setContentsMargins(6, 1, 6, 1)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(2, 1)

        labels = []
        for row in range(MAX_ROWS + 2):
            marker, left, right = QLabel(self), QLabel(self), QLabel(self)
            marker.setFixedWidth(10)
            left.setAlignment(Qt.AlignmentFlag.AlignLeft)
            right.setSizePolicy(QSizePolicy.Policy.Ignored,
                                QSizePolicy.Policy.Preferred)
            grid.addWidget(marker, row, 0)
            grid.addWidget(left, row, 1)
            grid.addWidget(right, row, 2)
            labels.append((marker, left, right))
        return labels

    def render_for(self, text: str, domains=(), selected: int = 0):
        """Show the menu for what has been typed."""
        self.rows = rows_for(text, domains, selected)
        self._paint_rows()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for (_marker, _left, right), row in zip(self._labels, self.rows):
            right.setText(self._fitted(right, row.right))

    def _paint_rows(self):
        for position, widgets in enumerate(self._labels):
            row = self.rows[position] if position < len(self.rows) else None
            self._render_row(widgets, row)

    def _render_row(self, widgets, row):
        marker, left, right = widgets
        if row is None:
            for label in widgets:
                label.setText("")
                label.hide()
            return

        ground = PALETTE["base2"] if row.selected else "transparent"
        weight = "bold" if row.selected else "normal"
        marker.setText("›" if row.selected else "")
        marker.setStyleSheet(
            f"color: {PALETTE['blue']}; background-color: {ground};")
        left.setText(row.left)
        left.setStyleSheet(f"color: {PALETTE[row.accent]}; font-weight: {weight}; "
                           f"background-color: {ground};")
        right.setText(self._fitted(right, row.right))
        right.setStyleSheet(
            f"color: {PALETTE['base1']}; background-color: {ground};")
        for label in widgets:
            label.show()

    @staticmethod
    def _fitted(label, written: str) -> str:
        """Cut written to the width the label has, with an ellipsis."""
        if label.width() <= 1:
            return written
        return label.fontMetrics().elidedText(
            written, Qt.TextElideMode.ElideRight, label.width())

