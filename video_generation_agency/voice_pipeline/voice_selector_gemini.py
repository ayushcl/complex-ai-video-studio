

import argparse
import json
import os
from typing import Any

import requests
from dotenv import load_dotenv
load_dotenv()
from elevenlabs import ElevenLabs
from google import genai
from google.genai import types


DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"

CASTING_DIRECTOR_SYSTEM_INSTRUCTION = (
    "You are an elite Casting Director for a high-end commercial agency. Your job is to read the creative storyboard and strictly match the demographic requirements, especially age, gender, accent, tone, and commercial context, to the provided ElevenLabs voice catalogue. Prioritize explicit demographic requirements such as young adult, female, British RP, neutral British, or presenter age over vague adjectives like authoritative or professional. Avoid selecting voices that sound elderly, matronly, overly mature, regional, American, robotic, or low-quality when the storyboard asks for a young polished British female presenter. You may only select voices from the provided catalogue. Do not invent voice IDs, owner IDs, names, or metadata."
)


def load_storyboard(path: str) -> dict:
    """Load a JSON storyboard packet (campaign brief, script, scenes, etc.)."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    if not raw.strip():
        raise ValueError(
            f"{path} is empty or contains only whitespace; expected a JSON storyboard object."
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{path} is not valid JSON ({e.msg} at line {e.lineno}, column {e.colno})."
        ) from e

    if not isinstance(data, dict):
        raise ValueError(
            f"{path} must be a JSON object (top-level {{}}), got {type(data).__name__}."
        )

    if not data:
        raise ValueError(
            f"{path} parses to an empty object {{}}; add your storyboard fields (campaign, script, scenes, …)."
        )

    return data


def format_storyboard_for_prompt(storyboard: dict) -> str:
    """Serialize the storyboard dict for Gemini (preserves structure, readable)."""
    return json.dumps(storyboard, indent=2, ensure_ascii=False)


def safe_get(obj: Any, name: str, default=None):
    """Read a field from either a dict or an SDK object."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def fetch_elevenlabs_voices(api_key: str, max_voices: int = 100) -> list[dict]:
    """
    Pull available ElevenLabs voices and normalize them into a compact catalogue
    that Gemini can inspect.
    Handles pagination to retrieve more than 100 voices if needed.
    Adds local caching to avoid repeat API calls.
    """
    import json

    cache_file = "elevenlabs_cache.json"
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        print("Loaded voices from local cache.")
        upgraded: list[dict] = []
        if isinstance(cached, list):
            for v in cached:
                if not isinstance(v, dict):
                    continue
                name = v.get("voice_name") or v.get("name") or ""
                upgraded.append(
                    {
                        "voice_id": v.get("voice_id"),
                        "owner_id": v.get("owner_id", ""),
                        "voice_name": name,
                        "name": name,
                        "category": v.get("category", ""),
                        "description": v.get("description", ""),
                        "labels": v.get("labels", {}) or {},
                        "preview_url": v.get("preview_url", ""),
                    }
                )
        upgraded = [v for v in upgraded if v.get("voice_id") and v.get("voice_name")]
        if upgraded:
            return upgraded
        return cached

    client = ElevenLabs(api_key=api_key)

    voices_raw = []
    cursor = None
    while len(voices_raw) < max_voices:
        batch_size = min(100, max_voices - len(voices_raw))
        kwargs = {"page_size": batch_size}
        if cursor:
            kwargs["next"] = cursor
        response = client.voices.search(**kwargs)
        batch = safe_get(response, "voices", response)
        if not isinstance(batch, list):
            raise TypeError("Could not read voices list from ElevenLabs response")
        voices_raw.extend(batch)
        cursor = safe_get(response, "next", None)
        if not cursor or not batch:
            break  # No more pages

    catalogue = []

    for voice in voices_raw[:max_voices]:
        voice_id = safe_get(voice, "voice_id")
        name = safe_get(voice, "name", "")
        category = safe_get(voice, "category", "")
        description = safe_get(voice, "description", "")
        labels = safe_get(voice, "labels", {}) or {}
        preview_url = safe_get(voice, "preview_url", "")

        catalogue.append(
            {
                "voice_id": voice_id,
                "owner_id": "",
                "voice_name": name,
                "name": name,
                "category": category,
                "description": description,
                "labels": labels,
                "preview_url": preview_url,
            }
        )

    catalogue = [voice for voice in catalogue if voice.get("voice_id") and voice.get("voice_name")]

    if not catalogue:
        raise RuntimeError("No usable voices returned from ElevenLabs")
    
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(catalogue, f, ensure_ascii=False, indent=2)

    return catalogue


