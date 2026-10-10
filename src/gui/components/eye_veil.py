import array
import logging
import math
import os
import shutil
import wave

from PyQt6.QtCore import (QDateTime, QObject, QProcess, QRect, Qt, QTimer, QVariantAnimation,
                          pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from src.config import PALETTE
from src.desktop.files import cache_path
from src.desktop.kwin_rules import EyeRule
from src.domain.eye_rest import (CLOSE, GAZE, LOOK, OPEN, READY, READY_MS, SET_REPETITION,
                                 SET_REPETITIONS, SQUEEZE, ScreenTime, blink_set, length_ms,
                                 look_away, step_at)
from src.gui.animations import retarget

log = logging.getLogger(__name__)

VEIL_CAPTION = "Traker eyes"
VEIL_ALPHA = 0.82
FADE_IN_MS = 1200
FADE_OUT_MS = 900
PACE_MS = 50

REST_TITLE = "BLINK CYCLE"
GAZE_NOTE = "6 M OR FURTHER · BLINK FULLY"

DONE = "done"
CUES = {
    CLOSE: (((988.0,), 0.16), ((659.0,), 0.3)),
    OPEN: (((659.0,), 0.16), ((988.0,), 0.3)),
    SQUEEZE: (((440.0, 880.0), 0.1),) * 3,
    LOOK: (((784.0, 1568.0), 1.2),),
    DONE: (((523.0, 659.0, 784.0), 1.4),),
}
CUE_AMPLITUDE = 0.45
TONE_RATE = 22050
TONE_ATTACK_S = 0.005
PLAYERS = {"pw-play": ["--latency=20ms"], "paplay": ["--latency-msec=20"], "aplay": ["-q"]}


def veil_caption(screen) -> str:
    """Return what to call the veil on screen."""
    name = screen.name() if screen is not None else ""
    return f"{VEIL_CAPTION} — {name}" if name else VEIL_CAPTION


def cue_samples(notes, amplitude=CUE_AMPLITUDE, rate=TONE_RATE) -> array.array:
    """Return (partials, seconds) notes in turn, each a decaying sine chord, as 16-bit samples."""
    attack = TONE_ATTACK_S * rate
    samples = array.array("h")
    for partials, seconds in notes:
        decay = 5.0 / seconds
        samples.extend(
            int(32767 * amplitude * min(1.0, i / attack) * math.exp(-decay * i / rate)
                * sum(math.sin(2 * math.pi * f * i / rate) for f in partials) / len(partials))
            for i in range(int(rate * seconds)))
    return samples


def routine_track(routine, lead_ms, cues, rate=TONE_RATE) -> array.array:
    """Return lead_ms of silence, then each step's cue at its start and the end chord after it."""
    onsets, at_ms = [], lead_ms
    for step in routine:
        onsets.append((step.motion, at_ms))
        at_ms += step.ms
    onsets.append((DONE, at_ms))
    track = array.array("h", bytes(2 * (at_ms * rate // 1000 + len(cues.get(DONE, "")))))
    for name, ms in onsets:
        cue = cues.get(name)
        if cue is not None:
            at = ms * rate // 1000
            track[at:at + len(cue)] = cue[:len(track) - at]
    return track


def write_tone(path, samples, rate=TONE_RATE):
    """Write samples as a mono 16-bit WAV file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.tobytes())


class Tones:
    """Plays a routine's cues as one track, so that every cue keeps to the routine's clock."""

    def __init__(self):
        self.cues = {}
        self.process = None
        self.player = next(filter(shutil.which, PLAYERS), None)
        if self.player is None:
            log.warning("The eye rest is silent: none of %s is installed.", ", ".join(PLAYERS))
            return
        self.cues = {name: cue_samples(notes) for name, notes in CUES.items()}

    def play(self, routine, lead_ms):
        """Start the routine's track in place of any playing, without waiting for it."""
        self.stop()
        if self.player is None:
            return
        path = cache_path("eye-routine.wav")
        try:
            write_tone(path, routine_track(routine, lead_ms, self.cues))
        except OSError as error:
            log.warning("The eye rest is silent: %s", error)
            return
        self.process = QProcess()
        self.process.setStandardOutputFile(QProcess.nullDevice())
        self.process.setStandardErrorFile(QProcess.nullDevice())
        self.process.start(self.player, PLAYERS[self.player] + [path])

    def stop(self):
        """Cut the track off."""
        if self.process is not None:
            self.process.kill()
            self.process.waitForFinished(1000)
            self.process = None


class EyeVeil(QWidget):
    """A dimming veil saying what the eyes do now, taking neither keys nor the pointer."""

    WINDOW_FLAGS = (Qt.WindowType.Window |
                    Qt.WindowType.FramelessWindowHint |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.WindowDoesNotAcceptFocus |
                    Qt.WindowType.WindowTransparentForInput)

    def __init__(self, parent=None, screen=None):
        super().__init__(parent)
        self.screen_covered = screen
        self.strength = 0.0
        self.raised = False
        self.lines = ("", "", "")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if parent is None:
            self.setWindowFlags(self.WINDOW_FLAGS)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setWindowTitle(veil_caption(screen))
        self.fade = QVariantAnimation(self)
        self.fade.valueChanged.connect(self._set_strength)
        self.fade.finished.connect(self._faded)
        self.hide()

    def say(self, step, count="", note=""):
        """Show three lines over everything beneath, fading in where the veil was down."""
        if (step, count, note) != self.lines:
            self.lines = (step, count, note)
            self.update()
        if not self.raised:
            self.raised = True
            self._cover()
            self._fade_to(1.0, FADE_IN_MS)

    def lift(self):
        """Fade out, and close a veil that is a window of its own."""
        if not self.raised:
            return
        self.raised = False
        self._fade_to(0.0, FADE_OUT_MS)

    def _cover(self):
        """Fill the parent, or the screen this veil was built for."""
        if self.isWindow():
            if self.screen_covered is not None:
                self.setScreen(self.screen_covered)
                self.setGeometry(self.screen_covered.geometry())
            self.showFullScreen()
            return
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()

    def _fade_to(self, target, duration_ms):
        retarget(self.fade, self.strength, target, duration_ms)

    def _set_strength(self, value):
        self.strength = float(value)
        self.update()

    def _faded(self):
        if self.raised:
            return
        self.hide()
        if self.isWindow():
            self.deleteLater()

    def paintEvent(self, event):
        if self.strength <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        shade = QColor(PALETTE['base03'])
        shade.setAlphaF(VEIL_ALPHA * self.strength)
        painter.fillRect(self.rect(), shade)

        height = self.height()
        styled = [(said, max(px, height // scale), colour)
                  for said, (px, scale, colour) in zip(
                      self.lines, ((28, 12, 'cyan'), (22, 18, 'base1'), (11, 60, 'base0')))
                  if said]
        fonts = []
        for said, px, colour in styled:
            font = QFont("Fira Code")
            font.setPixelSize(px)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(2, px // 8))
            fonts.append((said, font, colour, QFontMetrics(font).height() * 3 // 2))

        y = (height - sum(line for *_, line in fonts)) // 2
        for said, font, colour, line in fonts:
            ink = QColor(PALETTE[colour])
            ink.setAlphaF(self.strength)
            painter.setPen(ink)
            painter.setFont(font)
            painter.drawText(QRect(0, y, self.width(), line), Qt.AlignmentFlag.AlignCenter, said)
            y += line


class EyeRest(QObject):
    """Rests the eyes after a stretch of screen time, with a veil over every screen."""

    set_done = pyqtSignal()

    def __init__(self, every_ms, gaze_ms, walls, still, sound=True, parent=None):
        super().__init__(parent)
        self.gaze_ms = int(gaze_ms)
        self.screen_time = ScreenTime(int(every_ms), length_ms(look_away(gaze_ms)))
        self._walls = walls
        self._still = still
        self._sound = sound
        self.tones = None
        self.rule = EyeRule(VEIL_CAPTION)
        self.windows = []
        self.routine = ()
        self.title = ""
        self.repetitions = 0
        self.now = QDateTime.currentMSecsSinceEpoch
        self._began_ms = 0
        self._pace = QTimer(self)
        self._pace.setInterval(PACE_MS)
        self._pace.timeout.connect(self.pace)

    @property
    def running(self) -> bool:
        return bool(self.routine)

    def advance(self, delta_ms, away_ms):
        """Count screen time, and rest the eyes once enough has gathered."""
        if not self.running and self.screen_time.advance(delta_ms, away_ms):
            self.begin(look_away(self.gaze_ms), REST_TITLE)

    def begin_set(self, title):
        """Run a paced blink set now, in place of any rest running."""
        self.begin(blink_set(), title, SET_REPETITIONS)

    def begin(self, routine, title, repetitions=0):
        """Run a routine now, in place of any running."""
        self.routine, self.title, self.repetitions = tuple(routine), title, repetitions
        if self._sound and self.tones is None:
            self.tones = Tones()
        if self.tones is not None:
            self.tones.play(self.routine, READY_MS)
        self._began_ms = self.now() + READY_MS
        self._still(True)
        self._pace.start()
        self.pace()

    def pace(self):
        """Count down to the routine, show the step reached on every screen, and end on time."""
        if not self.running:
            return
        elapsed = self.now() - self._began_ms
        at = step_at(self.routine, elapsed)
        if at is None:
            self._finish()
            return
        lines = (READY, str(math.ceil(-elapsed / 1000)), self.title) if elapsed < 0 \
            else self._lines(*at)
        for veil in self._veils():
            veil.say(*lines)

    def _lines(self, index, left_ms) -> tuple:
        step = self.routine[index]
        if step.said == GAZE:
            return step.said, str(math.ceil(left_ms / 1000)), GAZE_NOTE
        if self.repetitions:
            return (step.said, f"{index // len(SET_REPETITION) + 1} / {self.repetitions}",
                    self.title)
        return step.said, "", self.title

    def _veils(self) -> list:
        """Return the walls' veils while walls stand, else one window per screen."""
        walls = self._walls()
        if walls:
            self._lift_windows()
            return [wall.veil for wall in walls]
        if not self.windows:
            self.windows = [EyeVeil(screen=screen) for screen in QApplication.screens()]
        return self.windows

    def _lift_windows(self):
        for veil in self.windows:
            veil.lift()
        self.windows = []

    def _finish(self):
        finished_a_set = bool(self.repetitions)
        self._stop()
        self.screen_time.rested()
        if finished_a_set:
            self.set_done.emit()

    def _stop(self):
        """Stop the routine and lift every veil, letting go of what was held still."""
        self._pace.stop()
        self.routine = ()
        self.repetitions = 0
        for wall in self._walls():
            wall.veil.lift()
        self._lift_windows()
        self._still(False)

    def shutdown(self):
        """Stop any routine, close the veils' windows at once and give the window rule back."""
        windows, self.windows = self.windows, []
        if self.tones is not None:
            self.tones.stop()
        if self.running:
            self._stop()
        for veil in windows:
            veil.hide()
            veil.deleteLater()
        self.rule.release()
