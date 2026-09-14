from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget

from src.config import PALETTE
from src.domain import media

BAR_PX = 3
TRACK = 'base01'
FILLED = 'cyan'

TEXT_PX = 13
TEXT = 'base2'
ROW_HEIGHT = 18
GAP = 3

HEIGHT = ROW_HEIGHT + GAP + BAR_PX

MARGIN = 12


class MediaProgress(QWidget):
    """One line and one readout, or nothing at all."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(HEIGHT)

        self._font = QFont("Fira Code")
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setPixelSize(TEXT_PX)
        self._says = ""
        self._fraction = 0.0

    @property
    def says(self) -> str:
        """The position it is showing, as the member reads it."""
        return self._says

    @property
    def fraction(self) -> float:
        """How much of the line is filled, between nothing and all of it."""
        return self._fraction

    def sizeHint(self) -> QSize:
        """As wide as it is given and exactly as tall as the band."""
        return QSize(super().sizeHint().width(), HEIGHT)

    def show_place(self, place, unit=media.TIME):
        """Say where place is."""
        says = media.how_far(place, unit)
        fraction = media.fraction(place, unit)
        if says == self._says and self._filled(fraction) == self._filled(self._fraction):
            self._fraction = fraction
            return
        self._says, self._fraction = says, fraction
        self.update()

    def _filled(self, fraction) -> int:
        return int(round(max(0.0, min(1.0, fraction)) * self.width()))

    def paintEvent(self, event):
        """The line, and the position over its right-hand end."""
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)

        bar = QRectF(0, self.height() - BAR_PX, self.width(), BAR_PX)
        painter.setBrush(QColor(PALETTE[TRACK]))
        painter.drawRect(bar)
        filled = self._filled(self._fraction)
        if filled:
            painter.setBrush(QColor(PALETTE[FILLED]))
            painter.drawRect(QRectF(bar.left(), bar.top(), filled, BAR_PX))

        row = QRectF(0, self.height() - BAR_PX - GAP - ROW_HEIGHT,
                     self.width() - MARGIN, ROW_HEIGHT)
        corner = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        painter.setFont(self._font)
        painter.setPen(QColor(PALETTE[TEXT]))
        painter.drawText(row, corner, self._says)
