import logging

from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.config import PALETTE

log = logging.getLogger(__name__)


class BreakPane(QWidget):
    """What a break shows, or one line in its place saying why nothing is shown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = None
        self._message = QLabel(self)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._message)

    def position(self) -> int:
        return 0

    def duration(self) -> int:
        return 0

    def stop(self):
        """Leave what is shown as it is, there being no place in it to keep."""

    def shutdown(self):
        """Let go of what is shown, once, at the end of the break."""
        self.stop()

    def _shown(self):
        """Return the widget shown while there is no message."""
        return self.view

    def _show_message(self, text, colour='red'):
        self._message.setText(text)
        self._message.setStyleSheet(f"color: {PALETTE[colour]}; font-size: 16px; "
                                    f"font-family: 'Fira Code'; letter-spacing: 2px;")
        self._show_only(self._message)

    def _clear_message(self):
        self._message.clear()
        self._show_only(self._shown())

    def _show_only(self, shown):
        layout = self.layout()
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            widget.setVisible(widget is shown)


class WebPane(BreakPane):
    """A pane a web view draws on paper, destroyed as soon as the break ends."""

    def __init__(self, refused, parent=None, quiet=True, alignment=Qt.AlignmentFlag(0)):
        super().__init__(parent)
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except ImportError as error:
            log.warning("No web engine for a break: %s", error)
            self._show_message(f"{refused}\n{error}")
            return
        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.page().setBackgroundColor(QColor(PALETTE['base3']))
        if quiet:
            self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.view.page().setAudioMuted(True)
        self.layout().addWidget(self.view, alignment=alignment)

    def shutdown(self):
        """Let go of what is shown and destroy the web view at once."""
        self.stop()
        if self.view is not None:
            sip.delete(self.view)
            self.view = None
