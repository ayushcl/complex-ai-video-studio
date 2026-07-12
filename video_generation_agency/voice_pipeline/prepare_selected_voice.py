#!/usr/bin/env python3
"""
Add a shared ElevenLabs voice (from Gemini selection JSON) into the workspace.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Add selected shared voice to ElevenLabs workspace and write prepared_voice.json."
    )
    p.add_argument(
        "--selected",
        default="selected_voices.json",
        help="Path to Gemini output JSON with recommended_voice and alternatives.",
    )
    p.add_argument(
        "--out",
        default="prepared_voice.json",
        help="Path to write the preparation result JSON.",
    )
    p.add_argument(
        "--rank",
        type=int,
        default=1,
        help="1 = recommended_voice; 2+ = alternatives by list order (alternatives[0], alternatives[1], …).",
    )
    return p.parse_args()


def require_str(d: dict[str, Any], key: str, ctx: str) -> str:
    v = d.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        raise SystemExit(
            f"Invalid selection ({ctx}): missing or empty {key!r}. "
            f"Expected voice_id, owner_id, and voice_name from {ctx}."
        )
    if not isinstance(v, str):
        v = str(v)
    s = v.strip()
    if not s:
        raise SystemExit(
            f"Invalid selection ({ctx}): {key!r} is empty after stripping."
        )
    return s


def pick_voice(data: dict[str, Any], rank: int) -> tuple[dict[str, Any], str]:
    if rank < 1:
        raise SystemExit("Rank must be 1 or greater.")

    rec = data.get("recommended_voice")
    if not isinstance(rec, dict):
        raise SystemExit(
            "selected_voices.json has no object 'recommended_voice'."
        )

    alts = data.get("alternatives")
    if alts is None:
        alts = []
    if not isinstance(alts, list):
        raise SystemExit("selected_voices.json has no list 'alternatives'.")

    total_voices = 1 + len(alts)
    if rank > total_voices:
        raise SystemExit(
            f"Rank {rank} requested, but only {total_voices} voices found."
        )

    if rank == 1:
        return rec, "recommended_voice"

    index = rank - 2
    item = alts[index]
    if not isinstance(item, dict):
        raise SystemExit(
            f"alternatives[{index}] must be an object for rank {rank}."
        )
    return item, f"alternatives[{index}]"


def extract_workspace_voice_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    vid = payload.get("voice_id")
    if isinstance(vid, str) and vid.strip():
        return vid.strip()
    return None


def main() -> None:
    args = parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing ELEVENLABS_API_KEY environment variable.")

    with open(args.selected, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{args.selected} must be a JSON object.")

    voice_obj, ctx = pick_voice(data, args.rank)

    voice_id = require_str(voice_obj, "voice_id", ctx)
    owner_id = require_str(voice_obj, "owner_id", ctx)
    voice_name = require_str(voice_obj, "voice_name", ctx)

    url = f"https://api.elevenlabs.io/v1/voices/add/{owner_id}/{voice_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    body = {"new_name": voice_name}

    result: dict[str, Any] = {
        "source_voice_id": voice_id,
        "owner_id": owner_id,
        "voice_name": voice_name,
        "requested_rank": args.rank,
        "workspace_voice_id": None,
        "raw_response": None,
        "status": None,
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=60)
        result["status"] = r.status_code

        try:
            parsed: Any = r.json()
        except json.JSONDecodeError:
            parsed = r.text or None

        result["raw_response"] = parsed

        if r.ok and isinstance(parsed, dict):
            wvid = extract_workspace_voice_id(parsed)
            if wvid:
                result["workspace_voice_id"] = wvid
    except requests.RequestException as e:
        result["status"] = "request_error"
        result["raw_response"] = str(e)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Wrote {args.out}")
    st = result.get("status")
    if st == "request_error":
        raise SystemExit(
            f"Request failed: {result.get('raw_response')!r}. See {args.out}."
        )
    if isinstance(st, int) and not (200 <= st < 300):
        raise SystemExit(
            f"ElevenLabs API returned HTTP {st}. See {args.out} for raw_response."
        )


if __name__ == "__main__":
    main()
