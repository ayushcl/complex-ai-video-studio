# Packet F12 — Scenes-to-generate: per-scene buttons + slider

> You have NO memory of any prior conversation. Rely only on this file and the files it names (all paths absolute).

## Bootstrap (read first, in order)
1. `C:\local-development\code\AGENTS.md` and `C:\local-development\code\CLAUDE.md`.
2. `C:\local-development\code\docs\handoff\storyboard-ux\CONTEXT_BRIEF.md`.
3. `C:\local-development\code\docs\plans\storyboard-review-ux-plan.html` — find **FEAT-12-SCENE-SLIDER** and read its **"Full implementation detail"** (authoritative).

## Your branch (isolation mandatory)
`git worktree add ..\wt-scene-slider -b feature/scene-slider core-features`, then work in `..\wt-scene-slider`.

## Outcome
Operators set "scenes to generate" with a row of per-scene buttons plus a slider (maximum = the scene count from the pasted JSON); the value the spend gate reads is byte-identical to today; a single-scene job shows a fixed read-out (no buttons/slider).

## Implementation summary (full detail in the FEAT-12 plan card)
1. In `renderSimpleReview`, replace the numeric `#s-cap` input with: per-scene buttons (1..`job.scene_count`), a `range` slider, and a live read-out — PLUS a **hidden `#s-cap`** element as the single source of truth, so `simpleGenerate`'s existing reads keep working unchanged.
2. Add a `setCap(n)` closure (clamped 1..`scene_count`) wired to the slider's `input` event and each button's `click`. The hidden `#s-cap` is the **sole** value read for both the generate POST and the cost-estimate (`ui/static/app.js` ~1797–1798 — the only `$("#s-cap")` read in the file), so `setCap(n)` must update the hidden `#s-cap.value` **first**, then sync the slider, the read-out and the active-button highlight.
3. Single-scene JSON (`scene_count <= 1`): degenerate branch — just a read-out fixed at 1, no buttons/slider.
4. Do NOT change `simpleGenerate`'s `#s-cap` reads (the single read at ~1797–1798 feeds `max_scenes` to BOTH `/api/simple/generate` and `/api/simple/confirm-token` — the server-side cost-estimate path; note `simpleGenerate` does NOT call `/api/simple/estimate`) or the backend `_normalize_max_scenes` clamp in `ui/simple_flow.py`.
5. styles.css: add `.scene-cap-btn` / `.scene-cap-slider` using existing tokens; keep the read-out on the existing `.spend-input` class.

## File scope — edit ONLY these, only for this feature
- `ui/static/app.js`: the spend-cap markup inside `renderSimpleReview` + the new `setCap` wiring (alongside the existing `bind*` calls).
- `ui/static/styles.css`: add `.scene-cap-btn` / `.scene-cap-slider`.
- `ui/static/index.html`: optional — leave the form-side `max_scenes` input as-is unless you also restyle it (not required).
Do **not** touch: `ui/simple_flow.py` `_normalize_max_scenes` (read-only contract), the reel, the edit panel, or the badge layout (F11 owns the header trim — coordinate at merge since you both edit `renderSimpleReview`).

## Acceptance (verify before reporting done)
- `python -m unittest discover -s ui/tests -v` passes — in particular the `max_scenes` clamp guard (`ui/tests/test_simple.py`, the "between 1 and" rejection) stays green.
- Simple-UI QA (preview_eval / preview_snapshot): a multi-scene job shows exactly `scene_count` buttons and `slider.max === scene_count`; clicking a button / moving the slider keeps the hidden `#s-cap`, slider and read-out in sync; a single-scene job shows the fixed read-out; Generate-draft still opens the cost-confirm with the chosen cap and the free dry-run still runs.
- No console errors; spend-gate / confirm-token flow unchanged.

## Commit + report
- Commit ONLY your edited files by explicit path (never `git add -A`). Push `feature/scene-slider`; if the remote refuses, commit locally and note it.
- Write `C:\local-development\code\docs\handoff\storyboard-ux\results\12_scene-slider.md`.
