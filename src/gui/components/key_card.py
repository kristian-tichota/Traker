from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QWidget

from src.config import PALETTE

BACKGROUND_ALPHA = 205

PAD_X = 11
PAD_Y = 8
GAP = 14
ROW_HEIGHT = 15
FONT_PX = 10

MARGIN = 20

RADIUS = 4.0


class KeyCard(QWidget):
    """One key per row, and what that key does."""

    def __init__(self, hints=(), parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._font = QFont("Fira Code")
        self._font.setPixelSize(FONT_PX)
        self._hints = []
        self.set_hints(hints)

    def set_hints(self, hints):
        """Show these keys."""
        self._hints = [(str(key), str(says)) for key, says in hints]
        self.resize(self.sizeHint())
        self.update()

    @property
    def hints(self) -> tuple:
        """What it is saying, as (key, what it does) pairs."""
        return tuple(self._hints)

    def sizeHint(self) -> QSize:
        """As wide as its widest row, because it is placed by its own corner."""
        if not self._hints:
            return QSize(0, 0)
        metrics = QFontMetrics(self._font)
        keys = max(metrics.horizontalAdvance(key) for key, _ in self._hints)
        says = max(metrics.horizontalAdvance(says) for _, says in self._hints)
        return QSize(keys + GAP + says + 2 * PAD_X,
                     ROW_HEIGHT * len(self._hints) + 2 * PAD_Y)

    def place_top_right(self, within):
        """Sit in the top-right corner of within, in its parent's own coordinates."""
        size = self.sizeHint()
        self.setGeometry(within.right() - size.width() - MARGIN,
                         within.top() + MARGIN, size.width(), size.height())

    def paintEvent(self, event):
        if not self._hints:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        behind = QColor(PALETTE['base03'])
        behind.setAlpha(BACKGROUND_ALPHA)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(behind)
        painter.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)

        painter.setFont(self._font)
        metrics = QFontMetrics(self._font)
        keys = max(metrics.horizontalAdvance(key) for key, _ in self._hints)

        top = PAD_Y
        for key, says in self._hints:
            row = QRectF(PAD_X, top, keys, ROW_HEIGHT)
            painter.setPen(QColor(PALETTE['base1']))
            painter.drawText(row, int(Qt.AlignmentFlag.AlignRight
                                      | Qt.AlignmentFlag.AlignVCenter), key)
            painter.setPen(QColor(PALETTE['base00']))
            painter.drawText(QRectF(PAD_X + keys + GAP, top,
                                    self.width() - PAD_X - keys - GAP, ROW_HEIGHT),
                             int(Qt.AlignmentFlag.AlignLeft
                                 | Qt.AlignmentFlag.AlignVCenter), says)
            top += ROW_HEIGHT
