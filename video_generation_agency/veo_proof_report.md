# Veo Presenter Proof Run Report

## Purpose

These proof runs validate the lean presenter-video generation path before
wrapping Veo into the Agency Swarm `VideoGenerator` tool. The goal was to prove
that the Gemini API credentials, Veo Lite request submission, operation polling,
MP4 download/save path, and presenter speech generation work end to end.

## Shared Model And Settings

- Model: `veo-3.1-lite-generate-preview`
- Duration: `4` seconds
- Aspect ratio: `16:9`
- Resolution setting: `720p`
- Number of videos: `1`

## V1 Proof

```text
A professional business presenter in a modern office speaking directly to camera. She says clearly: "Welcome to Cloudtech — let's get started." Clean soft lighting, subtle corporate background, realistic commercial video style, no on-screen text.
```

- Output file: `proof_output.mp4`
- Operation ID: `models/veo-3.1-lite-generate-preview/operations/2fmohpx6zcny`
- Approximate generation time: about 30 seconds polling plus submit/download overhead
- Size: `547,771 bytes` / `535K`
- Duration: `4.00` seconds
- Resolution: `1280x720`
- Video codec: `h264 High` / `avc1`
- Audio codec: `AAC LC`, `48000 Hz`, stereo

### V1 Review

- Visually good with usable corporate/commercial style.
- Lip sync was aligned.
- Speech result: **PARTIAL PASS**.
- The presenter clearly said "Welcome to Cloudtech" and "let's get started."
- About one second of unintelligible pseudo-speech was inserted between the two phrases.
- Likely cause: the em dash, unconstrained pause, or contraction.
- Not suitable as final STS source audio because STS would preserve the gibberish.

## V2 Proof

```text
A professional business presenter in a modern office, speaking directly to camera. Clean soft lighting, subtle corporate background, realistic commercial video style, no on-screen text. She says exactly and only these words, nothing else: "Welcome to Cloudtech. Let us get started."
```

- Output file: `proof_output_v2.mp4`
- Operation ID: `models/veo-3.1-lite-generate-preview/operations/hzs0cx3eaqff`
- Approximate generation time: about 40 seconds polling plus submit/download overhead
- Size: `587,307 bytes` / `574K`

### V2 Speech Accuracy Review

- Visible realistic presenter.
- Corporate/commercial visual style is usable.
- Audio is clear.
- Intended line: "Welcome to Cloudtech. Let us get started."
- `0.0s-1.0s`: "Welcome to Cloud-"
- `1.0s-2.0s`: "-tech. Let us get"
- `2.0s-3.0s`: "started."
- `3.0s-4.0s`: silence / smiling.
- No extra speech or gibberish.
- No missing, added, mispronounced, or unintelligible words.
- Lip sync is accurate.
- Final verdict: **PASS**.
- Suitable for STS handoff testing.

## V1 Versus V2

- V1 proved the visual and technical path, but its speech was only a partial pass
  because it inserted pseudo-speech during the prompted pause.
- V2 replaced the em dash and contraction with short clean sentences plus an
  explicit instruction to say exactly and only the requested words.
- V2 produced the complete intended line with no filler speech and passed manual
  speech-accuracy review.

## Prompting Rule Learned

For Veo presenter speech, prefer short clean sentences, avoid em dashes, avoid
contractions, and explicitly say: "exactly and only these words, nothing else."

## What This Proves

- Gemini API key works.
- Veo Lite model works.
- Request submission works.
- Operation polling works.
- Download/save works.
- Presenter-style spoken source video can be generated.
- Prompt structure can materially improve presenter speech accuracy.
- A presenter clip suitable for STS handoff testing can be generated.

## What This Does Not Yet Prove

- STS conversion has not been run on this generated clip yet.
- Muxing STS audio back onto this clip has not been tested yet.
- Final music integration has not been tested yet.

## Next Step

Use `proof_output_v2.mp4` as the source video for the ElevenLabs STS handoff
test.
