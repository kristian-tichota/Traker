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
from src.desktop import anki, rest_positions, rest_queue
from src.desktop.activities import (ANY_DECK, BOOK, DECK, DOCUMENT, PAGE, SHELF, contents,
                                    kind_of, library_for, readout_of)
from src.domain.media import UNKNOWN, Place, as_elapsed, finished, how_far
from src.gui.components.book_pane import BookPane
from src.gui.components.break_pane import BreakPane, WebPane
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
:root {{ color-scheme: light; }}
html, body.card {{ background-color: {PALETTE['base3']} !important; }}
body.card {{ margin: 20px; overflow-wrap: break-word; color: {PALETTE['base00']}; }}
img {{ max-width: 100%; max-height: 95vh; }}
hr {{ background-color: {PALETTE['base1']}; margin: 1em 0; border: none; height: 1px; }}
"""

TO_THE_ANSWER = ("<script>addEventListener('load', () => "
                 "document.getElementById('answer')?.scrollIntoView());</script>")

GOOD_SAID, AGAIN_SAID, UNDONE = "good", "again", "undone"
VERDICTS = {GOOD_SAID: ("GOOD", 'green'), AGAIN_SAID: ("AGAIN", 'red'),
            UNDONE: ("TAKEN BACK", 'yellow')}

VERDICT_CSS = f"""
#traker-verdict {{ position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%);
  z-index: 2147483647; pointer-events: none; padding: 6px 18px; border-radius: 4px;
  font: 600 18px 'Fira Code', monospace; letter-spacing: 3px; color: {PALETTE['base03']};
  animation: traker-verdict 2.5s ease-in forwards; }}
@keyframes traker-verdict {{ 0%, 60% {{ opacity: 1; }} 100% {{ opacity: 0; }} }}
"""

DECK_COLUMNS = ("DECK", "NEW", "LEARN", "DUE", "")
COUNT_COLOURS = ('blue', 'red', 'green')
FOLDER_COLUMNS = ("", "")
LIST_INDENT_PX = 28
LIST_FONT_PX = 20
PAGE_ROWS = 10
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
UNMARKED = Qt.ItemDataRole.UserRole


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
        """Return one player confined to this widget, or None with player_error set."""
        try:
            import mpv
        except (ImportError, OSError) as error:
            self.player_error = f"libmpv would not load: {error}"
            log.warning("No video in a break: %s", self.player_error)
            return None

        try:
            return mpv.MPV(vo="libmpv", hwdec="auto-safe", keep_open="yes",
                           input_default_bindings=False, input_vo_keyboard=False,
                           osc=False, osd_level=0, log_handler=_say_what_mpv_said,
                           loglevel="warn")
        except (OSError, RuntimeError, ValueError, SystemError,
                AttributeError, mpv.ArgumentError) as error:
            self.player_error = f"mpv would not start: {error}"
            log.warning("No video in a break: %s", self.player_error)
            return None

    def initializeGL(self):
        """Hand mpv this widget's framebuffer, once it has one."""
        if self.player is None:
            return
        import mpv

        self._proc_address = mpv.MpvGlGetProcAddressFn(_gl_proc_address)
        self._context = mpv.MpvRenderContext(
            self.player, "opengl",
            opengl_init_params={"get_proc_address": self._proc_address})
        self._context.update_cb = self.frame_ready.emit
        self._load_what_is_waiting()

    def play(self, path, start_seconds=0.0):
        """Play path from start_seconds, once there is a surface for it."""
        self._pending = (path, max(0.0, float(start_seconds)))
        self._load_what_is_waiting()

    def _load_what_is_waiting(self):
        """Hand mpv the file, once both it and the context exist."""
        if self._context is None or self._pending is None:
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


