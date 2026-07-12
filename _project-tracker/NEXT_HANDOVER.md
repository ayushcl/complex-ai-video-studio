# NEXT_HANDOVER

Continuation handover for the next agent. The user authorized the task list below;
take it up after reading `_project-tracker/TRACKER.md` and `CURRENT_STATE.md`.

Repo: `C:\local-development\code` · Branch: `core-features` (the integration branch,
built on the other developer's `c3a4a6a`). Operator UI is stdlib: `python ui/server.py`
(port 8765); tests: `python -m unittest discover -s ui/tests -v` (currently **227 green**);
`preview_screenshot` times out on this machine — use `preview_eval` / `preview_snapshot`.

## What was done this session (context, not tasks)
- Preserved the old local work to branch `ui-enhancements-v1`; reconciled `core-features` off the other dev's presenter-reference work.
- Shipped a **presenter-reference cost-honesty fix** (`ui/cost_estimator.py`, `ui/static/app.js`, tests) — commit `5e354f1`.
- Built two self-contained interactive HTML plans under `docs/plans/`:
  - `feature-implementation-plan.html` — **F1–F8** generation pipeline plan.
  - `storyboard-review-ux-plan.html` — **F9–F14** storyboard-review UX plan.
- Built the **`implementation-plan-visual` skill** at `.claude/skills/implementation-plan-visual/` (`SKILL.md` + `references/template.html` + `references/review_prompt.md`) that generates those plans (research-via-workflow, then assemble from the template), and added an adversarial-review ("roast") step + a "critically analyse findings, confirm with the human, then update" protocol.
- Built a **parallel-task handoff package** for F9–F14 in `docs/handoff/storyboard-ux/` (`RUN_ORDER.md`, `CONTEXT_BRIEF.md`, `09_…`–`14_…`, and `PLAN_REVIEW.md`).
- Fixed 3 external-review findings (commit `2509987`): F14 plan detail now drives F13's pill control (not a removed `<select>`); corrected wrong "git-ignored" wording (those dirs are untracked, not ignored); fixed the stale "Placeholder rates" cost-dialog copy.
- Ran an independent roast of the F9–F14 plan and analysed it (see Task 1).

## Git state
- `origin/core-features` is at `7d54e72`. Local `core-features` is **3 commits ahead** and **unpushed**: `bd0a1c0` (F9–F14 plan), `f6c9e4a` (handoff package), `2509987` (the 3 fixes).
- The GitHub remote (`cloudtechuk/VEO-AUDIO-PRODUCTION-PIPELINE`) has been **intermittently unreachable** ("Repository not found") — it worked mid-session then refused repeatedly. The user needs to confirm repo access; pushes are pending that.
- **Uncommitted working-tree changes from the last turn** (do not lose):
  - `docs/handoff/storyboard-ux/PLAN_REVIEW.md` — NEW, tracked, uncommitted.
  - `.claude/skills/implementation-plan-visual/SKILL.md` — edited (added the roast step + protocol).
  - `.claude/skills/implementation-plan-visual/references/review_prompt.md` — NEW.
  - Note: `.claude/skills/` and `_project-tracker/` are **untracked, not git-ignored** — they are committable; decide per the user.

## Tasks to carry out (user-authorized)

### Task 1 — Apply the roast's confirmed minor fixes (HANDOFF PACKETS ONLY)
These are wording-only; do **not** touch the plan HTML or any code. The roast's headline
"P1" (that F13's pill control "doesn't exist in the live code") is a **false alarm** — F9–F14
are unbuilt planned features and F14 is correctly gated to start only after F9 + F13 merge,
so the live code legitimately still has a `<select>`. **Do NOT act on that P1.**
- `docs/handoff/storyboard-ux/14_click-to-select.md`:
  - In the "Implementation summary" step that says *"confirm whether F13 left a `<select>` or pills and target accordingly"* — remove the hedge; state it definitively: F13 delivers a pill control (`#s-edit-scope` is a `data-scope` `<div>` with `.scene-pill` buttons + `.scene-pill-glider`); reuse F13's selection helper.
  - In "Acceptance": change *"higher scenes have no option … (the option-existence guard)"* → *"no pill button … (the pill-existence guard)"*.
  - In "Acceptance": make the scope assertions explicit — *"lock the reel and focus scene 2 → `#s-edit-scope` `dataset.scope === '2'` and the Scene 2 pill is `.active`; unlock → `dataset.scope === 'all'` and the 'Entire video' pill is `.active`."*
- `docs/handoff/storyboard-ux/12_scene-slider.md`:
  - Strengthen the hidden-`#s-cap` note: it is the **sole** value `simpleGenerate` + `estimate` read (`ui/static/app.js` ~1797–1798), so `setCap(n)` must update the hidden `#s-cap.value` **first**, then the slider + read-out.
- (Optional, user's call) add a one-line reinforcement to `RUN_ORDER.md` / the F14 packet header that the live code still has a `<select>` until F13 lands — to pre-empt the reviewer's confusion.
- Commit the packet edits (explicit paths).

### Task 2 — Make the `implementation-plan-visual` skill GLOBAL
- Copy `C:\local-development\code\.claude\skills\implementation-plan-visual\` (the `SKILL.md` + `references/template.html` + `references/review_prompt.md`) to the user-global skills dir `C:\Users\connect\.claude\skills\implementation-plan-visual\`, so it's available in every project — not just this repo.
- Keep the global copy consistent with the Task 3 edit.

### Task 3 — Amend the skill's roast step: OFFER it, never auto-run (do this in BOTH copies)
The current skill section ("After the plan: adversarial review") says to *"always produce an
adversarial review prompt **and run it** through a fresh reviewer."* Change the behaviour:
- The roast must be **offered to the user, never auto-run by internal subagents.** Producing the `PLAN_REVIEW.md` prompt is fine; **running** it requires **asking the user first** — both *whether* to run it and *which method*.
- The user referenced *"the three methods I suggested earlier"* for running it. **Confirm with the user which three options to present** (this could not be unambiguously identified from the conversation). Likely candidates to confirm: (a) the user runs `PLAN_REVIEW.md` themselves in a separate/external LLM; (b) an internal fresh-subagent workflow; (c) skip/defer.
- Reason this task exists: the current agent **auto-ran** the roast as an internal workflow without asking — the user flagged that as wrong. (Per the user, the current agent deliberately did NOT make this skill edit; it is yours.)

### Task 4 — Push
- Push the 3 local commits (+ the now-committed Task 1/2/3 work) to `origin/core-features` once the remote is reachable. **Verify access first** (the user should confirm the repo exists / re-auth). Commit `docs/handoff/storyboard-ux/PLAN_REVIEW.md` (tracked); decide with the user whether to commit the `.claude/skills/` files (they are committable).

## Caveats carried from this session
- **Don't blind-apply reviewer findings** — verify each, classify, and confirm impact with the user before editing (the roast protocol). The headline P1 above is the live example of a confidently-wrong finding.
- LPML is installed: this is the continuation handover; `CURRENT_STATE.md` is the rolling truth.
