#!/usr/bin/env python3
"""Generate background music from a campaign storyboard using Gemini and Lyria."""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_DURATION_SECONDS = 30.0


def fail(message):
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate instrumental background music for a storyboard."
    )
    parser.add_argument("--storyboard", default="storyboard.json")
    parser.add_argument("--voice", help="Optional path to voiceover MP3 for duration")
    parser.add_argument(
        "--duration",
        type=float,
        help="Optional target duration in seconds; overrides voice-derived value",
    )
    parser.add_argument("--out", default="music/background_music.mp3")
    parser.add_argument("--brief-out", default="music/music_brief.json")
    parser.add_argument("--report", default="music/music_report.json")
    parser.add_argument("--brief-model", default="gemini-3.1-flash-lite")
    parser.add_argument("--music-model", default="lyria-3-pro-preview")
    parser.add_argument(
        "--max-transient-retries",
        type=int,
        default=2,
        help="Retries on transient Lyria errors (network/5xx/429/timeout) per prompt. Default: 2",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=2.0,
        help="Linear backoff base (seconds) between transient retries. Default: 2.0",
    )
    parser.add_argument("--region", default="global")
    return parser.parse_args()


def require_file(path, label):
    if not path.exists():
        fail(f"{label} does not exist: {path}")
    if not path.is_file():
        fail(f"{label} is not a file: {path}")


def require_ffprobe():
    if shutil.which("ffprobe") is None:
        fail("ffprobe is required but was not found on PATH")


def ffprobe_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        fail("ffprobe is required but was not found on PATH")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        fail(f"ffprobe failed for {path}{detail}")

    output = result.stdout.strip()
    try:
        duration = float(output)
    except ValueError:
        fail(f"ffprobe returned an invalid duration for {path}: {output!r}")

    if duration <= 0:
        fail(f"ffprobe returned a non-positive duration for {path}: {duration}")
    return duration


def read_json(path, label):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        fail(f"{label} is not valid JSON: {exc}")
    except OSError as exc:
        fail(f"Could not read {label} at {path}: {exc}")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except OSError as exc:
        fail(f"Could not write JSON to {path}: {exc}")


def write_binary(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("wb") as handle:
            handle.write(data)
    except OSError as exc:
        fail(f"Could not write binary output to {path}: {exc}")


def extract_text_response(response_json, label):
    candidates = response_json.get("candidates")
    if not candidates:
        fail(f"{label} response did not include candidates")

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )
    text_chunks = [part.get("text", "") for part in parts if part.get("text")]
    text = "".join(text_chunks).strip()
    if not text:
        fail(f"{label} response did not include text content")
    return text


def parse_json_object(text, label):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        fail(f"{label} returned markdown/code fences instead of raw JSON")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        fail(f"{label} did not return valid JSON: {exc}")


def post_generate_content(model, api_key, body, label):
    url = GEMINI_API_URL.format(model=model)
    try:
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json=body,
            timeout=300,
        )
    except requests.RequestException as exc:
        fail(f"{label} request failed: {exc}")

    if response.status_code >= 400:
        fail(f"{label} request failed with HTTP {response.status_code}: {response.text}")

    try:
        return response.json()
    except ValueError as exc:
        fail(f"{label} response was not valid JSON: {exc}")