class VideoPane(BreakPane):
    """One file, playing."""

    def __init__(self, path=None, start_at=0, parent=None):
        super().__init__(parent)
        self._start_ms = 0
        self.screen_widget = MpvScreen(self)
        self.screen_widget.playback_failed.connect(self._show_failure)
        self.layout().addWidget(self.screen_widget)
        self.player = self.screen_widget.player
        if self.player is None:
            self._show_failure(self.screen_widget.player_error)
        if path:
            self.open(path, start_at)

    def open(self, path, start_at=0):
        """Play path from where it was left."""
        self._start_ms = max(0, int(start_at or 0))
        if self.player is None:
            return
        self._clear_message()
        self.screen_widget.play(os.path.abspath(path), self._start_ms / 1000.0)

    def _shown(self):
        return self.screen_widget

    def _show_failure(self, message):
        """Show the failure on screen as well as in the log."""
        log.warning("Could not play: %s", message)
        self._show_message(f"COULD NOT PLAY\n{message}")

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
        """Return milliseconds in, or where it was opened at until mpv has read it."""
        seconds = getattr(self.player, "time_pos", None)
        return self._start_ms if seconds is None else max(0, int(seconds * 1000))

    def duration(self) -> int:
        """Return the file length, or zero until mpv has read it."""
        return max(0, int((getattr(self.player, "duration", None) or 0) * 1000))

    def stop(self):
        if self.player is not None:
            self.player.command("stop")

    def shutdown(self):
        """Release libmpv's threads, once, at the end of the break."""
        self.screen_widget.shutdown()
        self.player = None


class DocumentPane(BreakPane):
    """One PDF, a whole page at a time."""

    def __init__(self, path=None, start_at=0, parent=None):
        super().__init__(parent)
        from PyQt6.QtPdf import QPdfDocument
        from PyQt6.QtPdfWidgets import QPdfView

        self._resume_at = self._asked = 0
        self.document = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        around = self.view.palette()
        around.setColor(QPalette.ColorRole.Dark, QColor(PALETTE['base03']))
        self.view.setPalette(around)
        self.layout().addWidget(self.view)

        self.pages = self.view.pageNavigator()
        self.pages.currentPageChanged.connect(self._page_changed)
        self.view.verticalScrollBar().rangeChanged.connect(self._hold_the_page)

        if path:
            self.open(path, start_at)

    def open(self, path, start_at=0):
        """Read path from the page it was left on."""
        from PyQt6.QtPdf import QPdfDocument

        self._resume_at, self._asked = 0, max(0, int(start_at or 0))
        error = self.document.load(os.path.abspath(path))
        if error != QPdfDocument.Error.None_:
            log.warning("Could not read %s: %s", path, error)
            self._show_message(f"COULD NOT READ\n{error.name}")
            return
        self._clear_message()
        self._resume_at = min(self._asked, max(0, self.document.pageCount() - 1))
        self._turn_to(self._resume_at)

    def _page_changed(self, page):
        """Put the page back where the turn did not come from the member."""
        if self._resume_at and page != self._resume_at:
            self._turn_to(self._resume_at)

    def _hold_the_page(self):
        """Turn to the page asked for, once layout lets a jump land."""
        if self._resume_at:
            self._turn_to(self._resume_at)

    def _turn_to(self, page):
        if self.pages.currentPage() == page and self.document.pageCount() > 1:
            self.pages.jump(0 if page else 1, QPointF())
        self.pages.jump(page, QPointF())

    def showEvent(self, event):
        """Scroll to the requested page, which needs the view on a screen."""
        super().showEvent(event)
        QTimer.singleShot(0, self._hold_the_page)

    def toggle(self):
        """Turn the page, there being nothing to pause."""
        self.step(1)

    def step(self, direction):
        """Turn a page forward or back, clamped inside the document."""
        self._resume_at = 0
        last = max(0, self.document.pageCount() - 1)
        wanted = max(0, min(last, self.pages.currentPage() + int(direction)))
        self.pages.jump(wanted, QPointF())

    def nudge(self, direction):
        """Scroll inside the page."""
        self._resume_at = 0
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.value() - int(direction) * SCROLL_STEP_PX)

    def position(self) -> int:
        """Return the page shown, or the page asked for where there is no document."""
        return self.pages.currentPage() if self.document.pageCount() else self._asked

    def duration(self) -> int:
        """Return how many pages there are."""
        return self.document.pageCount()

    def stop(self):
        """Release the file."""
        self._resume_at = 0
        self.document.close()


