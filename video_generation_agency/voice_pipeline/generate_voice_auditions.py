#!/usr/bin/env python3
"""
Batch-generate audition MP3s for shortlisted voices in selected_voices.json.

Runs prepare_selected_voice.py then segments_to_audio.py per rank (human still picks the winner).
Does not read or rewrite audition_packet.json; timing is preserved by passing the file path only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent
PREPARE_SCRIPT = REPO_ROOT / "prepare_selected_voice.py"
SEGMENTS_SCRIPT = REPO_ROOT / "segments_to_audio.py"
DEFAULT_OUTPUT_MP3 = REPO_ROOT / "output.mp3"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate audition MP3s for each shortlisted voice in selected_voices.json."
    )
    p.add_argument(
        "--selected",
        default="selected_voices.json",
        help="Path to selected_voices.json (default: selected_voices.json).",
    )
    p.add_argument(
        "--sample",
        default="audition_packet.json",
        help="Path to segment JSON passed to segments_to_audio.py --segments (default: audition_packet.json).",
    )
    p.add_argument(
        "--out-dir",
        default="auditions",
        help="Output directory for MP3s and temp prepared JSON (default: auditions).",
    )
    p.add_argument(
        "--count",
        type=int,
        default=10,
        help="Maximum number of voices to audition (default: 10).",
    )
    p.add_argument(
        "--python",
        default="python3",
        help="Python executable used to run prepare_selected_voice.py and segments_to_audio.py (default: python3).",
    )
    return p.parse_args()


def load_selected_voices(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise SystemExit(f"Could not read {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must be a JSON object.")
    return data


def build_ranked_voices(data: dict, count: int) -> list[tuple[int, dict]]:
    """Rank 1 = recommended_voice; ranks 2+ from alternatives, sorted by rank. Capped at count."""
    rec = data.get("recommended_voice")
    if not isinstance(rec, dict):
        raise SystemExit("selected_voices.json: missing or invalid 'recommended_voice' object.")

    rows: list[tuple[int, dict]] = [(1, rec)]
    alts = data.get("alternatives")
    if isinstance(alts, list):
        for item in alts:
            if not isinstance(item, dict):
                continue
            r = item.get("rank")
            if r is None:
                continue
            try:
                ri = int(r)
            except (TypeError, ValueError):
                continue
            if ri >= 2:
                rows.append((ri, item))

    rows.sort(key=lambda x: x[0])
    seen: set[int] = set()
    unique: list[tuple[int, dict]] = []
    for r, d in rows:
        if r in seen:
            continue
        seen.add(r)
        unique.append((r, d))
    return unique[:count]


def slugify_voice_name(name: str, max_len: int = 48) -> str:
    """Lowercase filename slug: spaces -> underscores, strip specials, cap length."""
    s = (name or "").lower().strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s or "voice"


def display_label(voice_name: str, max_chars: int = 56) -> str:
    n = (voice_name or "Unknown").strip()
    if len(n) > max_chars:
        return n[: max_chars - 1] + "…"
    return n


def run_subprocess(
    argv: list[str],
    *,
    cwd: Path,
) -> tuple[int, str, str]:
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return proc.returncode, out, err


def main() -> None:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be at least 1.")

    selected_path = Path(args.selected).expanduser()
    if not selected_path.is_absolute():
        selected_path = (Path.cwd() / selected_path).resolve()
    else:
        selected_path = selected_path.resolve()

    sample_path = Path(args.sample).expanduser()
    if not sample_path.is_absolute():
        sample_path = (Path.cwd() / sample_path).resolve()
    else:
        sample_path = sample_path.resolve()

    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        out_dir = (Path.cwd() / out_dir).resolve()
    else:
        out_dir = out_dir.resolve()

    if not selected_path.is_file():
        raise SystemExit(f"Selected voices file not found: {selected_path}")
    if not sample_path.is_file():
        raise SystemExit(f"Sample / segments file not found: {sample_path}")
    if not PREPARE_SCRIPT.is_file():
        raise SystemExit(f"Missing script: {PREPARE_SCRIPT}")
    if not SEGMENTS_SCRIPT.is_file():
        raise SystemExit(f"Missing script: {SEGMENTS_SCRIPT}")

    data = load_selected_voices(selected_path)
    batch = build_ranked_voices(data, args.count)
    if not batch:
        raise SystemExit("No voices to audition (empty batch).")

    out_dir.mkdir(parents=True, exist_ok=True)

    py = args.python
    successes: list[str] = []
    failures: list[tuple[int, str]] = []
    manifest_entries = []

    total = len(batch)
    for i, (rank, voice) in enumerate(batch, start=1):
        voice_name = str(voice.get("voice_name", "") or "Unknown")
        label = display_label(voice_name)
        print(f"Generating audition {i}/{total}: {label}")

        prepared_path = out_dir / f"prepared_rank_{rank:02d}.json"
        slug = slugify_voice_name(voice_name)
        final_mp3 = out_dir / f"rank_{rank:02d}_{slug}.mp3"

        prepare_argv = [
            py,
            str(PREPARE_SCRIPT),
            "--selected",
            str(selected_path),
            "--out",
            str(prepared_path),
            "--rank",
            str(rank),
        ]
        try:
            rc, out, err = run_subprocess(prepare_argv, cwd=REPO_ROOT)
            if rc != 0:
                msg = err or out or f"exit code {rc}"
                print(f"  Error (prepare rank {rank}): {msg}", file=sys.stderr)
                failures.append((rank, f"prepare_selected_voice: {msg}"))
                continue

            segments_argv = [
                py,
                str(SEGMENTS_SCRIPT),
                "--segments",
                str(sample_path),
                "--prepared-voice",
                str(prepared_path),
            ]
            rc2, out2, err2 = run_subprocess(segments_argv, cwd=REPO_ROOT)
            if rc2 != 0:
                msg = err2 or out2 or f"exit code {rc2}"
                print(f"  Error (segments rank {rank}): {msg}", file=sys.stderr)
                failures.append((rank, f"segments_to_audio: {msg}"))
                continue

            if not DEFAULT_OUTPUT_MP3.is_file():
                msg = f"Expected {DEFAULT_OUTPUT_MP3} after segments_to_audio; not found."
                print(f"  Error (rank {rank}): {msg}", file=sys.stderr)
                failures.append((rank, msg))
                continue

            try:
                if final_mp3.exists():
                    final_mp3.unlink()
                shutil.move(str(DEFAULT_OUTPUT_MP3), str(final_mp3))
            except OSError as e:
                print(f"  Error (move output.mp3 rank {rank}): {e}", file=sys.stderr)
                failures.append((rank, f"move output: {e}"))
                continue

            # Capture audition metadata for the Simple-picker manifest BEFORE the temp JSON is removed.
            workspace_voice_id = None
            try:
                if prepared_path.exists():
                    prepared_data = json.loads(prepared_path.read_text(encoding="utf-8"))
                    workspace_voice_id = prepared_data.get("workspace_voice_id")
            except (OSError, ValueError) as e:
                print(f"  Warning: could not read prepared metadata for rank {rank}: {e}", file=sys.stderr)

            if workspace_voice_id:
                manifest_entries.append({
                    "file": final_mp3.name,
                    "workspace_voice_id": workspace_voice_id,
                    "label": voice_name,
                    "notes": voice.get("reason") or None,
                })
            else:
                # mp3 exists but no usable workspace_voice_id -> NOT pickable by Simple.
                # Record as a failure so the operator sees it in the summary (not a silent 10->9).
                msg = "audition generated but no workspace_voice_id; not added to manifest (unpickable)"
                print(f"  Warning (rank {rank}): {msg}", file=sys.stderr)
                failures.append((rank, msg))

            if prepared_path.exists():
                try:
                    prepared_path.unlink()
                except OSError as e:
                    print(f"  Warning: could not remove {prepared_path}: {e}", file=sys.stderr)

            try:
                rel = final_mp3.relative_to(Path.cwd())
            except ValueError:
                rel = final_mp3
            print(f"Saved {rel}")
            successes.append(str(rel))
        except Exception as e:
            print(f"  Error (rank {rank}): {e}", file=sys.stderr)
            failures.append((rank, str(e)))

    # Write the Simple-picker manifest so the audition folder is directly pickable.
    if manifest_entries:
        manifest_path = out_dir / "auditions_manifest.json"
        try:
            manifest_path.write_text(
                json.dumps({"auditions": manifest_entries}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Wrote {manifest_path.name} ({len(manifest_entries)} pickable voices)")
        except OSError as e:
            print(f"  Warning: could not write auditions manifest: {e}", file=sys.stderr)

    print()
    print("Summary")
    print(f"  Successful: {len(successes)}/{total}")
    for p in successes:
        print(f"    - {p}")
    print(f"  Failed: {len(failures)}/{total}")
    for rank, reason in failures:
        print(f"    - rank {rank}: {reason}")

    if failures and not successes:
        sys.exit(1)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
