"""Dry-run-first full video/voice/music assembly chain runner.

By default this file validates inputs, creates a run folder scaffold, prints the
ordered plan, and writes a manifest. With --run, only explicitly wired stages are
executed; unwired production branches abort before any live command is launched.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


STAGES = ("video", "extract", "sts", "music", "assemble")
DEFAULT_MODEL = "veo-3.1-fast-generate-preview"
DEFAULT_RESOLUTION = "720p"
DEFAULT_ASPECT_RATIO = "9:16"
PRESENTER_REFERENCE_MODEL = "veo-3.1-fast-generate-preview"
PRESENTER_REFERENCE_RESOLUTION = "720p"
LIVE_EXECUTION_STATUS = "not_wired"
RUNTIME_GEN_DURATION = "<RUNTIME_GEN_DURATION>"
RUNTIME_TAIL_SECONDS = "<RUNTIME_TAIL_SECONDS>"
EXECUTABLE_STATUSES = {"WIRED"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan the full video, speech, music, and assembly chain."
    )
    parser.add_argument(
        "--video",
        help="Optional existing video to start from, skipping video generation.",
    )
    parser.add_argument(
        "--scenes",
        help="Scenes JSON for video generation, for example extension_scenes_maxiion.json.",
    )
    parser.add_argument(
        "--prepared-voice",
        help="prepared_voice.json. Required unless --skip-sts is set.",
    )
    parser.add_argument(
        "--presenter-reference-image",
        help=(
            "Optional single asset-reference image for generated video. "
            "Forces Veo 3.1 Fast reference-image settings."
        ),
    )
    parser.add_argument(
        "--storyboard",
        help="Storyboard JSON for music planning.",
    )
    parser.add_argument(
        "--skip-sts",
        action="store_true",
        help="Silent/branded video: skip the speech-to-speech stage.",
    )
    parser.add_argument(
        "--start-stage",
        choices=STAGES,
        default="video",
        help="First stage to plan as active. Earlier stages are marked SKIPPED.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Passthrough model for the video chain. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--resolution",
        default=DEFAULT_RESOLUTION,
        help=f"Passthrough resolution for the video chain. Default: {DEFAULT_RESOLUTION}",
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
        help="Optional passthrough cap for run_veo_extension_chain.py scene generation.",
    )
    parser.add_argument(
        "--output-dir",
        default="runs",
        help='Parent output directory. Default: "runs"',
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute explicitly wired stages. Unwired stages abort before execution.",
    )
    args = parser.parse_args()
    if args.presenter_reference_image and args.video:
        parser.error("--presenter-reference-image requires generated video via --scenes, not --video.")
    if args.presenter_reference_image and not Path(args.presenter_reference_image).expanduser().is_file():
        parser.error(
            "--presenter-reference-image was not found: "
            f"{Path(args.presenter_reference_image).expanduser()}"
        )
    return args


def run_id() -> str:
    return f"full_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def make_run_dirs(output_root: Path, current_run_id: str) -> dict[str, Path]:
    run_dir = output_root / current_run_id
    dirs = {
        "run": run_dir,
        "input": run_dir / "input",
        "video": run_dir / "video",
        "voice": run_dir / "voice",
        "music": run_dir / "music",
        "final": run_dir / "final",
        "reports": run_dir / "reports",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    return dirs


def as_path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def path_text(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def shell_join(parts: list[str | Path]) -> str:
    return " ".join(str(part) for part in parts)


def skipped_by_start(stage: str, start_stage: str) -> bool:
    return STAGES.index(stage) < STAGES.index(start_stage)


def missing(path: Path | None) -> bool:
    return path is None or not path.exists()


def add_warning(warnings: list[str], message: str) -> None:
    warnings.append(message)


def probe_duration_seconds(path: Path, warnings: list[str]) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        add_warning(warnings, "ffprobe is not available; GEN_DUR cannot be computed.")
        return None
    if not path.is_file():
        add_warning(warnings, f"Cannot compute GEN_DUR because video does not exist: {path}")
        return None

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip()
        suffix = f": {detail}" if detail else ""
        add_warning(warnings, f"ffprobe failed for {path}{suffix}")
        return None

    try:
        duration = float(result.stdout.strip())
    except ValueError:
        add_warning(warnings, f"ffprobe returned invalid duration for {path}: {result.stdout!r}")
        return None
    if duration <= 0:
        add_warning(warnings, f"ffprobe returned non-positive duration for {path}: {duration}")
        return None
    return duration


def generation_duration_plan(
    path: Path,
    warnings: list[str],
    *,
    allow_runtime: bool,
) -> tuple[str, float | None, int | None, str]:
    if allow_runtime and not path.is_file():
        return (
            RUNTIME_GEN_DURATION,
            None,
            None,
            "runtime: ceil(video_dur) + 20",
        )

    source_duration = probe_duration_seconds(path, warnings)
    generation_duration = math.ceil(source_duration) + 20 if source_duration is not None else None
    generation_duration_arg = str(generation_duration) if generation_duration is not None else "<GEN_DUR_UNRESOLVED>"
    if source_duration is None or generation_duration is None:
        return generation_duration_arg, source_duration, generation_duration, "unresolved"
    return (
        generation_duration_arg,
        source_duration,
        generation_duration,
        f"{generation_duration} from ceil({source_duration:.6f}) + 20",
    )


def stage_entry(
    stage: str,
    status: str,
    command: str,
    notes: list[str] | None = None,
    expected_outputs: list[Path] | None = None,
    execution_commands: list[list[str | Path]] | None = None,
    runtime_duration: dict[str, str | Path] | None = None,
    runtime_tail: dict[str, str | Path] | None = None,
) -> dict[str, Any]:
    entry = {
        "stage": stage,
        "status": status,
        "planned_command": command,
        "notes": notes or [],
        "expected_outputs": [str(path) for path in expected_outputs or []],
        "execution_commands": [
            [str(part) for part in command_parts]
            for command_parts in execution_commands or []
        ],
        "final_status": "PENDING",
        "output_paths": [],
    }
    if runtime_tail is not None:
        entry["runtime_tail"] = {
            name: str(value)
            for name, value in runtime_tail.items()
        }
    if runtime_duration is not None:
        entry["runtime_duration"] = {
            name: str(value)
            for name, value in runtime_duration.items()
        }
    return entry


def build_plan(args: argparse.Namespace, dirs: dict[str, Path]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    plan: list[dict[str, Any]] = []

    video_input = as_path(args.video)
    scenes_path = as_path(args.scenes)
    prepared_voice = as_path(args.prepared_voice)
    presenter_reference_image = as_path(args.presenter_reference_image)
    storyboard = as_path(args.storyboard)

    source_video = dirs["video"] / "source_video.mp4"
    video_final_raw = dirs["video"] / "final_raw.mp4"
    video_final_silent = dirs["video"] / "final_silent.mp4"
    active_raw_video = video_input if video_input is not None else video_final_raw
    active_silent_video = video_input if video_input is not None else video_final_silent
    extracted_audio = dirs["voice"] / "source_audio.wav"
    converted_voice = dirs["voice"] / "converted.mp3"
    voice_fixed_video = dirs["voice"] / "voice_fixed_video.mp4"
    generated_music = dirs["music"] / "background_music.mp3"
    music_brief = dirs["music"] / "music_brief.json"
    music_report = dirs["music"] / "music_report.json"
    music_mix = dirs["music"] / "final_mixed.mp3"
    mix_report = dirs["music"] / "mix_report.json"
    final_video = dirs["final"] / "final_video.mp4"

    if args.video and missing(video_input):
        add_warning(warnings, f"--video does not exist: {video_input}")
    if not args.video and missing(scenes_path):
        add_warning(warnings, f"--scenes is required for video generation and was missing/not found: {scenes_path}")
    if not args.skip_sts and missing(prepared_voice):
        add_warning(
            warnings,
            "--prepared-voice is required unless --skip-sts and was missing/not found: "
            f"{prepared_voice}",
        )
    if missing(storyboard):
        add_warning(warnings, f"--storyboard was missing/not found: {storyboard}")

    video_notes: list[str] = []
    if skipped_by_start("video", args.start_stage):
        video_status = "SKIPPED"
        if args.video:
            video_notes.append("Skipped by --start-stage; later stages use the existing --video input.")
        else:
            video_notes.append("Skipped by --start-stage, but no --video was supplied.")
        video_command = "SKIPPED"
    elif args.video:
        video_status = "WIRED"
        video_execution = ["cp", video_input or "<missing-video>", source_video]
        video_command = shell_join(video_execution)
        active_raw_video = source_video
        active_silent_video = source_video
        video_notes.append("Existing video supplied; video generation is skipped.")
    else:
        video_status = "WIRED"
        video_model = PRESENTER_REFERENCE_MODEL if presenter_reference_image else args.model
        video_resolution = (
            PRESENTER_REFERENCE_RESOLUTION if presenter_reference_image else args.resolution
        )
        video_execution = [
            sys.executable,
            "video_generation_agency/run_veo_extension_chain.py",
            "--scenes",
            scenes_path or "<missing-scenes>",
            "--model",
            video_model,
            "--resolution",
            video_resolution,
            "--aspect-ratio",
            args.aspect_ratio,
            "--output-dir",
            dirs["video"],
            "--run",
        ]
        if presenter_reference_image is not None:
            video_execution.extend(
                ["--presenter-reference-image", presenter_reference_image]
            )
            video_notes.append(
                "Asset reference mode forces Veo 3.1 Fast, 8s, 720p, "
                "selected aspect ratio, allow_adult, and one output for the seed call."
            )
        elif not args.skip_sts:
            video_execution.extend(["--person-generation", "allow_adult"])
            video_notes.append(
                "Generated adult presenter seed uses person_generation=allow_adult."
            )
        if args.max_scenes is not None:
            video_execution.extend(["--max-scenes", str(args.max_scenes)])
        video_command = shell_join(video_execution)
        active_raw_video = video_final_raw
        active_silent_video = video_final_silent
        video_notes.append("Video output contract: runner must produce video/final_raw.mp4.")
        video_notes.append("Video output contract: runner must produce video/final_silent.mp4.")
        video_notes.append("Video output contract: runner must produce video/chain_report.json.")
        video_notes.append("run_veo_extension_chain.py uses --output-dir directly; no nested timestamp folder when supplied.")
    plan.append(
        stage_entry(
            "video",
            video_status,
            video_command,
            video_notes,
            expected_outputs=[video_final_raw, video_final_silent, dirs["video"] / "chain_report.json"] if not args.video else [source_video],
            execution_commands=[video_execution] if not skipped_by_start("video", args.start_stage) else [],
        )
    )

    extract_notes: list[str] = []
    if args.skip_sts:
        extract_status = "SKIPPED_NO_STS"
        extract_command = "SKIPPED (extract only feeds STS in this skeleton)"
        extract_notes.append("No speech requested, so source audio extraction is not needed.")
    else:
        extract_status = "SKIPPED_SELF_EXTRACT"
        extract_command = "SKIPPED (apply_sts.py extracts source audio internally from --video)"
        extract_notes.append("Presenter path does not need a separate extract stage.")
        extract_notes.append("apply_sts.py extracts source audio internally from --video.")
    plan.append(
        stage_entry(
            "extract",
            extract_status,
            extract_command,
            extract_notes,
            expected_outputs=[],
        )
    )

    sts_notes: list[str] = []
    if args.skip_sts:
        sts_status = "SKIPPED_NO_SPEECH"
        sts_command = "STS: SKIPPED (no speech)"
        sts_notes.append("Speech stage disabled by --skip-sts.")
    elif skipped_by_start("sts", args.start_stage):
        sts_status = "SKIPPED"
        sts_command = "SKIPPED"
    else:
        sts_status = "WIRED"
        sts_convert_execution = [
            sys.executable,
            "apply_sts.py",
            "--video",
            active_raw_video,
            "--prepared-voice",
            prepared_voice or "<missing-prepared-voice>",
            "--out",
            converted_voice,
        ]
        sts_mux_execution = [
            "ffmpeg",
            "-y",
            "-i",
            active_raw_video,
            "-i",
            converted_voice,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            voice_fixed_video,
        ]
        sts_command = (
            shell_join(sts_convert_execution)
            + "\n"
            + shell_join(sts_mux_execution)
        )
        sts_notes.append("Step 1 converts source speech with apply_sts.py.")
        sts_notes.append("Step 2 muxes converted voice onto the presenter video.")
        sts_notes.append("If apply_sts.py fails, the executor stops before the mux command.")
    plan.append(
        stage_entry(
            "sts",
            sts_status,
            sts_command,
            sts_notes,
            expected_outputs=[] if args.skip_sts or skipped_by_start("sts", args.start_stage) else [converted_voice, voice_fixed_video],
            execution_commands=[sts_convert_execution, sts_mux_execution] if not args.skip_sts and not skipped_by_start("sts", args.start_stage) else [],
        )
    )

    sts_will_run = not skipped_by_start("sts", args.start_stage) and not args.skip_sts
    music_mode = "mix under voice" if sts_will_run else "music bed only (no voice)"
    music_video_reference = voice_fixed_video if sts_will_run else active_silent_video
    music_notes: list[str] = []
    generation_duration_arg: str | None = None
    generation_duration_source: Path | None = None
    if skipped_by_start("music", args.start_stage):
        music_status = "SKIPPED"
        music_command = "SKIPPED"
        music_expected_outputs: list[Path] = []
    elif args.skip_sts:
        generation_duration_source = active_silent_video
        generation_duration_arg, source_duration, generation_duration, generation_duration_note = generation_duration_plan(
            generation_duration_source,
            warnings,
            allow_runtime=not args.video,
        )
        music_status = "WIRED"
        generate_music_execution = [
            sys.executable,
            "generate_music.py",
            "--storyboard",
            storyboard or "<missing-storyboard>",
            "--duration",
            generation_duration_arg,
            "--out",
            generated_music,
            "--brief-out",
            music_brief,
            "--report",
            music_report,
        ]
        mix_audio_execution = [
            sys.executable,
            "mix_audio.py",
            "--music",
            generated_music,
            "--duration-from",
            active_silent_video,
            "--out",
            music_mix,
            "--report",
            mix_report,
        ]
        music_command = (
            shell_join(generate_music_execution)
            + "\n"
            + shell_join(mix_audio_execution)
        )
        if generation_duration_arg == RUNTIME_GEN_DURATION:
            music_command = music_command.replace(
                RUNTIME_GEN_DURATION,
                "runtime: ceil(video_dur) + 20",
            )
            music_notes.append(
                f"Mode: music bed only (no voice). GEN_DUR={generation_duration_note}."
            )
        elif source_duration is not None and generation_duration is not None:
            music_notes.append(
                f"Mode: music bed only (no voice). GEN_DUR={generation_duration_note}."
            )
        else:
            music_notes.append("Mode: music bed only (no voice). GEN_DUR could not be computed.")
        music_notes.append("Step 1 generates a foreground music bed from the storyboard.")
        music_notes.append("Step 2 shapes the bed with mix_audio.py music-only mode to the video duration.")
        music_expected_outputs = [generated_music, music_brief, music_report, music_mix, mix_report]
    else:
        generation_duration_source = active_raw_video
        generation_duration_arg, source_duration, generation_duration, generation_duration_note = generation_duration_plan(
            generation_duration_source,
            warnings,
            allow_runtime=not args.video,
        )
        music_status = "WIRED"
        generate_music_execution = [
            sys.executable,
            "generate_music.py",
            "--storyboard",
            storyboard or "<missing-storyboard>",
            "--duration",
            generation_duration_arg,
            "--out",
            generated_music,
            "--brief-out",
            music_brief,
            "--report",
            music_report,
        ]
        mix_audio_execution = [
            sys.executable,
            "mix_audio.py",
            "--voice",
            converted_voice,
            "--music",
            generated_music,
            "--tail-seconds",
            RUNTIME_TAIL_SECONDS,
            "--out",
            music_mix,
            "--report",
            mix_report,
        ]
        mix_audio_plan = [
            RUNTIME_TAIL_SECONDS
            if str(part) == RUNTIME_TAIL_SECONDS
            else part
            for part in mix_audio_execution
        ]
        tail_expression = "runtime: max(0, video_dur - voice_dur)"
        music_command = (
            shell_join(generate_music_execution)
            + "\n"
            + shell_join(
                [
                    tail_expression
                    if str(part) == RUNTIME_TAIL_SECONDS
                    else part
                    for part in mix_audio_plan
                ]
            )
        )
        if generation_duration_arg == RUNTIME_GEN_DURATION:
            music_command = music_command.replace(
                RUNTIME_GEN_DURATION,
                "runtime: ceil(video_dur) + 20",
            )
            music_notes.append(f"Mode: {music_mode}. GEN_DUR={generation_duration_note}.")
        elif source_duration is not None and generation_duration is not None:
            music_notes.append(
                f"Mode: {music_mode}. GEN_DUR={generation_duration_note}."
            )
        else:
            music_notes.append(f"Mode: {music_mode}. GEN_DUR could not be computed.")
        music_notes.append(f"TAIL={tail_expression}.")
        music_notes.append("Step 1 generates an under-voice music bed from the storyboard.")
        music_notes.append("Step 2 mixes music under the converted voice with mix_audio.py voice mode.")
        music_expected_outputs = [generated_music, music_brief, music_report, music_mix, mix_report]
    plan.append(
        stage_entry(
            "music",
            music_status,
            music_command,
            music_notes,
            expected_outputs=music_expected_outputs,
            execution_commands=[generate_music_execution, mix_audio_execution] if not skipped_by_start("music", args.start_stage) else [],
            runtime_duration={
                "source": generation_duration_source,
            } if generation_duration_arg == RUNTIME_GEN_DURATION and not skipped_by_start("music", args.start_stage) else None,
            runtime_tail={
                "video": active_raw_video,
                "voice": converted_voice,
            } if not args.skip_sts and not skipped_by_start("music", args.start_stage) else None,
        )
    )

    assembly_video_reference = active_raw_video if sts_will_run else active_silent_video
    if skipped_by_start("assemble", args.start_stage):
        assemble_status = "SKIPPED"
        assemble_command = "SKIPPED"
        assemble_execution: list[str | Path] = []
    else:
        assemble_status = "WIRED"
        assemble_execution = [
            "ffmpeg",
            "-y",
            "-i",
            assembly_video_reference,
            "-i",
            music_mix,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            final_video,
        ]
        assemble_command = shell_join(assemble_execution)
    plan.append(
        stage_entry(
            "assemble",
            assemble_status,
            assemble_command,
            expected_outputs=[] if skipped_by_start("assemble", args.start_stage) else [final_video],
            execution_commands=[assemble_execution] if assemble_execution else [],
        )
    )

    return plan, warnings


def manifest_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "video": args.video,
        "scenes": args.scenes,
        "prepared_voice": args.prepared_voice,
        "presenter_reference_image": args.presenter_reference_image,
        "storyboard": args.storyboard,
        "skip_sts": args.skip_sts,
        "start_stage": args.start_stage,
        "model": args.model,
        "resolution": args.resolution,
        "aspect_ratio": args.aspect_ratio,
        "max_scenes": args.max_scenes,
        "output_dir": args.output_dir,
        "run": args.run,
    }


def output_path_status(paths: list[str]) -> list[dict[str, Any]]:
    statuses = []
    for raw_path in paths:
        path = Path(raw_path)
        statuses.append(
            {
                "path": raw_path,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
            }
        )
    return statuses


def set_stage_output_status(stage: dict[str, Any]) -> None:
    stage["output_paths"] = output_path_status(stage.get("expected_outputs", []))


def mark_non_executed_stages(plan: list[dict[str, Any]]) -> None:
    for stage in plan:
        if stage["final_status"] != "PENDING":
            continue
        if stage["status"].startswith("SKIPPED"):
            stage["final_status"] = stage["status"]
        elif stage["status"] in EXECUTABLE_STATUSES:
            stage["final_status"] = f"{stage['status']}_NOT_RUN"
        else:
            stage["final_status"] = stage["status"]
        set_stage_output_status(stage)


def live_stage_indexes(plan: list[dict[str, Any]]) -> list[int]:
    return [
        index
        for index, stage in enumerate(plan)
        if not stage["status"].startswith("SKIPPED")
    ]


def find_unwired_live_stage(plan: list[dict[str, Any]]) -> dict[str, Any] | None:
    for index in live_stage_indexes(plan):
        stage = plan[index]
        if stage["status"] not in EXECUTABLE_STATUSES or not stage.get("execution_commands"):
            return stage
    return None


def resolve_runtime_tail(stage: dict[str, Any]) -> str:
    runtime_tail = stage.get("runtime_tail")
    if not isinstance(runtime_tail, dict):
        raise RuntimeError("Runtime tail requested, but no runtime_tail context was provided.")

    warnings: list[str] = []
    video_path = Path(str(runtime_tail.get("video", "")))
    voice_path = Path(str(runtime_tail.get("voice", "")))
    video_duration = probe_duration_seconds(video_path, warnings)
    voice_duration = probe_duration_seconds(voice_path, warnings)
    if video_duration is None or voice_duration is None:
        detail = "; ".join(warnings) if warnings else "duration could not be computed"
        raise RuntimeError(f"Could not resolve runtime tail seconds: {detail}")
    return f"{max(0.0, video_duration - voice_duration):.6f}"


def resolve_runtime_generation_duration(stage: dict[str, Any]) -> str:
    runtime_duration = stage.get("runtime_duration")
    if not isinstance(runtime_duration, dict):
        raise RuntimeError("Runtime GEN_DUR requested, but no runtime_duration context was provided.")

    warnings: list[str] = []
    source_path = Path(str(runtime_duration.get("source", "")))
    source_duration = probe_duration_seconds(source_path, warnings)
    if source_duration is None:
        detail = "; ".join(warnings) if warnings else "duration could not be computed"
        raise RuntimeError(f"Could not resolve runtime GEN_DUR: {detail}")
    return str(math.ceil(source_duration) + 20)


def resolve_command(command: list[str], stage: dict[str, Any]) -> list[str]:
    resolved_command = command
    if RUNTIME_GEN_DURATION in resolved_command:
        runtime_gen_duration = resolve_runtime_generation_duration(stage)
        resolved_command = [
            runtime_gen_duration if part == RUNTIME_GEN_DURATION else part
            for part in resolved_command
        ]
    if RUNTIME_TAIL_SECONDS in resolved_command:
        runtime_tail_seconds = resolve_runtime_tail(stage)
        resolved_command = [
            runtime_tail_seconds if part == RUNTIME_TAIL_SECONDS else part
            for part in resolved_command
        ]
    return resolved_command


def run_command(command: list[str], stage_name: str, command_index: int) -> dict[str, Any]:
    display_command = shell_join([Path(part) if isinstance(part, Path) else part for part in command])
    print(f"\n[{stage_name}] command {command_index}: {display_command}")
    result = subprocess.run(command, capture_output=True, text=True)
    print(f"[{stage_name}] return code: {result.returncode}")
    if result.stdout:
        print(f"[{stage_name}] stdout:")
        print(result.stdout.rstrip())
    else:
        print(f"[{stage_name}] stdout: <empty>")
    if result.stderr:
        print(f"[{stage_name}] stderr:")
        print(result.stderr.rstrip())
    else:
        print(f"[{stage_name}] stderr: <empty>")
    return {
        "command_index": command_index,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def execute_live_plan(plan: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    unwired_stage = find_unwired_live_stage(plan)
    if unwired_stage is not None:
        message = f"stage {unwired_stage['stage']} not wired for live execution; aborting"
        print(message, file=sys.stderr)
        for stage in plan:
            if stage is unwired_stage:
                stage["final_status"] = "FAILED_NOT_WIRED"
            elif stage["status"].startswith("SKIPPED"):
                stage["final_status"] = stage["status"]
            else:
                stage["final_status"] = "NOT_RUN"
            set_stage_output_status(stage)
        return "failed", {
            "stage": unwired_stage["stage"],
            "reason": "not_wired",
            "stderr": message,
        }

    for index, stage in enumerate(plan):
        if stage["status"].startswith("SKIPPED"):
            stage["final_status"] = stage["status"]
            set_stage_output_status(stage)
            continue

        stage["command_results"] = []
        print(f"\nExecuting stage {stage['stage']}: {stage['status']}")
        for command_index, command in enumerate(stage["execution_commands"], start=1):
            try:
                resolved_command = resolve_command(command, stage)
            except RuntimeError as exc:
                result = {
                    "command_index": command_index,
                    "command": command,
                    "returncode": 1,
                    "stdout": "",
                    "stderr": str(exc),
                }
                print(f"\n[{stage['stage']}] command {command_index}: {shell_join(command)}")
                print(f"[{stage['stage']}] return code: 1")
                print(f"[{stage['stage']}] stdout: <empty>")
                print(f"[{stage['stage']}] stderr:")
                print(str(exc))
            else:
                result = run_command(resolved_command, stage["stage"], command_index)
            stage["command_results"].append(result)
            if result["returncode"] != 0:
                stage["final_status"] = "FAILED"
                set_stage_output_status(stage)
                for later_stage in plan[index + 1:]:
                    if later_stage["status"].startswith("SKIPPED"):
                        later_stage["final_status"] = later_stage["status"]
                    else:
                        later_stage["final_status"] = "NOT_RUN_AFTER_FAILURE"
                    set_stage_output_status(later_stage)
                return "failed", {
                    "stage": stage["stage"],
                    "command_index": command_index,
                    "returncode": result["returncode"],
                    "stderr": result["stderr"],
                }
        stage["final_status"] = "EXECUTED"
        set_stage_output_status(stage)

    return "executed", None


def write_manifest(
    manifest_path: Path,
    current_run_id: str,
    args: argparse.Namespace,
    dirs: dict[str, Path],
    plan: list[dict[str, Any]],
    warnings: list[str],
    live_execution: str,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mark_non_executed_stages(plan)
    manifest = {
        "run_id": current_run_id,
        "args": manifest_args(args),
        "resolved_paths": {name: str(path) for name, path in dirs.items()},
        "ordered_stage_plan": plan,
        "warnings": warnings,
        "live_execution": live_execution,
    }
    if failure is not None:
        manifest["failure"] = failure
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return manifest


def print_plan(
    current_run_id: str,
    dirs: dict[str, Path],
    plan: list[dict[str, Any]],
    warnings: list[str],
    manifest_path: Path,
    run_requested: bool,
) -> None:
    if run_requested:
        print("FULL CHAIN LIVE RUN")
        print("Only explicitly wired stages will execute; unwired stages abort before execution.")
    else:
        print("FULL CHAIN PLAN - DRY RUN ONLY")
        print("No API calls, no media generation, and no sub-scripts will be invoked.")
    if run_requested:
        print("--run supplied; live preflight will run after this plan.")
    print(f"Run ID: {current_run_id}")
    print(f"Run directory: {dirs['run']}")
    print("Created directories:")
    for name in ("input", "video", "voice", "music", "final", "reports"):
        print(f"  {name}/ -> {dirs[name]}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  WARNING: {warning}")
    else:
        print("\nWarnings: none")

    print("\nOrdered plan:")
    for index, item in enumerate(plan, start=1):
        print(f"{index}. {item['stage']}: {item['status']}")
        for note in item["notes"]:
            print(f"   note: {note}")
        print(f"   command: {item['planned_command']}")
        if item["expected_outputs"]:
            print("   expected outputs:")
            for output in item["expected_outputs"]:
                print(f"     - {output}")

    print(f"\nManifest: {manifest_path}")
    print(f"live_execution: {'pending' if run_requested else LIVE_EXECUTION_STATUS}")


def main() -> int:
    args = parse_args()
    current_run_id = run_id()
    dirs = make_run_dirs(Path(args.output_dir), current_run_id)
    plan, warnings = build_plan(args, dirs)
    manifest_path = dirs["run"] / "manifest.json"
    print_plan(current_run_id, dirs, plan, warnings, manifest_path, args.run)
    if not args.run:
        write_manifest(
            manifest_path,
            current_run_id,
            args,
            dirs,
            plan,
            warnings,
            LIVE_EXECUTION_STATUS,
        )
        return 0

    live_execution, failure = execute_live_plan(plan)
    write_manifest(
        manifest_path,
        current_run_id,
        args,
        dirs,
        plan,
        warnings,
        live_execution,
        failure,
    )
    print(f"\nManifest: {manifest_path}")
    print(f"live_execution: {live_execution}")
    if failure is not None:
        print(
            f"Failure: stage={failure.get('stage')} "
            f"returncode={failure.get('returncode', 'n/a')}",
            file=sys.stderr,
        )
        return int(failure.get("returncode") or 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
