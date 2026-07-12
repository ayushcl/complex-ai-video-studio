"""Dry-run-first proof script for a two-scene Veo extension chain.

WARNING: Run with --run only after explicit approval. Veo generation may be paid
and may require billing, quota, and preview/model access.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

VEO_MODEL = "veo-3.1-generate-preview"

OUTPUT_DIR = Path("veo_extension_proof")
SCENE_01_PATH = OUTPUT_DIR / "scene_01_seed.mp4"
SCENE_02_PATH = OUTPUT_DIR / "scene_02_extended.mp4"
REPORT_PATH = OUTPUT_DIR / "extension_report.json"

POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 600

SCENE_1_PROMPT = (
    "A silent website hero background video, 16:9, 720p, 24fps. Warm amber and "
    "copper accent tones on a near-black ambient ground. A minimal dark modern "
    "desk surface with a closed premium unbranded laptop on the right. A clear "
    "rectangular glass prism sits near the right edge. Copper-gold refracted "
    "light moves slowly across the dark surface, grazing the laptop. No text, "
    "no logos, no people. Locked off camera, calm motion."
)

SCENE_2_PROMPT = (
    "Resume motion seamlessly from the exact last frame. Hold the lighting and "
    "composition exactly. A single anonymous hand in a dark sleeve enters "
    "briefly from the right edge and opens the laptop slowly. A warm amber glow "
    "emerges from the screen. The hand exits. No text, no faces, no extra "
    "monitors."
)

NEGATIVE_CONSTRAINTS = (
    "audio, music, narration, dialogue, ambience, sound effects, readable text, "
    "logos, watermarks, identifiable faces, extra people, external monitor, "
    "second screen, camera shake"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or run a two-scene Veo extension proof."
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Submit the two paid Veo requests. Omit for dry-run only.",
    )
    parser.add_argument(
        "--extension-input-mode",
        choices=("video", "source"),
        default="video",
        help=(
            "Use video= for the extension call by default. Use source= only "
            "after confirming video= is rejected; the script never auto-retries."
        ),
    )
    return parser.parse_args()


def generate_video_config_fields() -> set[str]:
    return set(types.GenerateVideosConfig.model_fields.keys())


def build_generate_videos_config(*, include_duration: bool) -> tuple[types.GenerateVideosConfig, dict[str, Any]]:
    fields = generate_video_config_fields()
    config_kwargs: dict[str, Any] = {}

    if "aspect_ratio" in fields:
        config_kwargs["aspect_ratio"] = "16:9"
    if "resolution" in fields:
        config_kwargs["resolution"] = "720p"
    if "number_of_videos" in fields:
        config_kwargs["number_of_videos"] = 1
    if include_duration and "duration_seconds" in fields:
        config_kwargs["duration_seconds"] = 8
    if "negative_prompt" in fields:
        config_kwargs["negative_prompt"] = NEGATIVE_CONSTRAINTS

    return types.GenerateVideosConfig(**config_kwargs), config_kwargs


def require_gemini_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or api_key in {"your-gemini-api-key", "your-gemini-api-key-here"}:
        raise RuntimeError("Add GEMINI_API_KEY to local .env before running this script.")

    return api_key


def wait_for_operation(client: genai.Client, operation: Any, label: str) -> Any:
    print(f"{label} operation: {operation.name}")
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while not operation.done:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for {label} after {TIMEOUT_SECONDS} seconds. "
                f"Operation can be checked later by reference: {operation.name}"
            )

        print(f"Waiting for {label} to complete...")
        time.sleep(POLL_INTERVAL_SECONDS)
        operation = client.operations.get(operation)

    if operation.error:
        raise RuntimeError(f"{label} failed: {operation.error}")

    return operation


def first_generated_video(operation: Any, label: str) -> Any:
    generated_videos = operation.response.generated_videos if operation.response else []
    if not generated_videos:
        raise RuntimeError(f"{label} completed but returned no generated videos.")
    return generated_videos[0].video


def extension_video_reference(scene_1_video: types.Video) -> tuple[types.Video, str]:
    if scene_1_video.uri:
        return (
            types.Video(uri=scene_1_video.uri, mime_type=scene_1_video.mime_type),
            "returned Video URI",
        )

    raise RuntimeError(
        "Scene 1 returned no video URI to pass into the extension call. "
        "This script intentionally does not fall back to raw video_bytes."
    )


def save_video(client: genai.Client, video: types.Video, output_path: Path) -> None:
    client.files.download(file=video)
    video.save(str(output_path))


def run_chain(extension_input_mode: str) -> int:
    api_key = require_gemini_api_key()
    client = genai.Client(api_key=api_key)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    scene_1_config, scene_1_config_kwargs = build_generate_videos_config(
        include_duration=True
    )
    scene_2_config, scene_2_config_kwargs = build_generate_videos_config(
        include_duration=False
    )

    print(f"Submitting Scene 1 seed request with model: {VEO_MODEL}")
    scene_1_operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=SCENE_1_PROMPT,
        config=scene_1_config,
    )
    scene_1_operation = wait_for_operation(client, scene_1_operation, "Scene 1")
    scene_1_video = first_generated_video(scene_1_operation, "Scene 1")
    scene_1_extension_video, scene_1_reference_kind = extension_video_reference(
        scene_1_video
    )

    save_video(client, scene_1_video, SCENE_01_PATH)
    print(f"Saved Scene 1 seed video to: {SCENE_01_PATH}")

    print(f"Submitting Scene 2 extension request with model: {VEO_MODEL}")
    try:
        if extension_input_mode == "source":
            scene_2_operation = client.models.generate_videos(
                model=VEO_MODEL,
                source=types.GenerateVideosSource(
                    video=scene_1_extension_video,
                    prompt=SCENE_2_PROMPT,
                ),
                config=scene_2_config,
            )
            extension_call_pattern = "source=types.GenerateVideosSource(video=scene_1_video, prompt=SCENE_2_PROMPT)"
        else:
            scene_2_operation = client.models.generate_videos(
                model=VEO_MODEL,
                prompt=SCENE_2_PROMPT,
                video=scene_1_extension_video,
                config=scene_2_config,
            )
            extension_call_pattern = "prompt=SCENE_2_PROMPT, video=scene_1_video"
    except Exception as exc:
        print(
            "Scene 2 extension submission failed. No fallback request was "
            "attempted automatically."
        )
        print(
            "If video= was rejected before submission, inspect the error and "
            "rerun explicitly with --extension-input-mode source."
        )
        raise exc

    scene_2_operation = wait_for_operation(client, scene_2_operation, "Scene 2")
    scene_2_video = first_generated_video(scene_2_operation, "Scene 2")
    save_video(client, scene_2_video, SCENE_02_PATH)
    print(f"Saved Scene 2 extended video to: {SCENE_02_PATH}")

    report = {
        "model": VEO_MODEL,
        "scene_1_operation": scene_1_operation.name,
        "scene_2_operation": scene_2_operation.name,
        "scene_1_output": str(SCENE_01_PATH),
        "scene_2_output": str(SCENE_02_PATH),
        "scene_1_prompt": SCENE_1_PROMPT,
        "scene_2_prompt": SCENE_2_PROMPT,
        "negative_constraints": NEGATIVE_CONSTRAINTS,
        "scene_1_config": scene_1_config_kwargs,
        "scene_2_config": scene_2_config_kwargs,
        "extension_input_mode": extension_input_mode,
        "extension_input_reference": scene_1_reference_kind,
        "extension_call_pattern": extension_call_pattern,
    }
    with REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(f"Saved extension report to: {REPORT_PATH}")

    return 0


def dry_run(extension_input_mode: str) -> int:
    fields = sorted(generate_video_config_fields())
    scene_1_config, scene_1_config_kwargs = build_generate_videos_config(
        include_duration=True
    )
    scene_2_config, scene_2_config_kwargs = build_generate_videos_config(
        include_duration=False
    )
    _ = scene_1_config, scene_2_config

    print("DRY RUN ONLY - no API calls will be made.")
    print(f"Model: {VEO_MODEL}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Scene 1 output: {SCENE_01_PATH}")
    print(f"Scene 2 output: {SCENE_02_PATH}")
    print(f"Report output: {REPORT_PATH}")
    print(f"GenerateVideosConfig fields supported: {', '.join(fields)}")
    print(f"negative_prompt supported: {'negative_prompt' in fields}")
    print(
        "generate_audio omitted because Gemini Developer API rejects this field; "
        "audio is discouraged through negative_prompt and can be stripped in post."
    )

    print("\nScene 1 planned call:")
    print(
        "client.models.generate_videos("
        "model=VEO_MODEL, prompt=SCENE_1_PROMPT, config=GenerateVideosConfig(...))"
    )
    print(json.dumps(scene_1_config_kwargs, indent=2))

    print("\nScene 2 planned extension call:")
    if extension_input_mode == "source":
        print(
            "client.models.generate_videos("
            "model=VEO_MODEL, "
            "source=types.GenerateVideosSource("
            "video=<Scene 1 returned Video URI>, prompt=SCENE_2_PROMPT), "
            "config=GenerateVideosConfig(...))"
        )
    else:
        print(
            "client.models.generate_videos("
            "model=VEO_MODEL, prompt=SCENE_2_PROMPT, "
            "video=<Scene 1 returned Video URI>, "
            "config=GenerateVideosConfig(...))"
        )
    print(json.dumps(scene_2_config_kwargs, indent=2))
    print(f"Extension input mode: {extension_input_mode}")
    print("Extension input reference: returned Video object with URI; no raw video_bytes")
    print("client.files.get: not used by this script unless future SDK output changes")

    return 0


def main() -> int:
    args = parse_args()
    if not args.run:
        return dry_run(args.extension_input_mode)
    return run_chain(args.extension_input_mode)


if __name__ == "__main__":
    raise SystemExit(main())