def card_page(side, ordinal, answer=False, verdict=None) -> str:
    """Wrap a card's side as Anki's reviewer does by day, with any verdict on it."""
    body = CARD_MARKERS.sub("", side)
    said = ""
    if verdict in VERDICTS:
        word, colour = VERDICTS[verdict]
        said = (f'<div id="traker-verdict" style="background: {PALETTE[colour]};">'
                f"{word}</div>")
    return ('<!doctype html><html><head><meta charset="utf-8">'
            f"<style>{CARD_CSS}{VERDICT_CSS if said else ''}</style></head>"
            f'<body class="card card{int(ordinal) + 1} isLin">'
            f"{said}{body}{TO_THE_ANSWER if answer else ''}</body></html>")


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


def _chooser(parent, columns) -> QTreeWidget:
    """Build a list driven by keys alone, in Solarized light."""
    tree = QTreeWidget(parent)
    tree.setColumnCount(len(columns))
    tree.setHeaderLabels(columns)
    tree.setRootIsDecorated(False)
    tree.setItemsExpandable(False)
    tree.setIndentation(LIST_INDENT_PX)
    tree.setUniformRowHeights(True)
    tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tree.setFrameShape(QFrame.Shape.NoFrame)
    tree.setStyleSheet(
        f"QTreeWidget {{ background-color: {PALETTE['base3']}; border: none;"
        f" font-family: 'Fira Code'; font-size: {LIST_FONT_PX}px; padding: 20px; }}"
        f" QTreeWidget::item {{ padding: 4px 16px; }}"
        f" QHeaderView::section {{ background-color: {PALETTE['base3']};"
        f" color: {PALETTE['base1']}; border: none; font-family: 'Fira Code';"
        f" font-size: 11px; letter-spacing: 2px; padding: 4px 16px; }}")
    return tree


def _deck_list(parent) -> QTreeWidget:
    """Build the list a deck is chosen from, in the columns of Anki's own."""
    tree = _chooser(parent, DECK_COLUMNS)
    header = tree.header()
    header.setStretchLastSection(True)
    for column in range(len(DECK_COLUMNS) - 1):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    for column in range(1, len(COUNT_COLOURS) + 1):
        tree.headerItem().setTextAlignment(column, RIGHT)
    return tree


def _folder_list(parent) -> QTreeWidget:
    """Build the list a file is chosen from: each name, and how far into it."""
    tree = _chooser(parent, FOLDER_COLUMNS)
    header = tree.header()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    tree.headerItem().setTextAlignment(1, RIGHT)
    return tree


def _name_colour(deck) -> QColor:
    """Return the colour of a deck's name: faint when it owes nothing."""
    return QColor(PALETTE['base00' if deck.owed else 'base1'])


def _ink(row, colour):
    """Colour a row's name, kept for when the row is no longer marked."""
    row.setForeground(0, colour)
    row.setData(0, UNMARKED, colour)


def _deck_rows(tree, decks) -> list:
    """Put each deck under its parent with what it owes, and return the rows in list order."""
    rows, placed = [], {}
    for deck in decks:
        parent = placed.get(deck.name.rpartition(anki.SEPARATOR)[0])
        counts = (deck.new, deck.learning, deck.review)
        row = QTreeWidgetItem([deck.name if parent is None else deck.leaf,
                               *map(str, counts)])
        _ink(row, _name_colour(deck))
        for column, (count, colour) in enumerate(zip(counts, COUNT_COLOURS), start=1):
            row.setTextAlignment(column, RIGHT)
            row.setForeground(column, QColor(PALETTE[colour if count else 'base1']))
        if parent is None:
            tree.addTopLevelItem(row)
        else:
            parent.addChild(row)
        placed[deck.name] = row
        rows.append(row)
    tree.expandAll()
    return rows


class _MarkedList:
    """A pane choosing from the rows of its chooser, one marked at a time."""

    marked = 0
    _rows = ()

    def _mark(self, index):
        """Mark the row at index, within the list, and keep it in view."""
        if not self._rows:
            return
        self._paint_row(False)
        self.marked = max(0, min(len(self._rows) - 1, int(index)))
        self._paint_row(True)
        self.chooser.scrollToItem(self._rows[self.marked],
                                  QAbstractItemView.ScrollHint.PositionAtCenter)

    def _paint_row(self, marked):
        """Paint the marked row as marked, or as it reads once it is not."""
        if not 0 <= self.marked < len(self._rows):
            return
        row = self._rows[self.marked]
        row.setForeground(0, QColor(PALETTE['base02']) if marked else row.data(0, UNMARKED))
        for column in range(self.chooser.columnCount()):
            row.setData(column, Qt.ItemDataRole.BackgroundRole,
                        QColor(PALETTE['base2']) if marked else None)


