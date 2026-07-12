# VEO Ad Pipeline — Operator UI

An internal operator console for the packet-based video pipeline. It wraps
`video_generation_agency/run_from_packet.py` ("packet in, proven command out")
and never calls the generation scripts directly.

**Zero dependencies**: the server, document parsing, and the dry-run path use
only the Python standard library. No pip install, no Node, no build step.

## Simple mode (the default page)

Document in → draft video → high-quality video:

1. **Describe** — paste scene descriptions, or upload a document (`.txt`,
   `.md`, `.json`, `.docx`, `.pdf` — text is extracted server-side, stdlib
   only). Optional: a name and a seed image (a generated placeholder is used
   otherwise, with a warning).
2. **Build (free)** — the document becomes `scenes.json` + `storyboard.json` +
   a validated job. With a Gemini key configured (and AI extraction enabled in
   settings) one small Gemini text call authors the artifacts; without it, a
   deterministic parser splits scenes on `Scene N:` markers / headings /
   numbered lists. Review the extracted prompts, artifacts, and the
   scenes-to-generate spend cap before anything is spent.
3. **Draft preview (paid)** — generates the whole video with the fast draft
   model. Requires the typed `SPEND` confirmation; the server then runs the
   full gate sequence (packet → fresh dry-run → adapter `--run`). The draft
   video plays in the app.
4. **High quality (paid)** — unlocked once the draft succeeds; re-runs the
   same prompts with the high-quality model. Both videos stay visible.

Simple mode makes silent brand videos (music is the soundtrack). Voice jobs,
existing-footage jobs, and every advanced control live in the
**Administrator** console (button in the header).

Draft/HQ models and resolutions are configurable in **Admin → Settings**
(defaults: `veo-3.1-fast-generate-preview` @ 720p / `veo-3.1-generate-preview`
@ 1080p), stored in `ui/data/settings.json`.

## Running without API keys

The app always runs. Capabilities degrade visibly instead of failing late:

- **No keys at all** — building jobs, document extraction (basic parser),
  dry-runs, and the full admin planning flow all work. Header chips say what
  paid stages need.
- **Gemini key only** — adds AI document extraction, Veo generation, and
  music. ElevenLabs is only needed for presenter (voice) jobs — simple mode
  never needs it.
- API keys are managed in **Admin → Settings**: values are **write-only**
  (stored in the server's `.env`, injected into engine subprocesses, never
  displayed or returned by any endpoint). Live stages also need the engine's
  python packages once: `pip install requests python-dotenv google-genai`.

> **Windows multi-Python gotcha.** Install those packages into the **same**
> Python you start the server with. If `python ui/server.py` and your
> `pip install` resolve to different interpreters (e.g. a Microsoft Store
> Python vs `C:\Program Files\Python312`), generation fails with
> "google-genai is not installed" even though you installed it. The error
> message names the exact interpreter to fix; or start the server explicitly,
> e.g. `py -3.12 ui/server.py` / `"C:\Program Files\Python312\python.exe" ui/server.py`,
> and run pip against that same one.

## Start

From the repo root:

```bash
python ui/server.py
```

Then open <http://127.0.0.1:8765>.

Options: `--port 9000`, `--host 0.0.0.0` (defaults bind to localhost only —
this is an internal tool).

Live runs additionally need whatever the engine itself needs: `ffmpeg`/`ffprobe`
on PATH, `requests` + `python-dotenv` installed, and API keys in `.env`
(`GEMINI_API_KEY`, `ELEVENLABS_API_KEY` for presenter jobs). The header chips
show readiness as booleans — the UI never reads or displays key material.

## Smoke tests

```bash
python -m unittest discover -s ui/tests -v
```

Free by construction: dry-runs go through the real adapter (which never spends
without `--run`), and the one live-run test mocks the process spawn.

## The Administrator console

The admin console is a single-screen wizard (no page scrolling at desktop
sizes) with a persistent status rail showing the spend gates and the stage
pipeline at all times. A subtle WebGL fluid simulation runs behind the glass
UI in both modes (cursor-reactive; disabled under `prefers-reduced-motion` or
without WebGL; paused when hidden).

