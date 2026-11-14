import fcntl
import logging
import os
import shutil
import subprocess
from typing import NamedTuple

from PyQt6.QtCore import (QElapsedTimer, QMetaObject, QObject, QSocketNotifier, Qt, QThread,
                          QTimer, pyqtSignal, pyqtSlot)
from PyQt6.QtMultimedia import QMediaDevices

from src.desktop import ambience

log = logging.getLogger(__name__)

FADE_IN_SECS = 8.0
FADE_OUT_SECS = 4.0
SCENE_SECS = 5.0
VOLUME_SECS = 0.4
VOLUME_STEP = 0.1
TEND_MS = 250
RETRY_MS = 5000
RATE = 48_000
BLOCK_FRAMES = 2400
PIPE_BYTES = 1 << 18

PLAYER = ("pw-cat", "--playback", "--raw", "--format", "f32", "--rate", str(RATE),
          "--channels", "2", "--properties",
          '{ node.name = "traker-ambience" media.name = "Ambience" application.name = "Traker" }',
          "-")


class Wish(NamedTuple):
    """What the engine should be playing: a scene, at a volume, or nothing."""

    scene: ambience.Scene
    volume: float
    audible: bool


class _Engine(QObject):
    """The mix on its own thread, written into a PipeWire player following the default output."""

    def __init__(self, command=PLAYER):
        super().__init__()
        self._command = list(command)
        self._mix = None
        self._player = None
        self._writable = None
        self._pending = b""
        self._failed = False
        self._ending = []
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
        """Stop the player at once."""
        if self._tending is not None:
            self._tending.stop()
        self._stop()
        for player in self._ending:
            player.kill()
            player.wait()
        self._ending = []

    def _start(self, wish):
        """Start the player and fade the scene in."""
        self._tried.start()
        try:
            player = subprocess.Popen(self._command, stdin=subprocess.PIPE,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error:
            self._warn(f"The ambience player would not start: {error}")
            return
        self._warned = False
        self._failed = False
        self._pending = b""
        pipe = player.stdin.fileno()
        os.set_blocking(pipe, False)
        try:
            fcntl.fcntl(pipe, fcntl.F_SETPIPE_SZ, PIPE_BYTES)
        except OSError as error:
            log.debug("The ambience pipe keeps its own size: %s", error)
        self._player = player
        self._mix = ambience.Ambience(RATE, wish.volume)
        self._mix.play(wish.scene, FADE_IN_SECS)
        self._writable = QSocketNotifier(pipe, QSocketNotifier.Type.Write, self)
        self._writable.activated.connect(self._feed)

    def _feed(self):
        """Write as much of the mix as the pipe takes now."""
        pipe = self._player.stdin.fileno()
        try:
            while True:
                if not self._pending:
                    self._pending = self._mix.render(BLOCK_FRAMES).tobytes()
                self._pending = self._pending[os.write(pipe, self._pending):]
        except BlockingIOError:
            return
        except OSError as error:
            log.info("The ambience player stopped taking sound: %s", error)
        except Exception:
            log.exception("The ambience stopped rendering.")
        self._failed = True
        self._writable.setEnabled(False)

    def _warn(self, said):
        if not self._warned:
            log.warning(said)
            self._warned = True

    def _tend(self):
        """Let the player drain once the mix fell silent, and start it again if it ended."""
        self._ending = [player for player in self._ending if player.poll() is None]
        if self._mix is not None and self._mix.silent:
            self._stop(drain=True)
        if not self._wish.audible:
            if self._mix is None and not self._ending:
                self._tending.stop()
            return
        if self._plays() or self._tried.elapsed() < RETRY_MS:
            return
        if self._mix is not None:
            log.info("The ambience player ended: starting it again.")
        self._stop()
        self._start(self._wish)

    def _plays(self) -> bool:
        """Report whether the player runs and takes the mix."""
        return self._player is not None and not self._failed and self._player.poll() is None

    def _stop(self, drain=False):
        """Close the player's input, letting it play out what it holds when drain is set."""
        if self._writable is not None:
            self._writable.setEnabled(False)
            self._writable.deleteLater()
        if self._player is not None:
            self._player.stdin.close()
            if not drain:
                self._player.kill()
            self._ending.append(self._player)
        if self._mix is not None:
            self._mix.close()
        self._player = self._writable = self._mix = None
        self._pending = b""


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
        """Report whether the player is installed and an audio output exists to play on."""
        return (shutil.which(PLAYER[0]) is not None
                and not QMediaDevices.defaultAudioOutput().isNull())

    def _renders(self) -> bool:
        """Report whether numpy, soundfile, soxr and the player are there, warning once."""
        if self._can_render is None:
            if shutil.which(PLAYER[0]) is None:
                log.warning("No ambience: %s is not installed.", PLAYER[0])
                self._can_render = False
                return False
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
