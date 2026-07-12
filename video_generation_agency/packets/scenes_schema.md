# Scenes Schema (scenes.json)

This document defines the contract for `scenes.json`, the file the **video
generation** stage reads when `video_source` is `generate`. It is a companion to
`project_packet_schema.md` and `storyboard_schema.md`. A packet references this
file through its `scenes_path`. It is **only** used for generated-video jobs;
`existing`-video jobs ignore it.

## What this file is

`scenes.json` describes the Veo generation as an ordered chain: a **seed scene**
plus zero or more **extension scenes**. `run_veo_extension_chain.py` generates
the seed from a still image, then extends it scene by scene, each extension
continuing from the previous combined clip.

## How the code actually uses it

Unlike the storyboard, scenes.json **is** structurally validated by
`load_scenes()` before any paid call. The enforced rules:

- The root is **either** a JSON array of scenes **or** an object with a
  `"scenes"` array. Any other top-level keys (e.g. `campaign`, `model_default`,
  `config`) are **ignored** — the runner only reads the scenes array.
- There must be **at least one** scene.
- Each scene must be a JSON object.
- Each scene must have a non-empty string `prompt`.
- `negative_prompt`, if present, must be a string.
- No `prompt` or `negative_prompt` may be the literal placeholder
  `"FILL_FROM_PROOF_SCRIPT"`.

Beyond validation, the **runtime** imposes one more requirement the validator is
currently lax about: **scene 1 is always generated as an image seed**, so it
**must** have a `seed_image` pointing at an existing image file. The validator
only checks `seed_image` when the scene sets `mode: "image"`, but the runtime
(`image_seed()`) requires it for scene 1 regardless — a scene-1 without it passes
validation and then fails at the paid call. Treat `seed_image` as **required for
scene 1**. (Hardening note for later: the validator should enforce `seed_image`
on scene 1 unconditionally so this fails for free instead of at spend.)

## Per-scene fields

`prompt` — **REQUIRED**, non-empty string. The Veo generation prompt for this
scene. **Accent, voice character, and the spoken line belong here.** STS
preserves whatever accent exists in the source video's speech, so for presenter
jobs the desired accent must be described in this prompt — it cannot be chosen at
the voice step. Avoid em-dashes in prompts; prefer positive description over
stacked negatives.

`negative_prompt` — optional string. Passed to the Veo config when present.

`seed_image` — **required for scene 1**, path to an existing image file
(repo-relative). Used as the seed frame for the first generation. Ignored on
extension scenes.

`mode` — convention. Set `"image"` on scene 1 to mark it as the image seed (and
to satisfy the validator's `seed_image` check). Not read on extensions.

`duration_seconds` (or `duration`) — optional; **only affects scene 1**. Accepts
an integer (`6`) or a string (`"6s"`). At `1080p`/`4k` the seed duration is
forced to 8 regardless of this value. Extension scenes ignore it; each extension
adds roughly 7s as produced by Veo.

## Fields that are NOT read per-scene

- **resolution** — set at the run level via `--resolution` (or the packet's
  `resolution`), not per scene. A per-scene `resolution` is printed in the
  dry-run plan but never consumed.
- **aspect_ratio** — set at the run level via the packet/CLI, defaulting to
  vertical `9:16` and selectable as `9:16` or `16:9`. Not read from the scene;
  there is no per-scene aspect-ratio override.

## Scene-chain behaviour

- **Scene 1 (seed):** generated from `seed_image` + `prompt`, at the run's
  resolution, for `duration_seconds` (720p) or 8s (1080p/4k).
- **Scenes 2..N (extensions):** each generated as a continuation of the previous
  combined clip, using that scene's `prompt`. Each adds about 7s.
- `max_scenes` (from the packet/CLI) caps how many scenes run. `max_scenes: 1`
  generates only the seed — this is the cheap proof lever, and the proven
  generated-video route used exactly this.

## Worked example (object form, seed + one extension)

```json
{
  "campaign": "ignored top-level metadata is fine here",
  "scenes": [
    {
      "mode": "image",
      "seed_image": "video_generation_agency/assets/brand_wordmark.png",
      "duration_seconds": 6,
      "prompt": "A modern brand wordmark animates onto a clean premium background, confident and forward-looking, soft studio lighting.",
      "negative_prompt": "text artifacts, watermark, distortion, low quality"
    },
    {
      "prompt": "The camera pulls back slowly to reveal the full brand mark centered, the scene settling into a calm confident hold.",
      "negative_prompt": "text artifacts, watermark, distortion, low quality"
    }
  ]
}
```

The bare-array form (a top-level `[ ... ]` of scene objects) is also accepted.

## Presenter note (generate -> presenter)

For a generated *presenter* job, the spoken line and the desired accent must be
written into the seed/scene `prompt`, because that is where the source speech is
created before STS converts the voice identity. This combination (generate ->
presenter) is expressible but has not yet been validated end to end.

## Relationship to the packet and the external authoring LLM

The packet stays thin and references this file via `scenes_path`. An external
creative LLM produces this file from raw client inputs for generated-video jobs.
Its structure *is* validated by the runner, but the seed-image-at-scene-1
requirement and the accent-in-prompt rule are the two things most easily missed,
so encode them explicitly.
