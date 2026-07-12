import argparse
import json
import math
import os
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Iterable, Optional

from elevenlabs import ElevenLabs
from pydub import AudioSegment


# ----------------------------
# Configure these two values.
# ----------------------------
ELEVEN_LABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
VOICE_ID = "4Ihiyat2AFvCRGQ2Hycm"



DEFAULT_MODEL_ID = "eleven_v3"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_FRAME_RATE = 44100
DEFAULT_CHANNELS = 2


_TIMECODE_RE = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\s*$")


@dataclass(frozen=True)
class Segment:
    start_time_seconds: float
    target_duration_seconds: float
    text: str


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
        target_duration_seconds = float(item["target_duration_seconds"])
        if not math.isfinite(target_duration_seconds) or target_duration_seconds <= 0:
            raise ValueError(f"segments[{i}].target_duration_seconds must be > 0")

        text = str(item["text"]).strip()
        if text == "":
            raise ValueError(f"segments[{i}].text cannot be empty")

        segments.append(
            Segment(
                start_time_seconds=start_time_seconds,
                target_duration_seconds=target_duration_seconds,
                text=text,
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


def _fit_to_duration(seg: AudioSegment, target_duration_seconds: float) -> AudioSegment:
    target_ms = int(round(target_duration_seconds * 1000))
    if target_ms <= 0:
        return AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE).set_channels(DEFAULT_CHANNELS)

    if len(seg) > target_ms:
        return seg[:target_ms]

    if len(seg) < target_ms:
        pad = AudioSegment.silent(duration=(target_ms - len(seg)), frame_rate=seg.frame_rate).set_channels(seg.channels)
        return seg + pad

    return seg


def build_audio(
    *,
    segments: list[Segment],
    api_key: str,
    voice_id: str,
    model_id: str,
    output_format: str,
) -> AudioSegment:
    if not segments:
        return AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE).set_channels(DEFAULT_CHANNELS)

    client = ElevenLabs(api_key=api_key)

    rendered: list[tuple[int, AudioSegment]] = []
    end_ms = 0

    for seg in segments:
        start_ms = int(round(seg.start_time_seconds * 1000))
        audio_seg = _generate_segment_audio(
            client=client,
            voice_id=voice_id,
            text=seg.text,
            model_id=model_id,
            output_format=output_format,
        )
        audio_seg = _fit_to_duration(audio_seg, seg.target_duration_seconds)
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
    args = parser.parse_args()

    api_key = (os.environ.get("ELEVENLABS_API_KEY") or ELEVEN_LABS_API_KEY).strip()
    voice_id = (os.environ.get("ELEVENLABS_VOICE_ID") or VOICE_ID).strip()

    if not api_key:
        raise SystemExit("Set ELEVEN_LABS_API_KEY at top of segments_to_audio.py (or ELEVENLABS_API_KEY env var).")
    if not voice_id:
        raise SystemExit("Set VOICE_ID at top of segments_to_audio.py (or ELEVENLABS_VOICE_ID env var).")

    segments = _read_segments(args.segments)
    audio = build_audio(
        segments=segments,
        api_key=api_key,
        voice_id=voice_id,
        model_id=args.model_id,
        output_format=args.output_format,
    )

    audio.export(args.out, format="mp3")
    print(f"Wrote {args.out} ({len(audio)/1000:.2f}s)")


if __name__ == "__main__":
    main()
