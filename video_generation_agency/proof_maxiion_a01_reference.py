"""Dry-run-first MAXIION A01 reference-image Veo proof.

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

DEFAULT_VEO_MODEL = "veo-3.1-fast-generate-preview"
REFERENCE_IMAGE_PATH = Path("video_generation_agency/assets/maxiion_wordmark.png")
OUTPUT_DIR = Path("maxiion_a01_proof")
POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 600

PROMPT = """Use the supplied MAXIION wordmark reference image as the authoritative letterform guide for this shot. Preserve the exact spelling, exact letter order, and exact letter structure from the reference. The visible word must read exactly as MAXIION in all capitals: M A X I I O N. The two consecutive uppercase I letters between X and O must be clearly separated, individually readable, and unmistakably present as two letters. Do not simplify, omit, merge, fuse, interrupt, or reinterpret either I. These are strict correctness rules for the brand typography; the shot itself should still feel primarily like a premium product hero.

Create a very dark, low key, premium macro hero shot of that exact MAXIION wordmark, transformed into a sculptural object made from clear optical glass with a warm copper amber tint through the thickness of the material. The wordmark rests directly on a clean, dry, near black desk surface. There are no other objects on the desk.

The scene should be dark and restrained. The base world is deep warm charcoal, graphite black, dark espresso black, and smoked bronze shadow. Most of the frame sits in controlled darkness. The glass wordmark is visible because light passes through it, not because the whole scene is brightly lit. The contrast between dark glass, deep shadow, and sharp copper light effects is the central visual idea.

The exact MAXIION wordmark is rendered as dimensional optical glass with crisp polished faces, sharp edges, subtle internal depth, and strong refraction. The glass should be highly refractive. Light bends visibly through the letters, splitting into clean angular internal lines, bright copper edge catches, and narrow shards of refracted light across the dry desk surface. These are shards of light only, not broken glass fragments.

Typography construction rule. The full MAXIION wordmark should remain on one continuous glass wordmark plaque wherever possible. If the shot includes multiple glass sections, internal refraction lines, panel boundaries, edge glows, caustic streaks, shadow lines, or material breaks, they must not cut through, touch, pass between, or visually interfere with the two I letters. Keep the space between the two I letters clean and readable so the viewer immediately sees two separate uppercase I letters, while preserving the overall premium optical glass composition.

A single concentrated warm copper key light passes through the wordmark from one low side angle. The light creates elegant copper gold internal glow, bright amber edge highlights, and sharp refracted light shards that cut across the desk in narrow angular streaks. Some shards are bright warm copper, some are darker smoked bronze, and a few edge glints may catch as warm ivory. The effect should feel like precision cut optical glass splitting light in a dark studio.

In the final half second, one controlled copper edge glint brightens softly across the glass, like a brief flash of light passing through the wordmark, then settles. The flash is elegant, restrained, and photographic. It must not cross between the two I letters, split either I, or create a bright boundary that makes the double I look merged or interrupted. It is not an explosion, not a burst, not a shockwave, and not a particle effect.

The desk surface is smooth, dark, matte to satin, and completely dry. It is a warm charcoal black surface, not a cold black surface. There is no puddle, no liquid, no spill, no wet sheen, and no glossy pool around or beneath the wordmark. The refracted light appears as dry, crisp, angular copper light shards and narrow caustic streaks on the surface, not watery reflection.

Camera is locked off in a tight macro composition. The full MAXIION wordmark is fully visible in frame and fills most of the horizontal composition. Very slight optional push in only, almost imperceptible. No camera shake. No visible environment detail beyond the dry desk surface and dark background. The background falls into warm graphite black with a faint bronze undertone.

Colour theme lock. Deep warm charcoal and graphite black base. Copper gold, amber ochre, smoked bronze, and warm honeyed copper light. Tiny warm ivory glints only on the brightest glass edges and the sharpest light shards. No cold blue cast, no green drift, no teal lighting, no rainbow prism look, no grey contamination.

