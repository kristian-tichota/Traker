#!/usr/bin/env python3

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.desktop import ambience  # noqa: E402
from src.profile import UserProfile  # noqa: E402

TIMEOUT_S = 60
PAUSE_S = 1.0
WORKERS = 4
AGENT = "Traker ambience bank (https://github.com/kristian-tichota/Traker)"
PREVIEW = "https://cdn.freesound.org/previews/{folder}/{id}_{user_id}-hq.ogg"
SOURCE = "https://freesound.org/s/{id}/"


class Recording(NamedTuple):
    """One Freesound recording of a scene, with the gain and span it plays at."""

    id: int
    user_id: int
    author: str
    licence: str
    title: str
    gain_db: float
    span: tuple


SCENES = {
    "rain": (
        Recording(169031, 7037, "tim.kahn", "CC-BY-4.0", "light forest rain.wav",
                  10.6, (205.0, 490.0)),
        Recording(592997, 11710404, "Petrosilia", "CC0", "heavy rain on a small tent",
                  5.3, (320.0, 670.0)),
        Recording(795397, 16961272, "Guillermo_de_La_Matera", "CC-BY-4.0",
                  "El agua de lluvia cae por el canalón del techo (Rainwater falls through the "
                  "roof gutter)",
                  0.8, (300.0, 735.0)),
        Recording(168562, 2843367, "MrAuralization", "CC-BY-4.0", "Rain with distant thunder",
                  11.6, (5.0, 470.0)),
    ),
    "storm": (
        Recording(437133, 1661766, "felix.blume", "CC0",
                  "Thunder and rain in south of France during summer",
                  -3.1, (109.0, 1230.0)),
        Recording(119065, 28867, "inchadney", "CC-BY-4.0", "thunder storm.wav",
                  15.7, (5.0, 364.0)),
        Recording(105272, 28867, "inchadney", "CC-BY-4.0", "strong wind in the forest.WAV",
                  -4.5, (5.0, 290.0)),
        Recording(645682, 2061858, "Garuda1982", "CC-BY-4.0",
                  "light thunderstorm in the forest at night",
                  3.1, (5.0, 1676.0)),
    ),
    "ocean": (
        Recording(197792, 154509, "DrNI", "CC0", "Fehmarn-Sea-Waves-404-1.flac",
                  -2.6, (5.0, 719.0)),
        Recording(362300, 1857065, "kingsrow", "CC0", "2016-10-11-DR-05-Ocean Waves-EDITED.wav",
                  -1.7, (150.0, 1375.0)),
        Recording(785566, 10711943, "Sandy-Ogilvie", "CC0",
                  "Small waves washing over and through sand, shells and shingle",
                  14.2, (5.0, 1450.0)),
        Recording(167405, 8043, "dobroide", "CC-BY-4.0", "20121014_surf_distant_08.flac",
                  0.4, (5.0, 376.0)),
    ),
    "stream": (
        Recording(730159, 12768873, "lastraindrop", "CC0",
                  "Stream flow over the stones in the fields in spring",
                  8.2, (5.0, 480.0)),
        Recording(730828, 15715496, "alenym7", "CC0", "stream",
                  -1.4, (100.0, 860.0)),
        Recording(578068, 7241289, "BurghRecords", "CC0", "Calm Stream In Forest.wav",
                  8.8, (5.0, 461.0)),
        Recording(184731, 7037, "tim.kahn", "CC-BY-4.0", "2013-04-12 falls creek falls.WAV",
                  -10.0, (5.0, 297.0)),
    ),
    "forest": (
        Recording(564158, 7455632, "naturenotesuk", "CC0", "Norsey Wood Soundscape",
                  -3.5, (5.0, 457.0)),
        Recording(649028, 3571340, "AtoMediaDesign", "CC-BY-4.0",
                  "Birds singing in the forest at morning",
                  -3.2, (360.0, 696.0)),
        Recording(718411, 11519060, "bruno.auzet", "CC0", "sweet wind in automn foliage",
                  11.3, (5.0, 112.0)),
        Recording(477187, 2014656, "doxent", "CC0", "Summer forest winds 18 July 2019",
                  25.7, (120.0, 800.0)),
    ),
    "night": (
        Recording(476116, 1661766, "felix.blume", "CC0",
                  "Toads and frogs during the night in the desert (San Luis Potosi, Mexico)",
                  -11.4, (5.0, 1250.0)),
        Recording(197328, 591879, "jymdavis", "CC0", "Summer night in Georgia",
                  10.3, (5.0, 600.0)),
        Recording(645706, 13222620, "MeliaRoger", "CC0",
                  "AMBRurl_BR Serrinha do alambari night frogs chorus with close crickets_Melia "
                  "Roger_ORTF Schoeps.WAV",
                  6.2, (5.0, 523.0)),
        Recording(647289, 1661766, "felix.blume", "CC0",
                  "Wind slightly shaking trees at night, with very light rain, few birds sing far"
                  " in the countryside in Nebraska",
                  4.9, (5.0, 567.0)),
    ),
    "wind": (
        Recording(105272, 28867, "inchadney", "CC-BY-4.0", "strong wind in the forest.WAV",
                  0.5, (5.0, 290.0)),
        Recording(647289, 1661766, "felix.blume", "CC0",
                  "Wind slightly shaking trees at night, with very light rain, few birds sing far"
                  " in the countryside in Nebraska",
                  10.1, (5.0, 567.0)),
        Recording(718411, 11519060, "bruno.auzet", "CC0", "sweet wind in automn foliage",
                  10.9, (5.0, 112.0)),
        Recording(477187, 2014656, "doxent", "CC0", "Summer forest winds 18 July 2019",
                  25.2, (120.0, 800.0)),
    ),
    "fire": (
        Recording(257371, 4415905, "YleArkisto", "CC-BY-4.0",
                  "Tulipalo, talo palaa / Big fire, a house burning, flames humming and crackling",
                  2.3, (5.0, 237.0)),
        Recording(83986, 28867, "inchadney", "CC-BY-4.0", "Fireplace.wav",
                  14.0, (5.0, 420.0)),
        Recording(132534, 28867, "inchadney", "CC0", "Fireplace.wav",
                  9.5, (5.0, 255.0)),
    ),
    "blizzard": (
        Recording(816508, 962598, "pblzr", "CC0", "AMBIENCE_INTERIOR_WIND_NOISE_WINDOW",
                  9.8, (62.0, 290.0)),
        Recording(454371, 612689, "kyles", "CC0",
                  "wind strong gusty storm form inside, battering kitchen windows.flac",
                  10.0, (503.0, 880.0)),
        Recording(575287, 97550, "TRP", "CC0", "window wind moans long.flac",
                  -4.1, (5.0, 1100.0)),
        Recording(83986, 28867, "inchadney", "CC-BY-4.0", "Fireplace.wav",
                  2.2, (5.0, 420.0)),
    ),
}


