import logging
import math

import numpy as np
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QToolTip, QWidget, QVBoxLayout
from PyQt6.QtCore import QPoint, QThreadPool, QTimer
from PyQt6.QtGui import QCursor, QFont
import matplotlib

matplotlib.use('Agg')
from matplotlib.figure import Figure

from src.config import PALETTE
from src.gui.graphs.canvas import ChartCanvas
from src.gui.lifecycle import PausesWhenHidden, ShutdownMixin
from src.gui.workers import discard, run_in_background
from src.profile import UserProfile

log = logging.getLogger(__name__)

_NOTHING = object()


def style_trend_axes(ax):
    """Apply the Solarized styling of a trend panel to ax."""
    ax.set_facecolor(PALETTE['base3'])
    ax.spines['bottom'].set_color(PALETTE['base01'])
    ax.spines['left'].set_color(PALETTE['base01'])
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(colors=PALETTE['base00'], labelsize=8)
    ax.grid(True, color=PALETTE['base2'], linestyle='--')


class BaseGraphView(ShutdownMixin, PausesWhenHidden, QWidget):
    """A Solarized matplotlib canvas, rendered off the interface thread."""

    PULSE_INTERVAL_MS = 50

    CLOCK_STEP = 0.05

    CONTENT_MARGINS = (5, 5, 5, 5)

    MIN_CANVAS_PX = 60

    RESIZE_SETTLE_MS = 90

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.threadpool = QThreadPool.globalInstance()
        self.profile = UserProfile()

        self.master_clock = 0.0
        self.anim_nodes = []
        self.figure_bg = None
        self._needs_bg_recapture = True
        self._last_hovered = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(*self.CONTENT_MARGINS)

        self.fig = Figure(facecolor=PALETTE['base3'], layout='constrained')
        self.canvas = ChartCanvas(self.fig)

        self._render_generation = 0
        self._last_payload = _NOTHING
        self._owed_render = None
        self._render_size = None
        self._renders_out = 0

        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.update_animation)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._flush_owed_render)

    def fetch(self, fn, on_result, *args, on_error=None, **kwargs):
        """Read off the interface thread, with both outcomes wired."""
        if self.is_shut_down():
            return None
        return run_in_background(self.threadpool, fn, on_result, on_error,
                                 *args, **kwargs)

    paused_timer_attribute = "pulse_timer"

    @property
    def paused_timer_interval_ms(self):
        return self.PULSE_INTERVAL_MS

    def install_canvas(self):
        """Add the canvas to the layout and start listening for resizes."""
        self.main_layout.addWidget(self.canvas, stretch=1)
        self.canvas.resized.connect(self.on_resize)

    def on_resize(self, event=None):
        self.invalidate_background()
        self._owe(read=False)
        if self.isVisible():
            self._resize_timer.start(self.RESIZE_SETTLE_MS)

    def resume_animation(self):
        """Restart the pulse and the loading arc, and pay any owed render."""
        super().resume_animation()
        if self._renders_out:
            self.canvas.spinner.start()
        if self._owed_render is not None:
            self._resize_timer.start(self.RESIZE_SETTLE_MS)

    def pause_animation(self):
        """Stop the pulse and the loading arc."""
        super().pause_animation()
        self.canvas.spinner.stop()

    def invalidate_background(self):
        """Mark the blit cache as no longer matching the canvas."""
        self._needs_bg_recapture = True

    def refresh(self):
        """Re-read the profile, then read and draw this chart's rows on a worker thread."""
        self.profile.reload()
        self.prepare_refresh()
        self._render(read=True)

    def prepare_refresh(self):
        """Do whatever a refresh must do on the interface thread."""

    def read_chart_data(self):
        """Return the rows this chart draws."""
        return None

    def reset_axes(self):
        """Clear the axes and re-apply the Solarized styling."""

    def draw_chart(self, data):
        """Build this chart's artists for data."""

    def _owe(self, read: bool):
        """Note a render to do when this chart is next shown."""
        if self._owed_render is None or read:
            self._owed_render = read

    def _render(self, read: bool):
        if self.is_shut_down():
            return None
        if read is False and self._last_payload is _NOTHING:
            return None
        size = self.canvas.size()
        if (not self.isVisible()
                or size.width() < self.MIN_CANVAS_PX
                or size.height() < self.MIN_CANVAS_PX):
            self._owe(read)
            return None
        self._owed_render = None
        self._render_generation += 1
        self._render_size = size
        self.invalidate_background()
        worker = self.fetch(self._read_and_render, self._on_render_finished,
                            self._render_generation, read, self._render_size,
                            self.devicePixelRatioF() or 1.0,
                            on_error=self._on_render_failed)
        if worker is not None:
            self._renders_out += 1
            self.canvas.spinner.start()
        return worker

    def _flush_owed_render(self):
        owed, self._owed_render = self._owed_render, None
        if owed is None:
            return
        if owed is False and self.canvas.size() == self._render_size:
            return
        self._render(read=owed)

    def _read_and_render(self, generation, read, size, ratio):
        """Read, build and rasterise the whole chart, on a worker thread."""
        data = self.read_chart_data() if read else self._last_payload
        with self.canvas.render_lock:
            if generation != self._render_generation:
                log.debug("Dropping a superseded render of %s", type(self).__name__)
                return generation, data, None, None
            self.canvas.size_figure_for(size, ratio)
            self.anim_nodes.clear()
            self._last_hovered = None
            self.reset_axes()
            self.draw_chart(data)
            self.canvas.draw_offscreen()
            background = self.canvas.copy_from_bbox(self.fig.bbox)
            image = self.canvas.snapshot()
        return generation, data, background, image

    def _on_render_finished(self, outcome):
        """Adopt a finished render."""
        self._render_settled()
        generation, data, background, image = outcome
        if generation != self._render_generation:
            return
        self._last_payload = data
        if image is None:
            return
        self.figure_bg = background
        self._needs_bg_recapture = False
        self.canvas.set_image(image)

    def _on_render_failed(self, failure):
        """Handle a render that raised on the worker."""
        self._render_settled()
        error, formatted = failure
        log.error("Rendering %s failed: %s\n%s", type(self).__name__, error, formatted)

    def _render_settled(self):
        """Record that one render is no longer out, however it ended."""
        self._renders_out = max(0, self._renders_out - 1)
        if not self._renders_out:
            self.canvas.spinner.stop()

    def show_hover(self, key, text) -> bool:
        """Show text for key under the cursor, reporting whether it was not showing already."""
        if self._last_hovered == key:
            return False
        QToolTip.setFont(QFont("Fira Code", 10))
        QToolTip.showText(QCursor.pos() + QPoint(15, 15), text, self.canvas)
        self._last_hovered = key
        return True

    def clear_hover(self) -> bool:
        """Take the tooltip down, reporting whether one was up."""
        if self._last_hovered is None:
            return False
        QToolTip.hideText()
        self._last_hovered = None
        return True

    def wave(self, speed: float) -> float:
        """Return a 0..1 sine on the shared clock, so every chart pulses in step."""
        return (math.sin(self.master_clock * speed) + 1) / 2

    def has_animation(self) -> bool:
        """Report whether anything needs redrawing this pulse."""
        return bool(self.anim_nodes)

    PULSE_SPEED = 3.0

    def draw_animated_artists(self):
        """Advance and draw everything this chart animates."""
        for node in self.anim_nodes:
            self.animate_node(node, self.wave(node.get("speed", self.PULSE_SPEED)))
            node["ax"].draw_artist(node["artist"])
        self.draw_extra_artists()

    def animate_node(self, node, wave: float):
        """Advance one node by wave, a 0..1 sine on the shared clock."""
        node["artist"].set_markersize(node["base_size"] + (wave * 5))
        node["artist"].set_alpha(0.3 + (wave * 0.5))

    def draw_extra_artists(self):
        """Draw anything animated that is not one of anim_nodes."""

    def update_animation(self):
        """Draw one frame of the pulse: restore, redraw what moves, blit."""
        if not self.has_animation():
            return
        if self._needs_bg_recapture or not self.figure_bg:
            return
        if not self.canvas.render_lock.acquire(blocking=False):
            return
        try:
            self.canvas.restore_region(self.figure_bg)
            self.master_clock += self.CLOCK_STEP
            self.draw_animated_artists()
            self.canvas.blit(self.fig.bbox)
            self.canvas.show_current_buffer()
        finally:
            self.canvas.render_lock.release()


