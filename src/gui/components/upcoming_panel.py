from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.config import PALETTE
from src.domain.media import UNKNOWN
from src.gui.animations import TextGlow
from src.gui.components.key_card import MarkedLine

TITLE_PX, LINE_PX = 11, 13

GLOW, HELD_GLOW = 'base2', 'yellow'

TITLE_SPACING_PX = 2

MARK_SCALE = 1.4


class UpcomingPanel(QWidget):
    """A titled list per section, or nothing at all."""

    line_pressed = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 12, 0, 0)
        self._layout.setSpacing(2)
        self.sections = []
        self._titles, self._notes, self._lines = {}, {}, {}
        self._marked = []
        self._gate = None
        self.setVisible(False)

    def set_sections(self, sections, inputs=None):
        """Show sections, each line marked by what inputs names for its title, if anything."""
        before = {title: [_squeezed(line) for line in lines] for title, lines in self.sections}
        self.sections = [(title, list(lines)) for title, lines in sections]
        self._clear()
        for title, lines in self.sections:
            label = self._label(self._said(title), TITLE_PX, "base00", bold=True)
            self._titles[title] = label
            self._layout.addWidget(label)
            self._lines[title] = []
            was = before.get(title, [])
            marked = self._marked_lines(title, lines, (inputs or {}).get(title))
            for index, line in enumerate(lines):
                if marked:
                    shown = marked[index].label
                    self._layout.addWidget(marked[index])
                else:
                    shown = self._label(line, LINE_PX, "base01")
                    self._layout.addWidget(shown)
                self._lines[title].append(shown)
                if index < len(was) and was[index] != _squeezed(line):
                    shown.glowing.glow(PALETTE[GLOW])
            self._marked.extend(marked)
        self.setVisible(bool(self.sections))

    def _marked_lines(self, title, lines, names) -> list:
        """Return the lines as pressable rows, their inputs in a column before them, or []."""
        if names is None:
            return []
        names = [tuple(said) for said in names] + [()] * len(lines)
        marked = []
        for index, line in enumerate(lines):
            row = MarkedLine(self._label(line, LINE_PX, "base01"), MARK_SCALE)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.pressed.connect(lambda index=index: self.line_pressed.emit(title, index))
            row.marks.set_names(names[index])
            row.marks.set_gate(self._gate)
            row.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            marked.append(row)
        column = max(row.marks.width_wanted() for row in marked)
        text = max(row.label.sizeHint().width() for row in marked)
        for row in marked:
            row.set_names(row.marks.names, column)
            row.label.setFixedWidth(text)
        return marked

    def set_gate(self, gate):
        """Outline the lines a gesture serving its hold acts on, its sign ringed."""
        self._gate = gate
        for line in self._marked:
            line.set_gate(gate)

    def held_lines(self) -> list:
        """Return the text of every line a gesture serving its hold acts on."""
        return [line.label.text() for line in self._marked if line.marks.held]

    def glow(self, title, index, held=False):
        """Flash one line of a section, yellow with its title while held back, then settle."""
        lines = self._lines.get(title, [])
        if not 0 <= index < len(lines):
            return
        lines[index].glowing.glow(PALETTE[HELD_GLOW if held else GLOW])
        if held:
            self._titles[title].glowing.glow(PALETTE[HELD_GLOW])

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
        self._titles, self._notes, self._lines = {}, {}, {}
        self._marked = []
        while self._layout.count():
            taken = self._layout.takeAt(0).widget()
            if taken is not None:
                taken.hide()
                taken.deleteLater()

    @staticmethod
    def _label(text, size_px, colour, bold=False):
        label = QLabel(str(text))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFont(_font(size_px, bold))
        label.setStyleSheet(f"color: {PALETTE[colour]};")
        label.glowing = TextGlow(label, PALETTE[colour])
        return label


def _squeezed(line) -> str:
    """Return a line as it reads, whatever spaces and unknown readouts align it."""
    return " ".join(word for word in str(line).split() if word != UNKNOWN)


def _font(size_px, bold=False) -> QFont:
    """Return Fira Code, monospaced in every case."""
    font = QFont("Fira Code")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(size_px)
    font.setBold(bold)
    if bold:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, TITLE_SPACING_PX)
    return font
