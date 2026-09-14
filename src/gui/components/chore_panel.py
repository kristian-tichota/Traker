from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.config import PALETTE
from src.domain import chores

TITLE = "CHORES TODAY"

KEYS = "abcdefghijklmnopqrstuvwxyz"


def chore_key(index) -> str:
    """The key for the chore at index, or "" past the twenty-sixth."""
    return KEYS[index] if 0 <= index < len(KEYS) else ""

STANDING_COLOURS = {
    chores.OVERDUE: "red",
    chores.DUE: "orange",
    chores.EARLY: "base00",
}

TITLE_PX, LINE_PX = 11, 13

DONE_MARK = "✓"


class ChoreLine(QLabel):
    """One chore, its key, and how late it is."""

    def __init__(self, entry, key, on_click, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.chore_id = entry.id
        self.key = key
        self._on_click = on_click
        self.done = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._draw()

    def mark_done(self):
        """Struck through, at once, on the member's own keystroke."""
        self.done = True
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._draw()

    def text_shown(self) -> str:
        """The line as it reads, for a test and for ChorePanel.lines."""
        key = DONE_MARK if self.done else (self.key or " ")
        return f"{key}  {self.entry.name}  ·  {self.entry.said()}"

    def _draw(self):
        colour = "base1" if self.done else STANDING_COLOURS.get(
            self.entry.standing, "base01")
        self.setText(self.text_shown())
        self.setStyleSheet(
            f"color: {PALETTE[colour]}; font-size: {LINE_PX}px; "
            f"font-family: 'Fira Code';"
            f"{' text-decoration: line-through;' if self.done else ''}")

    def mousePressEvent(self, event):
        if not self.done and event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.chore_id)
        super().mousePressEvent(event)


class ChorePanel(QWidget):
    """The chores a break offers, in key order, or nothing at all."""

    chore_ticked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 12, 0, 0)
        self._layout.setSpacing(2)
        self.entries = []
        self._lines = []
        self.setVisible(False)

    def set_entries(self, entries):
        """Replace what is offered."""
        self.entries = list(entries)
        self._clear()
        if not self.entries:
            self.setVisible(False)
            return

        self._layout.addWidget(self._title())
        for index, entry in enumerate(self.entries):
            line = ChoreLine(entry, chore_key(index), self._clicked, self)
            self._layout.addWidget(line)
            self._lines.append(line)
        self.setVisible(True)

    def chore_at(self, index):
        """The chore a key opens, or None — which is a key left alone."""
        if 0 <= index < len(self.entries):
            return self.entries[index]
        return None

    def mark_done(self, chore_id):
        """Strike one row through, on the keystroke that ticked it."""
        for line in self._lines:
            if line.chore_id == chore_id:
                line.mark_done()

    def is_done(self, chore_id) -> bool:
        return any(line.chore_id == chore_id and line.done for line in self._lines)

    def lines(self) -> list:
        """Every line shown, title first, in the order shown."""
        return [TITLE] + [line.text_shown() for line in self._lines]

    def _clicked(self, chore_id):
        self.chore_ticked.emit(chore_id)

    def _clear(self):
        self._lines = []
        while self._layout.count():
            taken = self._layout.takeAt(0).widget()
            if taken is not None:
                taken.setParent(None)
                taken.deleteLater()

    def _title(self):
        label = QLabel(TITLE)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"color: {PALETTE['base00']}; font-size: {TITLE_PX}px; "
            f"font-family: 'Fira Code'; font-weight: bold; letter-spacing: 2px;")
        return label