def fetch(recording, target) -> bool:
    """Download one recording's 192 kbps Vorbis preview to target, unless present."""
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return True
    url = PREVIEW.format(folder=recording.id // 1000, id=recording.id,
                         user_id=recording.user_id)
    partial = target + ".part"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as answer, \
                open(partial, "wb") as out:
            while chunk := answer.read(1 << 16):
                out.write(chunk)
    except (urllib.error.URLError, OSError) as error:
        print(f"  {recording.id}: {error}", file=sys.stderr)
        if os.path.exists(partial):
            os.remove(partial)
        return False
    os.replace(partial, target)
    time.sleep(PAUSE_S)
    return True


def manifest(recordings) -> str:
    """Return scene.toml for the recordings, credits included."""
    said = ["# Fetched from freesound.org by scripts/fetch_ambience.py.\n"]
    for recording in recordings:
        start, stop = recording.span
        said.append(
            f"[[layer]]\n"
            f"file = \"{recording.id}.ogg\"\n"
            f"gain_db = {recording.gain_db:.1f}\n"
            f"span = [{start:.1f}, {stop:.1f}]\n"
            f"title = {json.dumps(recording.title, ensure_ascii=False)}\n"
            f"author = {json.dumps(recording.author, ensure_ascii=False)}\n"
            f"licence = \"{recording.licence}\"\n"
            f"source = \"{SOURCE.format(id=recording.id)}\"\n")
    return "\n".join(said)


def place(source, target):
    """Link or copy a fetched recording into another scene's folder, unless present."""
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download the curated ambience scenes into the bank.")
    parser.add_argument("scenes", nargs="*", metavar="SCENE",
                        help=f"scenes to fetch, of {', '.join(SCENES)}; none means all")
    parser.add_argument("--bank", help="the bank folder; default [strict_break.ambience] path")
    args = parser.parse_args()

    unknown = set(args.scenes) - set(SCENES)
    if unknown:
        parser.error(f"no such scene: {', '.join(sorted(unknown))}")
    bank = os.path.abspath(os.path.expanduser(args.bank)) if args.bank \
        else ambience.bank_for(UserProfile())
    names = args.scenes or list(SCENES)

    first = {}
    for name in names:
        os.makedirs(os.path.join(bank, name), exist_ok=True)
        for recording in SCENES[name]:
            first.setdefault(recording.id, os.path.join(bank, name, f"{recording.id}.ogg"))
    recordings = {recording.id: recording for name in names for recording in SCENES[name]}
    with ThreadPoolExecutor(WORKERS) as pool:
        done = dict(zip(first, pool.map(fetch, [recordings[n] for n in first], first.values())))

    failed = 0
    for name in names:
        folder = os.path.join(bank, name)
        fetched = [recording for recording in SCENES[name] if done[recording.id]]
        for recording in fetched:
            place(first[recording.id], os.path.join(folder, f"{recording.id}.ogg"))
        failed += len(SCENES[name]) - len(fetched)
        print(f"{name} -> {folder}: {len(fetched)} of {len(SCENES[name])}")
        with open(os.path.join(folder, ambience.MANIFEST), "w", encoding="utf-8") as out:
            out.write(manifest(fetched))
    if failed:
        print(f"{failed} recording(s) could not be fetched; run again to retry.",
              file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
