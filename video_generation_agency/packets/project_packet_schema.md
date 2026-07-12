# Project Packet Schema

This document defines the proposed JSON packet contract for a media job that can be translated into `run_full_chain.py` arguments. The runner does not currently read packet files directly; this schema describes the contract a future packet adapter or UI layer should map into the runner CLI.

## Current Runner Flags

`run_full_chain.py` currently exposes these flags:

```text
--video
--scenes
--prepared-voice
--presenter-reference-image
--storyboard
--skip-sts
--start-stage
--model
--resolution
--aspect-ratio
--max-scenes
--output-dir
--run
```

## Routing Summary

- `silent_brand` maps to `--skip-sts`. The runner skips extract and STS, generates or reuses a silent video bed, generates music, shapes it to the video duration, and assembles `final_video.mp4`.
- `presenter` omits `--skip-sts` and requires `--prepared-voice`. The runner lets `apply_sts.py` extract source speech internally from `--video` or generated `video/final_raw.mp4`, converts it with STS, creates an under-voice music bed, and assembles `final_video.mp4`.
- `existing` video source maps to `--video <video_path>`. The runner copies the supplied file into the run folder and uses it as the active video source.
- `generate` video source maps to `--scenes <scenes_path>`. The runner calls `video_generation_agency/run_veo_extension_chain.py` and expects `video/final_raw.mp4`, `video/final_silent.mp4`, and `video/chain_report.json`.
- `--storyboard` is consumed by the music generation stage for both silent and presenter paths.
- `--model`, `--resolution`, `--aspect-ratio`, and `--max-scenes` are passed through to the Veo extension-chain runner when `video_source` is `generate`.
- `--presenter-reference-image` is optional for any `generate` job (`silent_brand` or `presenter`). When present, scene 1 uses the supplied adult asset reference and fixed Veo 3.1 Fast reference-image settings: 8 seconds, 720p, selected aspect ratio (default 9:16), `allow_adult`, one video.
- `--start-stage` controls which stages are active. Earlier stages are marked skipped; later stages still plan against the expected stage contracts.
- `--output-dir` defaults to `runs` and controls the parent run directory. The runner writes final output by convention to `runs/<run_id>/final/final_video.mp4`.
- `--run` is the live-execution switch. Without it, the runner creates a run folder and manifest and prints the plan only.

## Packet Shape

```json
{
  "job_id": "string",
  "content_path": "silent_brand | presenter",
  "video_source": "existing | generate",
  "video_path": "path/to/existing.mp4",
  "scenes_path": "path/to/scenes.json",
  "presenter_reference_image_path": "path/to/adult-presenter.jpeg",
  "storyboard_path": "path/to/storyboard.json",
  "model": "veo-3.1-fast-generate-preview",
  "resolution": "720p",
  "aspect_ratio": "9:16",
  "max_scenes": 1,
  "voice": {
    "prepared_voice_path": "prepared_voice.json"
  },
  "accent_dialect": "string",
  "start_stage": "adapter-derived",
  "output_settings": {
    "output_dir": "runs",
    "final_video_name": "final_video.mp4"
  },
  "spend_controls": {
    "allow_live_run": false,
    "notes": "string"
  },
  "metadata": {
    "client": "string",
    "campaign": "string",
    "notes": "string"
  }
}
```

## Fields

`job_id` - [FORWARD-LOOKING -> not yet read by the runner]  
Human-readable or system-generated packet identifier for UI, audit, or job queue use.

`content_path` - [CONSUMED NOW -> maps to `--skip-sts` for `silent_brand`; presenter implies STS path]  
Allowed values: `silent_brand`, `presenter`. `silent_brand` means pass `--skip-sts`. `presenter` means do not pass `--skip-sts` and provide `voice.prepared_voice_path`.

`video_source` - [CONSUMED NOW -> maps to `--video` vs `--scenes`]  
Allowed values: `existing`, `generate`. `existing` requires `video_path`. `generate` requires `scenes_path`.

`video_path` - [CONSUMED NOW -> maps to `--video`]  
Path to an existing MP4. Used only when `video_source` is `existing`.