class WindowedGraphView(BaseGraphView):
    """A chart whose series are averaged over a rolling window the member stores."""

    PERIOD_SETTING = ""

    PERIODS = {1: "1 Day (Raw)", 7: "7 Days (Weekly Average)"}

    DEFAULT_PERIOD = 1

    def __init__(self, db):
        super().__init__(db)
        self.rolling_period = self.DEFAULT_PERIOD

        self.controls_layout = QHBoxLayout()
        self.controls_layout.addWidget(QLabel("<b>Rolling Average Window:</b>"))
        self.period_select = QComboBox()
        self.period_select.addItems(list(self.PERIODS.values()))
        self.period_select.setCurrentText(self.PERIODS[self.DEFAULT_PERIOD])
        self.period_select.currentTextChanged.connect(self.on_period_changed)
        self.controls_layout.addWidget(self.period_select)
        self.main_layout.addLayout(self.controls_layout)

    def _read_preferences(self):
        return self.db.get_settings([self.PERIOD_SETTING],
                                    {self.PERIOD_SETTING: self.PERIODS[self.DEFAULT_PERIOD]})

    def _apply_preferences(self, saved):
        self._adopt_period(saved[self.PERIOD_SETTING])
        self.refresh()

    def _days_of(self, label) -> int:
        """Return the window a control label names, or the default for one it does not offer."""
        return next((days for days, offered in self.PERIODS.items() if offered == str(label)),
                    self.DEFAULT_PERIOD)

    def _adopt_period(self, saved_period):
        """Show a stored window on the control without writing it back."""
        self.rolling_period = self._days_of(saved_period)
        self.period_select.blockSignals(True)
        self.period_select.setCurrentText(self.PERIODS[self.rolling_period])
        self.period_select.blockSignals(False)

    def _remember_period(self, text):
        self.fetch(lambda: self.db.set_setting(self.PERIOD_SETTING, text), discard)

    def on_period_changed(self, text):
        self.rolling_period = self._days_of(text)
        self._remember_period(text)
        self.refresh()

    def set_rolling_period(self, days: int):
        """Adopt a window chosen from the keyboard, store it, and redraw at it."""
        self._adopt_period(self.PERIODS[days])
        self._remember_period(self.PERIODS[days])
        self.refresh()

    def _compute_rolling_avg(self, data: np.ndarray, window: int) -> np.ndarray:
        """Average each day with the window - 1 days before it."""
        if window <= 1:
            return data
        if len(data) < window:
            return data[:0]
        return np.convolve(data, np.ones(window)/window, mode='valid')
