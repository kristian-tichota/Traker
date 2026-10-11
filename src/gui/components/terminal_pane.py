import codecs
import fcntl
import json
import logging
import os
import shlex
import struct
import subprocess
import termios
import time
from functools import partial

from PyQt6.QtCore import QObject, QSocketNotifier, QThreadPool, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWidgets import QTreeWidgetItem

from src.config import PALETTE
from src.desktop import sessions
from src.gui.components.break_pane import RIGHT, MarkedList, WebPane, ink, named_list
from src.gui.icons import ASSETS_DIR
from src.gui.workers import run_in_background

log = logging.getLogger(__name__)

XTERM_DIR = os.path.join(ASSETS_DIR, "xterm")
FONT_PX = 18
READ_BYTES = 65_536
QUIT_WAIT_SECS = 1.0
PAGE_ROWS = 10
ESCAPE = "\x1b"
NEW_CHAT = "NEW CHAT"
PROJECTS = "PROJECTS"
LISTING_FAILED = (OSError, ValueError, subprocess.SubprocessError)

THEME = {
    "background": PALETTE['base03'], "foreground": PALETTE['base0'],
    "cursor": PALETTE['base1'], "selectionBackground": PALETTE['base02'],
    "black": PALETTE['base02'], "brightBlack": PALETTE['base01'],
    "red": PALETTE['red'], "brightRed": PALETTE['orange'],
    "green": PALETTE['green'], "brightGreen": PALETTE['green'],
    "yellow": PALETTE['yellow'], "brightYellow": PALETTE['yellow'],
    "blue": PALETTE['blue'], "brightBlue": PALETTE['blue'],
    "magenta": PALETTE['magenta'], "brightMagenta": PALETTE['violet'],
    "cyan": PALETTE['cyan'], "brightCyan": PALETTE['cyan'],
    "white": PALETTE['base2'], "brightWhite": PALETTE['base3'],
}

OPTIONS = {"fontFamily": "'Fira Code', monospace", "fontSize": FONT_PX, "theme": THEME,
           "cursorBlink": False, "scrollback": 5000}

TERMINAL_PAGE = ("""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="xterm.css">
<style>html, body { margin: 0; height: 100%; overflow: hidden; background: __GROUND__; }
#terminal { height: 100%; padding: 12px; box-sizing: border-box; }</style>
<script src="xterm.js"></script><script src="addon-fit.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head><body><div id="terminal"></div><script>
new QWebChannel(qt.webChannelTransport, async channel => {
  const bridge = channel.objects.bridge;
  const term = new Terminal(__OPTIONS__);
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  await document.fonts.load('__FONT_PX__px "Fira Code"').catch(() => null);
  term.open(document.getElementById('terminal'));
  fit.fit();
  bridge.output.connect(data => term.write(data));
  term.onData(data => bridge.send(data));
  term.onResize(size => bridge.resize(size.cols, size.rows));
  new ResizeObserver(() => fit.fit()).observe(document.body);
  term.focus();
  bridge.ready(term.cols, term.rows);
});
</script></body></html>"""
                 .replace("__GROUND__", THEME["background"])
                 .replace("__OPTIONS__", json.dumps(OPTIONS))
                 .replace("__FONT_PX__", str(FONT_PX)))


class Pty(QObject):
    """One program in a pseudo-terminal of its own, read as the event loop allows."""

    output = pyqtSignal(str)
    ended = pyqtSignal(int)

    def __init__(self, argv, cols, rows, parent=None):
        super().__init__(parent)
        self.master, follower = os.openpty()
        try:
            self.resize(cols, rows)
            self.process = subprocess.Popen(
                ["setsid", "--ctty", *argv], stdin=follower, stdout=follower,
                stderr=follower, env=_environment(), close_fds=True)
        except OSError:
            os.close(self.master)
            raise
        finally:
            os.close(follower)
        self._closed = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._notifier = QSocketNotifier(self.master, QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._read)

    def write(self, text):
        """Type text into the program."""
        data = str(text).encode("utf-8")
        try:
            while data and not self._closed:
                data = data[os.write(self.master, data):]
        except OSError as error:
            log.warning("Could not type into a terminal: %s", error)

    def resize(self, cols, rows):
        """Give the program a terminal of cols by rows."""
        if cols > 0 and rows > 0:
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def close(self):
        """End the program and release the terminal, once."""
        if self._closed:
            return
        self._closed = True
        self._notifier.setEnabled(False)
        self._reap()
        os.close(self.master)
        self.deleteLater()

    def _read(self):
        try:
            data = os.read(self.master, READ_BYTES)
        except OSError:
            data = b""
        if data:
            self.output.emit(self._decoder.decode(data))
            return
        self._notifier.setEnabled(False)
        self.ended.emit(self._reap())

    def _reap(self) -> int:
        """Return the program's exit status, ending it where it still runs."""
        if self.process.poll() is None:
            self.process.terminate()
        try:
            return self.process.wait(QUIT_WAIT_SECS)
        except subprocess.TimeoutExpired:
            self.process.kill()
            return self.process.wait()


