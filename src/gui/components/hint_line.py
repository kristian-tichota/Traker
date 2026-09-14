from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QLineEdit

from src.config import PALETTE

HINT_GAP_PX = 6


class HintingLineEdit(QLineEdit):
    """A bar that shows what Tab would write, and writes it when Tab is pressed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hint_text = ""
        self.completion_text = ""
        self.hint_color = QColor(PALETTE.get("base1", "#93a1a1"))

    def event(self, event):
        if event.type() == event.Type.KeyPress and event.key() in (
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.accept_completion()
            return True
        return super().event(event)

    def accept_completion(self):
        """Write the current suggestion into the bar."""
        if self.completion_text:
            self.setText(self.text() + self.completion_text)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not (self.hint_text and self.text() and self.hasFocus()):
            return
        metrics = self.fontMetrics()
        x_pos = metrics.horizontalAdvance(self.text()) + HINT_GAP_PX
        if x_pos >= self.rect().width():
            return
        painter = QPainter(self)
        try:
            painter.setPen(self.hint_color)
            painter.setFont(self.font())
            y_pos = (int((self.rect().height() + metrics.height()) / 2)
                     - metrics.descent())
            painter.drawText(x_pos, y_pos, self.hint_text)
        finally:
            painter.end()
