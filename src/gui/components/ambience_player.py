import logging
from typing import NamedTuple

from PyQt6.QtCore import (QElapsedTimer, QIODevice, QMetaObject, QObject, Qt, QThread, QTimer,
                          pyqtSignal, pyqtSlot)
from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices, QtAudio

from src.desktop import ambience

log = logging.getLogger(__name__)

FADE_IN_SECS = 8.0
FADE_OUT_SECS = 4.0
SCENE_SECS = 5.0
VOLUME_SECS = 0.4
VOLUME_STEP = 0.1
BUFFER_SECS = 0.5
TEND_MS = 250
RETRY_MS = 5000
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
        self.failed = False

    def readData(self, maxlen):
        frames = maxlen // FRAME_BYTES
        if frames <= 0:
            return b""
        if not self.failed:
            try:
                return self._render(frames).tobytes()
            # Workaround: an exception escaping a Qt virtual aborts the interpreter.
            except Exception:
                self.failed = True
                log.exception("The ambience stopped rendering.")
        return bytes(frames * FRAME_BYTES)

    def writeData(self, data):
        return -1

    def bytesAvailable(self):
        return (1 << 16) + super().bytesAvailable()

    def isSequential(self):
        return True


class _Engine(QObject):
    """The sink and the mix, on a thread of their own, reopened on the default output."""

    def __init__(self):
        super().__init__()
        self._mix = None
        self._sink = None
        self._stream = None
        self._device = None
        self._wish = None
        self._tending = None
        self._tried = QElapsedTimer()
        self._warned = False

    @pyqtSlot(object)
    def steer(self, wish):
        """Move towards wish: start, crossfade, change volume or fade out."""
        self._wish = wish
        if self._tending is None:
            self._tending = QTimer(self)
            self._tending.setInterval(TEND_MS)
            self._tending.timeout.connect(self._tend)
        if wish.audible and not self._tending.isActive():
            self._tending.start()
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
        if self._tending is not None:
            self._tending.stop()
        self._stop()

    def _start(self, wish):
        """Open the sink on the default output and fade the scene in."""
        self._tried.start()
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self._warn("No audio output: the ambience waits for one.")
            return
        shape = QAudioFormat()
        shape.setSampleRate(RATE)
        shape.setChannelCount(2)
        shape.setSampleFormat(QAudioFormat.SampleFormat.Float)
        if not device.isFormatSupported(shape):
            self._warn(f"{device.description()} cannot play {RATE} Hz stereo floats: "
                       "the ambience waits for another output.")
            return
        self._warned = False
        self._device = device
        self._mix = ambience.Ambience(RATE, wish.volume)
        self._mix.play(wish.scene, FADE_IN_SECS)
        self._stream = _Stream(self._mix.render, self)
        self._stream.open(QIODevice.OpenModeFlag.ReadOnly)
        self._sink = QAudioSink(device, shape, self)
        self._sink.setBufferSize(int(RATE * BUFFER_SECS) * FRAME_BYTES)
        self._sink.start(self._stream)

    def _warn(self, said):
        if not self._warned:
            log.warning(said)
            self._warned = True

    def _tend(self):
        """Close the sink once the mix fell silent, and reopen it wherever it broke."""
        if self._mix is not None and self._mix.silent:
            self._stop()
        if not self._wish.audible:
            if self._mix is None:
                self._tending.stop()
            return
        if self._sounds() or self._tried.elapsed() < RETRY_MS:
            return
        if self._mix is not None:
            log.info("The ambience output stopped or changed: reopening it.")
        self._stop()
        self._start(self._wish)

    def _sounds(self) -> bool:
        """Report whether the sink plays the mix on the default output."""
        return (self._sink is not None and not self._stream.failed
                and self._sink.state() != QtAudio.State.StoppedState
                and self._device == QMediaDevices.defaultAudioOutput())

    def _stop(self):
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        if self._stream is not None:
            self._stream.close()
            self._stream.deleteLater()
        if self._mix is not None:
            self._mix.close()
        self._sink = self._stream = self._mix = self._device = None


class AmbiencePlayer(QObject):
    """One scene of the bank at a time, faded in and out."""

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
        self.lacks_extra = False

    @property
    def scene_name(self) -> str:
        return ambience.shown_name(self.scene) if self.scene is not None else ""

    @property
    def chosen(self) -> str:
        """Return the name of the scene playing, or of the one play would fade in."""
        return self.scene.name if self.audible else self._wanted

    def scenes(self) -> list:
        """Return the scenes the bank offers now, noise included, in name order."""
        return ambience.scenes(self._bank)

    def play(self):
        """Fade the chosen scene in, the bank read afresh."""
        if self.audible or not self._renders():
            return
        scenes = self.scenes()
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

    def choose(self, name) -> str:
        """Make name the scene to play, crossfading to it if one plays already."""
        scene = next((scene for scene in self.scenes()
                      if scene.name.casefold() == str(name).casefold()), None)
        if scene is None:
            return ""
        self._wanted = scene.name
        if self.audible and scene != self.scene:
            self.scene = scene
            self._send()
        return ambience.shown_name(scene)

    def step(self, by) -> str:
        """Crossfade to the scene by places after the one playing, in name order."""
        if not self.audible:
            return ""
        scenes = self.scenes()
        names = [scene.name for scene in scenes]
        at = names.index(self.scene.name) if self.scene.name in names else 0
        self.scene = scenes[(at + by) % len(scenes)]
        self._wanted = self.scene.name
        self._send()
        return self.scene_name

    def nudge(self, by) -> float:
        """Raise or lower the volume by VOLUME_STEP per step, within 0 and 1."""
        return self.set_volume(self.volume + by * VOLUME_STEP)

    def set_volume(self, volume) -> float:
        """Set the volume, held within 0 and 1."""
        volume = min(1.0, max(0.0, round(float(volume), 2)))
        if volume != self.volume:
            self.volume = volume
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

    def has_output(self) -> bool:
        """Report whether an audio output exists to play on."""
        return not QMediaDevices.defaultAudioOutput().isNull()

    def _renders(self) -> bool:
        """Report whether numpy, soundfile and soxr load, warning once."""
        if self._can_render is None:
            try:
                import numpy  # noqa: F401
                import soundfile  # noqa: F401
                import soxr  # noqa: F401
                self._can_render = True
            except (ImportError, OSError) as error:
                log.warning("No ambience: %s", error)
                self._can_render = False
                self.lacks_extra = True
        return self._can_render

    def _send(self):
        if self._thread is None:
            self._thread = QThread(self)
            self._engine = _Engine()
            self._engine.moveToThread(self._thread)
            self._thread.finished.connect(self._engine.deleteLater)
            self._steer.connect(self._engine.steer)
            self._thread.start()
        self._steer.emit(Wish(self.scene, self.volume, self.audible))
