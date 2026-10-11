#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import NamedTuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.desktop import ambience  # noqa: E402
from src.profile import UserProfile  # noqa: E402

TIMEOUT_S = 60
PAUSE_S = 1.0
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


SCENES = {}


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

    failed = 0
    for name in args.scenes or SCENES:
        folder = os.path.join(bank, name)
        os.makedirs(folder, exist_ok=True)
        print(f"{name} -> {folder}")
        fetched = [recording for recording in SCENES[name]
                   if fetch(recording, os.path.join(folder, f"{recording.id}.ogg"))]
        failed += len(SCENES[name]) - len(fetched)
        with open(os.path.join(folder, ambience.MANIFEST), "w", encoding="utf-8") as out:
            out.write(manifest(fetched))
    if failed:
        print(f"{failed} recording(s) could not be fetched; run again to retry.",
              file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