class DeckPane(WebPane, _MarkedList):
    """One Anki deck, a card at a time, chosen and scheduled by Anki's reviewer."""

    changed = pyqtSignal()

    def __init__(self, deck=None, start_at=0, parent=None, client=None):
        super().__init__("COULD NOT REVIEW", parent)
        self.client = client or anki.AnkiConnect(UserProfile().get_metric(
            "strict_break", "anki_url", anki.DEFAULT_URL))
        self.deck = ""
        self.card = None
        self.side = None
        self.verdict = None
        self.answered = 0
        self.busy = False
        self.listing = []
        self.choosing = False
        self.from_list = False
        self._generation = 0
        self._media = ""
        self.chooser = None
        if self.view is None:
            return
        self.chooser = _deck_list(self)
        self.chooser.hide()
        self.layout().addWidget(self.chooser)
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
        if not self.choosing:
            self.step(1)
        elif not self.busy and self.listing:
            self._review(self.listing[self.marked].name)

    def step(self, direction):
        """Show the answer, then answer Good or Again; on the list, skip to an owing deck."""
        forward = int(direction) > 0
        if self.busy:
            return
        if self.choosing:
            self._mark(_next_owing(self.listing, self.marked, 1 if forward else -1))
        elif self.card is None:
            if self.from_list and forward:
                self._list()
        elif self.side == QUESTION:
            self._run(anki.reveal, self._revealed, self.client)
        else:
            self._run(anki.grade, self._answered_good if forward else self._answered_again,
                      self.client, self.deck, self.card.card_id,
                      anki.GOOD if forward else anki.AGAIN)

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
        elif self.view is not None:
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

    def _opening(self, choosing):
        """Let go of what was shown, to review a deck or to choose one."""
        self.stop()
        self.answered, self.choosing = 0, choosing

    def _review(self, deck):
        """Open Anki's reviewer on deck and show the card it chooses."""
        self._opening(choosing=False)
        self.deck = deck
        if self.view is not None:
            self._clear_message()
            self._run(anki.begin, self._began, self.client, self.deck)
        self.changed.emit()

    def _list(self):
        """Read every deck Anki has, with what each owes, to choose one from."""
        self._opening(choosing=True)
        self.listing, self._rows = [], []
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
            self._failed(_why_not(error, self.client.url, self.deck))
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

    def _answered_good(self, outcome):
        self._graded(outcome, GOOD_SAID)

    def _answered_again(self, outcome):
        self._graded(outcome, AGAIN_SAID)

    def _graded(self, outcome, verdict):
        if self._settles(outcome):
            landed, shown = outcome[1]
            self.answered += int(bool(landed))
            self._present(shown, verdict if landed else None)

    def _taken_back(self, outcome):
        if self._settles(outcome):
            self.answered = max(0, self.answered - 1)
            self._present(outcome[1], UNDONE)

    def _reread(self, outcome):
        if self._settles(outcome):
            self._present(outcome[1])

    def _crashed(self, failure):
        """Show a step that failed in a way nothing expected."""
        self.busy = False
        self._failed(failure[0])

    def _failed(self, why):
        """Let go of the card and say on screen why the step went wrong."""
        self.card, self.side, self.verdict = None, None, None
        self._show_message(f"COULD NOT REVIEW\n{why}")

    def _present(self, shown, verdict=None):
        """Show the question of the card Anki holds, or that the deck owes nothing."""
        self.card = shown
        if shown is None:
            self.side = None
            said = f"{VERDICTS[verdict][0]}\n" if verdict in VERDICTS else ""
            back = "\nSPACE OR 0 FOR THE DECKS" if self.from_list else ""
            self._show_message(f"{said}NOTHING DUE IN {self.deck}{back}", colour='base01')
            self.verdict = verdict
            return
        self.side = QUESTION
        self._render(shown.question, verdict=verdict)

    def _render(self, side, answer=False, verdict=None):
        self._clear_message()
        self.verdict = verdict
        self.view.setHtml(card_page(side, self.card.ordinal, answer, verdict),
                          QUrl.fromLocalFile(self._media.rstrip("/") + "/"))

    def _shown(self):
        return self.chooser if self.choosing else self.view