class Bridge(QObject):
    """What the page's terminal calls: its size once laid out, what is typed, and each resize."""

    output = pyqtSignal(str)
    laid_out = pyqtSignal(int, int)
    typed = pyqtSignal(str)
    resized = pyqtSignal(int, int)

    @pyqtSlot(int, int)
    def ready(self, cols, rows):
        self.laid_out.emit(cols, rows)

    @pyqtSlot(str)
    def send(self, data):
        self.typed.emit(data)

    @pyqtSlot(int, int)
    def resize(self, cols, rows):
        self.resized.emit(cols, rows)


class TerminalPane(WebPane, MarkedList):
    """The projects a session program lists, a project's sessions, and one session running."""

    changed = pyqtSignal()

    def __init__(self, command=None, start_at=0, parent=None, spawn=Pty):
        super().__init__("COULD NOT OPEN A TERMINAL", parent, quiet=False)
        self.command = ""
        self.projects = []
        self.project = None
        self.listing = []
        self.choosing = True
        self.busy = False
        self.pty = None
        self.chooser = None
        self._spawn = spawn
        self._argv = None
        self._session = ""
        self._generation = 0
        if self.view is None:
            return
        self.view.page().setBackgroundColor(QColor(THEME["background"]))
        self.bridge = Bridge(self)
        self.bridge.laid_out.connect(self._start)
        self.bridge.typed.connect(self._type)
        self.bridge.resized.connect(self._resize)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.chooser = named_list(self)
        self.chooser.hide()
        self.layout().addWidget(self.chooser)
        if command:
            self.open(command, start_at)

    def open(self, command, start_at=0):
        """List the projects command offers, with the sessions each has."""
        self.command = str(command)
        self.project = None
        self._list()

    def toggle(self):
        """Open the marked project, session or new chat."""
        if not self.choosing or self.busy or not self.listing:
            return
        chosen = self.listing[self.marked]
        if isinstance(chosen, sessions.Project):
            self.project = chosen.path
            if chosen.sessions:
                self._render()
                self.changed.emit()
            else:
                self._attach()
        else:
            self._attach(chosen.name if chosen is not None else "")

    def step(self, direction):
        """Open the marked row going right, or go back to the projects going left."""
        if int(direction) > 0:
            self.toggle()
        else:
            self.undo()

    def undo(self):
        """Drop a half-typed hint, or leave a project's sessions for the projects."""
        if not self.forget_hint() and self.choosing and self.project is not None:
            self._to_the_projects()

    def nudge(self, direction):
        """Mark the row above or below."""
        if self.choosing and not self.busy:
            self._mark(self.marked - int(direction))

    def turn(self, direction):
        """Mark the row a page further down or up."""
        if self.choosing and not self.busy:
            self._mark(self.marked + int(direction) * PAGE_ROWS)

    def back(self) -> bool:
        """Leave a session for its project, or a project for the projects, reporting whether it did."""
        if self.chooser is None:
            return False
        if not self.choosing:
            self._list()
            return True
        if self.project is not None:
            self._to_the_projects()
            return True
        return False

    def escape(self):
        """Send one Escape to the session shown."""
        self._type(ESCAPE)

    def title(self) -> str:
        """Return the project chosen, or nothing while the projects are listed."""
        project = self._project()
        return project.label if project is not None else ""

    def stop(self):
        """Detach from the session shown, which goes on running, and forget the listing."""
        self._let_go()
        self._generation += 1
        self.choosing, self.busy = True, False

    def _list(self):
        """Let go of the session shown and read the projects and their sessions again."""
        self._let_go()
        self.choosing, self.busy = True, True
        self._rows, self._labels, self.typed, self.listing = [], [], "", []
        if self.chooser is None:
            return
        self.chooser.clear()
        self._clear_message()
        self._generation += 1
        run_in_background(QThreadPool.globalInstance(), _attempt, self._listed,
                          self._crashed, self._generation, self.command)
        self.changed.emit()

    def _listed(self, outcome):
        generation, projects, error = outcome
        if generation != self._generation:
            return
        self.busy = False
        if error is not None:
            log.warning("Could not list the sessions of %r: %s", self.command, error)
            self._show_message(f"COULD NOT LIST THE SESSIONS\n{error}")
            return
        self.projects = projects
        self._render(self._session)

    def _crashed(self, failure):
        self.busy = False
        self._show_message(f"COULD NOT LIST THE SESSIONS\n{failure[0]}")

    def _render(self, mark=""):
        """List the projects, or the chosen project's sessions under a new chat."""
        project = self._project()
        self.project = project.path if project is not None else None
        now = int(time.time())
        if project is None:
            title, self.listing = PROJECTS, list(self.projects)
            rows = [_row(each.label, _how_many(each), 'base00' if each.sessions else 'base1',
                         'green') for each in self.listing]
            marks = [each.path for each in self.listing]
        else:
            title, self.listing = project.label, [None, *project.sessions]
            rows = [_row(NEW_CHAT, "", 'blue')]
            rows += [_row(each.title or each.name, sessions.described(each, now), 'base00')
                     for each in project.sessions]
            marks = ["", *(each.name for each in project.sessions)]
        self.chooser.clear()
        self.chooser.headerItem().setText(0, title)
        for row in rows:
            self.chooser.addTopLevelItem(row)
        self._rows = rows
        self._label()
        self.marked = 0
        self._mark(marks.index(mark) if mark in marks else 0)
        if self.listing:
            self._clear_message()
        else:
            self._show_message("NO PROJECTS LISTED", 'base01')

    def _to_the_projects(self):
        left, self.project = self.project, None
        self._render(left)
        self.changed.emit()

    def _project(self):
        return next((each for each in self.projects if each.path == self.project), None)

    def _attach(self, session=""):
        """Run session of the chosen project in the terminal, or a new chat without one."""
        self._let_go()
        self.choosing = False
        self._session = session
        self._argv = sessions.opening(self.command, self.project, session)
        self._clear_message()
        self.view.setHtml(TERMINAL_PAGE, QUrl.fromLocalFile(XTERM_DIR + os.sep))
        self.view.setFocus()
        self.changed.emit()

    def _start(self, cols, rows):
        """Start the program once the page has a terminal of cols by rows."""
        if self._argv is None or self.pty is not None or self.choosing:
            return
        try:
            self.pty = self._spawn(self._argv, cols, rows, self)
        except OSError as error:
            log.warning("Could not run %s: %s", shlex.join(self._argv), error)
            self._show_message(f"COULD NOT OPEN A TERMINAL\n{error}")
            return
        self.pty.output.connect(self.bridge.output)
        self.pty.ended.connect(partial(self._ended, self.pty))

    def _ended(self, pty, status):
        """List again once a session detaches, or leave a failure's last words on screen."""
        if pty is not self.pty:
            return
        if status == 0:
            self._list()
            return
        log.warning("%s ended with %d.", shlex.join(self._argv or ()), status)
        self.pty = None
        pty.close()

    def _type(self, data):
        if self.pty is not None:
            self.pty.write(data)

    def _resize(self, cols, rows):
        if self.pty is not None:
            self.pty.resize(cols, rows)

    def _let_go(self):
        """Detach from the session shown and blank the terminal."""
        self._argv = None
        if self.pty is not None:
            pty, self.pty = self.pty, None
            pty.close()
        if self.view is not None:
            self.view.setHtml("")

    def _shown(self):
        return self.chooser if self.choosing else self.view


def _attempt(generation, command) -> tuple:
    """List the sessions: (the listing that asked, the projects, what went wrong)."""
    try:
        return generation, sessions.listing(command), None
    except LISTING_FAILED as error:
        return generation, [], error


def _how_many(project) -> str:
    count = len(project.sessions)
    return f"{count} SESSION{'' if count == 1 else 'S'}" if count else ""


def _row(name, note, colour, note_colour='base1') -> QTreeWidgetItem:
    """Build one row: its name, and its note to the right."""
    row = QTreeWidgetItem([name, note])
    ink(row, QColor(PALETTE[colour]))
    row.setForeground(1, QColor(PALETTE[note_colour]))
    row.setTextAlignment(1, RIGHT)
    return row


def _environment() -> dict:
    """Return this process's environment for a terminal of xterm's kind, outside any tmux."""
    kept = {name: value for name, value in os.environ.items()
            if name not in ("TMUX", "TMUX_PANE")}
    return kept | {"TERM": "xterm-256color", "COLORTERM": "truecolor"}