`scenes_path` - [CONSUMED NOW -> maps to `--scenes`]  
Path to a scenes JSON file for `run_veo_extension_chain.py`. Used only when `video_source` is `generate`.

`presenter_reference_image_path` - [CONSUMED NOW -> maps to `--presenter-reference-image`]
Optional path to an adult asset reference image. Valid for `content_path=presenter` or `silent_brand` with `video_source=generate`. When present, it overrides the normal scene-1 image seed call with Veo reference-image mode and forces `veo-3.1-fast-generate-preview`, 8 seconds, 720p, selected aspect ratio (default 9:16), `person_generation=allow_adult`, and one output. The packet references a per-run image; it does not create or persist a character identity.

`storyboard_path` - [CONSUMED NOW -> maps to `--storyboard`]  
Path to the storyboard JSON used by `generate_music.py`.

`model` - [CONSUMED NOW -> maps to `--model`]  
Veo model passed through to `run_veo_extension_chain.py` for generated-video jobs.

`resolution` - [CONSUMED NOW -> maps to `--resolution`]  
Resolution passed through to `run_veo_extension_chain.py`. Proven route currently uses `720p`.

`aspect_ratio` - [CONSUMED NOW -> maps to `--aspect-ratio`]
Optional top-level aspect ratio for generated-video jobs. Allowed values are `9:16` and `16:9`; default is `9:16`. Ignored for `video_source=existing`.

`max_scenes` - [CONSUMED NOW -> maps to `--max-scenes`]  
Optional cap for generated-video jobs. This is the main proof/spend-cap lever for Veo generation; for example, `1` generates only the seed scene.

`voice.prepared_voice_path` - [CONSUMED NOW -> maps to `--prepared-voice` when `content_path` is `presenter`; null when `content_path` is `silent_brand`]  
Path to a human-selected `prepared_voice.json` artifact. Required for presenter jobs; unused for silent jobs.

`accent_dialect` - [FORWARD-LOOKING -> belongs at video-generation prompt time; runner does NOT consume it]  
This may inform future prompt generation or client-facing creative controls. The runner does not consume it. STS preserves whatever accent or dialect exists in the source video speech; it does not create an accent choice from the packet.

`start_stage` - [CONSUMED NOW -> future packet adapter derives `--start-stage` from `video_source` and `content_path`]  
This should not be treated as a raw user-authored packet field defaulted to `video`. The adapter should derive the proven invocation:
- `video_source=existing` and `content_path=silent_brand` -> `--start-stage extract`
- `video_source=existing` and `content_path=presenter` -> `--start-stage sts`
- `video_source=generate` -> `--start-stage video`

`output_settings` - [FORWARD-LOOKING -> runner currently writes `runs/<run_id>/final/final_video.mp4` by convention]  
The runner supports `--output-dir`, but does not currently consume a structured output settings object or custom final filename.

`spend_controls.allow_live_run` - [FORWARD-LOOKING -> not yet read by the runner]  
The runner only honors the CLI `--run` flag today. A future adapter may require this to be true before adding `--run`.

`spend_controls.notes` - [FORWARD-LOOKING -> not yet read by the runner]  
Human-readable budget or quota notes.

`metadata` - [FORWARD-LOOKING -> not yet read by the runner]  
Client, campaign, and note fields for UI, audit trail, or job queue display.

## Voice Rules

- The voice is never hardcoded and never defaulted. `Anna` was only a test voice.
- `prepared_voice.json` is produced upstream by the audition and human-pick flow:
  `voice_selector_gemini.py -> generate_voice_auditions.py -> human/client listens and selects -> prepare_selected_voice.py -> prepared_voice.json`.
- The packet only references that human-selected artifact by path. It never names, chooses, ranks, or defaults a voice itself.
- The audition -> review -> human/client pick step is mandatory and permanent. It becomes a UI screen later. Packet and runner consume only its result.

## Proven Routes

- `existing -> silent_brand` is executable today.
- `existing -> presenter` is executable today.
- `generate -> silent_brand` is executable today and was proven with `--max-scenes 1`.
- `generate -> presenter` is expressible in this schema and planned by the runner, but has not been validated end to end yet.
