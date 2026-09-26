import logging
import os
import re

from PyQt6.QtCore import QPointF, QThreadPool, QUrl, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QOpenGLContext, QPalette
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHeaderView, QLabel,
                             QStackedWidget, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

from src.config import PALETTE
from src.desktop import anki
from src.desktop.activities import ANY_DECK, DECK, DOCUMENT, readout_of
from src.domain.media import Place, as_elapsed
from src.gui.components.key_card import KeyCard
from src.gui.components.media_progress import MediaProgress
from src.gui.workers import run_in_background
from src.profile import UserProfile

log = logging.getLogger(__name__)

SEEK_MS = 30_000

VOLUME_STEP = 0.1
SCROLL_STEP_PX = 160

QUESTION, ANSWER = "question", "answer"

CARD_MARKERS = re.compile(r"\[anki:play:[qa]:\d+\]|\[\[type:[^\]]*\]\]")

CARD_CSS = f"""
:root {{ color-scheme: dark; --canvas: {PALETTE['base03']}; --fg: {PALETTE['base0']}; }}
body {{ margin: 20px; overflow-wrap: break-word; }}
body.nightMode {{ background-color: var(--canvas); color: var(--fg); }}
img {{ max-width: 100%; max-height: 95vh; }}
hr {{ background-color: {PALETTE['base01']}; margin: 1em 0; border: none; height: 1px; }}
.nightMode .latex {{ filter: invert(100%); }}
.nightMode img.drawing {{ filter: invert(1) hue-rotate(180deg); }}
"""

TO_THE_ANSWER = ("<script>addEventListener('load', () => "
                 "document.getElementById('answer')?.scrollIntoView());</script>")

