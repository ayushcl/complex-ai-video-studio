import argparse

# --- Asymmetric sync-fit policy (used in sync-fit mode only) ---
def _underfilled_quality_risk(unfilled_gap_seconds: float) -> str:
    """Quality risk for under-filled sync window (no stretch)."""
    if unfilled_gap_seconds <= 0.5:
        return "low"
    if unfilled_gap_seconds <= 1.5:
        return "medium"
    return "high"
import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Optional

from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from pydub import AudioSegment

load_dotenv()

# Default workspace voice id when --prepared-voice is not used (not secret).
VOICE_ID = "4Ihiyat2AFvCRGQ2Hycm"

DEFAULT_MODEL_ID = "eleven_v3"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_FRAME_RATE = 44100
DEFAULT_CHANNELS = 2
DEFAULT_TAIL_TOLERANCE_SECONDS = 0.35


_TIMECODE_RE = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\s*$")


@dataclass(frozen=True)
class Segment:
    start_time_seconds: float
    target_duration_seconds: float
    text: str
    segment_id: Optional[str] = None
    start_raw: Optional[str] = None


def _parse_start_time_seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError("start_time must be >= 0")
        return float(value)

    if not isinstance(value, str):
        raise TypeError("start_time must be a number of seconds or a timecode string")

    s = value.strip()
    if s == "":
        raise ValueError("start_time cannot be empty")

    # Allow plain numeric strings ("12.34")
    try:
        n = float(s)
        if n < 0:
            raise ValueError("start_time must be >= 0")
        return n
    except ValueError:
        pass

    # Timecode: [H:]MM:SS[.mmm]
    m = _TIMECODE_RE.match(s)
    if not m:
        raise ValueError(f"Unrecognized start_time format: {value!r}")

    hours = int(m.group(1) or 0)
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    millis = int((m.group(4) or "0").ljust(3, "0")[:3])

    total = hours * 3600 + minutes * 60 + seconds + (millis / 1000.0)
    if total < 0:
        raise ValueError("start_time must be >= 0")
    return total


def _read_segments(path: str) -> list[Segment]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, dict) and "segments" in payload:
        payload = payload["segments"]

    if not isinstance(payload, list):
        raise TypeError(
            "segments.json must be a JSON array of segment objects "
            "(or an object with a 'segments' key)"
        )

    segments: list[Segment] = []
    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            raise TypeError(f"segments[{i}] must be an object")

        if "start_time" not in item and "start" not in item:
            raise KeyError(
                f"segments[{i}] missing required field: start_time or start"
            )
        if "target_duration_seconds" not in item:
            raise KeyError(f"segments[{i}] missing required field: target_duration_seconds")
        if "text" not in item:
            raise KeyError(f"segments[{i}] missing required field: text")

        start_raw = item["start_time"] if "start_time" in item else item["start"]
        start_time_seconds = _parse_start_time_seconds(start_raw)
        if isinstance(start_raw, str):
            start_raw_str: Optional[str] = start_raw.strip()
        else:
            start_raw_str = None
        target_duration_seconds = float(item["target_duration_seconds"])
        if not math.isfinite(target_duration_seconds) or target_duration_seconds <= 0:
            raise ValueError(f"segments[{i}].target_duration_seconds must be > 0")

        text = str(item["text"]).strip()
        if text == "":
            raise ValueError(f"segments[{i}].text cannot be empty")

        seg_id: Optional[str] = None
        for key in ("id", "segment_id", "voiceover_segment_id"):
            if key in item and item[key] is not None:
                sid = str(item[key]).strip()
                if sid:
                    seg_id = sid
                    break

        segments.append(
            Segment(
                start_time_seconds=start_time_seconds,
                target_duration_seconds=target_duration_seconds,
                text=text,
                segment_id=seg_id,
                start_raw=start_raw_str,
            )
        )

    segments.sort(key=lambda s: s.start_time_seconds)
    return segments


