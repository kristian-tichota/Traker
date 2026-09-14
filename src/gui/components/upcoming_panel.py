from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.config import PALETTE

TITLE_PX, LINE_PX = 11, 13

TITLE_SPACING_PX = 2


class UpcomingPanel(QWidget):
    """A titled list per section, or nothing at all."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 12, 0, 0)
        self._layout.setSpacing(2)
        self.sections = []
        self._titles, self._notes = {}, {}
        self.setVisible(False)

    def set_sections(self, sections):
        self.sections = [(title, list(lines)) for title, lines in sections]
        self._clear()
        for title, lines in self.sections:
            label = self._label(self._said(title), TITLE_PX, "base00", bold=True)
            self._titles[title] = label
            self._layout.addWidget(label)
            for line in lines:
                self._layout.addWidget(self._label(line, LINE_PX, "base01"))
        self.setVisible(bool(self.sections))

    def set_note(self, title, note):
        """Show a note beside one section title, without rebuilding either."""
        if title not in self._titles:
            return
        self._notes[title] = note
        self._titles[title].setText(self._said(title))

    def lines(self) -> list:
        """Return every line on the panel, titles included, in the order shown."""
        said = []
        for title, lines in self.sections:
            said.append(self._said(title))
            said.extend(lines)
        return said

    def _said(self, title) -> str:
        """Return a title as shown, with whatever note it carries, or bare."""
        note = self._notes.get(title)
        return f"{title}   ({note})" if note else title

    def _clear(self):
        self._titles, self._notes = {}, {}
        while self._layout.count():
            taken = self._layout.takeAt(0).widget()
            if taken is not None:
                taken.setParent(None)
                taken.deleteLater()

    @staticmethod
    def _label(text, size_px, colour, bold=False):
        label = QLabel(str(text))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFont(_font(size_px, bold))
        label.setStyleSheet(f"color: {PALETTE[colour]};")
        return label


def _font(size_px, bold=False) -> QFont:
    """Return Fira Code, monospaced in every case."""
    font = QFont("Fira Code")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(size_px)
    font.setBold(bold)
    if bold:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, TITLE_SPACING_PX)
    return font
