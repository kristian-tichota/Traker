import numpy as np
import pytest
import soundfile

from src.desktop import ambience

RATE = 8000


def recording(path, seconds, level=0.1, rate=RATE, seed=0):
    noise = np.random.default_rng(seed).standard_normal((int(seconds * rate), 2)) * level
    soundfile.write(path, noise.astype(np.float32), rate)
    return str(path)


def rendered(source, seconds, block=4096):
    frames = int(seconds * RATE)
    return np.concatenate([source.render(block) for _ in range(frames // block + 1)])[:frames]


def windowed_rms(signal, seconds=0.1):
    width = int(seconds * RATE)
    trimmed = signal[:len(signal) // width * width]
    return np.sqrt((trimmed.reshape(-1, width, signal.shape[1]) ** 2).mean(axis=(1, 2)))


def test_the_bank_lists_its_folders_and_noise_in_name_order(tmp_path):
    for name in ("stream", "Rain"):
        (tmp_path / name).mkdir()
        recording(tmp_path / name / "a.flac", 4)
    (tmp_path / "empty").mkdir()
    (tmp_path / ".hidden").mkdir()
    recording(tmp_path / ".hidden" / "a.flac", 4)

    assert [scene.name for scene in ambience.scenes(tmp_path)] == ["noise", "Rain", "stream"]


def test_a_missing_bank_still_offers_noise(tmp_path):
    assert ambience.scenes(tmp_path / "absent") == [ambience.Scene(ambience.NOISE)]


def test_a_manifest_names_each_layers_gain_and_span(tmp_path):
    recording(tmp_path / "bed.flac", 4)
    (tmp_path / ambience.MANIFEST).write_text(
        '[[layer]]\nfile = "bed.flac"\ngain_db = -6.5\nspan = [1.0, 3.0]\n\n'
        '[[layer]]\nfile = "gone.flac"\n', encoding="utf-8")

    scene = ambience.read_scene(tmp_path)

    assert scene.layers == (ambience.Layer(str(tmp_path / "bed.flac"), -6.5, (1.0, 3.0)),)


def test_segments_join_without_a_dip(tmp_path):
    layer = ambience.Layer(recording(tmp_path / "bed.flac", 200))
    voice = ambience.FileVoice(layer, RATE, np.random.default_rng(1))

    levels = windowed_rms(rendered(voice, 400))

    assert levels.min() > 0.8 * np.median(levels)


def test_nothing_outside_the_span_plays(tmp_path):
    quiet = np.random.default_rng(2).standard_normal((60 * RATE, 2)) * 0.01
    quiet[:10 * RATE] = quiet[50 * RATE:] = 0.9
    soundfile.write(tmp_path / "bed.flac", quiet.astype(np.float32), RATE)
    layer = ambience.Layer(str(tmp_path / "bed.flac"), 0.0, (10.0, 50.0))
    voice = ambience.FileVoice(layer, RATE, np.random.default_rng(3))

    assert np.abs(rendered(voice, 300)).max() < 0.1


def test_a_layer_at_another_rate_is_left_out(tmp_path):
    layer = ambience.Layer(recording(tmp_path / "bed.flac", 10, rate=2 * RATE))

    with pytest.raises(ValueError):
        ambience.FileVoice(layer, RATE, np.random.default_rng(4))


def test_each_layer_drifts_within_its_bounds():
    drift = ambience.Drift(RATE, np.random.default_rng(5))

    gains = np.concatenate([drift.gains(4096) for _ in range(600 * RATE // 4096)])

    assert ambience.DRIFT[0] <= gains.min() and gains.max() <= ambience.DRIFT[1]


def test_noise_is_wide_and_steady():
    mix = ambience.Ambience(RATE, 1.0, np.random.default_rng(6))
    mix.play(ambience.Scene(ambience.NOISE), 0.01)

    out = rendered(mix, 30)[RATE:]

    assert abs(np.corrcoef(out[:, 0], out[:, 1])[0, 1]) < 0.1
    assert windowed_rms(out).min() > 0.2 * np.median(windowed_rms(out))


def test_a_hushed_mix_falls_silent_and_lets_go(tmp_path):
    scene = ambience.Scene("rain", (ambience.Layer(recording(tmp_path / "bed.flac", 20)),))
    mix = ambience.Ambience(RATE, 1.0, np.random.default_rng(7))
    mix.play(scene, 1.0)
    rendered(mix, 3)

    mix.hush(1.0)
    tail = rendered(mix, 3)

    assert mix.silent and not tail[-RATE:].any()


def test_a_new_scene_crossfades_in_as_the_old_one_leaves(tmp_path):
    rain = ambience.Scene("rain", (ambience.Layer(recording(tmp_path / "a.flac", 20)),))
    stream = ambience.Scene("stream", (ambience.Layer(recording(tmp_path / "b.flac", 20)),))
    mix = ambience.Ambience(RATE, 1.0, np.random.default_rng(8))
    mix.play(rain, 0.01)
    rendered(mix, 1)

    mix.play(stream, 2.0)
    rendered(mix, 3)

    assert mix.scene == stream and len(mix._mixes) == 1
