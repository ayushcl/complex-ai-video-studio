# MAXIION A01 Seed — Image-to-Video Proof (SUCCESS)

**Status:** Proven. The A01 brand-wordmark seed generates correctly via literal image-to-video on the
live stack, human-reviewed with no issues.

## What this proves

Literal image-to-video works on our actual setup — Gemini Developer API, Fast model, our key and SDK.
The MAXIION wordmark image was used as the seed and produced a dark copper-amber optical-glass clip
with the brand letterforms reading correctly, including the two separate I letters (M A X I I O N).

This is the brand-asset → branded-video-seed capability the product depends on: client imagery can
seed generation, not just a text prompt.

## Proven recipe

- Script: `video_generation_agency/proof_maxiion_a01_reference.py`
- Mode: **image** (literal image-to-video — the seed image is passed as `image=` to `generate_videos`).
  `reference_images` mode also exists in the script but was **not** tested; image mode is the proven path.
- Model: `veo-3.1-fast-generate-preview`
- Seed image: `video_generation_agency/assets/maxiion_wordmark.png`
- Config: 16:9, 720p, 1 video, duration 6s, A01 negative prompt, no `generate_audio`
- Operation ID: `models/veo-3.1-fast-generate-preview/operations/97hdmp6q19qx`

## Output

- `a01_seed.mp4` — 6.000s, 1280×720, 24 fps, 144 frames, H.264 High
- The source MP4 carried an AAC audio track (Veo attaches audio on image-to-video); it is stripped for
  the silent review derivative, and audio is replaced downstream by STS/music anyway.
- Generated media remains gitignored — not committed.

## What made the double-I land

The A01 prompt was tightened specifically to protect the two I letters:

- explicit "M A X I I O N" spelling rule
- a typography construction rule keeping panel / refraction / glow / material boundaries from splitting
  or interrupting the two I's
- final-glint wording that must not merge or break the double I
- preservation wording for the established look (separate M icon tile, copper-amber glass, dark low-key
  luxury background)
- negative-prompt terms covering double-I failure modes (interrupted / unreadable / split double I,
  boundary running between or through the I letters)

This is the correct pattern: positive construction rules plus targeted exclusions in the dedicated
negative-prompt field, rather than inline "don't" phrasing in the positive prompt.

## Open / not yet proven

- `reference_images` mode (style/subject guidance, not a literal first frame) — untested, and not
  needed for A01 now that image mode delivers.
- Photo-to-video (product or person photos) — same mechanism, but not directly tested. Product/object
  photos are low-risk; photos of real, identifiable people may hit content-policy caution and need a
  separate test before being relied on.
- Standard-model fidelity pass — not run; A01 is proven on Fast only.

## Next

A01 is the proven seed for the A01–A06 extension chain. Teach the chain runner to take this image seed
in image mode, dry-run, then run the full chain on Fast.
