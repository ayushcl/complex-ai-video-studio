# Packet F9 — Reel click-to-lock / unlock

> You have NO memory of any prior conversation. Rely only on this file and the files it names (all paths absolute).

## Bootstrap (read first, in order)
1. `C:\local-development\code\AGENTS.md` and `C:\local-development\code\CLAUDE.md` — project rules.
2. `C:\local-development\code\docs\handoff\storyboard-ux\CONTEXT_BRIEF.md` — shared context + the collision/branch rules (important).
3. `C:\local-development\code\docs\plans\storyboard-review-ux-plan.html` — open it, find the **FEAT-09-REEL-LOCK** card, and read its **"Full implementation detail"**. That is the authoritative, code-grounded step list (exact symbols/lines); the summary below orients you.

## Your branch (isolation mandatory)
`git worktree add ..\wt-reel-lock -b feature/reel-lock core-features`, then work in `..\wt-reel-lock`. Branch off the LOCAL `core-features`.

## Outcome
Clicking a storyboard image **locks** the rotating reel on that scene with a clear visual lock effect; clicking the locked image again **unlocks** and resumes auto-rotation; the lock never expires on its own. Rotation is otherwise unchanged, and the free dry-run / spend-gate is untouched.

## Implementation summary (full detail in the FEAT-09 plan card)
1. Add a `locked` boolean to the `simple.cover` state (keep `paused` / `resumeTimer`); `locked` holds `paused` true indefinitely.
2. Add `lockCover(frameIndex)` / `unlockCover()` helpers (after `manualNav`): focus the frame via `coverGoFrame`, set `locked`, toggle a `cover-locked` class + aria-label, clear the resume timer.
3. Rewire the reel card-click branch to toggle: click → lock on that scene; click the locked focused card → unlock; click a different card while locked → re-lock. Leave arrows/dots as transient nav.
4. Guard `scheduleResume` to no-op while locked (so hover/drag/focusout can't silently resume after 5s).
5. styles.css: a cyan inset ring + a lock badge on the focused face, and grayscale the non-focused faces using `filter` (NOT `opacity` — layout writes inline opacity each pass).
6. Give the focused card a pointer cursor; leave reduced-motion + drag behaviour intact.
7. **Both `lockCover()` and `unlockCover()` must end by calling `syncScopeToLockedFrame()` IF that function exists** (added by F14) — guard with `typeof`; these are the F14 hooks, harmless before F14 lands. The `lockCover` hook matters: `lockCover` focuses the frame (running `layoutCoverFlow`) BEFORE it sets `locked = true`, so F14's end-of-`layoutCoverFlow` hook can't catch the initial lock — the call at the end of `lockCover` is what syncs the selector on that first lock.

## File scope — edit ONLY these, only for this feature
- `ui/static/app.js`: the `simple.cover` state object, the new `lockCover`/`unlockCover` helpers, the reel card-click branch, the `scheduleResume` guard.
- `ui/static/styles.css`: the new `.cover-locked` rules + the focused-card cursor.
Do **not** touch: the backend, `renderSimpleReview`/the review badges, the spend-cap, the edit-prompts panel, or any dry-run / confirm-token / spend-gate code. Do not reformat `layoutCoverFlow` internals (F10 owns its spacing logic).

## Acceptance (verify before reporting done)
- `python -m unittest discover -s ui/tests -v` passes (run from `C:\local-development\code`).
- Simple-UI QA (`python ui/server.py`, port 8765; use preview_eval / preview_snapshot): clicking a card sets `simple.cover.locked === true` and adds `cover-locked`; the reel does NOT advance after >5s while locked; clicking the focused card unlocks and rotation resumes; clicking a different card re-locks. Reduced-motion still suppresses auto-rotate.
- No console errors; the free dry-run + spend-gate behave exactly as before.

## Commit + report
- Commit ONLY your edited files by explicit path (never `git add -A`). Push `feature/reel-lock`; if the remote refuses (it has been intermittently unreachable), commit locally and note it — the integrator pushes.
- Write `C:\local-development\code\docs\handoff\storyboard-ux\results\09_reel-lock.md`: files/symbols changed, test output, QA result, push status.
