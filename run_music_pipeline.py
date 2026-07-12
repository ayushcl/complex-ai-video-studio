#!/usr/bin/env python3
"""Run music generation and voice/music mixing as one command."""

import argparse
import subprocess
import sys
from pathlib import Path


MUSIC_PATH = "music/background_music.mp3"
FINAL_MIX_PATH = "music/final_mixed.mp3"
MIX_REPORT_PATH = "music/mix_report.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate music, then mix with voice.")
    parser.add_argument("voice", help="Path to the voice MP3")
    parser.add_argument("--storyboard", default="storyboard.json")
    parser.add_argument("--music-volume", type=float, default=0.12)
    parser.add_argument("--tail-seconds", type=float, default=3.0)
    return parser.parse_args()


def run_step(label, command):
    print(f"\n=== {label} ===", flush=True)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Error: {label} failed with exit code {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1
    return 0


def main():
    args = parse_args()
    voice_path = Path(args.voice)
    if not voice_path.exists():
        print(f"Error: voice file does not exist: {voice_path}", file=sys.stderr)
        return 1

    code = run_step(
        "STEP 1/2: Generating music",
        [
            sys.executable, "generate_music.py",
            "--voice", str(voice_path),
            "--storyboard", args.storyboard,
        ],
    )
    if code:
        return code

    code = run_step(
        "STEP 2/2: Mixing voice and music",
        [
            sys.executable, "mix_audio.py",
            "--voice", str(voice_path),
            "--music", MUSIC_PATH,
            "--out", FINAL_MIX_PATH,
            "--report", MIX_REPORT_PATH,
            "--music-volume", str(args.music_volume),
            "--tail-seconds", str(args.tail_seconds),
        ],
    )
    if code:
        return code

    print(f"\n=== DONE: {FINAL_MIX_PATH} ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