def _coerce_audio_bytes(audio: Any) -> bytes:
    if isinstance(audio, (bytes, bytearray)):
        return bytes(audio)
    if isinstance(audio, str):
        raise TypeError("Unexpected ElevenLabs response type: str")
    if isinstance(audio, Iterable):
        out = bytearray()
        for chunk in audio:
            if isinstance(chunk, (bytes, bytearray)):
                out.extend(chunk)
            else:
                raise TypeError(f"Unexpected audio chunk type: {type(chunk).__name__}")
        return bytes(out)
    raise TypeError(f"Unexpected ElevenLabs response type: {type(audio).__name__}")


def _generate_segment_audio(
    *,
    client: ElevenLabs,
    voice_id: str,
    text: str,
    model_id: str,
    output_format: str,
) -> AudioSegment:
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
    )
    audio_bytes = _coerce_audio_bytes(audio)
    seg = AudioSegment.from_file(BytesIO(audio_bytes), format="mp3")
    seg = seg.set_frame_rate(DEFAULT_FRAME_RATE).set_channels(DEFAULT_CHANNELS)
    return seg


def _require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit(
            "FFmpeg is required for --sync-fit but was not found on PATH. "
            "Install FFmpeg and ensure it is available in your environment."
        )
    return exe


def _decompose_atempo_chain(tempo_total: float) -> list[float]:
    """Break tempo_total into FFmpeg atempo factors, each in [0.5, 2.0]."""
    if not math.isfinite(tempo_total) or tempo_total <= 0:
        raise ValueError(f"Invalid tempo factor: {tempo_total!r}")
    factors: list[float] = []
    t = float(tempo_total)
    eps = 1e-9
    while t > 2.0 + eps:
        factors.append(2.0)
        t /= 2.0
    while t < 0.5 - eps:
        factors.append(0.5)
        t /= 0.5
    factors.append(t)
    return factors


def _sync_fit_status_and_quality(tempo_factor: float) -> tuple[str, str]:
    """Status and quality_risk for overlong segments that need speed-up."""
    delta = abs(float(tempo_factor) - 1.0)
    if delta <= 0.08:
        return "fits_naturally", "low"
    if delta <= 0.15:
        return "tempo_adjusted", "medium"
    if delta <= 0.25:
        return "tempo_adjusted", "high"
    return "tempo_adjusted_extreme", "extreme"


def _underfilled_quality_risk(unfilled_gap_seconds: float) -> str:
    """Quality risk when a short segment is left natural and the remaining window is silence."""
    if unfilled_gap_seconds <= 0.5:
        return "low"
    if unfilled_gap_seconds <= 1.5:
        return "medium"
    return "high"


def _sanitize_segment_file_slug(segment_id: Optional[str], index: int) -> str:
    if segment_id:
        s = re.sub(r"[^a-zA-Z0-9_-]+", "_", segment_id.strip()).strip("_")
        if s:
            return s[:120]
    return f"segment_{index:04d}"


def _allocate_unique_slug(base: str, used_counts: dict[str, int]) -> str:
    n = used_counts.get(base, 0)
    used_counts[base] = n + 1
    if n == 0:
        return base
    return f"{base}_{n}"