def build_music_brief_system_prompt():
    schema = {
        "music_brief": {
            "project_name": "string",
            "brand_name": "string",
            "region": "string",
            "target_duration_seconds": 0.0,
            "genre": "string",
            "tempo_bpm": 0,
            "mood": ["string"],
            "instrumentation": ["string"],
            "vocal_policy": "instrumental_only",
            "energy_arc": [
                {
                    "start": "00:00.000",
                    "end": "00:00.000",
                    "energy": "low|medium|high",
                    "instruction": "string",
                }
            ],
            "avoid": ["string"],
            "rights_safety": {
                "no_artist_imitation": True,
                "no_copyrighted_references": True,
                "commercial_use_required": True,
                "metadata_required": True,
            },
            "synthid_expected": True,
            "mixing_notes": "string",
        }
    }
    return (
        "You are a music director for modern brand and product advertisements — "
        "short-form video ads for tech companies, SaaS products, consumer brands, "
        "and similar commercial campaigns. Create a concise, commercially safe "
        "music brief from the storyboard and timing details. Bias toward polished, "
        "modern, gently-rhythmic instrumental music suitable for contemporary "
        "brand advertising. Think the style of music behind product videos from "
        "companies like Stripe, Notion, Linear, Apple, or modern SaaS demos. Do "
        "NOT produce briefs for ambient drone, meditation music, sparse "
        "atmospheric textures, clinical minimalism, or cinematic orchestral drama "
        "UNLESS the storyboard explicitly describes stillness, contemplation, or "
        "somber serious tone. target_duration_seconds in the output JSON MUST "
        "exactly equal the value passed in the user payload. Do not round, "
        "substitute, or estimate. Copy the value verbatim. tempo_bpm must be a "
        'real BPM integer between 70 and 130. Never 0, never null, never "unspecified". '
        "Pick a sensible value for the genre. All mood adjectives must be "
        "internally consistent. Do NOT mix contradictory words (e.g. don't combine "
        '"minimalist" with "authoritative", or "calm" with "energetic"). Pick a '
        "coherent emotional direction. Concrete examples: Tech product launch → "
        'genre "modern electronic", mood ["confident", "forward", "polished", '
        '"uplifting"], instrumentation ["soft synth pulse", "subtle electronic '
        'percussion", "warm bass", "light piano motif"]. B2B SaaS demo → genre '
        '"corporate electronic", mood ["focused", "modern", "trustworthy", '
        '"smooth"], instrumentation ["steady synth bed", "soft electronic pulse", '
        '"atmospheric pad", "clean piano"]. Consumer brand video → genre '
        '"uplifting indie pop instrumental", mood ["warm", "optimistic", "human", '
        '"modern"], instrumentation ["acoustic guitar", "gentle percussion", '
        '"warm synths", "bright piano"]. Output ONLY a valid JSON object matching '
        "this exact shape. Do not include prose, markdown, comments, or code "
        "fences. Use vocal_policy exactly as "
        '"instrumental_only". Avoid artist imitation, copyrighted references, and '
        "lyrics. Required shape:\n"
        f"{json.dumps(schema, indent=2)}"
    )


