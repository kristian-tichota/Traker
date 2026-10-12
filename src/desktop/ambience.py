import logging
import math
import os
import re
import tomllib
from typing import NamedTuple

log = logging.getLogger(__name__)

NOISE = "noise"
MANIFEST = "scene.toml"
AUDIO = (".ogg", ".oga", ".opus", ".flac", ".wav")

DEFAULT_BANK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Ambience")

SEGMENT_SECS = (40.0, 110.0)
CROSSFADE_SECS = 6.0
SHORTEST_SECS = 3.0
CANDIDATES = 6
PROBE_SECS = 2.0
DRIFT = (0.79, 1.12)
DRIFT_SECS = (30.0, 90.0)
NOISE_BLOCK = 1 << 16
KNEE = 0.5

NOISE_BANDS = (
    ("deep", 2.0, 25.0, 300.0, -19.5),
    ("warm", 1.0, 150.0, 3000.0, -29.5),
    ("air", 1.0, 1500.0, 12000.0, -40.0),
)


class Layer(NamedTuple):
    """One recording of a scene: its file, its gain, and the seconds of it that play."""

    path: str
    gain_db: float = 0.0
    span: tuple = (0.0, math.inf)


class Scene(NamedTuple):
    """One mix the bank offers; a scene without layers is generated noise."""

    name: str
    layers: tuple = ()


def bank_for(profile) -> str:
    """Return this member's ambience bank, from [strict_break.ambience] path."""
    written = str(profile.get_metric("strict_break.ambience", "path", "") or "").strip()
    return os.path.abspath(os.path.expanduser(written)) if written else DEFAULT_BANK


def scenes(bank) -> list:
    """Return every scene in bank that has something to play, and noise, in name order."""
    found = [Scene(NOISE)]
    try:
        with os.scandir(bank) as scanned:
            folders = [entry for entry in scanned
                       if entry.is_dir() and not entry.name.startswith(".")]
    except OSError:
        folders = []
    for folder in folders:
        scene = read_scene(folder.path)
        if scene.layers and scene.name != NOISE:
            found.append(scene)
    return sorted(found, key=lambda scene: scene.name.casefold())


def read_scene(folder) -> Scene:
    """Return the scene a folder holds: its manifest's layers, or every audio file at 0 dB."""
    name = os.path.basename(os.path.normpath(folder))
    manifest = os.path.join(folder, MANIFEST)
    if not os.path.isfile(manifest):
        try:
            files = sorted(entry for entry in os.listdir(folder)
                           if entry.lower().endswith(AUDIO) and not entry.startswith("."))
        except OSError:
            files = []
        return Scene(name, tuple(Layer(os.path.join(folder, file)) for file in files))
    try:
        with open(manifest, "rb") as handle:
            written = tomllib.load(handle).get("layer", [])
    except (OSError, tomllib.TOMLDecodeError) as error:
        log.warning("Scene %r has a manifest that cannot be read: %s", name, error)
        return Scene(name)
    layers = (_layer(folder, entry) for entry in written if isinstance(entry, dict))
    return Scene(name, tuple(layer for layer in layers if layer is not None))


def _layer(folder, entry):
    """Return one manifest entry as a Layer, or None with the reason logged."""
    path = os.path.join(folder, str(entry.get("file") or ""))
    if not os.path.isfile(path):
        log.warning("Ambience layer %r is missing: skipped.", path)
        return None
    try:
        gain = float(entry.get("gain_db", 0.0))
        start, stop = (float(at) for at in entry.get("span", (0.0, math.inf)))
    except (TypeError, ValueError):
        log.warning("Ambience layer %r has an unreadable gain or span: skipped.", path)
        return None
    return Layer(path, gain, (max(0.0, start), stop))


def shown_name(scene) -> str:
    """Return a scene's name as the walls write it."""
    return re.sub(r"[-_]+", " ", scene.name).strip().capitalize()


