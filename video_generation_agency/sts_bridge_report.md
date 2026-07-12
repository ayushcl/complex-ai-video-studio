# STS Bridge Proof Report

## Purpose

This proof validates the first end-to-end bridge from a Veo-generated presenter
video through ElevenLabs Speech-to-Speech and back into a muxed video preview.
The goal was technical validation of the video-to-STS-to-mux path, not final
production casting.

## Files Used

- Source video: `proof_output_v2.mp4`
- Prepared voice config: `prepared_voice.json`
- STS output audio: `output_v2_anna.mp3`
- Muxed preview: `sts_bridge_preview.mp4`
- Voice: `Anna - British, Podcasts & Narration`
- Voice ID: `GNNHfA70qSrbkQtRy6bh`
- STS model: `eleven_multilingual_sts_v2`

## STS Conversion Command

```bash
source venv/bin/activate
python apply_sts.py \
  --video proof_output_v2.mp4 \
  --prepared-voice prepared_voice.json \
  --out output_v2_anna.mp3
```

## FFmpeg Mux Command

```bash
ffmpeg \
  -i proof_output_v2.mp4 \
  -i output_v2_anna.mp3 \
  -c:v copy \
  -map 0:v:0 \
  -map 1:a:0 \
  -shortest \
  sts_bridge_preview.mp4
```

## Generated Output Metadata

- STS output audio size: `65,663 bytes` / `64K`
- Muxed preview size: `545,404 bytes` / `533K`
- Muxed preview duration: `4.00` seconds
- Muxed video codec: `h264 High` / `avc1`
- Muxed resolution: `1280x720`
- Muxed frame rate: `24 fps`
- Muxed audio codec: `AAC LC`, `44100 Hz`, mono

## Manual Review Notes

- `sts_bridge_preview.mp4` looks good.
- The selected Anna voice was applied.
- Lip sync remains usable.
- The final word "started" was not clipped.
- Volume level is acceptable compared with the original video.
- No weird artifact, stutter, or robotic sound was heard.
- The American accent from the Veo source video carries through, which is
  expected because STS preserves source speech characteristics.
- The actor/voice identity mismatch is acceptable for this technical proof.

## What This Proves

- A Veo-generated presenter clip can be used as the STS source video.
- Source audio extraction works.
- ElevenLabs STS conversion works with the prepared Anna voice.
- The converted audio preserves usable timing and lip sync.
- The converted audio can be muxed back onto the original video.
- The complete video-to-STS-to-mux bridge works.

## Limitations Observed

- The source accent is preserved by STS.
- Actor/voice identity mismatch is not solved yet.
- This is a technical proof, not final production casting.

## Next Steps

- Create a repeatable bridge script.
- Later integrate the bridge with run folders and JSON packets.
- Eventually automate `QAReviewer` speech and audio checks.