def build_brief_request(storyboard, target_duration_seconds, region):
    user_payload = {
        "storyboard": storyboard,
        "target_duration_seconds": target_duration_seconds,
        "region": region,
    }
    return {
        "systemInstruction": {
            "parts": [{"text": build_music_brief_system_prompt()}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Create the music brief from this JSON input:\n"
                            f"{json.dumps(user_payload, indent=2, ensure_ascii=False)}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.4,
        },
    }


def validate_music_brief(brief_json):
    if not isinstance(brief_json, dict):
        fail("Gemini brief response must be a JSON object")
    if "music_brief" not in brief_json:
        fail("Gemini brief response is missing required key: music_brief")
    if not isinstance(brief_json["music_brief"], dict):
        fail("music_brief must be a JSON object")


def as_text_list(values):
    if not isinstance(values, list):
        return ""
    return ", ".join(str(value) for value in values if str(value).strip())


def build_lyria_prompt(brief_json, target_duration_seconds):
    brief = brief_json["music_brief"]

    def clean_value(value):
        return str(value).strip().rstrip(".").strip()

    def prompt_sentence(text):
        return f"{clean_value(text)}."

    genre = clean_value(brief.get("genre", "commercial background music"))
    instrumentation_values = brief.get("instrumentation", [])
    avoid_values = brief.get("avoid", [])
    energy_arc = brief.get("energy_arc", [])

    instrumentation_text = as_text_list(instrumentation_values).lower()
    avoid_text = as_text_list(avoid_values).lower()
    energy_instructions = " ".join(
        str(segment.get("instruction", ""))
        for segment in energy_arc
        if isinstance(segment, dict)
    ).lower()
    ambient_texture_direction = (
        "ambient" in genre.lower()
        or "ambient pad" in instrumentation_text
        or "texture" in instrumentation_text
    )
    static_nonmusical_direction = (
        any(term in avoid_text for term in ("beats", "drums", "melody"))
        or "static" in energy_instructions
        or "without any rhythmic movement" in energy_instructions
    )

    # Lyria similarity filtering may reject generated audio; for texture-only beds,
    # avoid sending song-like negative vocabulary and BPM.
    if ambient_texture_direction and static_nonmusical_direction:
        return (
            f"Create approximately {target_duration_seconds:.1f} seconds of original "
            "abstract ambient sound design. Use a quiet warm low tonal layer with soft "
            "air-like texture. Keep it sparse, static, non-rhythmic, and non-melodic. "
            "No vocals or speech. Avoid recognizable musical phrases, repeating motifs, "
            "or genre imitation. Fade in gently and fade out cleanly."
        )

    tempo_bpm = clean_value(brief.get("tempo_bpm", "unspecified"))
    mood = clean_value(as_text_list(brief.get("mood", []))) or "polished, brand-safe"
    instrumentation = (
        clean_value(as_text_list(instrumentation_values))
        or "modern production elements suitable for short-form advertising"
    )
    avoid = clean_value(as_text_list(avoid_values)) or "vocals, lyrics, artist imitation, copyrighted references"

    energy_lines = []
    if isinstance(energy_arc, list):
        for segment in energy_arc:
            if not isinstance(segment, dict):
                continue
            start = clean_value(segment.get("start", "00:00.000"))
            end = clean_value(segment.get("end", "00:00.000"))
            energy = clean_value(segment.get("energy", "medium"))
            energy_descriptor = {
                "low": "low (gentle resolution)",
                "medium": "medium",
                "high": "high (energetic lift)",
            }.get(energy.lower(), energy)
            energy_lines.append(f"{start}-{end} {energy_descriptor}")

    prompt_parts = [
        prompt_sentence(f"Create approximately {target_duration_seconds:.1f} seconds of {genre} music"),
        prompt_sentence(f"Tempo/BPM: {tempo_bpm}"),
        prompt_sentence(f"Mood adjectives: {mood}"),
        prompt_sentence(f"Instrumentation: {instrumentation}"),
        "instrumental only — no vocals or lyrics.",
        prompt_sentence(f"Avoid: {avoid}"),
    ]
    if energy_lines:
        prompt_parts.append(prompt_sentence("Energy progression: " + ", ".join(energy_lines)))

    return " ".join(prompt_parts)


def build_lyria_request(lyria_prompt):
    return {
        "contents": [
            {
                "parts": [
                    {
                        "text": lyria_prompt,
                    }
                ]
            }
        ]
    }


class LyriaTransientError(Exception):
    """Network/timeout/5xx/429/invalid-JSON: safe to retry the SAME prompt."""

    def __init__(self, message, http_status=None):
        super().__init__(message)
        self.http_status = http_status


class LyriaContentRejection(Exception):
    """200-without-audio, no candidates, or hard 4xx (e.g. similarity/copyright
    filter): retrying the same prompt does not help - try a safer prompt."""

    def __init__(self, message, response_json=None, http_status=None):
        super().__init__(message)
        self.response_json = response_json
        self.http_status = http_status


TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}


def _finish_reason(response_json):
    if not isinstance(response_json, dict):
        return None
    cands = response_json.get("candidates") or []
    if cands and isinstance(cands[0], dict):
        return cands[0].get("finishReason") or cands[0].get("finish_reason")
    return None


