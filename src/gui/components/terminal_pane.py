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
SESSIONS = "SESSIONS"
CLOSING = "DEL AGAIN TO END IT"
LISTING_FAILED = (OSError, ValueError, subprocess.SubprocessError)

THEME = {
    "background": PALETTE['base3'], "foreground": PALETTE['base00'],
    "cursor": PALETTE['base01'], "cursorAccent": PALETTE['base3'],
    "selectionBackground": PALETTE['base2'],
    "black": PALETTE['base02'], "brightBlack": PALETTE['base03'],
    "red": PALETTE['red'], "brightRed": PALETTE['orange'],
    "green": PALETTE['green'], "brightGreen": PALETTE['base01'],
    "yellow": PALETTE['yellow'], "brightYellow": PALETTE['base00'],
    "blue": PALETTE['blue'], "brightBlue": PALETTE['base0'],
    "magenta": PALETTE['magenta'], "brightMagenta": PALETTE['violet'],
    "cyan": PALETTE['cyan'], "brightCyan": PALETTE['base1'],
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
    """What the page's terminal calls: its first size, what is typed, and each resize."""

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
    """A new chat per project and every session in one list, and one session running."""

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
        self._resuming = None
        self._closing = None
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
        """List a new chat for each project command offers, then every session."""
        self.command = str(command)
        self.project = None
        self._list()

    def toggle(self):
        """Open the marked new chat or session."""
        if not self.choosing or self.busy or not self.listing:
            return
        project, session = self.listing[self.marked]
        self.project = project.path
        self._attach(session.name if session is not None else "")

    def step(self, direction):
        """Open the marked row going right, or drop a half-typed hint going left."""
        if int(direction) > 0:
            self.toggle()
        else:
            self.undo()

    def undo(self):
        """Drop a half-typed hint."""
        self.forget_hint()

    def nudge(self, direction):
        """Mark the row above or below."""
        if self.choosing and not self.busy:
            self._mark(self.marked - int(direction))

    def turn(self, direction):
        """Mark the row a page further down or up."""
        if self.choosing and not self.busy:
            self._mark(self.marked + int(direction) * PAGE_ROWS)

    def back(self) -> bool:
        """Leave a session for the list, reporting whether it did."""
        if self.chooser is None or self.choosing:
            return False
        self._list()
        return True

    def close_marked(self) -> bool:
        """Ask once, then end the marked session, reporting whether a session is marked."""
        if not self.choosing or self.busy or not self.listing:
            return False
        project, session = self.listing[self.marked]
        if session is None:
            return False
        if self._closing is None:
            row = self._rows[self.marked]
            self._closing = (self.marked, row.text(1))
            row.setText(1, CLOSING)
            row.setForeground(1, QColor(PALETTE['red']))
            return True
        self._closing = None
        self.busy = True
        run_in_background(QThreadPool.globalInstance(), _end, self._ended_one,
                          self._ended_one, self.command, project.path, session.name)
        return True

    def _mark(self, index):
        """Mark the row at index, taking back a pending request to end a session."""
        if self._closing is not None:
            at, note = self._closing
            self._closing = None
            if at < len(self._rows):
                self._rows[at].setText(1, note)
                self._rows[at].setForeground(1, QColor(PALETTE['base1']))
        MarkedList._mark(self, index)

    def _ended_one(self, outcome):
        """List again once the program has ended a session or failed to."""
        if isinstance(outcome, tuple) and outcome:
            log.warning("Could not end a session of %r: %s", self.command, outcome[0])
        self._session = ""
        self._list()

    def attached(self):
        """Return (project, session) of the session shown, or None while the list shows."""
        if self.choosing or self.project is None:
            return None
        return self.project, self._session

    def reattach(self, project, session=""):
        """Attach session of project once listed, the project's latest where it is unnamed."""
        self._resuming = (str(project), str(session or ""))
        if not self.busy and self.projects:
            self._resume()

    def escape(self):
        """Send one Escape to the session shown."""
        self._type(ESCAPE)

    def title(self) -> str:
        """Return the project of the session shown, or nothing while the list shows."""
        project = self._project()
        return project.label if project is not None and not self.choosing else ""

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
        self._render((self.project, self._session))
        self._resume()

    def _resume(self):
        """Attach the session reattach() asked for, where its project is still listed."""
        if self._resuming is None:
            return
        path, session = self._resuming
        self._resuming = None
        project = next((each for each in self.projects if each.path == path), None)
        if project is None:
            return
        if not session and project.sessions:
            session = max(project.sessions, key=lambda each: each.active_at).name
        if not any(each.name == session for each in project.sessions):
            return
        self.project = path
        self._attach(session)

    def _crashed(self, failure):
        self.busy = False
        self._show_message(f"COULD NOT LIST THE SESSIONS\n{failure[0]}")

    def _render(self, mark=None):
        """List a new chat per project, then every session, latest first, marking mark."""
        now = int(time.time())
        chats = [(project, None) for project in self.projects]
        held = sorted(((project, session) for project in self.projects
                       for session in project.sessions),
                      key=lambda pair: -pair[1].active_at)
        self.listing = chats + held
        rows = [_row(f"{NEW_CHAT} · {project.label}", "", 'blue') for project, _ in chats]
        rows += [_row(session.title or session.name,
                      f"{project.label} · {sessions.described(session, now)}", 'base00')
                 for project, session in held]
        marks = [(project.path, session.name if session is not None else "")
                 for project, session in self.listing]
        self._closing = None
        self.chooser.clear()
        self.chooser.headerItem().setText(0, SESSIONS)
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


def _end(command, path, session):
    sessions.close(command, path, session)


def _attempt(generation, command) -> tuple:
    """List the sessions: (the listing that asked, the projects, what went wrong)."""
    try:
        return generation, sessions.listing(command), None
    except LISTING_FAILED as error:
        return generation, [], error


def _row(name, note, colour, note_colour='base1') -> QTreeWidgetItem:
    """Build one row: its name, and its note to the right."""
    row = QTreeWidgetItem([name, note])
    ink(row, QColor(PALETTE[colour]))
    row.setForeground(1, QColor(PALETTE[note_colour]))
    row.setTextAlignment(1, RIGHT)
    return row


def _environment() -> dict:
    """Return this process's environment for a light xterm-like terminal, outside any tmux."""
    kept = {name: value for name, value in os.environ.items()
            if name not in ("TMUX", "TMUX_PANE")}
    return kept | {"TERM": "xterm-256color", "COLORTERM": "truecolor", "COLORFGBG": "11;15"}
