# Veo Extension Proof Report

## Purpose

Prove the Veo 3.1 extension mechanism with a minimal two-scene chain:

`Scene 1 text-to-video seed -> Scene 2 extension using the returned Scene 1 Video URI -> combined extended output`

This validates that a generated Veo clip can be passed back into Veo using the SDK's
`video=` parameter and extended into a longer continuous result.

## Script

- Script: `video_generation_agency/proof_veo_extension_chain.py`
- Model: `veo-3.1-generate-preview`
- Output folder: `veo_extension_proof/`
- Generated media is ignored by git and must not be committed.

## Call Pattern

Scene 1 was generated from text:

```python
client.models.generate_videos(
    model=VEO_MODEL,
    prompt=SCENE_1_PROMPT,
    config=scene_1_config,
)
```

Scene 2 was extended from the returned Scene 1 video reference:

```python
client.models.generate_videos(
    model=VEO_MODEL,
    prompt=SCENE_2_PROMPT,
    video=scene_1_video,
    config=scene_2_config,
)
```

- Extension input mode: `video`
- Extension input reference: returned Video URI
- Extension call pattern: `prompt=SCENE_2_PROMPT, video=scene_1_video`
- `generate_audio` is omitted because the Gemini Developer API rejects that field.
- Native audio is discouraged through `negative_prompt` and should be stripped in post
  for silent website hero outputs.

## Operations

- Scene 1 operation: `models/veo-3.1-generate-preview/operations/gn5ovfuoigg1`
- Scene 2 operation: `models/veo-3.1-generate-preview/operations/g9n3hk1c071z`

## Generated Files

- Scene 1 output: `veo_extension_proof/scene_01_seed.mp4`
  - Size: `1,312,697 bytes` / `1.3M`
  - Duration: `8.00s`
  - Resolution: `1280x720`
  - Video codec: H.264 High / AVC1
  - Frame rate: `24 fps`
  - Audio: AAC LC, 48000 Hz, stereo
- Scene 2 extended output: `veo_extension_proof/scene_02_extended.mp4`
  - Size: `2,846,344 bytes` / `2.7M`
  - Duration: `15.00s`
  - Resolution: `1280x720`
  - Video codec: H.264 High / AVC1
  - Frame rate: `24 fps`
  - Audio: AAC LC, 48000 Hz, stereo
- Run report: `veo_extension_proof/extension_report.json`

## QA Summary

Gemini Ultra QA verdict: **PASS for Veo extension mechanism and visual continuity.**

Findings:

- Video plays normally.
- Duration is exactly 15 seconds.
- Output appears as one continuous combined video rather than two unrelated clips.
- Scene 1 includes a dark modern desk, laptop, glass prism, warm amber/copper palette,
  and stable restrained camera.
- Scene 2 extends seamlessly without visual reset.
- Laptop and prism remain consistent in placement and scale.
- An anonymous hand enters from the right and opens the laptop.
- A warm glow emerges from the laptop screen.
- The transition around 8 seconds is virtually undetectable.
- No jump cuts, scale changes, or major object drift were observed.
- Left-side negative space remains good for website copy.
- Native audio exists, but it is harmless and can be stripped in post.

## Verdict

**PASS** for the extension mechanism.

The proof demonstrates that:

- Text-to-video Scene 1 generation works.
- The returned Scene 1 Video URI can be reused through `video=`.
- Scene 2 extension produces a combined 15-second output.
- Visual continuity is strong across the extension boundary.

## Client-Readiness Note

**PARTIAL PASS** for client-readiness.

Known issue:

- The laptop has a visible Apple logo.
- This violates the unbranded/no-logo requirement.
- Treat this as a prompt adherence and brand-safety issue, not an extension mechanism
  failure.

Future prompts should strongly specify:

> plain generic unbranded laptop, no Apple logo, no illuminated logo, no logo-shaped
> mark, no manufacturer badge.

## Audio Note

Native audio is present in both generated videos despite audio being discouraged through
the negative prompt. For silent website hero outputs, the production chain should strip
native audio automatically after generation.

## Recommended Next Step

Adapt the full six-scene chain using:

- Stronger no-logo laptop language.
- Automatic audio stripping after each generated or extended clip.
- The proven `video=` extension pattern.
- A generated-media policy that keeps all proof and production MP4 files out of git.