def post_lyria_classified(model, api_key, body):
    """POST to the music model. Returns parsed JSON, or raises a classified
    exception instead of exiting, so the caller can retry or fail loud."""
    url = GEMINI_API_URL.format(model=model)
    try:
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json=body,
            timeout=300,
        )
    except requests.RequestException as exc:
        raise LyriaTransientError(f"request failed: {exc}")

    status = response.status_code
    if status >= 400:
        if status in TRANSIENT_HTTP_STATUSES:
            raise LyriaTransientError(
                f"HTTP {status}: {response.text}",
                http_status=status,
            )
        raise LyriaContentRejection(
            f"HTTP {status}: {response.text}",
            http_status=status,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise LyriaTransientError(f"response was not valid JSON: {exc}")


def extract_audio_or_reject(response_json):
    """Pure classifier (no network): return decoded audio bytes, or raise
    LyriaContentRejection for the no-audio / filtered shape. Unit-testable."""
    if not isinstance(response_json, dict):
        raise LyriaContentRejection("response was not a JSON object", response_json=response_json)

    candidates = response_json.get("candidates")
    if not candidates:
        raise LyriaContentRejection(
            "response did not include candidates",
            response_json=response_json,
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )
    for part in parts:
        inline_data = part.get("inline_data") or part.get("inlineData")
        if not isinstance(inline_data, dict):
            continue
        mime_type = inline_data.get("mime_type") or inline_data.get("mimeType") or ""
        if not mime_type.startswith("audio/"):
            continue
        encoded = inline_data.get("data")
        if not encoded:
            raise LyriaContentRejection(
                "audio part missing inline_data.data",
                response_json=response_json,
            )
        try:
            return base64.b64decode(encoded)
        except (ValueError, TypeError) as exc:
            raise LyriaTransientError(f"audio data was not valid base64: {exc}")

    raise LyriaContentRejection(
        "response did not include an inline audio part",
        response_json=response_json,
    )


def build_safe_lyria_prompt(brief_json, target_duration_seconds):
    """Conservative retry prompt after a content rejection. Reuses the proven-safer
    abstract style: no BPM, no genre imitation, no song-like negatives."""
    brief = brief_json.get("music_brief", {})
    mood_words = as_text_list(brief.get("mood", [])).strip()
    mood_clause = f" Aim for a {mood_words} feel." if mood_words else ""
    return (
        f"Create approximately {target_duration_seconds:.1f} seconds of original, "
        "non-derivative instrumental background texture for a commercial. Use warm, modern "
        "tonal layers and gentle movement. Keep it brand-safe and understated."
        f"{mood_clause} No vocals or speech. Avoid recognizable musical phrases, repeating "
        "signature motifs, sampled material, or imitation of any existing artist, song, or "
        "genre style. Fade in gently and fade out cleanly."
    )


def write_failure_report(
    report_path,
    storyboard_path,
    voice_path,
    target_duration_seconds,
    args,
    attempts,
    error_summary,
):
    write_json(
        report_path,
        {
            "status": "failed",
            "failure_stage": "lyria",
            "error_summary": error_summary,
            "storyboard_file": str(storyboard_path),
            "voice_file": str(voice_path) if voice_path else None,
            "target_duration_seconds": target_duration_seconds,
            "brief_model_used": args.brief_model,
            "music_model_used": args.music_model,
            "attempts": attempts,
            "warnings": [
                "Lyria produced no audio. Fail-loud default: no fallback bed substituted."
            ],
        },
    )


def validate_environment(storyboard_path, voice_path):
    require_file(storyboard_path, "Storyboard")
    if voice_path is not None:
        require_file(voice_path, "Voice file")
        require_ffprobe()

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        fail("GEMINI_API_KEY was not found. Add it to .env or the environment")
    return api_key


def main():
    args = parse_args()

    storyboard_path = Path(args.storyboard)
    voice_path = Path(args.voice) if args.voice else None
    output_path = Path(args.out)
    brief_path = Path(args.brief_out)
    report_path = Path(args.report)

    if args.duration is not None and args.duration <= 0:
        fail("--duration must be greater than 0")

    api_key = validate_environment(storyboard_path, voice_path)

    if args.duration is not None:
        target_duration_seconds = args.duration
    elif voice_path is not None:
        target_duration_seconds = ffprobe_duration(voice_path)
    else:
        target_duration_seconds = DEFAULT_DURATION_SECONDS

    print("Loading storyboard...")
    storyboard = read_json(storyboard_path, "storyboard")

    print("Calling Gemini for brief...")
    brief_started = time.monotonic()
    brief_response = post_generate_content(
        args.brief_model,
        api_key,
        build_brief_request(storyboard, target_duration_seconds, args.region),
        "Gemini brief",
    )
    brief_generation_time_seconds = time.monotonic() - brief_started
    brief_text = extract_text_response(brief_response, "Gemini brief")
    brief_json = parse_json_object(brief_text, "Gemini brief")
    validate_music_brief(brief_json)

    write_json(brief_path, brief_json)
    print(f"Saved brief to {brief_path}")

    primary_prompt = build_lyria_prompt(brief_json, target_duration_seconds)
    attempts = []

    def _attempt(prompt, label):
        for t in range(args.max_transient_retries + 1):
            try:
                resp = post_lyria_classified(
                    args.music_model,
                    api_key,
                    build_lyria_request(prompt),
                )
                audio = extract_audio_or_reject(resp)
                attempts.append(
                    {
                        "label": label,
                        "outcome": "success",
                        "attempt": t + 1,
                        "prompt": prompt,
                    }
                )
                return audio, resp
            except LyriaTransientError as exc:
                attempts.append(
                    {
                        "label": label,
                        "outcome": "transient_error",
                        "attempt": t + 1,
                        "http_status": exc.http_status,
                        "detail": str(exc),
                        "prompt": prompt,
                    }
                )
                if t < args.max_transient_retries:
                    time.sleep(args.retry_backoff_seconds * (t + 1))
                    continue
                raise
            except LyriaContentRejection as exc:
                attempts.append(
                    {
                        "label": label,
                        "outcome": "content_rejection",
                        "attempt": t + 1,
                        "http_status": exc.http_status,
                        "detail": str(exc),
                        "finish_reason": _finish_reason(exc.response_json),
                        "prompt": prompt,
                    }
                )
                raise

    print("Calling Lyria for music...")
    music_started = time.monotonic()
    used_safe_prompt = False
    lyria_prompt = primary_prompt
    try:
        try:
            audio_bytes, music_response = _attempt(primary_prompt, "primary")
        except LyriaContentRejection:
            print("Primary prompt rejected by Lyria; retrying with a safe prompt...")
            used_safe_prompt = True
            lyria_prompt = build_safe_lyria_prompt(brief_json, target_duration_seconds)
            audio_bytes, music_response = _attempt(lyria_prompt, "safe")
    except (LyriaContentRejection, LyriaTransientError) as exc:
        write_failure_report(
            report_path,
            storyboard_path,
            voice_path,
            target_duration_seconds,
            args,
            attempts,
            str(exc),
        )
        print(f"Saved failure report to {report_path}", file=sys.stderr)
        fail(
            "Lyria music generation failed"
            + (" (primary + safe prompt)" if used_safe_prompt else " (primary)")
            + f" after retries: {exc}. No fallback bed (fail-loud default)."
        )
    music_generation_time_seconds = time.monotonic() - music_started

    write_binary(output_path, audio_bytes)
    print(f"Saved music to {output_path}")

    require_ffprobe()
    output_duration_seconds = ffprobe_duration(output_path)

    report = {
        "status": "succeeded",
        "storyboard_file": str(storyboard_path),
        "voice_file": str(voice_path) if voice_path else None,
        "target_duration_seconds": target_duration_seconds,
        "brief_model_used": args.brief_model,
        "music_model_used": args.music_model,
        "brief_file": str(brief_path),
        "output_file": str(output_path),
        "lyria_prompt_sent": lyria_prompt,
        "brief_generation_time_seconds": brief_generation_time_seconds,
        "music_generation_time_seconds": music_generation_time_seconds,
        "output_duration_seconds": output_duration_seconds,
        "synthid_expected": True,
        "attempts": attempts,
        "used_safe_prompt": used_safe_prompt,
        "warnings": (
            [
                "Primary prompt rejected by Lyria; a safe fallback prompt was used. Review music for brand fit."
            ]
            if used_safe_prompt
            else []
        ),
    }
    write_json(report_path, report)
    print(f"Saved report to {report_path}")


if __name__ == "__main__":
    main()
