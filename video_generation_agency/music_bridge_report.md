# Music Bridge Proof Report

## Purpose

Prove the complete bridge from generated presenter video through STS voice replacement,
music generation, voice/music mixing, and final muxed video:

`video -> STS voice -> music generation -> audio mix -> final muxed video`

## Files Used

- `output_v2_anna.mp3` - ElevenLabs STS proof voice
- `video_generation_agency/proof_storyboard_v2.json` - controlled music creative direction
- `proof_output_v2.mp4` - Veo presenter proof video
- `run_music_pipeline.py` - music generation and mixing wrapper
- `generate_music.py` - Gemini brief and Lyria generation
- `mix_audio.py` - FFmpeg voice/music mixer

Anna is the proof-run selected voice only. Production voice selection comes from the
audition and human/client selection flow through `prepared_voice.json`.

## Lyria Filter Issue And Fix

The first controlled generation reached Lyria but was rejected by its provider-side
copyright-similarity filter. Inspection showed that the Gemini music brief was clean,
but the Lyria prompt builder still sent a forced BPM and a long negative-vocabulary
avoid list containing song-like terms.

`build_lyria_prompt()` was patched with an ambient-safe mode. For ambient,
no-beat/no-melody, static-texture briefs, it sends a compact texture-only prompt with
no BPM and without the long song-like negative vocabulary. Normal non-ambient prompt
behavior remains unchanged.

The next single controlled run passed using this exact Lyria prompt:

> Create approximately 4.0 seconds of original abstract ambient sound design. Use a
> quiet warm low tonal layer with soft air-like texture. Keep it sparse, static,
> non-rhythmic, and non-melodic. No vocals or speech. Avoid recognizable musical
> phrases, repeating motifs, or genre imitation. Fade in gently and fade out cleanly.

## Commands Used

```bash
python run_music_pipeline.py output_v2_anna.mp3 \
  --storyboard video_generation_agency/proof_storyboard_v2.json \
  --music-volume 0.08 \
  --tail-seconds 1.0
```

```bash
ffmpeg -i proof_output_v2.mp4 -i music/final_mixed.mp3 \
  -c:v copy -map 0:v:0 -map 1:a:0 -shortest music_bridge_preview.mp4
```

## Successful Run Metadata

- Gemini brief model: `gemini-3.1-flash-lite`
- Lyria music model: `lyria-3-pro-preview`
- Requested duration: `4.040272` seconds
- Raw generated music duration: `65.070958` seconds
- Mixed audio duration: `5.040272` seconds
- Music volume: `0.08`
- Final preview duration: `4.00` seconds
- Final preview resolution: `1280x720`
- Final preview video codec: H.264 High / AVC1
- Final preview audio codec: AAC LC, 44100 Hz, mono

Lyria produced approximately 65 seconds for the four-second request. The mixer trimmed
the raw music and added a one-second tail to the voice duration. The final mux used
`-shortest`, so the preview remained limited to the four-second source-video duration.

## QA Result

**PASS**

- Speech remains accurate and clear over the music.
- The STS voice sounds natural with no audible artifacts.
- Lip sync remains tight.
- The ambient bed is quiet and free of beat or melody.
- The voice/music mix is balanced.
- No clipping was observed.

## Limitations

- Lyria similarity filtering is stochastic; this successful pass is not a permanent
  guarantee against future rejections.
- The Gemini brief still describes the direction as `corporate ambient` with `70 BPM`.
  The fix currently lives in the Lyria prompt builder, which intercepts suitable
  ambient briefs, rather than in the Gemini brief itself.
- Lyria output duration is highly variable. This run generated approximately 65
  seconds of raw music for a four-second request.
- **Important:** the ambient-safe patch in this local `generate_music.py` has not yet
  been upstreamed to `ayush/music-pipeline` and must be ported back there.
- The four-second video ends before the mixed audio's one-second tail. Extending the
  video tail by approximately 0.5 to 1.0 seconds would allow the full music fade to
  play.

## Next Steps

1. Add a fallback ambient bed so a Lyria rejection does not hard-fail the pipeline.
2. Build a repeatable full-chain runner.
3. Packetize the workflow using JSON inputs and outputs.
4. Integrate the proven steps into Agency Swarm agents.
5. Build the UI.
