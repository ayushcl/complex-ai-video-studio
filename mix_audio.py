#!/usr/bin/env python3
"""
Mix a voiceover MP3 with background music to produce final advert audio.

Phase 1 music pipeline (MVP): FFmpeg-only, no music generation or external APIs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mix voiceover MP3 with background music (FFmpeg)."
    )
    p.add_argument("--voice", help="Optional path to voiceover MP3.")
    p.add_argument(
        "--music",
        default="music/placeholder_music.mp3",
        help="Path to background music MP3 (default: music/placeholder_music.mp3).",
    )
    p.add_argument(
        "--out",
        default="music/final_mixed.mp3",
        help="Output mixed MP3 path (default: music/final_mixed.mp3).",
    )
    p.add_argument(
        "--report",
        default="music/mix_report.json",
        help="Mix report JSON path (default: music/mix_report.json).",
    )
    p.add_argument(
        "--music-volume",
        type=float,
        default=None,
        help=(
            "Background music level relative to source. "
            "Default: 0.12 with --voice, 1.0 in music-only mode."
        ),
    )
    p.add_argument(
        "--voice-volume",
        type=float,
        default=1.0,
        help="Voice level relative to source (default: 1.0).",
    )
    p.add_argument(
        "--fade-in",
        type=float,
        default=1.0,
        help="Music fade-in duration in seconds (default: 1.0).",
    )
    p.add_argument(
        "--fade-out",
        type=float,
        default=2.0,
        help="Music fade-out duration in seconds (default: 2.0).",
    )
    p.add_argument(
        "--tail-seconds",
        type=float,
        default=3.0,
        help="Duration in seconds that music continues after the voice ends (default: 3.0).",
    )
    p.add_argument(
        "--target-duration",
        type=float,
        help="Music-only target duration in seconds.",
    )
    p.add_argument(
        "--duration-from",
        help="Music-only media file whose duration should be matched.",
    )
    return p.parse_args()


def _require_executable(name: str, display_name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        raise SystemExit(
            f"{display_name} is required but was not found on PATH. "
            f"Install {display_name} and ensure it is available in your environment."
        )
    return exe


def _validate_input_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise SystemExit(f"{label} not found: {path}")


def _probe_duration_seconds(ffprobe_exe: str, path: Path) -> float:
    cmd = [
        ffprobe_exe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise SystemExit(
            f"FFprobe failed to read duration for {path}"
            + (f": {stderr}" if stderr else ".")
        ) from e

    raw = result.stdout.strip()
    if not raw:
        raise SystemExit(f"FFprobe returned no duration for {path}")
    try:
        duration = float(raw)
    except ValueError as e:
        raise SystemExit(
            f"FFprobe returned invalid duration for {path}: {raw!r}"
        ) from e
    if duration <= 0:
        raise SystemExit(f"FFprobe reported non-positive duration for {path}: {duration}")
    return duration


def _build_voice_mix_ffmpeg_command(
    *,
    ffmpeg_exe: str,
    voice_path: Path,
    music_path: Path,
    output_path: Path,
    voice_duration: float,
    output_duration: float,
    music_volume: float,
    voice_volume: float,
    fade_in: float,
    fade_out: float,
) -> list[str]:
    fade_out_start = max(0.0, output_duration - fade_out)
    filter_complex = (
        f"[1:a]atrim=0:{output_duration:.6f},asetpts=PTS-STARTPTS,"
        f"volume={music_volume:.6g},"
        f"afade=t=in:st=0:d={fade_in:.6f},"
        f"afade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f}[music];"
        f"[0:a]volume={voice_volume:.6g},apad=whole_dur={output_duration:.6f}[voice];"
        f"[voice][music]amix=inputs=2:duration=first:dropout_transition=0,"
        f"alimiter=limit=0.95:attack=5:release=50[out]"
    )
    return [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(voice_path),
        "-stream_loop",
        "-1",
        "-i",
        str(music_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-t",
        f"{output_duration:.6f}",
        str(output_path),
    ]


def _build_music_only_ffmpeg_command(
    *,
    ffmpeg_exe: str,
    music_path: Path,
    output_path: Path,
    output_duration: float,
    music_volume: float,
    fade_in: float,
    fade_out: float,
) -> list[str]:
    fade_out_start = max(0.0, output_duration - fade_out)
    filter_complex = (
        f"[0:a]atrim=0:{output_duration:.6f},asetpts=PTS-STARTPTS,"
        f"volume={music_volume:.6g},"
        f"afade=t=in:st=0:d={fade_in:.6f},"
        f"afade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f}[out]"
    )
    return [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(music_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-t",
        f"{output_duration:.6f}",
        str(output_path),
    ]


def _collect_warnings(
    *,
    voice_duration: float,
    output_duration: float,
    music_duration: float,
    fade_in: float,
    fade_out: float,
) -> list[str]:
    warnings: list[str] = []
    if music_duration < output_duration:
        warnings.append(
            f"Music ({music_duration:.3f}s) is shorter than output duration ({output_duration:.3f}s); "
            "music was looped to cover the full mix duration."
        )
    if fade_in + fade_out > output_duration:
        warnings.append(
            f"Fade-in ({fade_in:.3f}s) plus fade-out ({fade_out:.3f}s) exceeds voice "
            f"duration including tail ({output_duration:.3f}s); fades may overlap."
        )
    if fade_out > output_duration:
        warnings.append(
            f"Fade-out ({fade_out:.3f}s) exceeds mix duration ({output_duration:.3f}s); "
            "fade-out start was clamped to 0."
        )
    return warnings


def _resolve_music_only_duration(args: argparse.Namespace, ffprobe_exe: str) -> tuple[float, dict[str, str | float]]:
    has_target_duration = args.target_duration is not None
    has_duration_from = bool(args.duration_from)
    if has_target_duration == has_duration_from:
        raise SystemExit(
            "Music-only mode requires exactly one of --target-duration or --duration-from."
        )

    if has_target_duration:
        target_duration = float(args.target_duration)
        if target_duration <= 0:
            raise SystemExit("--target-duration must be greater than 0")
        return target_duration, {
            "type": "target_duration",
            "seconds": target_duration,
        }

    duration_from_path = Path(args.duration_from).expanduser().resolve()
    _validate_input_file(duration_from_path, "Duration source file")
    target_duration = _probe_duration_seconds(ffprobe_exe, duration_from_path)
    return target_duration, {
        "type": "duration_from",
        "path": str(duration_from_path),
        "seconds": target_duration,
    }


def _run_ffmpeg(ffmpeg_cmd: list[str], output_path: Path) -> None:
    try:
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise SystemExit(
            "FFmpeg mix failed"
            + (f":\n{stderr}" if stderr else ".")
        ) from e

    if not output_path.is_file():
        raise SystemExit(f"FFmpeg completed but output file was not created: {output_path}")


def main() -> None:
    args = parse_args()

    voice_path = Path(args.voice).expanduser().resolve() if args.voice else None
    music_path = Path(args.music).expanduser().resolve()
    output_path = Path(args.out).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve()

    if voice_path is not None:
        _validate_input_file(voice_path, "Voice file")
    _validate_input_file(music_path, "Music file")

    ffmpeg_exe = _require_executable("ffmpeg", "FFmpeg")
    ffprobe_exe = _require_executable("ffprobe", "FFprobe")

    mode = "voice_mix" if voice_path is not None else "music_only"
    music_duration = _probe_duration_seconds(ffprobe_exe, music_path)
    music_volume = args.music_volume
    if music_volume is None:
        music_volume = 0.12 if mode == "voice_mix" else 1.0

    tail_seconds = float(args.tail_seconds)
    if tail_seconds < 0:
        raise SystemExit("tail-seconds must be >= 0")

    if mode == "voice_mix":
        voice_duration = _probe_duration_seconds(ffprobe_exe, voice_path)
        output_duration = voice_duration + tail_seconds
        duration_source = {
            "type": "voice_plus_tail",
            "voice_file": str(voice_path),
            "voice_duration_seconds": voice_duration,
            "tail_seconds": tail_seconds,
        }
        warnings = _collect_warnings(
            voice_duration=voice_duration,
            output_duration=output_duration,
            music_duration=music_duration,
            fade_in=args.fade_in,
            fade_out=args.fade_out,
        )
    else:
        voice_duration = None
        output_duration, duration_source = _resolve_music_only_duration(args, ffprobe_exe)
        warnings = _collect_warnings(
            voice_duration=0.0,
            output_duration=output_duration,
            music_duration=music_duration,
            fade_in=args.fade_in,
            fade_out=args.fade_out,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "voice_mix":
        ffmpeg_cmd = _build_voice_mix_ffmpeg_command(
            ffmpeg_exe=ffmpeg_exe,
            voice_path=voice_path,
            music_path=music_path,
            output_path=output_path,
            voice_duration=voice_duration,
            output_duration=output_duration,
            music_volume=music_volume,
            voice_volume=args.voice_volume,
            fade_in=args.fade_in,
            fade_out=args.fade_out,
        )
    else:
        ffmpeg_cmd = _build_music_only_ffmpeg_command(
            ffmpeg_exe=ffmpeg_exe,
            music_path=music_path,
            output_path=output_path,
            output_duration=output_duration,
            music_volume=music_volume,
            fade_in=args.fade_in,
            fade_out=args.fade_out,
        )

    _run_ffmpeg(ffmpeg_cmd, output_path)

    report = {
        "mode": mode,
        "voice_file": str(voice_path) if voice_path is not None else None,
        "music_file": str(music_path),
        "output_file": str(output_path),
        "duration_source": duration_source,
        "voice_duration_seconds": round(voice_duration, 6) if voice_duration is not None else None,
        "music_duration_seconds": round(music_duration, 6),
        "output_duration_seconds": round(output_duration, 6),
        "tail_seconds": tail_seconds,
        "music_volume": music_volume,
        "voice_volume": args.voice_volume,
        "fade_in_seconds": args.fade_in,
        "fade_out_seconds": args.fade_out,
        "ffmpeg_command_used": ffmpeg_cmd,
        "warnings": warnings,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"Mixed audio saved to {output_path}")
    print(f"Mix report saved to {report_path}")
    if warnings:
        for w in warnings:
            print(f"Warning: {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