def _entry_colour(entry, ended) -> QColor:
    """Return an entry's colour: blue for a folder, faint once it has ended."""
    return QColor(PALETTE['blue' if entry.folder else 'base1' if ended else 'base00'])


def _how_far_into(entry, places) -> tuple:
    """Return how far into a file the member is, and whether that is its end."""
    place = None if entry.folder else places.get(entry.path)
    if place is None:
        return "", False
    unit = readout_of(kind_of(entry.path))
    said = how_far(place, unit)
    return ("" if said == UNKNOWN else said), finished(place, unit)


class PagePane(WebPane):
    """One web page, which every key reaches but the break's own."""

    def __init__(self, url=None, start_at=0, parent=None):
        super().__init__("COULD NOT OPEN", parent, quiet=False)
        self.url = ""
        self.loaded = False
        if self.view is None:
            return
        self.view.loadFinished.connect(self._finished)
        if url:
            self.open(url, start_at)

    def open(self, url, start_at=0):
        """Load url and take the keyboard, keeping a page already loaded as it was left."""
        if self.view is None:
            return
        if str(url) != self.url or not self.loaded:
            self.url = str(url)
            self._clear_message()
            self.view.load(QUrl(self.url))
        self.view.setFocus()

    def _finished(self, ok):
        self.loaded = bool(ok)
        if ok:
            self._clear_message()
            return
        log.warning("Could not open %s in a break.", self.url)
        self._show_message(f"COULD NOT OPEN\n{self.url}")


class LibraryPane(BreakPane, _MarkedList):
    """The media folder as a list, a folder at a time, to open a file from."""

    chosen = pyqtSignal(str)

    def __init__(self, path=None, start_at=0, parent=None, root=None, positions=None):
        super().__init__(parent)
        profile = UserProfile()
        self.root = os.path.abspath(root or library_for(profile))
        self.positions = positions or rest_positions.beside(rest_queue.path_for(profile))
        self.folder = self.root
        self.entries = []
        self.chooser = _folder_list(self)
        self.layout().addWidget(self.chooser)
        if path:
            self.open(path, start_at)

    def open(self, path, start_at=0):
        """List the folder holding path, path marked, or path itself where it is a folder."""
        path = os.path.abspath(str(path))
        if os.path.isdir(path):
            self._list(path)
        else:
            self._list(os.path.dirname(path), path)

    def toggle(self):
        """List the marked folder, or open the marked file."""
        if not self.entries:
            return
        entry = self.entries[self.marked]
        if entry.folder:
            self._list(entry.path)
        else:
            self.chosen.emit(entry.path)

    def step(self, direction):
        """Open the marked entry going right, or go up a folder going left."""
        if int(direction) > 0:
            self.toggle()
        else:
            self.undo()

    def undo(self):
        """List the folder above, the one left marked, no higher than the media folder."""
        if self.folder != self.root:
            self._list(os.path.dirname(self.folder), self.folder)

    def nudge(self, direction):
        """Mark the entry above or below."""
        self._mark(self.marked - int(direction))

    def turn(self, direction):
        """Mark the entry a page further down or up."""
        self._mark(self.marked + int(direction) * PAGE_ROWS)

    def title(self) -> str:
        """Return the folder listed, named from the media folder down."""
        return os.path.relpath(self.folder, os.path.dirname(self.root))

    def _list(self, folder, mark=None):
        """List folder, or the nearest folder above it inside the media folder, marking mark."""
        folder = os.path.abspath(folder)
        if os.path.commonpath([self.root, folder]) != self.root:
            folder = self.root
        while folder != self.root and not os.path.isdir(folder):
            folder = os.path.dirname(folder)
        self.folder = folder
        self.entries = contents(folder)
        places = rest_positions.read(self.positions)
        self.chooser.clear()
        self.chooser.headerItem().setText(0, self.title())
        self._rows = []
        for entry in self.entries:
            said, ended = _how_far_into(entry, places)
            row = QTreeWidgetItem([entry.name + ("/" if entry.folder else ""), said])
            _ink(row, _entry_colour(entry, ended))
            row.setForeground(1, QColor(PALETTE['base1']))
            row.setTextAlignment(1, RIGHT)
            self.chooser.addTopLevelItem(row)
            self._rows.append(row)
        paths = [entry.path for entry in self.entries]
        self.marked = 0
        self._mark(paths.index(mark) if mark in paths else 0)
        if self.entries:
            self._clear_message()
        else:
            self._show_message(f"NOTHING TO SHOW IN\n{self.title()}", 'base01')

    def _shown(self):
        return self.chooser


