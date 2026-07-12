"""Dry-run-first N-scene Veo extension chain runner.

WARNING: Run with --run only after explicit approval. Veo generation may be paid
and may require billing, quota, and preview/model access.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

DEFAULT_VEO_MODEL = "veo-3.1-fast-generate-preview"
DEFAULT_SCENES_PATH = Path("video_generation_agency/extension_scenes_6.json")
DEFAULT_OUTPUT_ROOT = Path("veo_chain_runs")
DEFAULT_RESOLUTION = "720p"
DEFAULT_ASPECT_RATIO = "9:16"
PRESENTER_REFERENCE_MODEL = "veo-3.1-fast-generate-preview"
PRESENTER_REFERENCE_RESOLUTION = "720p"
PRESENTER_REFERENCE_DURATION_SECONDS = 8
# Video extension calls require an 8s duration; omitting it causes a
# 400 "input video must be ... processed". Proven live 2026-06-26.
EXTENSION_DURATION_SECONDS = 8
EXTENSION_PROMPT_PREFIX = "Extend from the previous shot."
EXTENSION_CONTINUITY_NEGATIVE_NUDGE = (
    "different subject, subject missing from frame, empty frame, abrupt scene change, "
    "inconsistent lighting"
)
POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 900


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or run an N-scene Veo extension chain."
    )
    parser.add_argument(
        "--scenes",
        default=str(DEFAULT_SCENES_PATH),
        help=f"Path to a JSON scene array. Default: {DEFAULT_SCENES_PATH}",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Output directory for --run mode. "
            "Default: timestamped veo_chain_runs/maxiion_YYYYMMDD_HHMMSS"
        ),
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Submit paid Veo requests. Omit for dry-run only.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_VEO_MODEL,
        help=f"Veo model to use. Default: {DEFAULT_VEO_MODEL}",
    )
    parser.add_argument(
        "--resolution",
        default=DEFAULT_RESOLUTION,
        help=f"Veo output resolution. Default: {DEFAULT_RESOLUTION}",
    )
    parser.add_argument(
        "--aspect-ratio",
        default=DEFAULT_ASPECT_RATIO,
        choices=["9:16", "16:9"],
        help=f"Veo output aspect ratio. Default: {DEFAULT_ASPECT_RATIO}",
    )
    parser.add_argument(
        "--max-scenes",
        type=int,
        default=None,
        help="Only plan or run the first N scenes from the scenes file. Default: all scenes.",
    )
    parser.add_argument(
        "--presenter-reference-image",
        default=None,
        help=(
            "Optional adult presenter asset image. Scene 1 uses Veo reference-image "
            "mode with fixed Fast/8s/720p/selected aspect ratio/allow_adult settings."
        ),
    )
    parser.add_argument(
        "--person-generation",
        choices=("allow_adult",),
        default=None,
        help=(
            "Optional first-scene person-generation policy for non-reference "
            "image seeds. Generated presenter jobs use allow_adult."
        ),
    )
    return parser.parse_args()


def default_output_dir() -> Path:
    return DEFAULT_OUTPUT_ROOT / f"maxiion_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def require_gemini_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or api_key in {"your-gemini-api-key", "your-gemini-api-key-here"}:
        raise RuntimeError("Add GEMINI_API_KEY to local .env before running this script.")

    return api_key


def load_scenes(path: Path, *, require_seed_image: bool = True) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    scenes = data.get("scenes") if isinstance(data, dict) else data
    if not isinstance(scenes, list):
        raise ValueError(f"Scenes file must contain a JSON array or an object with scenes: {path}")
    if not scenes:
        raise ValueError(f"Scenes file must contain at least one scene: {path}")

    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index} must be a JSON object.")
        if not isinstance(scene.get("prompt"), str) or not scene["prompt"].strip():
            raise ValueError(f"Scene {index} is missing a non-empty prompt.")
        if "negative_prompt" in scene and not isinstance(scene["negative_prompt"], str):
            raise ValueError(f"Scene {index} negative_prompt must be a string.")
        if scene.get("prompt") == "FILL_FROM_PROOF_SCRIPT":
            raise ValueError(f"Scene {index} prompt still contains a fill placeholder.")
        if scene.get("negative_prompt") == "FILL_FROM_PROOF_SCRIPT":
            raise ValueError(f"Scene {index} negative_prompt still contains a fill placeholder.")

    if require_seed_image:
        # Without a per-run presenter reference, scene 1 is generated from the
        # scenes file's image seed. Reference mode supplies its own asset image.
        first_scene = scenes[0]
        seed_image = first_scene.get("seed_image")
        if not isinstance(seed_image, str) or not seed_image.strip():
            raise ValueError("Scene 1 is the image seed and must include a non-empty seed_image path.")

    return scenes


def limit_scenes(scenes: list[dict[str, Any]], max_scenes: int | None) -> list[dict[str, Any]]:
    if max_scenes is None:
        return scenes
    if max_scenes < 1:
        raise ValueError("--max-scenes must be at least 1.")
    if max_scenes > len(scenes):
        raise ValueError(
            f"--max-scenes {max_scenes} exceeds available scene count {len(scenes)}."
        )
    return scenes[:max_scenes]


def generate_video_config_fields() -> set[str]:
    return set(types.GenerateVideosConfig.model_fields.keys())


def duration_seconds(scene: dict[str, Any]) -> int | None:
    raw_duration = scene.get("duration_seconds", scene.get("duration"))
    if raw_duration is None:
        return None
    if isinstance(raw_duration, int):
        return raw_duration
    if isinstance(raw_duration, str):
        cleaned = raw_duration.strip().lower()
        if cleaned.endswith("s"):
            cleaned = cleaned[:-1]
        try:
            return int(float(cleaned))
        except ValueError as exc:
            raise ValueError(f"Could not parse scene duration: {raw_duration!r}") from exc
    raise ValueError(f"Unsupported scene duration value: {raw_duration!r}")


def high_resolution_requires_eight_second_seed(resolution: str) -> bool:
    return resolution.strip().lower() in {"1080p", "4k"}


def seed_duration_seconds(scene: dict[str, Any], resolution: str) -> int | None:
    if high_resolution_requires_eight_second_seed(resolution):
        return 8
    return duration_seconds(scene)


def _has_scene_seed_anchor(scenes: list[dict[str, Any]]) -> bool:
    if not scenes:
        return False
    seed_image = scenes[0].get("seed_image")
    return isinstance(seed_image, str) and bool(seed_image.strip())


def _prefix_extension_prompt(prompt: str) -> str:
    if prompt.startswith(EXTENSION_PROMPT_PREFIX):
        return prompt
    prompt_body = prompt.lstrip()
    if not prompt_body:
        return EXTENSION_PROMPT_PREFIX
    return f"{EXTENSION_PROMPT_PREFIX} {prompt_body}"


def _merge_negative_prompt(existing: str | None) -> str:
    existing_text = existing.strip() if isinstance(existing, str) else ""
    if EXTENSION_CONTINUITY_NEGATIVE_NUDGE in existing_text:
        return existing_text
    if not existing_text:
        return EXTENSION_CONTINUITY_NEGATIVE_NUDGE
    return f"{existing_text}, {EXTENSION_CONTINUITY_NEGATIVE_NUDGE}"


def _effective_scene_for_chain(
    scene: dict[str, Any],
    scene_index: int,
    anchored_chain: bool,
) -> dict[str, Any]:
    if not anchored_chain or scene_index <= 1:
        return scene

    effective_scene = dict(scene)
    effective_scene["prompt"] = _prefix_extension_prompt(scene["prompt"])
    effective_scene["negative_prompt"] = _merge_negative_prompt(
        scene.get("negative_prompt")
    )
    return effective_scene


def build_config(
    scene: dict[str, Any],
    *,
    include_duration: bool,
    resolution: str,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    extension_duration_seconds: int | None = None,
    presenter_reference_image: Path | None = None,
    person_generation: str | None = None,
) -> tuple[types.GenerateVideosConfig, dict[str, Any]]:
    fields = generate_video_config_fields()
    config_kwargs: dict[str, Any] = {}

    if presenter_reference_image is not None:
        required_fields = {
            "aspect_ratio",
            "resolution",
            "number_of_videos",
            "duration_seconds",
            "person_generation",
            "reference_images",
        }
        missing_fields = sorted(required_fields - fields)
        if missing_fields:
            raise RuntimeError(
                "Installed google-genai does not support required presenter reference fields: "
                + ", ".join(missing_fields)
            )
        config_kwargs.update(
            {
                "aspect_ratio": aspect_ratio,
                "resolution": PRESENTER_REFERENCE_RESOLUTION,
                "number_of_videos": 1,
                "duration_seconds": PRESENTER_REFERENCE_DURATION_SECONDS,
                "person_generation": "allow_adult",
                "reference_images": [
                    types.VideoGenerationReferenceImage(
                        image=types.Image.from_file(location=str(presenter_reference_image)),
                        reference_type="asset",
                    )
                ],
            }
        )
        report_config = {
            key: value for key, value in config_kwargs.items() if key != "reference_images"
        }
        report_config["reference_images"] = [
            {"image": str(presenter_reference_image), "reference_type": "asset"}
        ]
        return types.GenerateVideosConfig(**config_kwargs), report_config

    if "aspect_ratio" in fields:
        config_kwargs["aspect_ratio"] = aspect_ratio
    if "resolution" in fields:
        config_kwargs["resolution"] = resolution
    if "number_of_videos" in fields:
        config_kwargs["number_of_videos"] = 1
    if include_duration and "duration_seconds" in fields:
        parsed_duration = seed_duration_seconds(scene, resolution)
        if parsed_duration is not None:
            config_kwargs["duration_seconds"] = parsed_duration
    elif extension_duration_seconds is not None and "duration_seconds" in fields:
        # Extension config must carry the known-good duration constant.
        config_kwargs["duration_seconds"] = extension_duration_seconds
    if include_duration and person_generation:
        if "person_generation" not in fields:
            raise RuntimeError(
                "Installed google-genai does not support person_generation."
            )
        config_kwargs["person_generation"] = person_generation
    if "negative_prompt" in fields and scene.get("negative_prompt"):
        config_kwargs["negative_prompt"] = scene["negative_prompt"]

    return types.GenerateVideosConfig(**config_kwargs), config_kwargs


def image_seed(scene: dict[str, Any]) -> types.Image:
    seed_image = scene.get("seed_image")
    if not isinstance(seed_image, str) or not seed_image.strip():
        raise ValueError("A01 image seed scene must include seed_image.")

    seed_image_path = Path(seed_image)
    if not seed_image_path.is_file():
        raise FileNotFoundError(f"A01 seed image not found: {seed_image_path}")

    return types.Image.from_file(location=str(seed_image_path))


def scene_output_path(output_dir: Path, scene_index: int) -> Path:
    if scene_index == 1:
        return output_dir / "scene_01_seed.mp4"
    return output_dir / f"scene_{scene_index:02d}_combined.mp4"


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


def video_uri_reference(video: types.Video, label: str) -> tuple[types.Video, str]:
    if video.uri:
        return types.Video(uri=video.uri, mime_type=video.mime_type), "returned Video URI"

    raise RuntimeError(
        f"{label} returned no video URI to pass into the next extension call. "
        "This runner intentionally does not fall back to raw video_bytes."
    )


def save_video(client: genai.Client, video: types.Video, output_path: Path) -> None:
    client.files.download(file=video)
    video.save(str(output_path))


def strip_audio(input_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-an",
        "-c:v",
        "copy",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def run_chain(
    scenes: list[dict[str, Any]],
    output_dir: Path,
    model: str,
    resolution: str,
    aspect_ratio: str,
    presenter_reference_image: Path | None,
    person_generation: str | None,
) -> int:
    api_key = require_gemini_api_key()
    client = genai.Client(api_key=api_key)
    output_dir.mkdir(parents=True, exist_ok=True)
    anchored_chain = presenter_reference_image is not None or _has_scene_seed_anchor(scenes)

    report: dict[str, Any] = {
        "model": model,
        "aspect_ratio": aspect_ratio,
        "presenter_reference_image": (
            str(presenter_reference_image) if presenter_reference_image else None
        ),
        "scenes_file_scene_count": len(scenes),
        "seed_call_pattern": (
            "prompt=scenes[0]['prompt'], config.reference_images=[asset image]"
            if presenter_reference_image
            else "prompt=scenes[0]['prompt'], image=types.Image.from_file(location=scenes[0]['seed_image'])"
        ),
        "anchored_chain": anchored_chain,
        "extension_prompt_prefix": EXTENSION_PROMPT_PREFIX if anchored_chain else None,
        "extension_negative_prompt_nudge": (
            EXTENSION_CONTINUITY_NEGATIVE_NUDGE if anchored_chain else None
        ),
        "extension_call_pattern": "prompt=effective_scene['prompt'], video=previous_combined_video",
        "scene_results": [],
    }
    previous_combined_video: types.Video | None = None
    last_output_path: Path | None = None

    for scene_index, scene in enumerate(scenes, start=1):
        label = f"Scene {scene_index}"
        effective_scene = _effective_scene_for_chain(
            scene, scene_index, anchored_chain
        )
        config, config_kwargs = build_config(
            effective_scene,
            include_duration=(scene_index == 1),
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            extension_duration_seconds=(
                EXTENSION_DURATION_SECONDS if scene_index != 1 else None
            ),
            presenter_reference_image=(
                presenter_reference_image if scene_index == 1 else None
            ),
            person_generation=person_generation if scene_index == 1 else None,
        )
        output_path = scene_output_path(output_dir, scene_index)

        if scene_index == 1:
            if presenter_reference_image is not None:
                print(f"Submitting {label} presenter reference request with model: {model}")
                operation = client.models.generate_videos(
                    model=model,
                    prompt=effective_scene["prompt"],
                    config=config,
                )
                call_pattern = (
                    "presenter reference: prompt=scenes[0]['prompt'], "
                    "config.reference_images=[VideoGenerationReferenceImage(asset)]"
                )
            else:
                print(f"Submitting {label} image seed request with model: {model}")
                operation = client.models.generate_videos(
                    model=model,
                    prompt=effective_scene["prompt"],
                    image=image_seed(scene),
                    config=config,
                )
                call_pattern = (
                    "image seed: prompt=scenes[0]['prompt'], "
                    "image=types.Image.from_file(location=scenes[0]['seed_image'])"
                )
        else:
            if previous_combined_video is None:
                raise RuntimeError("No previous video reference available for extension.")
            print(f"Submitting {label} extension request with model: {model}")
            operation = client.models.generate_videos(
                model=model,
                prompt=effective_scene["prompt"],
                video=previous_combined_video,
                config=config,
            )
            call_pattern = (
                "extension: prompt=effective_scene['prompt'], "
                "video=previous_combined_video"
            )

        operation = wait_for_operation(client, operation, label)
        generated_video = first_generated_video(operation, label)
        previous_combined_video, reference_kind = video_uri_reference(generated_video, label)
        save_video(client, generated_video, output_path)
        print(f"Saved {label} output to: {output_path}")
        last_output_path = output_path

        report["scene_results"].append(
            {
                "scene_index": scene_index,
                "operation": operation.name,
                "output": str(output_path),
                "prompt": effective_scene["prompt"],
                "negative_prompt": effective_scene.get("negative_prompt"),
                "config": config_kwargs,
                "call_pattern": call_pattern,
                "extension_input_reference": reference_kind if scene_index > 1 else None,
            }
        )

    if last_output_path is None:
        raise RuntimeError("No final scene output was created.")

    final_raw_path = output_dir / "final_raw.mp4"
    final_silent_path = output_dir / "final_silent.mp4"
    shutil.copyfile(last_output_path, final_raw_path)
    strip_audio(final_raw_path, final_silent_path)

    report["final_raw"] = str(final_raw_path)
    report["final_silent"] = str(final_silent_path)
    report["audio_strip"] = {
        "input": str(final_raw_path),
        "output": str(final_silent_path),
        "command": f"ffmpeg -y -i {final_raw_path} -an -c:v copy {final_silent_path}",
        "final_only": True,
    }

    report_path = output_dir / "chain_report.json"
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(f"Saved chain report to: {report_path}")
    print(f"Saved final raw video to: {final_raw_path}")
    print(f"Saved final silent video to: {final_silent_path}")

    return 0


def dry_run(
    scenes: list[dict[str, Any]],
    scenes_path: Path,
    output_dir: Path,
    model: str,
    resolution: str,
    aspect_ratio: str,
    max_scenes: int | None,
    presenter_reference_image: Path | None,
    person_generation: str | None,
) -> int:
    seed_duration = (
        PRESENTER_REFERENCE_DURATION_SECONDS
        if presenter_reference_image
        else seed_duration_seconds(scenes[0], resolution) or 6
    )
    extension_count = max(0, len(scenes) - 1)
    anchored_chain = presenter_reference_image is not None or _has_scene_seed_anchor(scenes)
    print("DRY RUN ONLY - no API calls will be made.")
    print(f"Scenes file: {scenes_path}")
    print(f"Max scenes: {max_scenes if max_scenes is not None else 'all'}")
    print(f"Scenes loaded/planned: {len(scenes)}")
    print(f"Model: {model}")
    print(f"Resolution: {resolution}")
    print(f"Person generation: {person_generation or 'SDK default'}")
    print(f"Anchored chain: {'yes' if anchored_chain else 'no'}")
    if anchored_chain:
        print(f"Extension prompt prefix: {EXTENSION_PROMPT_PREFIX}")
        print(f"Extension negative_prompt nudge: {EXTENSION_CONTINUITY_NEGATIVE_NUDGE}")
    if presenter_reference_image:
        print("A01 is PRESENTER ASSET REFERENCE.")
        print(f"A01 presenter reference image: {presenter_reference_image}")
        print("A01 uses config.reference_images=[VideoGenerationReferenceImage(reference_type='asset')].")
        print("A01 person_generation: allow_adult")
    else:
        print("A01 is IMAGE SEED.")
        print("A01 uses image=types.Image.from_file(location=scenes[0]['seed_image']).")
        print(f"A01 seed image: {scenes[0].get('seed_image')}")
    print(f"A01 duration_seconds: {seed_duration}")
    if len(scenes) > 1:
        if len(scenes) == 2:
            print("A02 is a video= extension from the previous combined Video.")
        else:
            print(f"A02-A{len(scenes):02d} are video= extensions from the previous combined Video.")
    else:
        print("No extension scenes are planned.")
    print("NO generate_audio is passed because Gemini Developer API rejects this field.")
    print("Final audio-strip happens only in --run mode.")
    print(f"Expected Veo call count: {len(scenes)}")
    print(
        "Expected duration: "
        f"about {seed_duration} + {extension_count}x7 = {seed_duration + extension_count * 7}s"
    )
    print(f"Timestamped output dir planned: {output_dir}")
    print(f"Final raw output: {output_dir / 'final_raw.mp4'}")
    print(f"Final silent output: {output_dir / 'final_silent.mp4'}")
    print(f"Report output: {output_dir / 'chain_report.json'}")
    if presenter_reference_image:
        print(
            "A01 call pattern: client.models.generate_videos("
            "model=model, prompt=scenes[0]['prompt'], config=GenerateVideosConfig("
            "reference_images=[VideoGenerationReferenceImage(..., reference_type='asset')], ...))"
        )
    else:
        print(
            "A01 call pattern: client.models.generate_videos("
            "model=model, prompt=scenes[0]['prompt'], "
            "image=types.Image.from_file(location=scenes[0]['seed_image']), config=config)"
        )
    print(
        "A02+ extension call pattern: client.models.generate_videos("
        "model=model, prompt=effective_scene['prompt'], "
        "video=previous_combined_video, config=config)"
    )

    for scene_index, scene in enumerate(scenes, start=1):
        effective_scene = _effective_scene_for_chain(
            scene, scene_index, anchored_chain
        )
        _, config_kwargs = build_config(
            effective_scene,
            include_duration=(scene_index == 1),
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            extension_duration_seconds=(
                EXTENSION_DURATION_SECONDS if scene_index != 1 else None
            ),
            presenter_reference_image=(
                presenter_reference_image if scene_index == 1 else None
            ),
            person_generation=person_generation if scene_index == 1 else None,
        )
        output_path = scene_output_path(output_dir, scene_index)
        if scene_index == 1:
            if presenter_reference_image:
                call_type = "PRESENTER ASSET REFERENCE"
                planned_call = (
                    "client.models.generate_videos("
                    "model=model, prompt=scenes[0]['prompt'], "
                    "config=GenerateVideosConfig(reference_images=[asset], ...))"
                )
            else:
                call_type = "IMAGE SEED"
                planned_call = (
                    "client.models.generate_videos("
                    "model=model, prompt=scenes[0]['prompt'], "
                    "image=types.Image.from_file(location=scenes[0]['seed_image']), "
                    "config=GenerateVideosConfig(...))"
                )
        else:
            call_type = "video= EXTENSION"
            planned_call = (
                "client.models.generate_videos("
                "model=model, prompt=effective_scene['prompt'], "
                "video=previous_combined_video, config=GenerateVideosConfig(...))"
            )

        print(f"\nScene {scene_index}: {call_type}")
        print(f"Output: {output_path}")
        print(f"Duration field: {scene.get('duration_seconds', scene.get('duration'))}")
        print(f"Resolution field: {scene.get('resolution')}")
        print(f"Effective prompt: {effective_scene['prompt']}")
        print(
            "Effective negative_prompt: "
            f"{effective_scene.get('negative_prompt') or '(none)'}"
        )
        print(f"Planned call: {planned_call}")
        print(json.dumps(config_kwargs, indent=2))

    return 0


def main() -> int:
    args = parse_args()
    scenes_path = Path(args.scenes)
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir()
    presenter_reference_image = (
        Path(args.presenter_reference_image).expanduser()
        if args.presenter_reference_image
        else None
    )
    if presenter_reference_image is not None and not presenter_reference_image.is_file():
        raise FileNotFoundError(
            f"Presenter reference image not found: {presenter_reference_image}"
        )
    model = PRESENTER_REFERENCE_MODEL if presenter_reference_image else args.model
    resolution = (
        PRESENTER_REFERENCE_RESOLUTION if presenter_reference_image else args.resolution
    )
    scenes = limit_scenes(
        load_scenes(scenes_path, require_seed_image=presenter_reference_image is None),
        args.max_scenes,
    )

    if not args.run:
        return dry_run(
            scenes,
            scenes_path,
            output_dir,
            model,
            resolution,
            args.aspect_ratio,
            args.max_scenes,
            presenter_reference_image,
            args.person_generation,
        )
    return run_chain(
        scenes,
        output_dir,
        model,
        resolution,
        args.aspect_ratio,
        presenter_reference_image,
        args.person_generation,
    )


if __name__ == "__main__":
    raise SystemExit(main())