class Ramp:
    """A level moving towards a target at a set pace, one frame at a time."""

    def __init__(self, value=0.0):
        self.value = float(value)
        self.target = float(value)
        self._step = 0.0

    def to(self, target, frames):
        """Move to target over frames, from wherever the level stands now."""
        self.target = float(target)
        self._step = abs(self.target - self.value) / max(1, int(frames))

    def levels(self, frames):
        """Return the level of each of the next frames."""
        import numpy as np

        if self.value == self.target:
            return np.full(frames, self.value, dtype=np.float32)
        sign = 1.0 if self.target > self.value else -1.0
        out = self.value + sign * self._step * np.arange(1, frames + 1, dtype=np.float64)
        out = np.minimum(out, self.target) if sign > 0 else np.maximum(out, self.target)
        self.value = float(out[-1])
        return out.astype(np.float32)


class Drift:
    """A gain wandering at random between DRIFT, on smooth curves DRIFT_SECS long."""

    def __init__(self, rate, rng):
        self._rate = rate
        self._rng = rng
        self.value = float(rng.uniform(*DRIFT))
        self._aim()

    def _aim(self):
        self._start = self.value
        self._target = float(self._rng.uniform(*DRIFT))
        self._length = max(1, int(self._rng.uniform(*DRIFT_SECS) * self._rate))
        self._at = 0

    def gains(self, frames):
        """Return the gain of each of the next frames."""
        import numpy as np

        out = np.empty(frames, dtype=np.float32)
        done = 0
        while done < frames:
            taken = min(frames - done, self._length - self._at)
            along = (self._at + np.arange(taken)) / self._length
            out[done:done + taken] = (self._start + (self._target - self._start)
                                      * (1 - np.cos(np.pi * along)) / 2)
            self._at += taken
            done += taken
            if self._at == self._length:
                self.value = self._target
                self._aim()
        return out


class _Head:
    """One read position in a file, yielding stereo frames at rate until its stop."""

    def __init__(self, path, start, stop, rate):
        import numpy as np
        import soundfile

        self._file = soundfile.SoundFile(path)
        self._file.seek(start)
        self._left = stop - start
        self._channels = min(self._file.channels, 2)
        self._resampler = None
        if self._file.samplerate != rate:
            import soxr

            self._resampler = soxr.ResampleStream(self._file.samplerate, rate, self._channels,
                                                  dtype="float32")
        self._ready = np.zeros((0, 2), dtype=np.float32)

    def read(self, frames):
        import numpy as np

        while len(self._ready) < frames and self._left > 0:
            data = self._file.read(min(frames, self._left), dtype="float32",
                                   always_2d=True)[:, :self._channels]
            self._left = self._left - len(data) if len(data) else 0
            if self._resampler is not None:
                data = self._resampler.resample_chunk(data, last=self._left == 0)
            stereo = np.repeat(data, 2, axis=1) if self._channels == 1 else data
            self._ready = np.concatenate([self._ready, stereo])
        out, self._ready = self._ready[:frames], self._ready[frames:]
        if len(out) < frames:
            out = np.concatenate([out, np.zeros((frames - len(out), 2), np.float32)])
        return out

    def close(self):
        self._file.close()


