from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

from src.config import PALETTE
from src.gui.commands import (belongs_to, candidates_for, command_being_typed,
                              command_word)
from src.gui.completion import DIRECTORY, FILE, describe_path, list_paths

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


def _counted(listing) -> str:
    """Say how much of the directory the rows show: 12 entries, or 3 of 12."""
    matching = sum(1 for choice in listing.choices if choice.kind in (DIRECTORY, FILE))
    if matching == listing.total:
        return f"{listing.total} {'entry' if listing.total == 1 else 'entries'}"
    return f"{matching} of {listing.total}"


def _path_rows(command, text: str, fragment: str, selected: int) -> list:
    """Build the command's line, the directory the path leads to, then its entries."""
    listing = list_paths(fragment, command.open_words(text))
    heading = MenuRow(command.name, command.usage, accent="green")
    if listing.problem:
        return [heading, MenuRow(listing.directory, listing.problem, accent="red")]
    shown, hidden = _window(list(enumerate(listing.choices)), selected)
    rows = [MenuRow(choice.name, describe_path(choice), selected=(position == selected))
            for position, choice in shown]
    where = MenuRow(listing.directory, _counted(listing), accent="blue")
    return [heading, where] + rows + _more(hidden)


def _window(items: list, focus: int) -> tuple:
    """Return at most MAX_ROWS items around the focus, and how many were left out."""
    if len(items) <= MAX_ROWS:
        return items, 0
    first = min(max(0, focus - MAX_ROWS + 1), len(items) - MAX_ROWS)
    return items[first:first + MAX_ROWS], len(items) - (first + MAX_ROWS)


def _more(hidden: int) -> list:
    return [MenuRow("", f"+{hidden} more", accent="base1")] if hidden else []


def _windowed(rows: list, focus: int) -> list:
    """Window to at most MAX_ROWS rows around the focus, plus an overflow line."""
    shown, hidden = _window(rows, focus)
    return shown + _more(hidden)


def rows_for(text: str, domains=(), selected: int = 0) -> list:
    """Build the menu content for what has been typed."""
    command = command_being_typed(text)
    if command is None:
        return _command_rows(text, domains, selected)
    fragment = command.path_fragment(text)
    if fragment:
        return _path_rows(command, text, fragment, selected)
    return _argument_rows(command, text)


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
        for row in range(MAX_ROWS + 3):
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

