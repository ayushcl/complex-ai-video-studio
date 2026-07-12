# Packet F13 — "Adjust Your Scenes" redesign

> You have NO memory of any prior conversation. Rely only on this file and the files it names (all paths absolute).

## Bootstrap (read first, in order)
1. `C:\local-development\code\AGENTS.md` and `C:\local-development\code\CLAUDE.md`.
2. `C:\local-development\code\docs\handoff\storyboard-ux\CONTEXT_BRIEF.md`.
3. `C:\local-development\code\docs\plans\storyboard-review-ux-plan.html` — find **FEAT-13-ADJUST-YOUR-SCENES** and read its **"Full implementation detail"** (authoritative).

## Your branch (isolation mandatory)
`git worktree add ..\wt-adjust-scenes -b feature/adjust-your-scenes core-features`, then work in `..\wt-adjust-scenes`.

## Outcome
A centred "Adjust Your Scenes" panel: a full-width instruction box directly below the scene description, and an animated pill scene selector ("Entire video" + Scene 1..N). The edit request payload and the backend contract are unchanged.

## Implementation summary (full detail in the FEAT-13 plan card)
1. Rename the panel heading "Edit the prompts" → **"Adjust Your Scenes"**; keep the `<details id="s-edit-prompt">` wrapper and the FREE tag.
2. Replace the `<select id="s-edit-scope">` with an animated pill / segmented control — **keep the id `s-edit-scope`**; carry the choice in `data-scope` ("all" or a scene-number string "1".."n"); render "Entire video" first, then Scene 1..N.
3. Reorder the body so the full-width `<textarea>` (rows=5, with a min-height) sits directly below the hint; centre the panel.
4. Update `confirmEditPrompt` to read `scopeEl.dataset.scope` (NOT `.value`) and to use a CSS busy class instead of `scopeEl.disabled` (a `<div>` has no `disabled`). Keep ids `s-edit-instruction` / `s-edit-error` / `s-edit-confirm` / `s-edit-note` byte-for-byte.
5. styles.css: add `.scene-pills` / `.scene-pill` / `.scene-pill-glider`; position the glider imperatively and re-measure it on `<details>` open (a collapsed panel measures 0).
6. The backend `simple_flow.edit_scenes` already accepts "all" or a numeric string — do NOT change it.

## File scope — edit ONLY these, only for this feature
- `ui/static/app.js`: `renderEditPromptSection`, `bindEditPromptSection`, and the scope-reading lines in `confirmEditPrompt`.
- `ui/static/styles.css`: the `.edit-prompt` block + new `.scene-pills`/`.scene-pill`/`.scene-pill-glider`.
Do **not** touch: `ui/simple_flow.py`, the reel, the review badges/spend-cap, or the dry-run / spend-gate. (F14 will read your `#s-edit-scope` selector — keep that id and the `data-scope` contract.)

## Acceptance (verify before reporting done)
- `python -m unittest discover -s ui/tests -v` passes.
- Simple-UI QA (preview_eval / preview_snapshot): heading reads "Adjust Your Scenes"; the textarea is full-width directly below the hint; pills render "Entire video" + Scene 1..N with the glider sliding under the active pill; clicking Scene 2 sets `#s-edit-scope` `dataset.scope === "2"`; submitting an instruction still POSTs `{job_dir, scope, instruction}` (scope "2"/"all") and the reel rebuilds without error; the empty-instruction guard still shows the error.
- No console errors; reel, spend-cap and confirm-token flow unchanged.

## Commit + report
- Commit ONLY your edited files by explicit path (never `git add -A`). Push `feature/adjust-your-scenes`; if the remote refuses, commit locally and note it.
- Write `C:\local-development\code\docs\handoff\storyboard-ux\results\13_adjust-your-scenes.md`.