class FileVoice:
    """A recording played at rate from random places, each crossfaded into the next at its level."""

    def __init__(self, layer, rate, rng):
        import soundfile

        info = soundfile.info(layer.path)
        start, stop = layer.span
        self._first = min(int(start * info.samplerate), info.frames)
        self._last = (info.frames if math.isinf(stop)
                      else min(info.frames, int(stop * info.samplerate)))
        self._ratio = rate / info.samplerate
        self._span = int((self._last - self._first) * self._ratio)
        if self._span < SHORTEST_SECS * rate:
            raise ValueError(f"{self._span / rate:.1f} s to play, under {SHORTEST_SECS:.0f} s")
        self._path = layer.path
        self._rate = rate
        self._rng = rng
        self._fade = min(int(CROSSFADE_SECS * rate), self._span // 3)
        self._shortest, self._longest = (int(secs * rate) for secs in SEGMENT_SECS)
        self._probe = soundfile.SoundFile(layer.path)
        self._probe_frames = max(1, min(int(PROBE_SECS * info.samplerate),
                                        int(self._fade / self._ratio)))
        self._stop = None
        self._current, length = self._head()
        self._until_cross = length - self._fade
        self._incoming = None
        self._incoming_length = 0
        self._crossed = 0

    def _head(self):
        """Open a segment at a random place, its level after the fade nearest the current one."""
        length = min(self._span, int(self._rng.integers(self._shortest, self._longest + 1)))
        length = max(length, 3 * self._fade)
        starts = self._first + (self._rng.integers(0, self._span - length + 1, CANDIDATES)
                                / self._ratio).astype(int)
        start = int(starts[0])
        if self._stop is not None:
            fade = int(self._fade / self._ratio)
            level = self._level(self._stop - fade - self._probe_frames)
            start = int(min(starts, key=lambda at: abs(self._level(at + fade) - level)))
        self._stop = min(self._last, start + math.ceil(length / self._ratio))
        return _Head(self._path, start, self._stop, self._rate), length

    def _level(self, at) -> float:
        """Return the level in dB of the probe's length of the recording from frame at."""
        import numpy as np

        self._probe.seek(max(self._first, at))
        data = self._probe.read(self._probe_frames, dtype="float32")
        return 10 * math.log10(float(np.mean(np.square(data))) + 1e-12) if len(data) else -120.0

    def render(self, frames):
        """Return the next frames, crossfading wherever a segment ends."""
        import numpy as np

        out = np.empty((frames, 2), dtype=np.float32)
        done = 0
        while done < frames:
            if self._incoming is None:
                taken = min(frames - done, self._until_cross)
                out[done:done + taken] = self._current.read(taken)
                self._until_cross -= taken
                done += taken
                if self._until_cross == 0:
                    self._incoming, self._incoming_length = self._head()
                    self._crossed = 0
                continue
            taken = min(frames - done, self._fade - self._crossed)
            angle = (self._crossed + np.arange(taken)) / self._fade * (np.pi / 2)
            out[done:done + taken] = (self._current.read(taken) * np.cos(angle)[:, None]
                                      + self._incoming.read(taken) * np.sin(angle)[:, None])
            self._crossed += taken
            done += taken
            if self._crossed == self._fade:
                self._current.close()
                self._current, self._incoming = self._incoming, None
                self._until_cross = self._incoming_length - 2 * self._fade
        return out

    def close(self):
        self._probe.close()
        for head in (self._current, self._incoming):
            if head is not None:
                head.close()


class NoiseVoice:
    """Endless stereo noise of one colour and band, shaped in the frequency domain."""

    def __init__(self, exponent, low, high, rate, rng):
        import numpy as np

        self._rng = rng
        freqs = np.fft.rfftfreq(NOISE_BLOCK, 1.0 / rate)
        freqs[0] = freqs[1]
        shape = (freqs ** (-exponent / 2) / np.sqrt(1 + (low / freqs) ** 4)
                 / np.sqrt(1 + (freqs / high) ** 4))
        shape[0] = 0.0
        self._shape = (shape / np.sqrt(np.mean(shape ** 2)))[:, None]
        self._window = np.sin(np.pi * (np.arange(NOISE_BLOCK) + 0.5) / NOISE_BLOCK)[:, None]
        self._tail = np.zeros((NOISE_BLOCK // 2, 2))
        self._ready = np.zeros((0, 2), dtype=np.float32)

    def _block(self):
        """Overlap-add one more windowed block, returning the half it completes."""
        import numpy as np

        white = self._rng.standard_normal((NOISE_BLOCK, 2))
        block = np.fft.irfft(np.fft.rfft(white, axis=0) * self._shape,
                             n=NOISE_BLOCK, axis=0) * self._window
        half = NOISE_BLOCK // 2
        done = self._tail + block[:half]
        self._tail = block[half:]
        return done.astype(np.float32)

    def render(self, frames):
        import numpy as np

        while len(self._ready) < frames:
            self._ready = np.concatenate([self._ready, self._block()])
        out, self._ready = self._ready[:frames], self._ready[frames:]
        return out

    def close(self):
        pass


class SceneMix:
    """One scene's layers summed, each wandering in level, under one fade."""

    def __init__(self, scene, rate, rng):
        self.scene = scene
        self.rate = rate
        self.fade = Ramp(0.0)
        self._voices = []
        if not scene.layers:
            for _, exponent, low, high, gain_db in NOISE_BANDS:
                self._add(NoiseVoice(exponent, low, high, rate, rng), gain_db, rng)
        for layer in scene.layers:
            try:
                self._add(FileVoice(layer, rate, rng), layer.gain_db, rng)
            except (OSError, RuntimeError, ValueError) as error:
                log.warning("Ambience layer %r is skipped: %s", layer.path, error)

    def _add(self, voice, gain_db, rng):
        self._voices.append((voice, 10 ** (gain_db / 20), Drift(self.rate, rng)))

    @property
    def silent(self) -> bool:
        return self.fade.value == 0.0 and self.fade.target == 0.0

    def render(self, frames):
        """Return the next frames of the mix, its fade an equal-power curve."""
        import numpy as np

        out = np.zeros((frames, 2), dtype=np.float32)
        for voice, gain, drift in self._voices:
            out += voice.render(frames) * (gain * drift.gains(frames))[:, None]
        return out * np.sin(self.fade.levels(frames) * (np.pi / 2))[:, None]

    def close(self):
        for voice, _, _ in self._voices:
            voice.close()


class Ambience:
    """Every scene still sounding, crossfading into the latest, under one volume."""

    def __init__(self, rate, volume, rng=None):
        import numpy as np

        self.rate = rate
        self._rng = rng if rng is not None else np.random.default_rng()
        self._volume = Ramp(volume)
        self._mixes = []

    @property
    def scene(self):
        """Return the scene playing or fading in, or None while all fade out."""
        live = [mix for mix in self._mixes if mix.fade.target > 0]
        return live[-1].scene if live else None

    @property
    def silent(self) -> bool:
        return not self._mixes

    def play(self, scene, secs):
        """Fade scene in over secs, and every other scene out."""
        for mix in self._mixes:
            if mix.scene != scene:
                mix.fade.to(0.0, secs * self.rate)
        mix = next((mix for mix in self._mixes if mix.scene == scene), None)
        if mix is None:
            mix = SceneMix(scene, self.rate, self._rng)
            self._mixes.append(mix)
        mix.fade.to(1.0, secs * self.rate)

    def hush(self, secs):
        """Fade every scene out over secs."""
        for mix in self._mixes:
            mix.fade.to(0.0, secs * self.rate)

    def set_volume(self, volume, secs):
        self._volume.to(volume, secs * self.rate)

    def render(self, frames):
        """Return the next frames, peaks above KNEE rounded off below full scale."""
        import numpy as np

        out = np.zeros((frames, 2), dtype=np.float32)
        for mix in self._mixes:
            out += mix.render(frames)
        for mix in [mix for mix in self._mixes if mix.silent]:
            mix.close()
            self._mixes.remove(mix)
        out *= (self._volume.levels(frames) ** 2)[:, None]
        peaks = np.abs(out) > KNEE
        out[peaks] = np.sign(out[peaks]) * (
            KNEE + (1 - KNEE) * np.tanh((np.abs(out[peaks]) - KNEE) / (1 - KNEE)))
        return out

    def close(self):
        for mix in self._mixes:
            mix.close()
        self._mixes.clear()