PANES = {DOCUMENT: DocumentPane, DECK: DeckPane, BOOK: BookPane, SHELF: LibraryPane,
         PAGE: PagePane}


def build_pane(activity, start_at=0, parent=None) -> QWidget:
    """Build the pane for what this activity is, a video where it is nothing else."""
    return PANES.get(activity.kind, VideoPane)(activity.path, start_at, parent)


class MediaSurface(QWidget):
    """The break's screen while it is showing something."""

    pane_changed = pyqtSignal()
    file_chosen = pyqtSignal(str)

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
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
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
            layout.addWidget(self.strip)

        self._dress(light=False)
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
            for name, relay in (("changed", self.pane_changed), ("chosen", self.file_chosen)):
                signal = getattr(pane, name, None)
                if signal is not None:
                    signal.connect(relay)
            self.panes[activity.kind] = pane
            self.stack.addWidget(pane)
        else:
            pane.open(activity.path, start_at)

        self.activity = activity
        self._dress(light=activity.kind in (BOOK, DECK, SHELF, PAGE))
        self.stack.setCurrentWidget(pane)
        self.set_keys(key_hints)
        if self.progress is not None:
            self.progress.setVisible(activity.kind not in (SHELF, PAGE))
            self.show_progress()
        return pane

    def set_keys(self, hints):
        """Name the keys that drive what is showing, under a page and over anything else."""
        self.keys.set_hints(hints)
        self.keys.setVisible(bool(hints) and self._only_screen and not self._under_a_page())
        self._place_the_overlays()
        self.update_display()

    def _under_a_page(self) -> bool:
        """Report whether a web page fills the surface, leaving the keys to the strip."""
        return self.activity is not None and self.activity.kind == PAGE

    def stop(self):
        """Stop what is showing and return the place it reached."""
        pane = self.pane
        self.activity = None
        self._dress(light=False)
        self.set_keys([])
        if self.progress is not None:
            self.progress.setVisible(False)
        self.stack.setCurrentIndex(0)
        if pane is None:
            return Place()
        where = Place(pane.position(), pane.duration())
        pane.stop()
        return where

    def _dress(self, light):
        """Paint the surface Solarized light around a book, a deck, a page or a list."""
        self.setStyleSheet(f"#mediaSurface {{ background-color: "
                           f"{PALETTE['base3' if light else 'base03']}; }}")
        self.keys.set_light(light)
        if self.strip is None:
            return
        self.progress.set_light(light)
        self.strip.setStyleSheet(
            f"color: {PALETTE['base01']}; background-color: "
            f"{PALETTE['base2' if light else 'base02']}; font-size: 10px;"
            f" font-family: 'Fira Code'; letter-spacing: 2px; padding: 3px;")

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
        way_on = (" · ".join(f"{key} {says.upper()}" for key, says in self.keys.hints)
                  if self._under_a_page() else self.timer_ref.wall_hint())
        if self.timer_ref.is_absent():
            self.strip.setText(
                f"AWAY +{as_elapsed(self.timer_ref.absent_for_ms())} · {way_on}")
            return
        if self.timer_ref.waiting_for_work_start:
            self.strip.setText(
                f"BREAK OVER +{as_elapsed(self.timer_ref.over_by_ms())} · {way_on}")
            return
        mins, secs = divmod(int(self.timer_ref.time_left_ms // 1000), 60)
        self.strip.setText(f"REST {mins:02d}:{secs:02d} · {way_on}")

    def show_hold(self, fraction, visible):
        """Show how much of the exit hold has been paid."""
        self._hold = (fraction, visible)
        self.update_display()
