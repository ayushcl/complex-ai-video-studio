# Packet F11 — Review layout: status badges to the bottom

> You have NO memory of any prior conversation. Rely only on this file and the files it names (all paths absolute).

## Bootstrap (read first, in order)
1. `C:\local-development\code\AGENTS.md` and `C:\local-development\code\CLAUDE.md`.
2. `C:\local-development\code\docs\handoff\storyboard-ux\CONTEXT_BRIEF.md`.
3. `C:\local-development\code\docs\plans\storyboard-review-ux-plan.html` — find **FEAT-11-REVIEW-BADGES** and read its **"Full implementation detail"** (authoritative).

## Your branch (isolation mandatory)
`git worktree add ..\wt-review-badges -b feature/review-badges-bottom core-features`, then work in `..\wt-review-badges`.

## Outcome
The review top shows only the validity badge plus the scenes-to-generate control; the warnings badge, the scene-count pill and the auto-seed note move to a clean footer; the warnings popover opens upward in the footer and is not clipped.

## Implementation summary (full detail in the FEAT-11 plan card)
1. In `renderSimpleReview`, keep only the validity badge (and the existing scenes-to-generate field) in the top `.review-head`.
2. Move the warnings badge, the scene-count meta-pill and the auto-seed note into a NEW `.review-foot` block at the END of the template string — reuse the exact same markup/variables (same `methodLabel(job.method)` title, same `6 + 7*(scene_count-1)` duration formula) so behaviour doesn't drift.
3. styles.css: add a `.review-foot` rule (top border + flex); reuse the existing `.review-badges`.
4. Flip the warnings popover upward in the footer: `.review-foot .warn-badge-list { top:auto; bottom:calc(100% + 6px); }` (it opens downward by default and would clip at the page bottom).
5. Leave all post-render wiring (gen-draft disable, storyboard/edit binds, cover-flow start) untouched — it selects purely by id/class.

## File scope — edit ONLY these, only for this feature
- `ui/static/app.js`: the badge markup inside `renderSimpleReview` (trim the header, add the `.review-foot` block). Do NOT change the `#s-cap` spend-cap markup (F12 owns it) or the post-render wiring.
- `ui/static/styles.css`: add `.review-foot` and the `.review-foot .warn-badge-list` flip; do not edit existing `.review-head`/`.warn-badge*`/`.meta-pill` rules.
Do **not** touch: the reel, the edit panel, or the backend.

## Acceptance (verify before reporting done)
- `python -m unittest discover -s ui/tests -v` passes (presentational change — must stay green).
- Simple-UI QA (preview_eval / preview_snapshot): `#s-review-body .review-head .review-badges` contains only the validity badge; `#s-review-body .review-foot` contains the warnings, scene-count and (when placeholder-seeded) auto-seed; opening the warnings summary reveals the full list without clipping; the reel and Generate-draft button still work.
- No console errors; free dry-run / spend-gate unchanged.

## Commit + report
- Commit ONLY your edited files by explicit path (never `git add -A`). Push `feature/review-badges-bottom`; if the remote refuses, commit locally and note it.
- Write `C:\local-development\code\docs\handoff\storyboard-ux\results\11_review-badges-bottom.md`.