Absence. No other objects in frame. No people. No papers. No screens. No props. No room detail. No extra text. No logos other than the referenced MAXIION wordmark itself. No captions, subtitles, watermarks, or overlays.

Preserve the successful overall look from the previous A01 proof: separate M icon tile, continuous premium MAXIION glass wordmark, copper amber glow, dark luxury background, cinematic low key lighting, clean desk surface, and restrained product-hero composition.

Mood is dark, precise, premium, restrained, and brand led. The shot should feel like a luxury optical glass object photographed in a dark studio, with immaculate control and sharp copper amber light refraction. Silent. No audio generated."""

NEGATIVE_PROMPT = """misspelled wordmark, incorrect spelling, missing second I, single I between X and O, merged double I, confusing double I, interrupted I letters, fused I letters, unreadable double I, double I looks like one letter, split between I letters, seam between the two I letters, panel break between the two I letters, refraction line between the two I letters, glow edge between the two I letters, caustic line between the two I letters, shadow line between the two I letters, material break through the I letters, boundary cutting through double I, fused letters, distorted lettering, altered typography, incorrect letter count, unreadable wordmark, cropped letters, extra letters, letter substitution, reinterpretation of the wordmark, overbright scene, high key lighting, bright studio lighting, flat evenly lit desk, explosion, light explosion, burst of light, shockwave, sparks, particles, smoke, fire, dramatic blast, aggressive lens flare, plain colourless glass, silver glass, blue glass, green glass, rainbow prism effect, multicolour refraction, cold blue cast, teal lighting, green lighting, grey colour drift, white studio lighting, sterile corporate lighting, puddle, water, liquid, spill, wet surface, glossy pool, reflective pool, condensation, splash, droplets, watery caustics, messy reflections, melted glass, molten effect, resin spill, physical broken glass shards, scattered glass fragments, extra desk objects, papers, laptop, monitor, pen, phone, hand, person, silhouette, reflections of people, room detail, captions, subtitles, watermarks, camera shake, handheld movement"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or run the MAXIION A01 reference-image Veo proof."
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Submit the paid Veo request. Omit for dry-run only.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_VEO_MODEL,
        help=f"Veo model to use. Default: {DEFAULT_VEO_MODEL}",
    )
    parser.add_argument(
        "--mode",
        choices=("reference", "image"),
        default="image",
        help="Use reference_images ASSET mode or literal image= input mode.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help=f"Directory for a01_seed.mp4 and a01_report.json. Default: {OUTPUT_DIR}",
    )
    return parser.parse_args()


def require_gemini_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or api_key in {"your-gemini-api-key", "your-gemini-api-key-here"}:
        raise RuntimeError("Add GEMINI_API_KEY to local .env before running this script.")

    return api_key


def wordmark_image() -> types.Image:
    if not REFERENCE_IMAGE_PATH.is_file():
        raise FileNotFoundError(f"Reference image not found: {REFERENCE_IMAGE_PATH}")

    return types.Image.from_file(location=str(REFERENCE_IMAGE_PATH))


def reference_image() -> types.VideoGenerationReferenceImage:
    return types.VideoGenerationReferenceImage(
        image=wordmark_image(),
        reference_type=types.VideoGenerationReferenceType.ASSET,
    )


def build_config(mode: str) -> tuple[types.GenerateVideosConfig, dict[str, Any]]:
    config_kwargs: dict[str, Any] = {
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "number_of_videos": 1,
        "duration_seconds": 6,
        "negative_prompt": NEGATIVE_PROMPT,
    }

    config_report: dict[str, Any] = {
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "number_of_videos": 1,
        "duration_seconds": 6,
        "negative_prompt": NEGATIVE_PROMPT,
    }

    if mode == "reference":
        config_kwargs["reference_images"] = [reference_image()]
        config_report["reference_images"] = [
            {
                "image": str(REFERENCE_IMAGE_PATH),
                "reference_type": "ASSET",
            }
        ]

    return types.GenerateVideosConfig(**config_kwargs), config_report


