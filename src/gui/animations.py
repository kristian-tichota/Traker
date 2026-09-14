import time
import typing

from PyQt6.QtCore import (QPropertyAnimation, QRectF, QTimer, QVariantAnimation,
                          QEasingCurve, QObject, QPointF, Qt, pyqtProperty)
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QColor, QPainter, QPen
from src.config import PALETTE


def blend(ground: QColor, accent: QColor, amount: float) -> QColor:
    """Move ground amount of the way towards accent, clamped."""
    amount = max(0.0, min(1.0, amount))
    keep = 1.0 - amount
    return QColor(
        round(ground.red() * keep + accent.red() * amount),
        round(ground.green() * keep + accent.green() * amount),
        round(ground.blue() * keep + accent.blue() * amount),
    )

SPINNER_GRACE_MS = 120

SPINNER_PERIOD_MS = 900

SPINNER_FRAME_MS = 16

SPINNER_RADIUS_PX = 17
SPINNER_THICKNESS_PX = 3
SPINNER_SWEEP_DEGREES = 110

SPINNER_INSET_PX = SPINNER_RADIUS_PX + SPINNER_THICKNESS_PX + 6


class LoadingSpinner(QObject):
    """The "something is being waited for" arc: its phase, and how it is drawn."""

    def __init__(self, widget, parent=None):
        super().__init__(parent if parent is not None else widget)
        self._widget = widget
        self.started_at = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.advance)

    def waited_ms(self):
        """Return milliseconds since the wait began, or None where none is on."""
        if self.started_at is None:
            return None
        return (time.monotonic() - self.started_at) * 1000.0

    @property
    def phase(self):
        """Return 0..1 through the revolution, or None where there is nothing to show."""
        waited = self.waited_ms()
        if waited is None or waited < SPINNER_GRACE_MS:
            return None
        return (waited % SPINNER_PERIOD_MS) / SPINNER_PERIOD_MS

    @property
    def showing(self) -> bool:
        return self.phase is not None

    def start(self):
        if self._timer.isActive():
            return
        self.started_at = time.monotonic()
        self._timer.start(SPINNER_FRAME_MS)

    def stop(self):
        """Stop waiting, and take the arc off the screen if it got there."""
        self._timer.stop()
        was_showing = self.showing
        self.started_at = None
        if was_showing:
            self._widget.update()

    def advance(self):
        """Advance one frame, repainting where there is anything to show."""
        if self.started_at is None:
            return
        if self.showing:
            self._widget.update()

    def paint(self, painter: QPainter, centre: QPointF):
        """Draw this frame's arc, centred on centre."""
        phase = self.phase
        if phase is None:
            return
        box = QRectF(centre.x() - SPINNER_RADIUS_PX, centre.y() - SPINNER_RADIUS_PX,
                     SPINNER_RADIUS_PX * 2, SPINNER_RADIUS_PX * 2)
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            track = QPen(QColor(PALETTE['base1']), SPINNER_THICKNESS_PX)
            track.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(track)
            painter.drawEllipse(box)
            arc = QPen(QColor(PALETTE['blue']), SPINNER_THICKNESS_PX)
            arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc)
            start = int(-phase * 360 * 16)
            painter.drawArc(box, start, int(-SPINNER_SWEEP_DEGREES * 16))
        finally:
            painter.restore()


class FadeOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._alpha = 255
        self.bg_color = QColor(PALETTE['base3'])
        self.spinner = LoadingSpinner(self)

    @pyqtProperty(int)
    def alpha(self):
        return self._alpha

    @alpha.setter
    def alpha(self, value):
        self._alpha = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setOpacity(self._alpha / 255.0)
            painter.fillRect(self.rect(), self.bg_color)
            self.spinner.paint(painter, QPointF(self.rect().center()))
        finally:
            painter.end()


class TabFadeManager(QObject):
    """Fades a tab in when its data arrives, not when the tab is clicked."""

    def __init__(self, tab_widget, duration=180):
        super().__init__(tab_widget)
        self.tab_widget = tab_widget
        self.duration = duration
        self.overlay = FadeOverlay()

        self.anim = QPropertyAnimation(self.overlay, b"alpha", self)
        self.anim.setDuration(self.duration)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.finished.connect(self._on_finished)

        self.covering = False

    def _on_finished(self):
        self.overlay.hide()
        self.covering = False
        self.overlay.spinner.stop()

    def cover(self, index: int):
        """Put the veil over a tab that is about to be repopulated."""
        widget = self.tab_widget.widget(index)
        if not widget:
            return
        self.anim.stop()
        self.overlay.setParent(widget)
        self.overlay.resize(widget.size())
        self.overlay.alpha = 255
        self.overlay.show()
        self.overlay.raise_()
        self.covering = True
        self.overlay.spinner.start()

    def reveal(self):
        """Fade the veil away: the rows behind it are the new ones."""
        if not self.covering:
            return
        self.overlay.spinner.stop()
        self.anim.stop()
        self.anim.setStartValue(self.overlay.alpha)
        self.anim.setEndValue(0)
        self.anim.start()


class ChangeGlow(QObject):
    """Fades a wash off the rows a refresh brought in or altered."""

    DURATION_MS = 650

    def __init__(self, model, duration=DURATION_MS, parent=None):
        super().__init__(parent)
        self.model = model
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(duration)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim.valueChanged.connect(self._apply)
        self.anim.finished.connect(self._on_finished)

    def start(self):
        """Wash the model's changed rows and begin fading it off."""
        if not self.model.changed_rows():
            self.stop()
            return False
        self.anim.stop()
        self.model.highlight_changes(1.0)
        self.anim.start()
        return True

    def stop(self):
        """Drop the wash now, without waiting for the fade."""
        self.anim.stop()
        self.model.highlight_changes(0.0)

    def _apply(self, value: typing.Any):
        self.model.highlight_changes(float(value))

    def _on_finished(self):
        self.model.highlight_changes(0.0)


class StatusBarPulser(QObject):
    def __init__(self, status_bar, base_bg_hex, text_color_hex, duration=500):
        super().__init__(status_bar)
        self.status_bar = status_bar
        self.base_bg = QColor(base_bg_hex)
        self.text_color = text_color_hex

        self.animation = QVariantAnimation(self)
        self.animation.setDuration(duration)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._apply_color)

    def pulse(self, flash_hex: str):
        self.animation.stop()
        self.animation.setStartValue(QColor(flash_hex))
        self.animation.setEndValue(self.base_bg)
        self.animation.start()

    def _apply_color(self, color: typing.Any):
        self.status_bar.setStyleSheet(
            f"background-color: {color.name()}; color: {self.text_color}; padding: 3px;"
        )
