#!/usr/bin/env python3
"""
run_from_packet.py - Packet adapter for run_full_chain.py

Reads a project packet JSON, validates it, derives the PROVEN run_full_chain.py
flags, and either prints the plan (default) or executes (--run, double-gated).

    "Packet in, proven command out."

INVOKE FROM THE REPO ROOT (paths inside packets are repo-relative), e.g.:

    python video_generation_agency/run_from_packet.py \
        --packet video_generation_agency/packets/silent_brand_existing_video_packet.json

By default this DRY-RUNS: it prints the validated summary and the exact
run_full_chain.py command it would call, then exits without spending anything.

To execute live you must satisfy BOTH gates:
    1. pass --run on this adapter's CLI, and
    2. set "spend_controls": {"allow_live_run": true} in the packet.
If --run is passed but the packet does not allow live runs, the adapter refuses.

The contract this maps to is documented in:
    video_generation_agency/packets/project_packet_schema.md
"""

import argparse
import json
import os
import shlex
import subprocess
import sys

# Mirror of run_full_chain.py's STAGES tuple. Kept here only so the adapter can
# validate the start_stage it derives against the values the runner accepts.
# (run_full_chain.py: STAGES = ("video", "extract", "sts", "music", "assemble"))
VALID_START_STAGES = ("video", "extract", "sts", "music", "assemble")
VALID_CONTENT_PATHS = ("silent_brand", "presenter")
VALID_VIDEO_SOURCES = ("existing", "generate")
DEFAULT_ASPECT_RATIO = "9:16"
VALID_ASPECT_RATIOS = ("9:16", "16:9")
PRESENTER_REFERENCE_MODEL = "veo-3.1-fast-generate-preview"
PRESENTER_REFERENCE_RESOLUTION = "720p"

# Path to the runner, relative to the repo root (this adapter is run from root).
RUNNER = "video_generation_agency/run_full_chain.py"


class PacketError(Exception):
    """Raised when a packet fails validation. The message is shown to the user."""


