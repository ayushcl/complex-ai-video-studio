# Packet F10 — Full-width centrepiece storyboard image

> You have NO memory of any prior conversation. Rely only on this file and the files it names (all paths absolute).

## Bootstrap (read first, in order)
1. `C:\local-development\code\AGENTS.md` and `C:\local-development\code\CLAUDE.md`.
2. `C:\local-development\code\docs\handoff\storyboard-ux\CONTEXT_BRIEF.md`.
3. `C:\local-development\code\docs\plans\storyboard-review-ux-plan.html` — find **FEAT-10-FULLWIDTH-IMAGE** and read its **"Full implementation detail"** (authoritative).

## Your branch (isolation mandatory)
`git worktree add ..\wt-fullwidth -b feature/fullwidth-image core-features`, then work in `..\wt-fullwidth`.

## Outcome
The focused storyboard image fills the review column (~700–800px) while side cards stay ~440px; the rotation and reduced-motion behaviour are unchanged; there is no horizontal page scroll.

## Implementation summary (full detail in the FEAT-10 plan card)
1. Make `.cover-card` width a `--cover-w` custom property (default `440px`).
2. Enlarge only the real focused frame: `.cover-card.focused[data-frame-index]{--cover-w:92%}` — the empty placeholder has no `data-frame-index`, so it stays small. The usable column is ~860px; do NOT add a `960px` cap (that arm is dead/misleading).
3. Grow the stage + focused height with `clamp()`; re-centre the nav buttons (`top:50%; transform:translateY(-50%)`) and remove the conflicting `translateY(-1px)` from the `.cover-nav:hover` rule (keep its box-shadow).
4. In `layoutCoverFlow`, scale neighbour spacing off the **stage** width (e.g. `step = max(150, stageW*0.20)`) instead of the magic `150` — do NOT measure the focused card's `getBoundingClientRect` before its `.focused` class is applied (it's applied later in the same loop).
5. Leave all rotation / interaction code untouched; reduced-motion stays honoured.

## File scope — edit ONLY these, only for this feature
- `ui/static/styles.css`: `.cover-card` (the `--cover-w`/height vars + focused rule), `.cover-stage`, `.cover-nav` (+ its hover).
- `ui/static/app.js`: the neighbour-spacing line inside `layoutCoverFlow` ONLY.
Do **not** touch: rotation/lock state, the click handlers, the review/edit panels, or the backend. (F9 owns the reel's lock state + click branch — coordinate at merge.)

## Acceptance (verify before reporting done)
- `python -m unittest discover -s ui/tests -v` passes.
- Simple-UI QA (preview_eval / preview_snapshot; `preview_screenshot` times out): the focused card's computed width is well above 440px (~700–800px on desktop), a non-focused card stays ~440px, the reel still auto-rotates (`simple.cover.index` advances ~every 2s), nav chevrons are vertically centred, and there is no horizontal page scroll.
- No console errors; the free storyboard POST and spend-gate are unchanged.

## Commit + report
- Commit ONLY your edited files by explicit path (never `git add -A`). Push `feature/fullwidth-image`; if the remote refuses, commit locally and note it.
- Write `C:\local-development\code\docs\handoff\storyboard-ux\results\10_full-width-image.md`.
