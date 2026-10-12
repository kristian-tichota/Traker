import logging
from typing import NamedTuple

from PyQt6.QtCore import (QIODevice, QMetaObject, QObject, Qt, QThread, QTimer, pyqtSignal,
                          pyqtSlot)
from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

from src.desktop import ambience

log = logging.getLogger(__name__)

FADE_IN_SECS = 8.0
FADE_OUT_SECS = 4.0
SCENE_SECS = 5.0
VOLUME_SECS = 0.4
VOLUME_STEP = 0.1
BUFFER_SECS = 0.5
TEND_MS = 250
RATE = 48_000
FRAME_BYTES = 8


class Wish(NamedTuple):
    """What the engine should be playing: a scene, at a volume, or nothing."""

    scene: ambience.Scene
    volume: float
    audible: bool


class _Stream(QIODevice):
    """Hands the sink whatever the mix renders next, as interleaved 32-bit floats."""

    def __init__(self, render, parent=None):
        super().__init__(parent)
        self._render = render
        self._failed = False

    def readData(self, maxlen):
        frames = maxlen // FRAME_BYTES
        if frames <= 0:
            return b""
        if not self._failed:
            try:
                return self._render(frames).tobytes()
            # Workaround: an exception escaping a Qt virtual aborts the interpreter.
            except Exception:
                self._failed = True
                log.exception("The ambience stopped rendering.")
        return bytes(frames * FRAME_BYTES)

    def writeData(self, data):
        return -1

    def bytesAvailable(self):
        return (1 << 16) + super().bytesAvailable()

    def isSequential(self):
        return True


class _Engine(QObject):
    """The sink and the mix, on a thread of their own."""

    def __init__(self):
        super().__init__()
        self._mix = None
        self._sink = None
        self._stream = None
        self._tending = None

    @pyqtSlot(object)
    def steer(self, wish):
        """Move towards wish: start, crossfade, change volume or fade out."""
        if self._tending is None:
            self._tending = QTimer(self)
            self._tending.setInterval(TEND_MS)
            self._tending.timeout.connect(self._tend)
        if self._mix is None:
            if wish.audible:
                self._start(wish)
            return
        if not wish.audible:
            self._mix.hush(FADE_OUT_SECS)
        elif self._mix.scene != wish.scene:
            fading_in = self._mix.scene is None
            self._mix.play(wish.scene, FADE_IN_SECS if fading_in else SCENE_SECS)
        self._mix.set_volume(wish.volume, VOLUME_SECS)

    @pyqtSlot()
    def halt(self):
        """Stop the sink at once."""
        self._stop()

    def _start(self, wish):
        """Open the sink and fade the scene in."""
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            log.warning("No audio output: the walls stay silent.")
            return
        shape = QAudioFormat()
        shape.setSampleRate(RATE)
        shape.setChannelCount(2)
        shape.setSampleFormat(QAudioFormat.SampleFormat.Float)
        if not device.isFormatSupported(shape):
            log.warning("%s cannot play %d Hz stereo floats: the walls stay silent.",
                        device.description(), RATE)
            return
        self._mix = ambience.Ambience(RATE, wish.volume)
        self._mix.play(wish.scene, FADE_IN_SECS)
        self._stream = _Stream(self._mix.render, self)
        self._stream.open(QIODevice.OpenModeFlag.ReadOnly)
        self._sink = QAudioSink(device, shape, self)
        self._sink.setBufferSize(int(RATE * BUFFER_SECS) * FRAME_BYTES)
        self._sink.start(self._stream)
        self._tending.start()

    def _tend(self):
        """Close the sink once the mix fell silent."""
        if self._mix is not None and self._mix.silent:
            self._stop()

    def _stop(self):
        if self._tending is not None:
            self._tending.stop()
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        if self._stream is not None:
            self._stream.close()
            self._stream.deleteLater()
        if self._mix is not None:
            self._mix.close()
        self._sink = self._stream = self._mix = None


class AmbiencePlayer(QObject):
    """The sound under a break's walls: one scene of the bank, faded in and out."""

    _steer = pyqtSignal(object)

    def __init__(self, bank, scene_name, volume, parent=None):
        super().__init__(parent)
        self._bank = bank
        self._wanted = str(scene_name or "")
        self.volume = min(1.0, max(0.0, float(volume)))
        self.scene = None
        self.audible = False
        self._thread = None
        self._engine = None
        self._can_render = None

    @property
    def scene_name(self) -> str:
        return ambience.shown_name(self.scene) if self.scene is not None else ""

    def play(self):
        """Fade the chosen scene in, the bank read afresh."""
        if self.audible or not self._renders():
            return
        scenes = ambience.scenes(self._bank)
        self.scene = next((scene for scene in scenes if scene.name == self._wanted),
                          ambience.Scene(ambience.NOISE))
        self.audible = True
        self._send()

    def hush(self):
        """Fade whatever plays out."""
        if not self.audible:
            return
        self.audible = False
        self._send()

    def step(self, by) -> str:
        """Crossfade to the scene by places after the one playing, in name order."""
        if not self.audible:
            return ""
        scenes = ambience.scenes(self._bank)
        names = [scene.name for scene in scenes]
        at = names.index(self.scene.name) if self.scene.name in names else 0
        self.scene = scenes[(at + by) % len(scenes)]
        self._wanted = self.scene.name
        self._send()
        return self.scene_name

    def nudge(self, by) -> float:
        """Raise or lower the volume by VOLUME_STEP per step, within 0 and 1."""
        self.volume = min(1.0, max(0.0, round(self.volume + by * VOLUME_STEP, 2)))
        if self.audible:
            self._send()
        return self.volume

    def shutdown(self):
        """Stop the sound at once and the thread it plays on."""
        if self._thread is None:
            return
        QMetaObject.invokeMethod(self._engine, "halt",
                                 Qt.ConnectionType.BlockingQueuedConnection)
        self._thread.quit()
        self._thread.wait(2000)
        self._thread = self._engine = None

    def _renders(self) -> bool:
        """Report whether numpy, soundfile and soxr load and an output exists, warning once."""
        if self._can_render is None:
            try:
                import numpy  # noqa: F401
                import soundfile  # noqa: F401
                import soxr  # noqa: F401
                self._can_render = True
            except (ImportError, OSError) as error:
                log.warning("No ambience under a break: %s", error)
                self._can_render = False
        return self._can_render and not QMediaDevices.defaultAudioOutput().isNull()

    def _send(self):
        if self._thread is None:
            self._thread = QThread(self)
            self._engine = _Engine()
            self._engine.moveToThread(self._thread)
            self._thread.finished.connect(self._engine.deleteLater)
            self._steer.connect(self._engine.steer)
            self._thread.start()
        self._steer.emit(Wish(self.scene, self.volume, self.audible))
