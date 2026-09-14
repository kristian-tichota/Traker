import threading

from PyQt6 import sip
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_agg import FigureCanvasAgg

from src.gui.animations import LoadingSpinner, SPINNER_INSET_PX


class ChartCanvas(QWidget):
    """A Qt widget that paints a figure someone else rendered."""

    resized = pyqtSignal()

    def __init__(self, figure, parent=None):
        super().__init__(parent)
        self._agg = FigureCanvasAgg(figure)
        self.render_lock = threading.RLock()
        self._image = None
        self._image_size = None

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._ground = _qcolor_of(figure.get_facecolor())
        self.spinner = LoadingSpinner(self)

    @property
    def figure(self):
        return self._agg.figure

    @property
    def device_pixel_ratio(self) -> float:
        return self._agg.device_pixel_ratio

    def mpl_connect(self, signal, func):
        """Return the matplotlib callback registry, unchanged."""
        return self._agg.mpl_connect(signal, func)

    def size_figure_for(self, size, ratio):
        """Resize the figure to a canvas size measured on the interface thread."""
        figure = self._agg.figure
        if figure is None:
            return
        self._agg._set_device_pixel_ratio(ratio or 1.0)
        width = max(1, size.width()) * self._agg.device_pixel_ratio
        height = max(1, size.height()) * self._agg.device_pixel_ratio
        figure.set_size_inches(width / figure.dpi, height / figure.dpi, forward=False)

    def draw_offscreen(self):
        """Rasterise the figure into the Agg buffer."""
        self._agg.draw()

    def snapshot(self) -> QImage:
        """Return the Agg buffer as an independent QImage."""
        buffer = memoryview(self._agg.buffer_rgba())
        height, width, _ = buffer.shape
        image = QImage(sip.voidptr(buffer), width, height,
                       QImage.Format.Format_RGBA8888).copy()
        image.setDevicePixelRatio(self.device_pixel_ratio)
        return image

    def set_image(self, image: QImage):
        """Adopt a finished render."""
        self._image = image
        self._image_size = self.size()
        self.update()

    def show_current_buffer(self):
        """Re-read the Agg buffer after a pulse blitted into it."""
        self.set_image(self.snapshot())

    def copy_from_bbox(self, bbox):
        return self._agg.copy_from_bbox(bbox)

    def restore_region(self, region):
        self._agg.restore_region(region)

    def blit(self, bbox=None):
        self._agg.blit(bbox)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            if self._image is None:
                painter.fillRect(self.rect(), self._ground)
            elif self._image_size == self.size():
                painter.drawImage(QPoint(0, 0), self._image)
            else:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(QRectF(self.rect()), self._image)
            self.spinner.paint(painter, self._spinner_centre())
        finally:
            painter.end()

    def _spinner_centre(self) -> QPointF:
        """Return the middle of an empty canvas and the corner of a full one."""
        box = self.rect()
        if self._image is None:
            return QPointF(box.center())
        return QPointF(box.right() - SPINNER_INSET_PX, box.top() + SPINNER_INSET_PX)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._deliver_motion(event.position().x(), event.position().y())

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._deliver_motion(-1.0, -1.0)

    def _deliver_motion(self, x_logical, y_logical):
        """Hand the move to matplotlib, unless the figure is being rendered."""
        if not self.render_lock.acquire(blocking=False):
            return
        try:
            ratio = self.device_pixel_ratio
            x = x_logical * ratio
            y = (self.height() - y_logical) * ratio
            MouseEvent("motion_notify_event", self._agg, x, y)._process()
        finally:
            self.render_lock.release()


def _qcolor_of(rgba) -> QColor:
    """Return a matplotlib 0..1 RGBA tuple as a Qt colour."""
    red, green, blue = (int(round(channel * 255)) for channel in rgba[:3])
    return QColor(red, green, blue)
