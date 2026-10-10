import json
import logging
import os
import re
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtNetwork import QLocalSocket

log = logging.getLogger(__name__)

PROTOCOL = 10

SOCKET_ENV = "LIBRE_DICTUM_HUD_SOCKET"

RETRY_MS = 5000

VOICE_PHRASES = 2

TOKENS = {
    "SPACE": "space", "ENTER": "enter", "ESC": "esc", "TAB": "tab", "BACKSPACE": "backspace",
    "←": "left", "→": "right", "↑": "up", "↓": "down", "PGUP": "pageup", "PGDN": "pagedown",
    **{str(digit): str(digit) for digit in range(10)},
}

CHORDS = {"CTRL": "ctrl+"}

SPELLINGS = {"escape": "esc", "return": "enter", "pgup": "pageup", "page_up": "pageup",
             "pgdn": "pagedown", "page_down": "pagedown"}

HELD = re.compile(r"\d+(\.\d+)?s")
REPEATED = re.compile(r"(?:\{\d+=\d+\}|\d+)\((.+)\)")
HOLDING = re.compile(r"hold\((.+)\)")
STANDING_IN = re.compile(r"(\w+) pedal")


def socket_path() -> str:
    """Return where libre-dictum publishes its catalogue and layer state."""
    override = os.environ.get(SOCKET_ENV)
    if override:
        return override
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    folder = Path(runtime) / "libre-dictum" if runtime else Path(f"/tmp/libre-dictum-{os.getuid()}")
    return str(folder / "hud.sock")


def key_sent(response) -> tuple:
    """Return the key a response sends and whether it stays down, or ("", False)."""
    said = re.sub(r"\s+", "", str(response or "")).lower()
    repeated = REPEATED.fullmatch(said)
    if repeated:
        said = repeated[1]
    holding = HOLDING.fullmatch(said)
    if holding:
        return SPELLINGS.get(holding[1], holding[1]), True
    return SPELLINGS.get(said, said), False


def bindings(catalogue, state) -> dict:
    """Return the input names that send each (key, held) pair, in the layers awake."""
    modes = {mode.get("name"): mode for mode in catalogue.get("modes", ())}
    asleep = set(state.get("asleep") or ())
    found, spoken = {}, {}

    def add(response, name, spoken_name=False):
        pair = key_sent(response)
        if spoken_name:
            spoken[pair] = spoken.get(pair, 0) + 1
            if spoken[pair] > VOICE_PHRASES:
                return
        found.setdefault(pair, []).append(name)

    pedals = {}
    if "pedal" not in asleep:
        for pedal, press, _release in modes.get(state.get("pedal_mode"), {}).get("pedals", ()):
            pedals[pedal] = press
            add(press, f"{pedal} pedal")
    if "gesture" not in asleep:
        gestures = modes.get(state.get("gesture_mode"), {}).get("gestures", ())
        standing_in = [(name, STANDING_IN.fullmatch(press)) for name, press, _ in gestures]
        for name, pedal in standing_in:
            if pedal:
                add(pedals.get(pedal[1], ""), name.replace("_", " "))
        for (name, press, _release), (_, pedal) in zip(gestures, standing_in):
            if not pedal:
                add(press, name.replace("_", " "))
    if "voice" not in asleep:
        for group in modes.get(state.get("mode"), {}).get("groups", ()):
            for phrase, response, *_ in group.get("entries", ()):
                if "{" not in phrase:
                    add(response, f"“{phrase}”", spoken_name=True)
    return {pair: tuple(names) for pair, names in found.items() if pair[0]}


def keys_of(label) -> list:
    """Split a card's key label into (shown, key, held) per key, or []."""
    words, keys = str(label).split(), []
    index = 0
    while index < len(words):
        word = words[index]
        if word in CHORDS and index + 1 < len(words) and words[index + 1] in TOKENS:
            following = words[index + 1]
            keys.append((f"{word} {following}", CHORDS[word] + TOKENS[following], False))
            index += 2
            continue
        if HELD.fullmatch(word) and keys:
            shown, key, _ = keys[-1]
            keys[-1] = (f"{shown} {word}", key, True)
        elif word in TOKENS:
            keys.append((word, TOKENS[word], False))
        else:
            return []
        index += 1
    return keys


def names_for(inputs, key, held) -> tuple:
    """Return the input names that send key, only holding ones where it is held."""
    names = inputs.get((key, True), ())
    return names if held else inputs.get((key, False), ()) + names


def legend(hints, inputs) -> list:
    """Return (key, says, input names) rows, one per key wherever a key has inputs."""
    rows = []
    for label, says in hints:
        found = [(shown, names_for(inputs, key, held)) for shown, key, held in keys_of(label)]
        if len(found) < 2 or not any(names for _, names in found):
            rows.append((label, says, found[0][1] if len(found) == 1 else ()))
            continue
        parts = says.split(", ")
        for index, (shown, names) in enumerate(found):
            rows.append((shown, parts[index] if len(parts) == len(found) else says, names))
    return rows


class DictumListener(QObject):
    """libre-dictum's live bindings, read off its display socket while started."""

    changed = pyqtSignal()

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.path = path or socket_path()
        self.inputs = {}
        self._catalogue = None
        self._state = None
        self._listening = False
        self._refused = False
        self._socket = QLocalSocket(self)
        self._socket.readyRead.connect(self._read)
        self._socket.disconnected.connect(self._lost)
        self._socket.errorOccurred.connect(self._lost)
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.setInterval(RETRY_MS)
        self._retry.timeout.connect(self._connect)

    def start(self):
        """Read the bindings until stopped, connecting again whenever the socket goes."""
        self._listening = True
        self._connect()

    def stop(self):
        """Close the socket and forget the bindings."""
        self._listening = False
        self._retry.stop()
        self._socket.abort()
        self._catalogue = self._state = None
        self.inputs = {}

    def _connect(self):
        idle = self._socket.state() == QLocalSocket.LocalSocketState.UnconnectedState
        if self._listening and idle:
            self._socket.connectToServer(self.path)

    def _lost(self, *_):
        if not self._listening:
            return
        self._catalogue = self._state = None
        self._settle()
        self._retry.start()

    def _read(self):
        while self._socket.canReadLine():
            self._take(bytes(self._socket.readLine()))
        self._settle()

    def _take(self, line):
        """Keep the newest catalogue and the newest layer state a frame carries."""
        try:
            frame = json.loads(line)
        except ValueError:
            log.debug("Ignoring a libre-dictum frame that is not JSON.")
            return
        if not isinstance(frame, dict):
            return
        if frame.get("protocol") != PROTOCOL:
            if not self._refused:
                self._refused = True
                log.warning("libre-dictum speaks protocol %r, not %d: no input names.",
                            frame.get("protocol"), PROTOCOL)
            return
        if frame.get("kind") == "catalogue":
            self._catalogue = frame
        elif frame.get("kind") == "state":
            self._state = frame

    def _settle(self):
        """Work out the bindings again, and say so where they changed."""
        inputs = (bindings(self._catalogue, self._state)
                  if self._catalogue is not None and self._state is not None else {})
        if inputs != self.inputs:
            self.inputs = inputs
            self.changed.emit()