DECK_COLUMNS = ("DECK", "NEW", "LEARN", "DUE", "")
COUNT_COLOURS = ('blue', 'red', 'green')
DECK_INDENT_PX = 28
DECK_FONT_PX = 20
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def _failure_label(parent, text, colour='red') -> QLabel:
    """Build the label that says on screen why nothing is shown."""
    label = QLabel(text, parent)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(f"color: {PALETTE[colour]}; font-size: 16px; "
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
        """Return one player, or None with player_error set."""
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
        """Build the player a break pane drives, with mpv confined to it."""
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
        """Handle mpv's event thread reporting that a file stopped."""
        reason = getattr(event.data, "reason", None)
        if str(reason).endswith("ERROR"):
            self.playback_failed.emit(str(getattr(event.data, "error", "")
                                          or "this file could not be played"))

    def _mpv_wants_a_frame(self):
        """Handle mpv's render thread reporting a frame."""
        self.frame_ready.emit()

    def paintGL(self):
        """Draw whatever mpv has into the framebuffer Qt provided."""
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
    """Return where a GL function lives, asked by mpv and answered by Qt."""
    context = QOpenGLContext.currentContext()
    return int(context.getProcAddress(name)) if context is not None else 0


def _say_what_mpv_said(level, prefix, text):
    """Log mpv's own complaints at the level it gave them."""
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
        """Play path from where it was left."""
        self._clear_failure()
        if self.player is None:
            return
        self.screen_widget.play(os.path.abspath(path),
                                max(0, int(start_at or 0)) / 1000.0)

    def _clear_failure(self):
        """Clear the failure left by a file that could not be played."""
        if self._failed is not None:
            self._failed.deleteLater()
            self._failed = None
        self.screen_widget.show()

    def _show_failure(self, message):
        """Show the failure on screen as well as in the log."""
        log.warning("Could not play: %s", message)
        self.screen_widget.hide()
        self._failed = _failure_label(self, f"COULD NOT PLAY\n{message}")
        self.layout().addWidget(self._failed)

    def toggle(self):
        """Pause, or carry on."""
        if self.player is not None:
            self.player.pause = not self.player.pause

    def step(self, direction):
        if self.player is None:
            return
        try:
            self.player.seek(int(direction) * SEEK_MS / 1000.0, "relative")
        except (OSError, SystemError):
            log.debug("A seek of %+d s was refused.", int(direction) * SEEK_MS // 1000)

    def nudge(self, direction):
        """Change the volume."""
        if self.player is None:
            return
        wanted = (self.player.volume or 0) + int(direction) * VOLUME_STEP * 100
        self.player.volume = max(0.0, min(100.0, wanted))

    def position(self) -> int:
        """Return milliseconds in, or zero before mpv has read the file."""
        return self._milliseconds("time_pos")

    def duration(self) -> int:
        """Return the file length, or zero until mpv has read it."""
        return self._milliseconds("duration")

    def _milliseconds(self, name) -> int:
        """Return one mpv property as whole milliseconds, or zero for no answer."""
        if self.player is None:
            return 0
        seconds = getattr(self.player, name, None)
        return max(0, int((seconds or 0) * 1000))

    def stop(self):
        if self.player is not None:
            self.player.command("stop")

    def shutdown(self):
        """Release libmpv's threads, once, at the end of the break."""
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
        """Read path from the page it was left on."""
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
        """Put the page back where the turn did not come from the member."""
        if self._resume_at and int(page) != self._resume_at:
            self._turn_to(self._resume_at)

    def _room_changed(self, minimum, maximum):
        """Handle the document being laid out, after which a jump can land."""
        if self._resume_at:
            self._turn_to(self._resume_at)

    def _turn_to(self, page):
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
        """Scroll to the requested page, which needs the view on a screen."""
        super().showEvent(event)
        if self._resume_at:
            QTimer.singleShot(0, self._turn_to_the_page_asked_for)

    def _turn_to_the_page_asked_for(self):
        """Turn to the page a break asked for, once layout has finished."""
        if self._resume_at:
            self._turn_to(self._resume_at)

    def toggle(self):
        """Turn the page, there being nothing to pause."""
        self.step(1)

    def step(self, direction):
        """Turn a page forward or back, clamped inside the document."""
        navigator = self.view.pageNavigator()
        if navigator is None:
            return
        self._resume_at = 0
        last = max(0, self.document.pageCount() - 1)
        wanted = max(0, min(last, navigator.currentPage() + int(direction)))
        navigator.jump(wanted, QPointF())

    def nudge(self, direction):
        """Scroll inside the page."""
        self._resume_at = 0
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.value() - int(direction) * SCROLL_STEP_PX)

    def position(self) -> int:
        navigator = self.view.pageNavigator()
        return int(navigator.currentPage()) if navigator is not None else 0

    def duration(self) -> int:
        """Return how many pages there are."""
        return max(0, int(self.document.pageCount()))

    def stop(self):
        """Release the file."""
        self._resume_at = 0
        self.document.close()


def card_page(side, ordinal, answer=False) -> str:
    """Wrap one side of a card as Anki's reviewer does, in night mode."""
    body = CARD_MARKERS.sub("", side)
    return ('<!doctype html><html><head><meta charset="utf-8">'
            f"<style>{CARD_CSS}</style></head>"
            f'<body class="card card{int(ordinal) + 1} isLin nightMode night_mode">'
            f"{body}{TO_THE_ANSWER if answer else ''}</body></html>")


def _attempt(generation, step, *args) -> tuple:
    """Run one review step: (the opening that asked, what it gave, what went wrong)."""
    try:
        return generation, step(*args), None
    except anki.EXPECTED as error:
        return generation, None, error


def _why_not(error, url, deck) -> str:
    """Say why a review step failed, in the words the wall shows."""
    if isinstance(error, anki.AnkiUnreachable):
        return f"Anki is not answering at {url}"
    if isinstance(error, anki.NoSuchDeck):
        return f"Anki has no deck called “{deck}”"
    if isinstance(error, anki.AnkiStalled):
        return "Anki took the answer and did not move on; a dialog may be open in it"
    return str(error)


def _next_owing(decks, start, direction=1) -> int:
    """Return the next deck from start, going direction and wrapping, that owes cards."""
    for step in range(1, len(decks) + 1):
        index = (start + step * direction) % len(decks)
        if decks[index].owed:
            return index
    return min(max(start, 0), max(len(decks) - 1, 0))


def _first_marked(decks, left="") -> int:
    """Return the deck the list opens on: the one left while it owes cards, else the next."""
    names = [deck.name for deck in decks]
    if left in names:
        at = names.index(left)
        return at if decks[at].owed else _next_owing(decks, at)
    return _next_owing(decks, -1)


def _deck_list(parent) -> QTreeWidget:
    """Build the list a deck is chosen from, in the columns of Anki's own."""
    tree = QTreeWidget(parent)
    tree.setColumnCount(len(DECK_COLUMNS))
    tree.setHeaderLabels(DECK_COLUMNS)
    tree.setRootIsDecorated(False)
    tree.setItemsExpandable(False)
    tree.setIndentation(DECK_INDENT_PX)
    tree.setUniformRowHeights(True)
    tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tree.setFrameShape(QFrame.Shape.NoFrame)
    header = tree.header()
    header.setStretchLastSection(True)
    for column in range(len(DECK_COLUMNS) - 1):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    for column in range(1, len(COUNT_COLOURS) + 1):
        tree.headerItem().setTextAlignment(column, RIGHT)
    tree.setStyleSheet(
        f"QTreeWidget {{ background-color: {PALETTE['base03']}; border: none;"
        f" font-family: 'Fira Code'; font-size: {DECK_FONT_PX}px; padding: 20px; }}"
        f" QTreeWidget::item {{ padding: 4px 16px; }}"
        f" QHeaderView::section {{ background-color: {PALETTE['base03']};"
        f" color: {PALETTE['base01']}; border: none; font-family: 'Fira Code';"
        f" font-size: 11px; letter-spacing: 2px; padding: 4px 16px; }}")
    return tree


def _name_colour(deck, marked=False) -> QColor:
    """Return the colour of a deck's name: bright when marked, faint when it owes nothing."""
    return QColor(PALETTE['base2' if marked else 'base0' if deck.owed else 'base01'])


def _deck_rows(tree, decks) -> list:
    """Put each deck under its parent with what it owes, and return the rows in list order."""
    rows, placed = [], {}
    for deck in decks:
        parent = placed.get(deck.name.rpartition(anki.SEPARATOR)[0])
        counts = (deck.new, deck.learning, deck.review)
        row = QTreeWidgetItem([deck.name if parent is None else deck.leaf,
                               *map(str, counts)])
        row.setForeground(0, _name_colour(deck))
        for column, (count, colour) in enumerate(zip(counts, COUNT_COLOURS), start=1):
            row.setTextAlignment(column, RIGHT)
            row.setForeground(column, QColor(PALETTE[colour if count else 'base01']))
        if parent is None:
            tree.addTopLevelItem(row)
        else:
            parent.addChild(row)
        placed[deck.name] = row
        rows.append(row)
    tree.expandAll()
    return rows


class DeckPane(QWidget):
    """One Anki deck, a card at a time, chosen and scheduled by Anki's reviewer."""

    changed = pyqtSignal()

    def __init__(self, deck=None, start_at=0, parent=None, client=None):
        super().__init__(parent)
        self.client = client or anki.AnkiConnect(UserProfile().get_metric(
            "strict_break", "anki_url", anki.DEFAULT_URL))
        self.deck = ""
        self.card = None
        self.side = None
        self.answered = 0
        self.busy = False
        self.listing = []
        self._rows = []
        self.marked = 0
        self.choosing = False
        self.from_list = False
        self._generation = 0
        self._media = ""
        self._message = None
        self.view = None
        self.chooser = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except ImportError as error:
            log.warning("No Anki deck in a break: %s", error)
            self._show_message(f"COULD NOT REVIEW\n{error}")
            return

        self.view = QWebEngineView(self)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.page().setBackgroundColor(QColor(PALETTE['base03']))
        self.view.page().setAudioMuted(True)
        layout.addWidget(self.view)
        self.chooser = _deck_list(self)
        self.chooser.hide()
        layout.addWidget(self.chooser)
        if deck:
            self.open(deck, start_at)

    def open(self, deck, start_at=0):
        """Open Anki's reviewer on deck, or list every deck to choose one for ANY_DECK."""
        self.from_list = str(deck) == ANY_DECK
        if self.from_list:
            self._list()
        else:
            self._review(str(deck))

    def toggle(self):
        """Review the marked deck, or show the answer and then answer Good."""
        if self.choosing:
            if not self.busy and self.listing:
                self._review(self.listing[self.marked].name)
            return
        self.step(1)

    def step(self, direction):
        """Show the answer, then answer Good or Again; on the list, skip to an owing deck."""
        if self.busy:
            return
        if self.choosing:
            self._mark(_next_owing(self.listing, self.marked, 1 if int(direction) > 0 else -1))
            return
        if self.card is None:
            if self.from_list and int(direction) > 0:
                self._list()
            return
        if self.side == QUESTION:
            self._run(anki.reveal, self._revealed, self.client)
            return
        ease = anki.GOOD if int(direction) > 0 else anki.AGAIN
        self._run(anki.grade, self._graded, self.client, self.deck,
                  self.card.card_id, ease)

    def undo(self):
        """Take this opening's last answer back and show that card again."""
        if self.busy or self.choosing or self.answered <= 0 or self.view is None:
            return
        self._run(anki.take_back, self._taken_back, self.client, self.deck)

    def nudge(self, direction):
        """Scroll the card, or mark the deck above or below."""
        if self.choosing:
            if not self.busy:
                self._mark(self.marked - int(direction))
            return
        if self.view is not None:
            self.view.page().runJavaScript(
                f"window.scrollBy(0, {-int(direction) * SCROLL_STEP_PX})")

    def back(self) -> bool:
        """Leave a deck chosen from the list for the list, reporting whether it did."""
        if not self.from_list or self.choosing or self.view is None:
            return False
        self._list()
        return True

    def title(self) -> str:
        """Return the deck chosen from the list while it is reviewed, or nothing."""
        return self.deck if self.from_list and not self.choosing else ""

    def position(self) -> int:
        """Return how many cards this opening has answered."""
        return self.answered

    def duration(self) -> int:
        """Return those answered, and the cards the deck still owes."""
        return self.answered + (self.card.due if self.card is not None else 0)

    def stop(self):
        """Let go of the card, which stays where it is in Anki's reviewer."""
        self._generation += 1
        self.card, self.side, self.busy = None, None, False
        if self.view is not None:
            self.view.setHtml("")

    def _review(self, deck):
        """Open Anki's reviewer on deck and show the card it chooses."""
        self._generation += 1
        self.deck = deck
        self.card, self.side, self.answered, self.busy = None, None, 0, False
        self.choosing = False
        if self.view is not None:
            self._clear_message()
            self._run(anki.begin, self._began, self.client, self.deck)
        self.changed.emit()

    def _list(self):
        """Read every deck Anki has, with what each owes, to choose one from."""
        self._generation += 1
        self.card, self.side, self.answered, self.busy = None, None, 0, False
        self.choosing, self.listing, self._rows = True, [], []
        if self.view is not None:
            self._run(anki.decks, self._listed, self.client)
        self.changed.emit()

    def _run(self, step, receiver, *args):
        """Run one step off the interface thread, taking no key until it lands."""
        self.busy = True
        run_in_background(QThreadPool.globalInstance(), _attempt, receiver,
                          self._crashed, self._generation, step, *args)

    def _settles(self, outcome) -> bool:
        """Report whether outcome is this opening's and went through, showing why not."""
        generation, _given, error = outcome
        if generation != self._generation:
            return False
        self.busy = False
        if error is not None:
            log.warning("Could not review %r: %s", self.deck, error)
            self.card, self.side = None, None
            self._show_message(
                f"COULD NOT REVIEW\n{_why_not(error, self.client.url, self.deck)}")
            return False
        return True

    def _began(self, outcome):
        if self._settles(outcome):
            self._media, shown = outcome[1]
            self._present(shown)

    def _listed(self, outcome):
        if not self._settles(outcome):
            return
        self.listing = list(outcome[1])
        self.chooser.clear()
        self._rows = _deck_rows(self.chooser, self.listing)
        self._clear_message()
        self._mark(_first_marked(self.listing, self.deck))

    def _revealed(self, outcome):
        if not self._settles(outcome):
            return
        if outcome[1] and self.card is not None:
            self.side = ANSWER
            self._render(self.card.answer, answer=True)
        else:
            self._run(anki.current, self._reread, self.client, self.deck)

    def _graded(self, outcome):
        if self._settles(outcome):
            landed, shown = outcome[1]
            self.answered += int(bool(landed))
            self._present(shown)

    def _taken_back(self, outcome):
        if self._settles(outcome):
            self.answered = max(0, self.answered - 1)
            self._present(outcome[1])

    def _reread(self, outcome):
        if self._settles(outcome):
            self._present(outcome[1])

    def _crashed(self, failure):
        """Show a step that failed in a way nothing expected."""
        error, _formatted = failure
        self.busy = False
        self.card, self.side = None, None
        self._show_message(f"COULD NOT REVIEW\n{error}")

    def _present(self, shown):
        """Show the question of the card Anki holds, or that the deck owes nothing."""
        self.card = shown
        if shown is None:
            self.side = None
            back = "\nSPACE OR 0 FOR THE DECKS" if self.from_list else ""
            self._show_message(f"NOTHING DUE IN {self.deck}{back}", colour='base1')
            return
        self.side = QUESTION
        self._render(shown.question)

    def _render(self, side, answer=False):
        self._clear_message()
        self.view.setHtml(card_page(side, self.card.ordinal, answer),
                          QUrl.fromLocalFile(self._media.rstrip("/") + "/"))

    def _mark(self, index):
        """Mark the deck at index, within the list, and keep it in view."""
        if not self._rows:
            return
        self._paint_row(False)
        self.marked = max(0, min(len(self._rows) - 1, int(index)))
        self._paint_row(True)
        self.chooser.scrollToItem(self._rows[self.marked],
                                  QAbstractItemView.ScrollHint.PositionAtCenter)

    def _paint_row(self, marked):
        """Paint the marked row as marked, or as what it owes once it is not."""
        if not 0 <= self.marked < len(self._rows):
            return
        row = self._rows[self.marked]
        row.setForeground(0, _name_colour(self.listing[self.marked], marked))
        for column in range(len(DECK_COLUMNS)):
            row.setData(column, Qt.ItemDataRole.BackgroundRole,
                        QColor(PALETTE['base02']) if marked else None)

    def _show_message(self, text, colour='red'):
        self._clear_message()
        for shown in (self.view, self.chooser):
            if shown is not None:
                shown.hide()
        self._message = _failure_label(self, text, colour)
        self.layout().addWidget(self._message)

    def _clear_message(self):
        if self._message is not None:
            self._message.deleteLater()
            self._message = None
        if self.view is not None:
            self.view.setVisible(not self.choosing)
            self.chooser.setVisible(self.choosing)


def build_pane(activity, start_at=0, parent=None) -> QWidget:
    """Build the pane for what this activity is."""
    if activity.kind == DOCUMENT:
        return DocumentPane(activity.path, start_at, parent)
    if activity.kind == DECK:
        return DeckPane(activity.path, start_at, parent)
    return VideoPane(activity.path, start_at, parent)


class MediaSurface(QWidget):
    """The break's screen while it is showing something."""

    pane_changed = pyqtSignal()

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
        """Return the pane the keys drive, or None where nothing is showing."""
        if self.activity is None:
            return None
        return self.panes.get(self.activity.kind)

    def open(self, activity, start_at=0, key_hints=()):
        """Show activity, from where it was left."""
        pane = self.panes.get(activity.kind)
        if pane is None:
            pane = self._build_pane(activity, start_at, parent=self.stack)
            changed = getattr(pane, "changed", None)
            if changed is not None:
                changed.connect(self.pane_changed)
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
        """Stop what is showing and return the place it reached."""
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
        """Release every pane before the wall this is a page of is dropped."""
        for pane in self.panes.values():
            closing = getattr(pane, "shutdown", None)
            if callable(closing):
                closing()

    def resizeEvent(self, event):
        """Keep the card and the band where they belong."""
        super().resizeEvent(event)
        self._place_the_overlays()

    def _place_the_overlays(self):
        """Place the card in its corner, in front."""
        self.keys.place_top_right(self.rect())
        self.keys.raise_()

    def title(self) -> str:
        """Return the name of what is showing, as narrowed by the pane."""
        if self.activity is None:
            return ""
        narrowed = getattr(self.pane, "title", None)
        return (narrowed() if callable(narrowed) else "") or self.activity.name

    def place(self):
        """Return where what is showing has reached, and which readout says it."""
        pane = self.pane
        if pane is None:
            return None
        return Place(pane.position(), pane.duration()), readout_of(self.activity.kind)

    def show_progress(self, place=None):
        """Put the pane position on the row under it, where there is one."""
        if self.progress is None:
            return
        place = place or self.place()
        if place is None:
            return
        self.progress.show_place(*place)

    def update_display(self):
        """Update the readouts every break surface carries."""
        if self.strip is None:
            return
        fraction, holding = self._hold
        if holding:
            left = max(0, int(round(self.timer_ref.release_hold_secs * (1.0 - fraction))))
            self.strip.setText(f"LEAVING IN {left}s")
            return
        if self.timer_ref.waiting_for_work_start:
            self.strip.setText(
                f"BREAK OVER +{as_elapsed(self.timer_ref.over_by_ms())}"
                f" · {self.timer_ref.wall_hint()}")
            return
        mins, secs = divmod(int(self.timer_ref.time_left_ms // 1000), 60)
        self.strip.setText(
            f"REST {mins:02d}:{secs:02d} · {self.timer_ref.wall_hint()}")

    def show_hold(self, fraction, visible):
        """Show how much of the exit hold has been paid."""
        self._hold = (fraction, visible)
        self.update_display()