def wait_for_operation(client: genai.Client, operation: Any) -> Any:
    print(f"Operation: {operation.name}")
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while not operation.done:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for Veo operation after {TIMEOUT_SECONDS} seconds. "
                f"Operation can be checked later by reference: {operation.name}"
            )

        print("Waiting for MAXIION A01 generation to complete...")
        time.sleep(POLL_INTERVAL_SECONDS)
        operation = client.operations.get(operation)

    if operation.error:
        raise RuntimeError(f"MAXIION A01 proof failed: {operation.error}")

    return operation


def output_paths(output_dir: Path) -> tuple[Path, Path]:
    return output_dir / "a01_seed.mp4", output_dir / "a01_report.json"


def run_generation(model: str, mode: str, output_dir: Path) -> int:
    api_key = require_gemini_api_key()
    client = genai.Client(api_key=api_key)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path, report_path = output_paths(output_dir)
    config, config_report = build_config(mode)

    print(f"Submitting one MAXIION A01 request with model: {model} in {mode} mode")
    if mode == "image":
        operation = client.models.generate_videos(
            model=model,
            prompt=PROMPT,
            image=wordmark_image(),
            config=config,
        )
    else:
        operation = client.models.generate_videos(
            model=model,
            prompt=PROMPT,
            config=config,
        )
    operation = wait_for_operation(client, operation)

    generated_videos = operation.response.generated_videos if operation.response else []
    if not generated_videos:
        raise RuntimeError("Veo operation completed but returned no generated videos.")

    generated_video = generated_videos[0].video
    client.files.download(file=generated_video)
    generated_video.save(str(output_path))

    report = {
        "model": model,
        "mode": mode,
        "operation": operation.name,
        "output": str(output_path),
        "reference_image": str(REFERENCE_IMAGE_PATH),
        "config": config_report,
        "prompt": PROMPT,
    }
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    print(f"Saved MAXIION A01 proof video to: {output_path}")
    print(f"Saved MAXIION A01 report to: {report_path}")
    return 0


def dry_run(model: str, mode: str, output_dir: Path) -> int:
    _, config_report = build_config(mode)
    output_path, report_path = output_paths(output_dir)
    print("DRY RUN ONLY - no API calls will be made.")
    print(f"Model: {model}")
    print(f"Mode: {mode}")
    print(f"Reference image: {REFERENCE_IMAGE_PATH}")
    print(f"Output path: {output_path}")
    print(f"Report path: {report_path}")
    print("Planned call:")
    if mode == "image":
        print(
            "client.models.generate_videos("
            "model=model, prompt=PROMPT, image=types.Image.from_file(location=WORDMARK_PATH), "
            "config=GenerateVideosConfig(...))"
        )
        print("reference_images used: False")
        print("image= used: True")
        print(
            "Literal image input pattern: "
            "image=types.Image.from_file(location='video_generation_agency/assets/maxiion_wordmark.png')"
        )
    else:
        print(
            "client.models.generate_videos("
            "model=model, prompt=PROMPT, config=GenerateVideosConfig(...))"
        )
        print("reference_images used: True")
        print("image= used: False")
        print("Reference image pattern:")
        print(
            "types.VideoGenerationReferenceImage("
            "image=types.Image.from_file(location='video_generation_agency/assets/maxiion_wordmark.png'), "
            "reference_type=types.VideoGenerationReferenceType.ASSET)"
        )
    print(json.dumps(config_report, indent=2))
    print("generate_audio omitted because Gemini Developer API rejects this field.")
    return 0


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    if not args.run:
        return dry_run(args.model, args.mode, output_dir)
    return run_generation(args.model, args.mode, output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
