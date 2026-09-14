import logging
import os

from PyQt6.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QOpenGLContext, QPalette
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import (QFrame, QLabel, QStackedWidget, QVBoxLayout,
                             QWidget)

from src.config import PALETTE
from src.desktop.activities import DOCUMENT, readout_of
from src.domain.media import Place
from src.gui.components.key_card import KeyCard
from src.gui.components.media_progress import MediaProgress

log = logging.getLogger(__name__)

SEEK_MS = 30_000

VOLUME_STEP = 0.1
SCROLL_STEP_PX = 160


def _failure_label(parent, text) -> QLabel:
    """Say it on the screen the member is looking at."""
    label = QLabel(text, parent)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(f"color: {PALETTE['red']}; font-size: 16px; "
                        f"font-family: 'Fira Code'; letter-spacing: 2px;")
    return label


class MpvScreen(QOpenGLWidget):
    """The rectangle libmpv draws each frame into, and nothing else."""

    frame_ready = pyqtSignal()
    playback_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._context = None
        self._proc_address = None
        self._pending = None
        self.player_error = None
        self.player = self._start_mpv()
        self.frame_ready.connect(self.update)
        if self.player is not None:
            self.player.event_callback("end-file")(self._file_ended)

    def _start_mpv(self):
        """One player, or None and player_error saying why."""
        try:
            import mpv
        except (ImportError, OSError) as error:
            self.player_error = f"libmpv would not load: {error}"
            log.warning("No video in a break: %s", self.player_error)
            return None

        try:
            return self._build_player(mpv)
        except (OSError, RuntimeError, ValueError, SystemError,
                AttributeError, mpv.ArgumentError) as error:
            self.player_error = f"mpv would not start: {error}"
            log.warning("No video in a break: %s", self.player_error)
            return None

    def _build_player(self, mpv):
        """The player a break's pane drives, with mpv told to keep to itself."""
        return mpv.MPV(
            vo="libmpv",
            hwdec="auto-safe",
            keep_open="yes",
            input_default_bindings=False,
            input_vo_keyboard=False,
            osc=False,
            osd_level=0,
            log_handler=_say_what_mpv_said,
            loglevel="warn",
        )

    def initializeGL(self):
        """Hand mpv this widget's framebuffer, once it has one."""
        if self.player is None:
            return
        import mpv

        self._proc_address = mpv.MpvGlGetProcAddressFn(_gl_proc_address)
        self._context = mpv.MpvRenderContext(
            self.player, "opengl",
            opengl_init_params={"get_proc_address": self._proc_address})
        self._context.update_cb = self._mpv_wants_a_frame
        self._load_what_is_waiting()

    def play(self, path, start_seconds=0.0):
        """Play path from start_seconds, once there is a surface for it."""
        self._pending = (path, max(0.0, float(start_seconds)))
        self._load_what_is_waiting()

    def _load_what_is_waiting(self):
        """Hand mpv the file, once both it and the context exist."""
        if self._context is None or self._pending is None or self.player is None:
            return
        path, start = self._pending
        self._pending = None
        self.player.loadfile(path, "replace", start=start)

    def _file_ended(self, event):
        """mpv's event thread, saying a file stopped and why."""
        reason = getattr(event.data, "reason", None)
        if str(reason).endswith("ERROR"):
            self.playback_failed.emit(str(getattr(event.data, "error", "")
                                          or "this file could not be played"))

    def _mpv_wants_a_frame(self):
        """mpv's render thread says there is a frame."""
        self.frame_ready.emit()

    def paintGL(self):
        """Draw whatever mpv has, into the framebuffer Qt gave us."""
        if self._context is None:
            return
        ratio = self.devicePixelRatioF()
        self._context.render(flip_y=True, opengl_fbo={
            "w": int(self.width() * ratio),
            "h": int(self.height() * ratio),
            "fbo": self.defaultFramebufferObject()})

    def shutdown(self):
        """Free the render context and the player, in that order."""
        if self._context is not None:
            self.makeCurrent()
            self._context.update_cb = None
            self._context.free()
            self.doneCurrent()
            self._context = None
        self._proc_address = None
        if self.player is not None:
            self.player.terminate()
            self.player = None