1. **Job** — plain-language choice cards over the job matrix
   (`silent_brand`/`presenter` × `existing`/`generate`); jargon shown as
   captions. `presenter` adds the voice field; `silent_brand` shows no voice
   controls. `existing` requires the video file; `generate` requires the
   scenes JSON (with a live seed-image/scene-count check) and surfaces the
   `max_scenes` spend cap prominently (default **1**). Music direction
   (storyboard JSON) is always required. Model/resolution/notes and the raw
   packet JSON (view, edit, or paste an external one) live behind "Advanced".
   `start_stage` is never exposed — the adapter derives it.
   `generate + presenter` is flagged experimental.
2. **Voice** — presenter jobs only (the step shows as "skipped" otherwise).
   Audition samples listed alphabetically; never ranked, preselected, or
   defaulted. "Use this voice" unlocks only after the operator plays that
   sample. The pick writes a `prepared_voice.json` (with
   `workspace_voice_id` + audit fields) referenced by the packet. No accent
   control — accent belongs in the video/scenes prompts.
3. **Preview** (FREE) — saving runs `run_from_packet.py` without `--run`
   automatically. Shows validation errors verbatim, the derived command,
   planned stages, warnings, and the spend-authorization gate (gate 1), which
   rewrites `spend_controls.allow_live_run` in the packet file and re-runs the
   dry-run. "Full engine plan" executes the derived command (still no
   `--run` — free, plan-only). Authorizing a packet outside the UI workspace
   (e.g. a repo example) first duplicates it into `ui/data/packets/`.
4. **Launch** (PAID) — the live button stays disabled until a passing dry-run
   of the **exact packet bytes** exists in this server session and the packet
   authorizes spend. Clicking it opens the confirmation modal ("Run live —
   this spends money") requiring the typed word `SPEND`. Per-stage status
   comes from the engine's own output and manifest; shows engine run ID,
   manifest path, run directory, report links, the final video, a review
   warning when music used the safe fallback prompt, and the failure
   report/stderr verbatim on failure. Run history is in the header drawer.

## Spend-safety model

A paid run requires ALL of, in order:

1. a passing **dry-run** of the byte-identical packet (sha256-matched, this
   server session — restarting the server forces a fresh preview),
2. the packet file carrying `spend_controls.allow_live_run: true`, set only by
   the explicit **"Authorize live spend"** action (audited, and it triggers a
   fresh dry-run because the file bytes changed),
3. the typed **`SPEND`** confirmation in the live-run modal,
4. the adapter's own double gate (`--run` + packet flag) — the UI launches
   `run_from_packet.py --packet … --run` and the adapter re-checks everything.

Only one live run may be in flight at a time. Every authorization, dry-run,
voice pick, and live start/finish is appended to `ui/data/audit.jsonl`.

## Files & data

- `ui/server.py` — stdlib HTTP server (static + JSON API), binds 127.0.0.1.
- `ui/engine_bridge.py` — the only module that touches the pipeline; reuses
  the adapter's own validation functions in-process and shells out to
  `run_from_packet.py` for dry/live execution. Also owns settings,
  capabilities, and write-only API-key storage.
- `ui/simple_flow.py` — simple mode: authoring (Gemini or heuristic), seed
  placeholder generation, job persistence, gated draft/HQ generation.
- `ui/docparse.py` — stdlib text extraction (.txt/.md/.json/.docx/.pdf) and
  the heuristic scene splitter.
- `ui/static/` — no-build frontend (HTML/CSS/JS + `fluid.js`, a
  self-contained WebGL fluid background with no dependencies).
- `ui/data/` — runtime data, gitignored: saved packets, simple-mode jobs and
  uploads, prepared-voice picks, settings, run ledger (`runs.json`), audit
  log (`audit.jsonl`).

All operator-supplied paths are resolved against the repo root and refused if
they escape it. The media endpoint only serves media/report file types.

## Voice auditions directory format

Point screen 2 at a directory of audio samples. Voice IDs come from any of:

- `auditions_manifest.json`:
  `{"auditions": [{"file": "a.mp3", "workspace_voice_id": "…", "label": "…"}]}`
- a per-sample sidecar (`a.mp3.json` or `a.json`) with `workspace_voice_id`,
- manual entry by the operator (recorded in the audit trail).

The selection output is a `prepared_voice.json` containing the
`workspace_voice_id` the STS stage consumes, plus selection provenance.