def fetch_elevenlabs_shared_voices(api_key: str, max_voices: int = 1000) -> list[dict]:
    """
    Pull voices from the ElevenLabs Shared Voice Library and normalize them into the
    same compact catalogue structure used for account voices.
    """
    url = "https://api.elevenlabs.io/v1/shared-voices"
    headers = {"xi-api-key": api_key}

    catalogue: list[dict] = []
    page = 0

    while len(catalogue) < max_voices:
        batch_size = min(100, max_voices - len(catalogue))
        params = {
            "page_size": batch_size,
            "page": page,
            "language": "en",
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json() or {}

        voices = data.get("voices", []) or []
        if not isinstance(voices, list):
            raise TypeError("Could not read voices list from ElevenLabs shared-voices response")

        for voice in voices:
            voice_id = safe_get(voice, "voice_id")
            name = safe_get(voice, "name", "")
            category = safe_get(voice, "category", "")
            description = safe_get(voice, "description", "")
            labels = safe_get(voice, "labels", {}) or {}
            preview_url = safe_get(voice, "preview_url", "")
            owner_id = safe_get(voice, "public_owner_id", "")

            if voice_id and name:
                catalogue.append(
                    {
                        "voice_id": voice_id,
                        "owner_id": owner_id,
                        "voice_name": name,
                        "name": name,
                        "category": category,
                        "description": description,
                        "labels": labels,
                        "preview_url": preview_url,
                    }
                )

            if len(catalogue) >= max_voices:
                break

        has_more = bool(data.get("has_more", False))
        if not has_more:
            break

        page += 1

    if not catalogue:
        raise RuntimeError("No usable shared voices returned from ElevenLabs")

    return catalogue


def build_prompt(formatted_storyboard: str, voices: list[dict], *, top_voices: int) -> str:
    """Create the instruction prompt for Gemini from a formatted JSON storyboard string."""
    n_alternatives = top_voices - 1
    return f"""
You are a professional voice casting director for AI video advertisements.

Your task:
Choose the best ElevenLabs voice for the storyboard/campaign brief below.

You will receive:
1. A storyboard packet (structured JSON describing the campaign — name, audience, tone, voice needs, script, scenes, etc.).
2. A catalogue of real ElevenLabs voices.

Strict rules:
- You MUST choose only from the provided ElevenLabs voice catalogue.
- Do NOT invent a voice_id.
- Do NOT invent a voice name.
- You must return the owner_id exactly as provided in the voice catalogue. Do not invent it.
- Do NOT select voices that are not in the provided catalogue.
- Return exactly one recommended_voice plus exactly {n_alternatives} alternatives (for a total shortlist of {top_voices} voices).
- The shortlist must be diverse: do not return {top_voices} near-identical voices. Include strong matches with useful variation in tone, age impression, warmth, brightness, and delivery style, while still respecting the storyboard requirements.
- Prioritise business suitability, audience fit, tone, accent, language, emotional fit, and brand fit.
- Avoid novelty, cartoonish, overly dramatic, robotic, or inappropriate voices unless the storyboard clearly asks for that.
- Be strict and practical. This is for business production.

Storyboard / Campaign Brief (JSON):
{formatted_storyboard}

ElevenLabs Voice Catalogue:
{json.dumps(voices, indent=2, ensure_ascii=False)}

Return your decision as JSON only.
"""


def select_voices_with_gemini(
    *,
    gemini_api_key: str,
    model: str,
    formatted_storyboard: str,
    voices: list[dict],
    top_voices: int,
) -> dict:
    """Ask Gemini to choose the best voice and top_voices - 1 alternatives."""
    if top_voices < 2:
        raise ValueError("top_voices must be at least 2 (one recommended voice plus at least one alternative).")

    client = genai.Client(api_key=gemini_api_key)

    n_alternatives = top_voices - 1
    schema = {
        "type": "object",
        "properties": {
            "recommended_voice": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "voice_id": {"type": "string"},
                    "owner_id": {"type": "string"},
                    "voice_name": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["rank", "voice_id", "owner_id", "voice_name", "confidence", "reason"],
            },
            "alternatives": {
                "type": "array",
                "minItems": n_alternatives,
                "maxItems": n_alternatives,
                "items": {
                    "type": "object",
                    "properties": {
                        "rank": {"type": "integer"},
                        "voice_id": {"type": "string"},
                        "owner_id": {"type": "string"},
                        "voice_name": {"type": "string"},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["rank", "voice_id", "owner_id", "voice_name", "confidence", "reason"],
                },
            },
            "selection_summary": {"type": "string"},
        },
        "required": ["recommended_voice", "alternatives", "selection_summary"],
    }

    response = client.models.generate_content(
        model=model,
        contents=build_prompt(formatted_storyboard, voices, top_voices=top_voices),
        config=types.GenerateContentConfig(
            system_instruction=CASTING_DIRECTOR_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    return json.loads(response.text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select top ElevenLabs voices for a storyboard using Gemini."
    )
    parser.add_argument(
        "--storyboard",
        default="storyboard.json",
        help="Path to JSON storyboard packet (campaign brief, script, scenes, …).",
    )
    parser.add_argument(
        "--out",
        default="selected_voices.json",
        help="Output JSON file for selected voices.",
    )
    parser.add_argument(
        "--max-voices",
        type=int,
        default=100,
        help="Maximum ElevenLabs voices to send to Gemini.",
    )
    parser.add_argument(
        "--source",
        choices=["account", "shared"],
        default="account",
        help="Voice source to fetch from: account (default) or shared library.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_GEMINI_MODEL,
        help=f"Gemini model name. Default: {DEFAULT_GEMINI_MODEL}",
    )
    parser.add_argument(
        "--top-voices",
        type=int,
        default=10,
        help="Total number of shortlisted voices to return. Default: 10.",
    )
    args = parser.parse_args()

    if args.top_voices < 2:
        raise SystemExit(
            "--top-voices must be at least 2 (one recommended voice plus at least one alternative)."
        )

    elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not elevenlabs_api_key:
        raise SystemExit("Missing ELEVENLABS_API_KEY environment variable.")

    if not gemini_api_key:
        raise SystemExit("Missing GEMINI_API_KEY environment variable.")

    storyboard_pkt = load_storyboard(args.storyboard)
    formatted_storyboard = format_storyboard_for_prompt(storyboard_pkt)

    print("Fetching ElevenLabs voices...")
    if args.source == "shared":
        voices = fetch_elevenlabs_shared_voices(elevenlabs_api_key, max_voices=args.max_voices)
    else:
        voices = fetch_elevenlabs_voices(elevenlabs_api_key, max_voices=args.max_voices)
    print(f"Fetched {len(voices)} voices.")

    print("Asking Gemini to select best voices...")
    selected = select_voices_with_gemini(
        gemini_api_key=gemini_api_key,
        model=args.model,
        formatted_storyboard=formatted_storyboard,
        voices=voices,
        top_voices=args.top_voices,
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(selected, f, indent=2, ensure_ascii=False)

    print(f"Wrote {args.out}")
    print(json.dumps(selected, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()