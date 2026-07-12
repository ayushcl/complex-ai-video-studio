# Packet F14 — Click image → sets the scene selector (unclick = all)

> You have NO memory of any prior conversation. Rely only on this file and the files it names (all paths absolute).

## ⚠ Dependency — start only after F9 and F13 are merged
This feature reads F9's reel **lock state** and drives F13's redesigned **scene selector**.
Do NOT start until both `feature/reel-lock` (F9) and `feature/adjust-your-scenes` (F13) are
merged into `core-features`. Branch off the post-merge `core-features`.

> **Expected pre-merge state:** until F13 lands, the live `ui/static/app.js` still has the
> old `<select id="s-edit-scope">` (~line 1375). That is correct, not a bug — F14 targets
> F13's replacement **pill** control (a `data-scope` `<div>` of `.scene-pill` buttons), so
> it can only start post-merge. Reviewing F14 against pre-F13 code looks like a mismatch but
> isn't one.

## Bootstrap (read first, in order)
1. `C:\local-development\code\AGENTS.md` and `C:\local-development\code\CLAUDE.md`.
2. `C:\local-development\code\docs\handoff\storyboard-ux\CONTEXT_BRIEF.md`.
3. `C:\local-development\code\docs\plans\storyboard-review-ux-plan.html` — find **FEAT-14-CLICK-TO-SELECT** and read its **"Full implementation detail"** (authoritative).

## Your branch (isolation mandatory)
`git worktree add ..\wt-click-select -b feature/click-to-select core-features` (after F9 + F13 are in core-features), then work in `..\wt-click-select`.

## Outcome
While the reel is locked (F9), the focused image pins the "Adjust Your Scenes" scene selector to that scene — however the reel arrived there (click, auto-rotate, arrows, dots, drag). Unlocking reverts the selector to "all scenes". An unlocked reel never overrides a manual scope pick.

## Implementation summary (full detail in the FEAT-14 plan card)
1. Add `syncScopeToLockedFrame()` + `isReelLocked()` helpers (near `coverGoScene`). When locked, set `#s-edit-scope` to the focused frame's `sceneIndex`; otherwise set "all". Guard defensively — only switch if a matching `.scene-pill` exists, else fall back to "all" (the reel frames and the pills both come from the same scene list, so a match is expected; this guard is insurance and is **not** tied to the spend cap, which does not change the pills). F13 delivers a **pill control**, not a `<select>`: `#s-edit-scope` is a `data-scope` `<div>` holding `.scene-pill` buttons + a `.scene-pill-glider`. So "set" means update the container's `dataset.scope` + the active pill + the glider — reuse F13's selection helper.
2. Hook `if (isReelLocked()) syncScopeToLockedFrame();` at the END of `layoutCoverFlow` — this keeps the scope pinned through focus changes **while already locked** (auto-rotate, arrows, dots, drag, re-locking to another card). Do NOT add a call in the click branch. This hook does NOT catch the **initial** lock: F9's `lockCover` focuses the frame (running `layoutCoverFlow`) *before* it sets `locked`, so the initial-lock sync must come from F9's `lockCover` hook (step 3), not from here.
3. Ensure F9's **`lockCover()` AND `unlockCover()`** each end with a `typeof`-guarded `syncScopeToLockedFrame()` call (F9 was asked to add both; if either is missing, add it). On lock the helper sees `locked === true` and pins the focused scene (this is what makes the first lock work — see step 2); on unlock it sees `locked === false` and resets the selector back to "all".
4. Rebuilds (edit-regenerate, fresh storyboard) already re-sync via `buildCoverFlow → layoutCoverFlow`; the empty-reel path stays "all".
5. Optional: a `scope-locked` CSS cue on the selector while locked.

## File scope — edit ONLY these, only for this feature
- `ui/static/app.js`: the new `syncScopeToLockedFrame`/`isReelLocked` helpers, the one-line `layoutCoverFlow` hook, and (if needed) the one-line call inside `unlockCover`.
- `ui/static/styles.css`: an optional `.scope-locked` cue.
Do **not** touch: the backend, the spend-cap, the review badges, or the reel's rotation/lock logic beyond the single `unlockCover` line.

## Acceptance (verify before reporting done)
- `python -m unittest discover -s ui/tests -v` passes.
- Simple-UI QA (preview_eval / preview_snapshot): with the reel unlocked, the selector keeps the operator's manual choice; **click a card to lock** (the initial lock, via `lockCover`) → `#s-edit-scope` `dataset.scope` matches that scene and its pill is `.active`; while locked, focus scene 2 (nav / re-lock) → `dataset.scope === '2'` and the Scene 2 pill is `.active`; unlock → `dataset.scope === 'all'` and the "Entire video" pill is `.active`. (The pill-existence guard is defensive only — it is not exercised by the spend cap, which does not change the pills.)
- No console errors; `confirmEditPrompt`'s edit POST and the spend-gate / dry-run are unchanged.

## Commit + report
- Commit ONLY your edited files by explicit path (never `git add -A`). Push `feature/click-to-select`; if the remote refuses, commit locally and note it.
- Write `C:\local-development\code\docs\handoff\storyboard-ux\results\14_click-to-select.md`.
