"""Standalone proof-of-call script for one Gemini API Veo generation.

WARNING: Do not run this casually. Veo generation may be paid and may require
billing, quota, and preview/model access on the Gemini API project.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

OUTPUT_PATH = Path("proof_output_v2.mp4")
POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 300
VEO_MODEL = "veo-3.1-lite-generate-preview"

PROMPT = (
    "A professional business presenter in a modern office, speaking directly to "
    "camera. Clean soft lighting, subtle corporate background, realistic commercial "
    "video style, no on-screen text. She says exactly and only these words, nothing "
    "else: \"Welcome to Cloudtech. Let us get started.\""
)


def require_gemini_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or api_key in {"your-gemini-api-key", "your-gemini-api-key-here"}:
        raise RuntimeError("Add GEMINI_API_KEY to local .env before running this script.")

    return api_key


def main() -> int:
    api_key = require_gemini_api_key()
    client = genai.Client(api_key=api_key)

    print(f"Submitting one Veo request with model: {VEO_MODEL}")
    operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=PROMPT,
        config=types.GenerateVideosConfig(
            aspect_ratio="16:9",
            duration_seconds=4,
            number_of_videos=1,
            resolution="720p",
        ),
    )
    print(f"Operation: {operation.name}")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    while not operation.done:
        if time.monotonic() >= deadline:
            print(f"Timed out waiting for Veo operation after {TIMEOUT_SECONDS} seconds.")
            print(f"Operation can be checked later by reference: {operation.name}")
            return 2

        print("Waiting for video generation to complete...")
        time.sleep(POLL_INTERVAL_SECONDS)
        operation = client.operations.get(operation)

    if operation.error:
        print(f"Veo operation failed: {operation.error}")
        return 1

    generated_videos = operation.response.generated_videos if operation.response else []
    if not generated_videos:
        print("Veo operation completed but returned no generated videos.")
        return 1

    generated_video = generated_videos[0]
    client.files.download(file=generated_video.video)
    generated_video.video.save(str(OUTPUT_PATH))

    print(f"Saved video to: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
