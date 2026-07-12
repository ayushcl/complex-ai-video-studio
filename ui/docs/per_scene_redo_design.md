# Per-scene generation and single-scene redo — design

**Status:** design only. No code in this document has been written yet. This
file describes how the engine *would* gain "generate one scene at a time" and
"redo a single scene", what new contract surface that requires, what it costs,
and how to land it safely.

**Audience:** whoever implements the engine change and the operator-UI wiring.

**Hard constraint that shapes everything below:** the spend-safety model is
non-negotiable. Every gate that exists today
(`engine_bridge.start_live_run` / `simple_flow.generate`: a passing dry-run of
the byte-identical packet by sha256, `spend_controls.allow_live_run: true` in
the packet file, the typed `SPEND` confirmation, the adapter's own
`--run` + packet-flag double gate, and one-live-run-at-a-time atomicity) must
survive unchanged. Per-scene generation makes *more* paid entry points, not
fewer gates. Each new entry point inherits the full gate sequence.

---

## 0. How the chain works today (the starting point)

`video_generation_agency/run_veo_extension_chain.py :: run_chain()` is a single
process that generates the **whole** chain in one pass:

1. Scene 1 is an **image seed**: `client.models.generate_videos(model, prompt,
   image=types.Image.from_file(location=scenes[0]['seed_image']), config)`.
2. Each later scene is a **video extension**:
   `client.models.generate_videos(model, prompt, video=previous_combined_video,
   config)`, where `previous_combined_video` is the in-memory
   `types.Video` returned by the prior operation.
3. The link between scenes is `video_uri_reference()`, which returns
   `types.Video(uri=video.uri, mime_type=...)` and **deliberately refuses to
   fall back to raw `video_bytes`**. The chain is wired entirely on Veo-side
   **URIs**, never on local files.
4. Each scene is saved to disk by `save_video()`
   (`client.files.download(file=video)` then `video.save(path)`), at
   `scene_output_path()`:
   - scene 1 -> `scene_01_seed.mp4`
   - scene N -> `scene_{N:02d}_combined.mp4`
5. After the loop, the last clip is copied to `final_raw.mp4`, audio-stripped to
   `final_silent.mp4`, and a `chain_report.json` is written.

The whole thing is driven from a packet through
`run_from_packet.py -> run_full_chain.py -> run_veo_extension_chain.py
--output-dir <run>/video --run`. `run_full_chain.py` always mints a **fresh
timestamped run directory** (`make_run_dirs`), so there is no concept today of
"continue an existing run" or "redo one clip in place".

**The two facts that make resume/redo non-trivial:**

- **A. The extension input is a URI, not a file.** Once `run_chain()` returns,
  the in-memory `previous_combined_video` (and its `.uri`) is gone. The only
  durable artifacts are the local `scene_NN_*.mp4` files. To extend *from* a
  saved clip you must give Veo a `video=` reference, and the runner only accepts
  a URI — so a saved local mp4 **must be re-uploaded** to obtain a fresh URI
  before it can seed an extension. (See §1.2.)
- **B. Veo-returned URIs are not durable.** They are tied to the generation
  operation / Files API object and expire. We cannot assume a URI captured on a
  previous run is still valid hours or days later, which is exactly the
  resume/redo case. So resume/redo cannot "remember the old URI"; it must
  re-derive one from the saved clip.

---

## 1. Resuming a chain from a saved scene clip

Goal: a chain of N scenes was run, clips `scene_01..scene_K` exist on disk
(K < N), and we want to produce `scene_{K+1}..scene_N` without re-paying for the
first K scenes.

### 1.1 The shape of the resume

A resume is "start the extension loop at index K+1, using `scene_K`'s clip as
the `previous_combined_video`". Concretely the loop in `run_chain()` becomes
parameterised by a **start index** and an **initial previous-video reference**:

- For a normal run: start index = 1, no initial reference (scene 1 is the
  image seed).
