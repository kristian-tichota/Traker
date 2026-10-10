from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QWidget

from src.config import PALETTE
from src.gui.animations import grey_of

BACKGROUND_ALPHA = 205

PAD_X = 11
PAD_Y = 8
GAP = 14
ROW_HEIGHT = 15
FONT_PX = 10

MARGIN = 20

RADIUS = 4.0

INPUTS_JOIN = " · "

CALM_INPUTS, CALM_SAYS, CALM_KEY = (grey_of(PALETTE['base0']), grey_of(PALETTE['base01']),
                                     grey_of(PALETTE['base01'], 0.75))

LEFT = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
RIGHT = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


class KeyCard(QWidget):
    """One key per row, what that key does, and the inputs that send it."""

    def __init__(self, hints=(), parent=None, scale=1.0, calm=False):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.scale = float(scale)
        self.calm = bool(calm)
        self._font = QFont("Fira Code")
        self._font.setPixelSize(round(FONT_PX * self.scale))
        self._rows = []
        self.light = False
        self.set_hints(hints)

    def set_hints(self, hints):
        """Show (key, effect) or (key, effect, input names) rows."""
        self._rows = [(str(key), str(says), tuple(str(name) for name in (rest[0] if rest else ())))
                      for key, says, *rest in hints]
        self.resize(self.sizeHint())
        self.updateGeometry()
        self.update()

    def set_light(self, light):
        """Paint the card for a light surface behind it, or a dark one."""
        self.light = bool(light)
        self.update()

    @property
    def hints(self) -> tuple:
        """Return what the card says, as (key, effect) pairs."""
        return tuple((key, says) for key, says, _ in self._rows)

    @property
    def inputs(self) -> tuple:
        """Return the input names each row carries, in row order."""
        return tuple(names for _, _, names in self._rows)

    def _px(self, length) -> int:
        return round(length * self.scale)

    def _columns(self) -> tuple:
        """Return the widths of the inputs, effect and key columns, inputs 0 where none."""
        metrics = QFontMetrics(self._font)
        inputs = max(metrics.horizontalAdvance(INPUTS_JOIN.join(names))
                     for _, _, names in self._rows)
        says = max(metrics.horizontalAdvance(says) for _, says, _ in self._rows)
        keys = max(metrics.horizontalAdvance(key) for key, _, _ in self._rows)
        return inputs, says, keys

    def sizeHint(self) -> QSize:
        """Size the card to its widest row."""
        if not self._rows:
            return QSize(0, 0)
        inputs, says, keys = self._columns()
        gaps = (2 if inputs else 1) * self._px(GAP)
        return QSize(inputs + says + keys + gaps + 2 * self._px(PAD_X),
                     self._px(ROW_HEIGHT) * len(self._rows) + 2 * self._px(PAD_Y))

    def place_top_right(self, within):
        """Place the card in the top-right corner of within, in parent coordinates."""
        size = self.sizeHint()
        self.setGeometry(within.right() - size.width() - MARGIN,
                         within.top() + MARGIN, size.width(), size.height())

    def _tones(self) -> tuple:
        """Return the bright, effect and faint colours."""
        if self.calm:
            return CALM_INPUTS, CALM_SAYS, CALM_KEY
        return (QColor(PALETTE['base01' if self.light else 'base1']), QColor(PALETTE['base00']),
                QColor(PALETTE['base1' if self.light else 'base01']))

    def paintEvent(self, event):
        if not self._rows:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.calm:
            behind = QColor(PALETTE['base2' if self.light else 'base03'])
            behind.setAlpha(BACKGROUND_ALPHA)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(behind)
            painter.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)

        painter.setFont(self._font)
        inputs, says, keys = self._columns()
        bright, said, faint = self._tones()
        gap, row_height = self._px(GAP), self._px(ROW_HEIGHT)
        left = self._px(PAD_X)

        top = self._px(PAD_Y)
        for key, effect, names in self._rows:
            if inputs:
                painter.setPen(bright)
                painter.drawText(QRectF(left, top, inputs, row_height), LEFT,
                                 INPUTS_JOIN.join(names))
                painter.setPen(said)
                painter.drawText(QRectF(left + inputs + gap, top, says, row_height), LEFT, effect)
                painter.setPen(faint)
                painter.drawText(QRectF(left + inputs + says + 2 * gap, top, keys, row_height),
                                 LEFT, key)
            else:
                painter.setPen(bright)
                painter.drawText(QRectF(left, top, keys, row_height), RIGHT, key)
                painter.setPen(said)
                painter.drawText(QRectF(left + keys + gap, top, says, row_height), LEFT, effect)
            top += row_height