def _clean_segment_work_dirs(work_root: Path) -> tuple[Path, Path]:
    raw_dir = work_root / "raw"
    fitted_dir = work_root / "fitted"
    work_root.mkdir(parents=True, exist_ok=True)
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    if fitted_dir.exists():
        shutil.rmtree(fitted_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    fitted_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir, fitted_dir


def _path_for_fit_report(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _run_ffmpeg_atempo(
    *,
    ffmpeg_exe: str,
    input_path: Path,
    output_path: Path,
    tempo_factors: list[float],
) -> None:
    filt = ",".join(f"atempo={float(f):.6g}" for f in tempo_factors)
    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-af",
        filt,
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip()
        raise SystemExit(
            f"FFmpeg failed fitting {input_path.name}: {err or e}"
        ) from e


def build_audio_sync_fit(
    *,
    segments: list[Segment],
    api_key: str,
    voice_id: str,
    model_id: str,
    output_format: str,
    work_root: Path,
) -> tuple[AudioSegment, list[dict[str, Any]]]:
    """
    Per-segment TTS then FFmpeg atempo to target duration; assemble timeline in pydub.
    """
    ffmpeg_exe = _require_ffmpeg()
    raw_dir, fitted_dir = _clean_segment_work_dirs(work_root.resolve())

    client = ElevenLabs(api_key=api_key)
    report_rows: list[dict[str, Any]] = []
    rendered: list[tuple[int, AudioSegment]] = []
    end_ms = 0
    used_slugs: dict[str, int] = {}

    for i, seg in enumerate(segments):
        base_slug = _sanitize_segment_file_slug(seg.segment_id, i)
        slug = _allocate_unique_slug(base_slug, used_slugs)
        raw_path = raw_dir / f"{slug}.mp3"
        fitted_path = fitted_dir / f"{slug}.mp3"

        audio_seg = _generate_segment_audio(
            client=client,
            voice_id=voice_id,
            text=seg.text,
            model_id=model_id,
            output_format=output_format,
        )
        audio_seg.export(str(raw_path), format="mp3")

        raw_duration_seconds = len(audio_seg) / 1000.0
        target = float(seg.target_duration_seconds)
        raw_to_target_ratio = raw_duration_seconds / target
        unfilled_gap_seconds = max(0.0, target - raw_duration_seconds)

        if raw_duration_seconds <= target:
            # Asymmetric sync-fit policy: short speech should stay natural;
            # the remaining timing window is represented by silence in the master timeline.
            shutil.copyfile(raw_path, fitted_path)
            tempo_factor = 1.0
            status = "under_filled_window"
            quality_risk = _underfilled_quality_risk(unfilled_gap_seconds)
        else:
            tempo_factor = raw_to_target_ratio
            factors = _decompose_atempo_chain(tempo_factor)
            _run_ffmpeg_atempo(
                ffmpeg_exe=ffmpeg_exe,
                input_path=raw_path.resolve(),
                output_path=fitted_path.resolve(),
                tempo_factors=factors,
            )
            status, quality_risk = _sync_fit_status_and_quality(tempo_factor)

        fitted_seg = AudioSegment.from_file(str(fitted_path), format="mp3")
        fitted_seg = fitted_seg.set_frame_rate(DEFAULT_FRAME_RATE).set_channels(DEFAULT_CHANNELS)
        fitted_duration_seconds = len(fitted_seg) / 1000.0

        report_id = seg.segment_id if seg.segment_id else slug
        start_display = seg.start_raw if seg.start_raw else str(seg.start_time_seconds)

        report_rows.append(
            {
                "id": report_id,
                "text": seg.text,
                "start": start_display,
                "target_duration_seconds": target,
                "raw_duration_seconds": round(raw_duration_seconds, 3),
                "fitted_duration_seconds": round(fitted_duration_seconds, 3),
                "tempo_factor": round(tempo_factor, 3),
                "raw_to_target_ratio": round(raw_to_target_ratio, 3),
                "unfilled_gap_seconds": round(unfilled_gap_seconds, 3),
                "status": status,
                "quality_risk": quality_risk,
                "raw_path": _path_for_fit_report(raw_path),
                "fitted_path": _path_for_fit_report(fitted_path),
            }
        )

        start_ms = int(round(seg.start_time_seconds * 1000))
        rendered.append((start_ms, fitted_seg))
        end_ms = max(end_ms, start_ms + len(fitted_seg))

    master = AudioSegment.silent(duration=end_ms, frame_rate=DEFAULT_FRAME_RATE).set_channels(DEFAULT_CHANNELS)
    for start_ms, clip in rendered:
        master = master.overlay(clip, position=start_ms)

    return master, report_rows


def _fit_segment_to_target(
    seg: AudioSegment,
    *,
    target_duration_seconds: float,
    tail_tolerance_seconds: float,
    segment_display: str,
) -> AudioSegment:
    """
    Align generated TTS to the sync slot: pad if short; if slightly long, keep
    natural ending within tail tolerance; otherwise fail loudly (no silent chop).
    """
    gen_s = len(seg) / 1000.0
    target = float(target_duration_seconds)
    tol = float(tail_tolerance_seconds)
    limit = target + tol

    target_ms = int(round(target * 1000))
    if target_ms <= 0:
        return AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE).set_channels(DEFAULT_CHANNELS)

    if gen_s <= target:
        if len(seg) > target_ms:
            return seg[:target_ms]
        if len(seg) < target_ms:
            pad = AudioSegment.silent(
                duration=(target_ms - len(seg)),
                frame_rate=seg.frame_rate,
            ).set_channels(seg.channels)
            return seg + pad
        return seg

    if gen_s <= limit:
        over_by = gen_s - target
        print(
            f"Warning: {segment_display} exceeds target by {over_by:.2f}s "
            "but is within tail tolerance; preserving natural ending."
        )
        return seg

    raise SystemExit(
        f"Segment {segment_display}: generated TTS duration is {gen_s:.2f}s, "
        f"target_duration_seconds is {target:.2f}s, "
        f"tail_tolerance_seconds is {tol:.2f}s (max allowed {limit:.2f}s). "
        "Shorten the copy or widen the timing slot in the sync packet."
    )


def build_audio(
    *,
    segments: list[Segment],
    api_key: str,
    voice_id: str,
    model_id: str,
    output_format: str,
    tail_tolerance_seconds: float = DEFAULT_TAIL_TOLERANCE_SECONDS,
) -> AudioSegment:
    if not segments:
        return AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE).set_channels(DEFAULT_CHANNELS)

    client = ElevenLabs(api_key=api_key)

    rendered: list[tuple[int, AudioSegment]] = []
    end_ms = 0

    for i, seg in enumerate(segments):
        segment_display = seg.segment_id if seg.segment_id else f"segments[{i}]"
        start_ms = int(round(seg.start_time_seconds * 1000))
        audio_seg = _generate_segment_audio(
            client=client,
            voice_id=voice_id,
            text=seg.text,
            model_id=model_id,
            output_format=output_format,
        )
        audio_seg = _fit_segment_to_target(
            audio_seg,
            target_duration_seconds=seg.target_duration_seconds,
            tail_tolerance_seconds=tail_tolerance_seconds,
            segment_display=segment_display,
        )
        rendered.append((start_ms, audio_seg))
        end_ms = max(end_ms, start_ms + len(audio_seg))

    master = AudioSegment.silent(duration=end_ms, frame_rate=DEFAULT_FRAME_RATE).set_channels(DEFAULT_CHANNELS)
    for start_ms, audio_seg in rendered:
        master = master.overlay(audio_seg, position=start_ms)

    return master


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate stitched voiceover audio from segments.json.")
    parser.add_argument("--segments", default="segments.json", help="Path to segments.json (default: ./segments.json)")
    parser.add_argument("--out", default="output.mp3", help="Output mp3 filename (default: output.mp3)")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help=f"ElevenLabs model_id (default: {DEFAULT_MODEL_ID})")
    parser.add_argument(
        "--output-format",
        default=DEFAULT_OUTPUT_FORMAT,
        help=f"ElevenLabs output_format (default: {DEFAULT_OUTPUT_FORMAT})",
    )
    parser.add_argument(
        "--prepared-voice",
        type=str,
        default=None,
        help="Path to prepared_voice.json to pull the workspace_voice_id",
    )
    parser.add_argument(
        "--tail-tolerance-seconds",
        type=float,
        default=DEFAULT_TAIL_TOLERANCE_SECONDS,
        help=(
            "If generated audio is longer than target_duration_seconds but not more than "
            "this many seconds beyond it, keep the full clip (natural ending). Default: 0.35."
        ),
    )
    parser.add_argument(
        "--sync-fit",
        action="store_true",
        help=(
            "Use FFmpeg atempo per segment to match target_duration_seconds, then assemble the timeline. "
            "Requires FFmpeg on PATH."
        ),
    )
    parser.add_argument(
        "--fit-report",
        default="fit_report.json",
        help="Path to write sync-fit JSON report (default: fit_report.json).",
    )
    parser.add_argument(
        "--segment-work-dir",
        default="segment_renders",
        help="Working directory for raw/fitted segment MP3s (default: segment_renders).",
    )
    args = parser.parse_args()

    if args.tail_tolerance_seconds < 0:
        raise SystemExit("--tail-tolerance-seconds must be >= 0.")

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing ELEVENLABS_API_KEY in .env")

    voice_id = (os.environ.get("ELEVENLABS_VOICE_ID") or VOICE_ID).strip()

    if args.prepared_voice:
        with open(args.prepared_voice, "r", encoding="utf-8") as f:
            prepared = json.load(f)
        if not isinstance(prepared, dict):
            raise SystemExit(f"{args.prepared_voice} must be a JSON object.")
        wid = prepared.get("workspace_voice_id")
        if wid is None or (isinstance(wid, str) and not wid.strip()):
            raise SystemExit(
                f"{args.prepared_voice} is missing a non-empty workspace_voice_id; "
                "run prepare_selected_voice.py successfully first."
            )
        voice_id = str(wid).strip()
        if not voice_id:
            raise SystemExit(
                f"{args.prepared_voice} has empty workspace_voice_id after parsing."
            )
    args.voice_id = voice_id

    if not voice_id:
        raise SystemExit(
            "Missing ElevenLabs voice id: set ELEVENLABS_VOICE_ID in the environment or use --prepared-voice."
        )

    segments = _read_segments(args.segments)

    if args.sync_fit:
        work_root = Path(args.segment_work_dir).expanduser()
        if not work_root.is_absolute():
            work_root = (Path.cwd() / work_root).resolve()
        else:
            work_root = work_root.resolve()

        audio, report_rows = build_audio_sync_fit(
            segments=segments,
            api_key=api_key,
            voice_id=voice_id,
            model_id=args.model_id,
            output_format=args.output_format,
            work_root=work_root,
        )

        audio.export(args.out, format="mp3")

        fit_path = Path(args.fit_report).expanduser()
        if not fit_path.is_absolute():
            fit_path = (Path.cwd() / fit_path).resolve()
        else:
            fit_path = fit_path.resolve()
        fit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(fit_path, "w", encoding="utf-8") as f:
            json.dump(report_rows, f, indent=2, ensure_ascii=False)

        print()
        print("Sync-fit summary")
        hdr = f"{'ID':<14} {'Target':>10} {'Raw':>10} {'Fitted':>10} {'Tempo':>8} {'Status':<18} {'Risk':<10}"
        print(hdr)
        print("-" * len(hdr))
        for row in report_rows:
            print(
                f"{str(row['id']):<14} "
                f"{row['target_duration_seconds']:>10.3f} "
                f"{row['raw_duration_seconds']:>10.3f} "
                f"{row['fitted_duration_seconds']:>10.3f} "
                f"{row['tempo_factor']:>8.3f} "
                f"{row['status']:<18} "
                f"{row['quality_risk']:<10}"
            )
        print()
        print(f"Wrote {args.out}")
        print(f"Wrote fit report {args.fit_report}")
        return

    audio = build_audio(
        segments=segments,
        api_key=api_key,
        voice_id=voice_id,
        model_id=args.model_id,
        output_format=args.output_format,
        tail_tolerance_seconds=args.tail_tolerance_seconds,
    )

    audio.export(args.out, format="mp3")
    print(f"Wrote {args.out} ({len(audio)/1000:.2f}s)")


if __name__ == "__main__":
    main()