- For a resume at K+1: start index = K+1, initial reference =
  *(a freshly uploaded URI for `scene_K`'s saved clip)*.

The seed-image branch (scene 1) only runs when start index == 1. On a resume the
seed scene is skipped entirely — its clip already exists and is the chain's
anchor several links back.

### 1.2 Re-uploading the saved clip to get a URI (the load-bearing step)

Because of fact A above, resume needs a new helper in
`run_veo_extension_chain.py`, e.g.:

```
def upload_video_reference(client, clip_path: Path, label: str) -> types.Video:
    """Upload a saved local mp4 to the Files API and return a types.Video
    carrying a usable URI to seed the next extension call. Mirrors
    video_uri_reference()'s contract: returns a URI reference, never bytes."""
    uploaded = client.files.upload(file=str(clip_path))   # Files API
    # Poll uploaded.state until ACTIVE (uploads are async, like generations).
    if not uploaded.uri:
        raise RuntimeError(f"{label}: upload returned no URI to extend from.")
    return types.Video(uri=uploaded.uri, mime_type=uploaded.mime_type or "video/mp4")
```

Notes / risks for the implementer:

- **This is the single most important detail.** A "resume" that tried to pass a
  local file path as `video=` would silently violate the runner's
  URI-only contract (`video_uri_reference` exists precisely to forbid the
  bytes fallback). The re-upload is mandatory, not an optimisation.
- The upload is **async with its own state machine** (`PROCESSING -> ACTIVE`)
  and can **fail** (`FAILED`) just like a generation. It needs the same
  `wait_for_operation`-style polling, timeout, and error surfacing. Treat a
  failed/again-and-again-processing upload as a hard, fail-loud error — never
  silently fall through to a no-reference extension.
- The re-uploaded clip must be the **combined** clip
  (`scene_{K:02d}_combined.mp4`), not a per-scene delta, because each
  `scene_NN_combined.mp4` already represents the full accumulated video up to
  scene N. Extending from the combined clip continues the chain correctly.
  (Confirm this against `chain_report.json`'s `extension_call_pattern`, which
  documents `video=previous_combined_video`.)
- **Audio/length caveat:** the saved combined clips still carry Veo audio (the
  audio strip only happens on the *final* clip today). Uploading the combined
  clip as the extension seed matches what the live chain does in-memory, so this
  is consistent — but the implementer should verify the uploaded clip's duration
  is what Veo expects as an extension input (Veo extends from the tail of the
  supplied video).

### 1.3 Where the resumed clips land

Two viable conventions; recommendation in **bold**:

- **(Recommended) Write into a NEW run directory, copying the reused clips
  forward.** A resume creates `runs/<new_run_id>/video/`, copies the operator's
  `scene_01..scene_K` into it (free, local), then generates
  `scene_{K+1}..scene_N` into the same folder, then does the normal
  `final_raw/final_silent/chain_report` finalisation. This keeps
  `run_full_chain.py`'s "one run dir per invocation" invariant intact, keeps the
  manifest honest (one manifest per run), and never mutates a prior run's
  artifacts. The provenance of the reused clips is recorded in the report.
- (Rejected) Mutate the original run directory in place. This breaks the
  "fresh run dir per invocation" model, makes the manifest ambiguous (which
  invocation produced which clip?), and risks clobbering a good artifact. Avoid.

### 1.4 Validating a resume at dry-run time (free)

The dry-run must prove the resume is well-formed **before** any spend:

- The reused clips `scene_01..scene_K` exist on disk and are non-empty.
- `K` is in range `1 <= K < len(scenes)` (resuming the whole file is just a
  normal run; resuming past the end is an error).
- The scenes file is otherwise valid (existing `load_scenes` checks: prompts
  present, scene-1 seed present, no `FILL_FROM_PROOF_SCRIPT`). Note scene 1's
  seed is still required in the file even on a resume, because the scenes file is
  the source of truth for prompts and the seed contract; the seed image just
  won't be *used* for generation on a resume.
- ffmpeg/ffprobe available for finalisation.
- The dry-run prints exactly which scenes are reused vs. generated, and an
  explicit "K clips reused (free), N-K clips will be generated (paid)" line so
  the spend is unambiguous on screen before `SPEND` is typed.

---

## 2. Regenerating scene N from scene N-1 output (single-scene redo)

Goal: scenes `1..N` exist, the operator dislikes scene N (or wants a prompt
tweak), and wants to regenerate **only** scene N, then re-finalise — without
re-paying for `1..N-1` and without touching scenes after N (if any).

### 2.1 Mechanics

A single-scene redo of scene N is a special case of resume:

- **N == 1 (redo the seed):** re-run the image-seed branch with
  `scenes[0]['seed_image']` + `scenes[0]['prompt']`. No upload needed — the seed
  is an image, exactly as a fresh run's scene 1. **But:** every later scene was
  extended from the old scene 1, so redoing scene 1 *invalidates the entire
  downstream chain*. A scene-1 redo is therefore really a full re-run from
  scratch (or must be followed by regenerating 2..N). The UI must say this
  plainly: "Redoing scene 1 regenerates the whole video." Do not let it masquerade
  as a cheap single-scene operation.
- **N > 1 (redo an extension):** re-upload `scene_{N-1:02d}_combined.mp4` to get
  a URI (§1.2), then call the extension with `scenes[N-1]['prompt']`
  (zero-based `scenes[N-1]` is scene N) and that URI. Produce a new
  `scene_{N:02d}_combined.mp4`.

### 2.2 The honest cost / dependency truth (must be surfaced)

Redoing scene N only gives a coherent final video if scene N is the **last**
scene used in the final output. If scenes `N+1..M` also exist, they were each
extended from the *old* scene N and are now **stale** — they no longer follow
from the regenerated scene N. There is no cheap fix: a redo of an interior scene
forces regeneration of every scene after it. So the contract is:

- Redo of the **last** scene = redo exactly one paid scene, then re-finalise.
- Redo of an **interior** scene N = redo scene N **and** `N+1..M` (a partial
  re-run that is really "resume from N", §1). The dry-run must compute and show
  the true paid-scene count, never just "1".

This is the single biggest correctness trap in the feature. The design choice
is: **do not silently regenerate downstream scenes, and do not silently leave
stale ones.** Force the operator to choose explicitly (redo-just-this-one is only
offered for the last scene; interior redo is presented as "redo from scene N
onward" with the real cost).

### 2.3 Where redo output lands

Same as §1.3: new run dir, reused clips copied forward, regenerated clip(s)
written fresh. Never overwrite the original `scene_NN` in the prior run. The
operator keeps the old take for comparison; the new run is the candidate.

---

## 3. New flags / contract surface

The principle (`run_from_packet.py`'s tagline "packet in, proven command out")
is preserved: the **packet** is the operator-facing contract; the adapter
derives runner flags; the UI never builds runner commands directly.

### 3.1 `run_veo_extension_chain.py` (lowest layer)

New CLI flags, all dry-run-aware and all defaulting to today's behaviour:

| Flag | Meaning |
|------|---------|
| `--resume-from-dir <dir>` | Directory holding the already-generated `scene_NN_*.mp4` clips to reuse. |
| `--start-scene <K>` | 1-based index of the first scene to **generate**. Scenes `< K` are reused from `--resume-from-dir`. `--start-scene 1` (default) is a normal full run and ignores `--resume-from-dir`. |
| `--only-scene <N>` | Convenience for a single-scene redo: generate exactly scene `N` (requires `--resume-from-dir` for `N > 1`; refuses if scenes after `N` exist unless `--allow-stale-tail` is set — see below). Mutually exclusive with `--start-scene`. |
| `--allow-stale-tail` | Explicit acknowledgement that a redo leaves later scenes stale (rarely wanted; off by default). |

Internal changes:

- `run_chain()` gains `start_scene` and an `initial_reference` (the uploaded URI
  for `scene_{start-1}`); the loop iterates `scenes[start_scene-1:]` with the
  index offset preserved so `scene_output_path` keeps the right numbering.
- New `upload_video_reference()` (§1.2) with full polling/timeout/error
  handling, reusing the `wait_for_operation` discipline.
- `dry_run()` learns to print the reuse/generate split and the true paid count.
- Reused clips are copied into the new output dir before the loop starts.

Backward compatibility: with none of the new flags, the script behaves exactly
as today.

### 3.2 `run_full_chain.py` (orchestrator)

`run_full_chain.py` owns the run directory and the video stage's command
assembly (`build_plan` -> the `python3 run_veo_extension_chain.py ... --run`
execution command). It needs matching passthrough flags:

| Flag | Maps to |
|------|---------|
| `--resume-from-dir <dir>` | passed through to `run_veo_extension_chain.py` |
| `--start-scene <K>` | passed through |
| `--only-scene <N>` | passed through |
| `--allow-stale-tail` | passed through |

Behaviour:

- These only apply when the video stage is active and `video_source=generate`
  (no meaning for `--video` existing-footage jobs; warn-and-ignore otherwise,
  matching how `max_scenes` is handled).
- The new run dir is still minted fresh per invocation. The copy-forward of
  reused clips happens **inside** `run_veo_extension_chain.py` (it owns
  `video/`), so `run_full_chain.py` just forwards the flags.
- The manifest already records `args` (`manifest_args`) — extend it to include
  the resume/redo args so the manifest is a faithful record of what reused what.
- The downstream stages (music, assemble) are unaffected: they consume
  `video/final_raw.mp4` / `video/final_silent.mp4`, which are produced exactly as
  before after the (partial) chain completes.

### 3.3 `run_from_packet.py` (adapter) and the packet

Add an optional, **off-by-default** block to the packet. Absent = today's full
run, so every existing packet is unchanged:

```json
"resume": {
  "from_run_dir": "runs/full_20260601_120000/video",
  "start_scene": 4,
  "only_scene": null,
  "allow_stale_tail": false
}
```

Adapter rules (in `validate_packet` / `build_command`):

- Only valid when `video_source == "generate"`. Reject (or warn-and-ignore,
  matching `max_scenes`) otherwise.
- `from_run_dir` must exist and contain the expected `scene_NN_*.mp4` clips for
  every reused index. The adapter file-checks them the same way it
  `_check_file`s `scenes_path` today, so a missing reused clip is caught at
  **dry-run** time, not after `SPEND`.
- `start_scene` / `only_scene` are mutually exclusive; both must be integers in
  range against the scenes file's length.
- `interior redo` (an `only_scene` with later scenes present) without
  `allow_stale_tail` is a **hard PacketError** at validation, with a message
  telling the operator to use `start_scene` (regenerate the tail) or set
  `allow_stale_tail` deliberately.
- `build_command` appends the derived `--resume-from-dir/--start-scene/...`
  flags. `derive_start_stage` is unchanged (`generate -> video`); resume still
  starts at the `video` stage — it just starts the *scene loop* partway through.

**The reused `from_run_dir` path must go through `bridge.safe_path`** in the UI
layer (repo-root constrained), exactly like every other operator path. A resume
must never read clips from outside the repo.

### 3.4 UI / `engine_bridge.py` / `simple_flow.py` surface (not built here, but the contract)

- New paid entry points (`engine_bridge.start_resume_run` /
  `simple_flow.regenerate_scene`) **reuse `start_live_run` wholesale.** They do
  not get a parallel, weaker path. The sequence is identical: build the resume
  packet -> write it to disk -> fresh dry-run of those exact bytes (sha256) ->
  authorize (`allow_live_run`) -> typed `SPEND` -> `start_live_run` (which
  re-checks freshness, the packet flag, atomicity, and shells the adapter with
  `--run`).
- The one-live-run-at-a-time lock (`_live_start_lock` / the running-run check)
  already covers resume runs because they go through `start_live_run`. A redo
  cannot start while any run (full or redo) is in flight. Keep it that way.
- The `SPEND` modal copy must show the **true paid scene count** (from the
  dry-run's reuse/generate split), e.g. "scene 5 redo: 1 scene generated
  (scenes 1-4 reused free)" or, for an interior redo, "scenes 3-6 regenerated (4
  paid; scenes 1-2 reused free)". The existing modal already renders a spend
  summary; extend that summary, do not add a new confirm path.
- `inspect_scenes` / the scenes-check panel can gain a free, read-only "which
  clips already exist in this run dir" hint to drive the redo UI, but it stays
  advisory — the dry-run + adapter remain authoritative.
- Media serving of the candidate clips for side-by-side review goes through the
  existing `/api/media` endpoint, which already only serves media/report types
  and is repo-root constrained. No new serving surface.

---

## 4. Cost implications

The whole point of the feature is **cost reduction** — it lets the operator stop
re-paying for scenes they already approved.

- **Veo generation is per-scene.** A full N-scene chain pays for N generations.
  A resume from K+1 pays for `N - K`. A last-scene redo pays for 1. The reused
  clips cost **nothing** (local copy).
- **The re-upload (§1.2) is essentially free** (Files API upload/storage), but
  it is a real network round-trip with its own latency and failure modes; budget
  for it in timeouts, not in dollars.
- **Music and assembly always re-run.** Even a single-scene redo produces a new
  `final_raw.mp4`, so the music stage (Lyria generation) and the ffmpeg
  assembly run again. Music generation has a cost and a latency; a "cheap" redo
  is "1 Veo scene + 1 full music generation + assembly", not "1 Veo scene". The
  cost estimate shown to the operator must include the music re-generation, or it
  will understate spend. (If music re-gen on every redo proves too costly, a
  later optimisation could reuse the prior `background_music.mp3` when the
  storyboard and final duration are unchanged — but that is out of scope here and
  must not be assumed.)
- **Interior redo is the expensive trap (§2.2):** "redo scene 3" in a 6-scene
  chain is 4 paid Veo scenes (3,4,5,6) + music + assembly, not 1. The dry-run
  must compute and display this honestly so the operator authorises the real
  amount.
- **Failed re-upload or failed mid-chain scene** still spent money on whatever
  scenes already generated in that invocation. This matches today's behaviour
  (a chain that fails at scene 4 already paid for 1-3); the manifest/report must
  record partial spend so it is auditable. Fail loud, never silently retry the
  whole chain.

---

## 5. Recommended phased approach + risks

### Phase 1 — Engine resume primitive (no UI), proven by dry-run
- Add `--resume-from-dir` + `--start-scene` to `run_veo_extension_chain.py`,
  plus `upload_video_reference()` with full polling/timeout/error handling.
- Make `dry_run()` print the reuse/generate split and true paid count.
- Add the copy-forward of reused clips into a fresh output dir.
- **Verification:** dry-run only (free). Unit-test the index math
  (`scene_output_path` numbering across a resume), the range validation, and the
  reuse/generate accounting. Live verification is a single deliberate
  `--max-scenes`-style minimal resume by a human, off the critical path.
- **Risk:** the re-upload URI contract (§1.2) is the thing most likely to be
  wrong. Prove it against the real Files API early, in isolation, before wiring
  anything else. Do not assume `files.upload` returns an immediately-usable URI.

### Phase 2 — Adapter + packet contract
- Add the optional `resume` block to the packet, the `validate_packet` rules
  (including the interior-redo hard error), and the `build_command` passthrough.
- Extend `manifest_args` so the manifest records the resume.
- **Verification:** adapter dry-run (`run_from_packet.py` without `--run`) on
  hand-written resume packets, asserting both the derived command and the
  rejections. All free.
- **Risk:** weakening a gate by accident. Add a test that a resume packet still
  refuses to run live without `allow_live_run` and without the typed phrase
  (i.e. the existing `start_live_run` gate tests, parameterised for resume).

### Phase 3 — Single-scene redo as the constrained, last-scene case
- Add `--only-scene` + `--allow-stale-tail` and the matching adapter rules.
- Offer redo in the UI **only for the last scene** initially (the unambiguous,
  genuinely-cheap case). Interior redo is presented as "regenerate from scene N"
  (Phase 1's resume) with the honest cost.
- **Verification:** UI smoke test that the redo path funnels through
  `start_live_run` (mock the spawn, as the existing one-live-run test does) and
  that the `SPEND` modal shows the true paid count.

### Phase 4 — UI polish: review-and-compare
- Side-by-side of old vs. candidate clip via the existing `/api/media` endpoint;
  "keep candidate" just means the operator points the next job at the new run
  dir. No new spend surface.

### Cross-cutting risks to watch
- **Spend-gate erosion (highest):** the temptation to add a "quick redo" button
  that POSTs straight to generation. Forbidden. Every redo is a full
  packet -> dry-run -> authorize -> SPEND -> adapter `--run` sequence. A redo is
  a paid run like any other.
- **Stale-tail silent corruption (§2.2):** the engine must never emit a final
  video stitched from a regenerated scene N plus stale `N+1..M`. Enforce at
  validation, not in the UI only.
- **Expired/again-uploaded URIs:** never persist and reuse an old Veo URI;
  always re-derive from the saved clip. (Fact B in §0.)
- **Reused-clip integrity:** a truncated or wrong-resolution reused clip would
  produce a bad extension seed. Dry-run checks existence/non-emptiness; consider
  an ffprobe duration/resolution sanity check before spending (free, and it
  catches a corrupt reuse before money is spent).
- **Path safety:** `from_run_dir` and every reused clip path go through
  `bridge.safe_path`. A resume reading clips from outside the repo is refused.
- **Audit completeness:** every resume/redo start and finish appends to
  `audit.jsonl` (reuse `audit()`), recording the run dir reused, the
  start/only scene, and the paid count, so partial-spend history is reconstructable.
