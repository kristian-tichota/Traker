from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget

from src.config import PALETTE
from src.domain import media
from src.gui.animations import grey_of

BAR_PX = 3
TRACK, LIGHT_TRACK = 'base01', 'base2'
FILLED = 'cyan'

TEXT_PX = 13
TEXT, LIGHT_TEXT = 'base2', 'base01'
ROW_HEIGHT = 18
GAP = 3

HEIGHT = ROW_HEIGHT + GAP + BAR_PX

MARGIN = 12

CALM_TRACK, CALM_FILLED, CALM_TEXT = (grey_of(PALETTE['base02']), grey_of(PALETTE['base01']),
                                      grey_of(PALETTE['base01']))


class MediaProgress(QWidget):
    """One line and one readout, or nothing, grey and in whole minutes where calm."""

    def __init__(self, parent=None, calm=False):
        super().__init__(parent)
        self.calm = bool(calm)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(HEIGHT)

        self._font = QFont("Fira Code")
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setPixelSize(TEXT_PX)
        self.says = ""
        self.fraction = 0.0
        self.light = False

    def set_light(self, light):
        """Paint the line and readout for a light surface behind them, or a dark one."""
        self.light = bool(light)
        self.update()

    def show_place(self, place, unit=media.TIME):
        """Show where place is."""
        says = media.how_far(place, unit, coarse=self.calm)
        fraction = media.fraction(place, unit, coarse=self.calm)
        if says == self.says and self._filled(fraction) == self._filled(self.fraction):
            self.fraction = fraction
            return
        self.says, self.fraction = says, fraction
        self.update()

    def _filled(self, fraction) -> int:
        return int(round(max(0.0, min(1.0, fraction)) * self.width()))

    def paintEvent(self, event):
        """Draw the line, and the position over its right-hand end."""
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)

        bar = QRectF(0, self.height() - BAR_PX, self.width(), BAR_PX)
        painter.setBrush(self._tone(LIGHT_TRACK if self.light else TRACK, CALM_TRACK))
        painter.drawRect(bar)
        filled = self._filled(self.fraction)
        if filled:
            painter.setBrush(self._tone(FILLED, CALM_FILLED))
            painter.drawRect(QRectF(bar.left(), bar.top(), filled, BAR_PX))

        row = QRectF(0, self.height() - BAR_PX - GAP - ROW_HEIGHT,
                     self.width() - MARGIN, ROW_HEIGHT)
        corner = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        painter.setFont(self._font)
        painter.setPen(self._tone(LIGHT_TEXT if self.light else TEXT, CALM_TEXT))
        painter.drawText(row, corner, self.says)

    def _tone(self, name, calm) -> QColor:
        return QColor(calm) if self.calm else QColor(PALETTE[name])