# --------------------------------------------------------------------------- #
# Load                                                                        #
# --------------------------------------------------------------------------- #
def load_packet(path):
    if not os.path.isfile(path):
        raise PacketError(f"Packet file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise PacketError(f"Packet is not valid JSON ({path}): {e}")


# --------------------------------------------------------------------------- #
# Validate                                                                    #
# --------------------------------------------------------------------------- #
def _require(packet, key):
    val = packet.get(key)
    if val is None or (isinstance(val, str) and not val.strip()):
        raise PacketError(f"Missing required field: '{key}'")
    return val


def _check_file(path, label):
    if not os.path.isfile(path):
        raise PacketError(f"{label} not found on disk: {path}")


def validate_packet(packet):
    """Validate the packet. Raises PacketError on the first hard problem.
    Returns a list of non-fatal warning strings."""
    warnings = []

    content_path = _require(packet, "content_path")
    if content_path not in VALID_CONTENT_PATHS:
        raise PacketError(
            f"content_path must be one of {VALID_CONTENT_PATHS}, got: {content_path!r}"
        )

    video_source = _require(packet, "video_source")
    if video_source not in VALID_VIDEO_SOURCES:
        raise PacketError(
            f"video_source must be one of {VALID_VIDEO_SOURCES}, got: {video_source!r}"
        )

    # storyboard feeds the music stage on every path, so it is always required.
    storyboard_path = _require(packet, "storyboard_path")
    _check_file(storyboard_path, "storyboard_path")

    # video-source specifics
    video_path = packet.get("video_path")
    scenes_path = packet.get("scenes_path")
    if video_source == "existing":
        if not video_path:
            raise PacketError("video_source 'existing' requires 'video_path'.")
        _check_file(video_path, "video_path")
        if scenes_path:
            warnings.append(
                "scenes_path is set but video_source is 'existing'; it will be ignored."
            )
    else:  # generate
        if not scenes_path:
            raise PacketError("video_source 'generate' requires 'scenes_path'.")
        _check_file(scenes_path, "scenes_path")
        if video_path:
            warnings.append(
                "video_path is set but video_source is 'generate'; it will be ignored."
            )

    # voice / STS - presenter requires a human-selected prepared_voice.json;
    # silent must NOT carry one (silent jobs never run STS).
    voice = packet.get("voice") or {}
    prepared_voice_path = voice.get("prepared_voice_path")
    if content_path == "presenter":
        if not prepared_voice_path:
            raise PacketError(
                "content_path 'presenter' requires voice.prepared_voice_path "
                "(the human-selected prepared_voice.json)."
            )
        _check_file(prepared_voice_path, "voice.prepared_voice_path")
    else:  # silent_brand
        if prepared_voice_path:
            raise PacketError(
                "content_path 'silent_brand' must not set voice.prepared_voice_path "
                "(silent jobs do not run STS)."
            )

    presenter_reference_image_path = packet.get("presenter_reference_image_path")
    if presenter_reference_image_path:
        if video_source != "generate":
            raise PacketError(
                "presenter_reference_image_path requires video_source 'generate'."
            )
        _check_file(
            presenter_reference_image_path,
            "presenter_reference_image_path",
        )
        if packet.get("model") not in (None, PRESENTER_REFERENCE_MODEL):
            warnings.append(
                "presenter_reference_image_path forces model "
                f"{PRESENTER_REFERENCE_MODEL}; packet model will be overridden."
            )
        if packet.get("resolution") not in (None, PRESENTER_REFERENCE_RESOLUTION):
            warnings.append(
                "presenter_reference_image_path forces resolution "
                f"{PRESENTER_REFERENCE_RESOLUTION}; packet resolution will be overridden."
            )

    if video_source == "generate":
        aspect_ratio = packet.get("aspect_ratio")
        if aspect_ratio is not None and aspect_ratio not in VALID_ASPECT_RATIOS:
            raise PacketError(
                f"aspect_ratio must be one of {VALID_ASPECT_RATIOS}, got: {aspect_ratio!r}"
            )

    # max_scenes is only meaningful for generated video.
    max_scenes = packet.get("max_scenes")
    if max_scenes is not None:
        if not isinstance(max_scenes, int) or max_scenes < 1:
            raise PacketError(
                f"max_scenes must be a positive integer, got: {max_scenes!r}"
            )
        if video_source == "existing":
            warnings.append(
                "max_scenes is set but video_source is 'existing'; it will be ignored."
            )

    # spend_controls.allow_live_run must be an explicit boolean.
    spend = packet.get("spend_controls") or {}
    allow = spend.get("allow_live_run", False)
    if not isinstance(allow, bool):
        raise PacketError("spend_controls.allow_live_run must be true or false.")

    return warnings


# --------------------------------------------------------------------------- #
# Derive + build                                                              #
# --------------------------------------------------------------------------- #
def derive_start_stage(content_path, video_source):
    """Derive the proven --start-stage from the job shape.

    existing + silent_brand -> extract   (skip generation; extract no-ops, music runs)
    existing + presenter    -> sts        (skip generation; STS self-extracts then runs)
    generate (either)       -> video      (start at generation)
    """
    if video_source == "generate":
        return "video"
    if content_path == "silent_brand":
        return "extract"
    return "sts"  # existing + presenter


def build_command(packet):
    """Translate a validated packet into a run_full_chain.py argv list
    (WITHOUT --run). Returns (argv_list, start_stage)."""
    content_path = packet["content_path"]
    video_source = packet["video_source"]

    argv = [sys.executable, RUNNER]

    # video source
    if video_source == "existing":
        argv += ["--video", packet["video_path"]]
    else:
        argv += ["--scenes", packet["scenes_path"]]

    # music storyboard (all paths)
    argv += ["--storyboard", packet["storyboard_path"]]

    # STS vs silent
    if content_path == "silent_brand":
        argv += ["--skip-sts"]
    else:  # presenter
        argv += ["--prepared-voice", packet["voice"]["prepared_voice_path"]]

    # start stage (derived, then re-validated against the runner's choices)
    start_stage = derive_start_stage(content_path, video_source)
    if start_stage not in VALID_START_STAGES:
        raise PacketError(
            f"Derived start_stage {start_stage!r} is not a valid runner choice "
            f"{VALID_START_STAGES}."
        )
    argv += ["--start-stage", start_stage]

    # generate-only passthroughs
    if video_source == "generate":
        presenter_reference = packet.get("presenter_reference_image_path")
        model = PRESENTER_REFERENCE_MODEL if presenter_reference else packet.get("model")
        resolution = (
            PRESENTER_REFERENCE_RESOLUTION
            if presenter_reference
            else packet.get("resolution")
        )
        if model:
            argv += ["--model", model]
        if resolution:
            argv += ["--resolution", resolution]
        argv += ["--aspect-ratio", packet.get("aspect_ratio") or DEFAULT_ASPECT_RATIO]
        if packet.get("max_scenes") is not None:
            argv += ["--max-scenes", str(packet["max_scenes"])]
        if presenter_reference:
            argv += ["--presenter-reference-image", presenter_reference]

    # output dir
    output_dir = (packet.get("output_settings") or {}).get("output_dir") or "runs"
    argv += ["--output-dir", output_dir]

    return argv, start_stage


# --------------------------------------------------------------------------- #
# Present                                                                     #
# --------------------------------------------------------------------------- #
def summarize(packet, start_stage):
    cp = packet["content_path"]
    vs = packet["video_source"]
    lines = [
        f"  job_id        : {packet.get('job_id', '(none)')}",
        f"  content_path  : {cp}",
        f"  video_source  : {vs}",
    ]
    if vs == "existing":
        lines.append(f"  video_path    : {packet.get('video_path')}")
    else:
        presenter_reference = packet.get("presenter_reference_image_path")
        lines.append(f"  scenes_path   : {packet.get('scenes_path')}")
        lines.append(
            "  model         : "
            f"{PRESENTER_REFERENCE_MODEL if presenter_reference else packet.get('model')}"
        )
        lines.append(
            "  resolution    : "
            f"{PRESENTER_REFERENCE_RESOLUTION if presenter_reference else packet.get('resolution')}"
        )
        lines.append(f"  aspect_ratio  : {packet.get('aspect_ratio') or DEFAULT_ASPECT_RATIO}")
        lines.append(f"  max_scenes    : {packet.get('max_scenes')}")
    lines.append(f"  storyboard    : {packet.get('storyboard_path')}")
    if cp == "presenter":
        lines.append(f"  prepared_voice: {packet['voice']['prepared_voice_path']}")
        lines.append(
            "  presenter_ref : "
            f"{packet.get('presenter_reference_image_path') or '(none)'}"
        )
    else:
        lines.append("  prepared_voice: (none - silent path)")
    lines.append(f"  start_stage   : {start_stage} (derived)")
    spend = packet.get("spend_controls") or {}
    lines.append(f"  allow_live_run: {bool(spend.get('allow_live_run', False))}")
    return "\n".join(lines)


def render(argv):
    """Render argv as a copy-pasteable command (display only)."""
    return " ".join(shlex.quote(a) for a in argv)


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description="Validate a project packet and translate it into a proven "
        "run_full_chain.py command. Dry-run by default."
    )
    ap.add_argument("--packet", required=True, help="Path to the project packet JSON.")
    ap.add_argument(
        "--run",
        action="store_true",
        help="Execute live. Also requires spend_controls.allow_live_run: true in the "
        "packet. Without this flag the adapter only prints the plan.",
    )
    args = ap.parse_args()

    try:
        packet = load_packet(args.packet)
        warnings = validate_packet(packet)
        argv, start_stage = build_command(packet)
    except PacketError as e:
        print(f"PACKET REJECTED: {e}", file=sys.stderr)
        return 2

    print("=" * 64)
    print("PACKET VALIDATED")
    print("=" * 64)
    print(summarize(packet, start_stage))
    for w in warnings:
        print(f"  WARNING: {w}")
    print()
    print("Derived run_full_chain.py command:")
    print(f"  {render(argv)}")
    print()

    spend = packet.get("spend_controls") or {}
    allow_live = bool(spend.get("allow_live_run", False))

    if not args.run:
        print("DRY-RUN (adapter): not executing. Pass --run to execute.")
        print("Note: run_full_chain.py itself also dry-runs unless it receives --run;")
        print("this adapter appends --run only when live execution is requested AND allowed.")
        return 0

    # --run requested: enforce the second gate.
    if not allow_live:
        print(
            "REFUSING TO RUN LIVE: --run was passed, but the packet has "
            "spend_controls.allow_live_run = false.",
            file=sys.stderr,
        )
        print(
            "Set allow_live_run: true in the packet to authorize spend, then re-run.",
            file=sys.stderr,
        )
        return 3

    # Both gates satisfied: execute live.
    live_argv = argv + ["--run"]
    print("EXECUTING LIVE (both gates satisfied):")
    print(f"  {render(live_argv)}")
    print("-" * 64)
    proc = subprocess.run(live_argv)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