def _gl_proc_address(_ctx, name):
    """Where a GL function lives, asked by mpv and answered by Qt."""
    context = QOpenGLContext.currentContext()
    return int(context.getProcAddress(name)) if context is not None else 0


def _say_what_mpv_said(level, prefix, text):
    """mpv's own complaints, in Traker's log, at the level it gave them."""
    said = text.strip()
    if said:
        log.log(logging.ERROR if level in ("error", "fatal") else logging.WARNING,
                "mpv %s: %s", prefix, said)


class VideoPane(QWidget):
    """One file, playing."""

    def __init__(self, path=None, start_at=0, parent=None):
        super().__init__(parent)
        self._failed = None
        self.player = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.screen_widget = MpvScreen(self)
        self.screen_widget.playback_failed.connect(self._show_failure)
        layout.addWidget(self.screen_widget)
        self.player = self.screen_widget.player

        if self.player is None:
            self._show_failure(self.screen_widget.player_error
                               or "no player")
            return
        if path:
            self.open(path, start_at)

    def open(self, path, start_at=0):
        """Play path from where the member left it."""
        self._clear_failure()
        if self.player is None:
            return
        self.screen_widget.play(os.path.abspath(path),
                                max(0, int(start_at or 0)) / 1000.0)

    def _clear_failure(self):
        """A file that could not be played does not damn the next one."""
        if self._failed is not None:
            self._failed.deleteLater()
            self._failed = None
        self.screen_widget.show()

    def _show_failure(self, message):
        """Say so where the member is looking, not only in the log."""
        log.warning("Could not play: %s", message)
        self.screen_widget.hide()
        self._failed = _failure_label(self, f"COULD NOT PLAY\n{message}")
        self.layout().addWidget(self._failed)

    def toggle(self):
        """Pause, or carry on."""
        if self.player is not None:
            self.player.pause = not self.player.pause

    def step(self, direction):
        """Seek thirty seconds."""
        if self.player is None:
            return
        try:
            self.player.seek(int(direction) * SEEK_MS / 1000.0, "relative")
        except (OSError, SystemError):
            log.debug("A seek of %+d s was refused.", int(direction) * SEEK_MS // 1000)

    def nudge(self, direction):
        """Volume, which is the only other thing a voice can usefully ask for."""
        if self.player is None:
            return
        wanted = (self.player.volume or 0) + int(direction) * VOLUME_STEP * 100
        self.player.volume = max(0.0, min(100.0, wanted))

    def position(self) -> int:
        """Milliseconds in, or zero before mpv has read the file."""
        return self._milliseconds("time_pos")

    def duration(self) -> int:
        """How long the file is, or zero until mpv has read it."""
        return self._milliseconds("duration")

    def _milliseconds(self, name) -> int:
        """One mpv property as whole milliseconds, and zero for no answer."""
        if self.player is None:
            return 0
        seconds = getattr(self.player, name, None)
        return max(0, int((seconds or 0) * 1000))

    def stop(self):
        """Stop playing."""
        if self.player is not None:
            self.player.command("stop")

    def shutdown(self):
        """Let go of libmpv's threads, once, when the break is over."""
        self.screen_widget.shutdown()
        self.player = None


class DocumentPane(QWidget):
    """One PDF, a whole page at a time."""

    def __init__(self, path=None, start_at=0, parent=None):
        super().__init__(parent)
        from PyQt6.QtPdf import QPdfDocument
        from PyQt6.QtPdfWidgets import QPdfView

        self._failed = None
        self._resume_at = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.document = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        around = self.view.palette()
        around.setColor(QPalette.ColorRole.Dark, QColor(PALETTE['base03']))
        self.view.setPalette(around)
        layout.addWidget(self.view)

        navigator = self.view.pageNavigator()
        if navigator is not None:
            navigator.currentPageChanged.connect(self._page_changed)
        self.view.verticalScrollBar().rangeChanged.connect(self._room_changed)

        if path:
            self.open(path, start_at)

    def open(self, path, start_at=0):
        """Read path from the page the member left it on."""
        from PyQt6.QtPdf import QPdfDocument

        self._resume_at = 0
        self._clear_failure()
        error = self.document.load(os.path.abspath(path))
        if error != QPdfDocument.Error.None_:
            log.warning("Could not read %s: %s", path, error)
            self.view.hide()
            self._failed = _failure_label(self, f"COULD NOT READ\n{error.name}")
            self.layout().addWidget(self._failed)
            return
        last = max(0, self.document.pageCount() - 1)
        self._resume_at = max(0, min(int(start_at or 0), last))
        self._turn_to(self._resume_at)

    def _page_changed(self, page):
        """Put the page back when it was not the member who turned it."""
        if self._resume_at and int(page) != self._resume_at:
            self._turn_to(self._resume_at)

    def _room_changed(self, minimum, maximum):
        """The view has laid the document out, so now a jump can land."""
        if self._resume_at:
            self._turn_to(self._resume_at)

    def _turn_to(self, page):
        """Turn to page."""
        navigator = self.view.pageNavigator()
        if navigator is None:
            return
        wanted = int(page)
        if navigator.currentPage() == wanted and self.document.pageCount() > 1:
            navigator.jump(0 if wanted else 1, QPointF())
        navigator.jump(wanted, QPointF())

    def _clear_failure(self):
        if self._failed is not None:
            self._failed.deleteLater()
            self._failed = None
        self.view.show()

    def showEvent(self, event):
        """A view can only scroll to a page once it is on a screen."""
        super().showEvent(event)
        if self._resume_at:
            QTimer.singleShot(0, self._turn_to_the_page_asked_for)

    def _turn_to_the_page_asked_for(self):
        """The page a break asked for, once the view has finished laying out."""
        if self._resume_at:
            self._turn_to(self._resume_at)

    def toggle(self):
        """There is nothing to pause, so the one big key turns the page."""
        self.step(1)

    def step(self, direction):
        """A page forward or back, clamped inside the document."""
        navigator = self.view.pageNavigator()
        if navigator is None:
            return
        self._resume_at = 0
        last = max(0, self.document.pageCount() - 1)
        wanted = max(0, min(last, navigator.currentPage() + int(direction)))
        navigator.jump(wanted, QPointF())

    def nudge(self, direction):
        """Scroll inside the page, for a figure that fell across the fold."""
        self._resume_at = 0
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.value() - int(direction) * SCROLL_STEP_PX)

    def position(self) -> int:
        navigator = self.view.pageNavigator()
        return int(navigator.currentPage()) if navigator is not None else 0

    def duration(self) -> int:
        """How many pages there are, which is what a page is out of."""
        return max(0, int(self.document.pageCount()))

    def stop(self):
        """Let go of the file."""
        self._resume_at = 0
        self.document.close()


def build_pane(activity, start_at=0, parent=None) -> QWidget:
    """The pane for what this activity is."""
    if activity.kind == DOCUMENT:
        return DocumentPane(activity.path, start_at, parent)
    return VideoPane(activity.path, start_at, parent)


class MediaSurface(QWidget):
    """The break's screen while it is showing something."""

    def __init__(self, timer_ref, pane_factory=None, only_screen=False,
                 parent=None):
        super().__init__(parent)
        self.timer_ref = timer_ref
        self._only_screen = only_screen
        self.activity = None
        self._hold = (0.0, False)
        self._build_pane = pane_factory or build_pane
        self.panes = {}

        self.setObjectName("mediaSurface")
        self.setStyleSheet(
            f"#mediaSurface {{ background-color: {PALETTE['base03']}; }}")
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget(self)
        self.stack.addWidget(QWidget(self.stack))
        layout.addWidget(self.stack)

        self.keys = KeyCard(parent=self)
        self.keys.setVisible(False)
        self.progress = None
        self.strip = None
        if only_screen:
            self.progress = MediaProgress()
            self.progress.setVisible(False)
            layout.addWidget(self.progress)
            self.strip = QLabel()
            self.strip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.strip.setStyleSheet(
                f"color: {PALETTE['base01']}; background-color: {PALETTE['base02']};"
                f" font-size: 10px; font-family: 'Fira Code'; letter-spacing: 2px;"
                f" padding: 3px;")
            layout.addWidget(self.strip)

        self.update_display()

    @property
    def pane(self):
        """The pane the keys drive, or None when nothing is showing."""
        if self.activity is None:
            return None
        return self.panes.get(self.activity.kind)

    def open(self, activity, start_at=0, key_hints=()):
        """Show activity, from where the member left it."""
        pane = self.panes.get(activity.kind)
        if pane is None:
            pane = self._build_pane(activity, start_at, parent=self.stack)
            self.panes[activity.kind] = pane
            self.stack.addWidget(pane)
        else:
            pane.open(activity.path, start_at)

        self.activity = activity
        self.stack.setCurrentWidget(pane)
        self.set_keys(key_hints)
        if self.progress is not None:
            self.progress.setVisible(True)
            self.show_progress()
        self._place_the_overlays()
        self.update_display()
        return pane

    def set_keys(self, hints):
        """Name the keys that drive what is showing, or none of them."""
        self.keys.set_hints(hints)
        self.keys.setVisible(bool(hints) and self._only_screen)
        self._place_the_overlays()

    def stop(self):
        """Stop what is showing, and answer the place it had got to."""
        pane = self.pane
        self.activity = None
        self.set_keys([])
        if self.progress is not None:
            self.progress.setVisible(False)
        self.stack.setCurrentIndex(0)
        if pane is None:
            return Place()
        where = Place(pane.position(), pane.duration())
        pane.stop()
        return where

    def shutdown(self):
        """Let every pane go, before the wall this is a page of is dropped."""
        for pane in self.panes.values():
            closing = getattr(pane, "shutdown", None)
            if callable(closing):
                closing()

    def resizeEvent(self, event):
        """Keep the card and the band where they belong."""
        super().resizeEvent(event)
        self._place_the_overlays()

    def _place_the_overlays(self):
        """The card in its corner, in front."""
        self.keys.place_top_right(self.rect())
        self.keys.raise_()

    def place(self):
        """Where what is showing has got to, and which readout says it."""
        pane = self.pane
        if pane is None:
            return None
        return Place(pane.position(), pane.duration()), readout_of(self.activity.kind)

    def show_progress(self, place=None):
        """Put the pane's position on the row under it, where there is one."""
        if self.progress is None:
            return
        place = place or self.place()
        if place is None:
            return
        self.progress.show_place(*place)

    def update_display(self):
        """The same two questions every other break surface answers."""
        if self.strip is None:
            return
        fraction, holding = self._hold
        if holding:
            left = max(0, int(round(self.timer_ref.release_hold_secs * (1.0 - fraction))))
            self.strip.setText(f"LEAVING IN {left}s")
            return
        if self.timer_ref.waiting_for_work_start:
            self.strip.setText(f"BREAK OVER · {self.timer_ref.wall_hint()}")
            return
        mins, secs = divmod(int(self.timer_ref.time_left_ms // 1000), 60)
        self.strip.setText(
            f"REST {mins:02d}:{secs:02d} · {self.timer_ref.wall_hint()}")

    def show_hold(self, fraction, visible):
        """How much of the exit has been paid, in the one line there is."""
        self._hold = (fraction, visible)
        self.update_display()
