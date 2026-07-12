# Plan review prompt (the "roast") — Storyboard-review UX (F9–F14)

Hand this to a FRESH reviewer LLM with access to this repository but NONE of the
conversation that produced the plan. Find what's wrong, grounded in the real code.

---

You are an adversarial reviewer. You have NO memory of the conversation that produced
the plan below. Rely only on this prompt, the files it names, and the live codebase.
Be skeptical: your value is finding real problems, not approving.

## What you are reviewing
- Plan: `C:\local-development\code\docs\plans\storyboard-review-ux-plan.html`
- Handoff package: `C:\local-development\code\docs\handoff\storyboard-ux\` (`RUN_ORDER.md`, `CONTEXT_BRIEF.md`, `09_…`–`14_…`)
- Project rules: `C:\local-development\code\AGENTS.md` and `C:\local-development\code\CLAUDE.md`
- Codebase root: `C:\local-development\code` (branch `core-features`)

## What the plan is for
Six UX features (F9–F14) on the Simple-mode storyboard-review screen, built one branch
per feature off `core-features`. The features all edit `ui/static/app.js` and
`ui/static/styles.css`, so the parallelism is **branch-level** with a sequenced merge
(F9–F13 are independent; **F14 depends on F9 (reel lock state) and F13 (the redesigned
scene selector)**). Hard constraints: changes are vanilla JS/CSS, additive and
presentational; they must NOT change the backend (`ui/simple_flow.py`), the free
dry-run, the storyboard render, or the confirm-token / spend-gate flow.

A prior review already fixed three things — **verify they are genuinely resolved and
consistent**, then look for anything else:
1. F14's "Full implementation detail" used to target a `<select>` that F13 removes; it
   should now drive F13's **pill control** (`#s-edit-scope` as a `data-scope` container
   with `.scene-pill` buttons + a `.scene-pill-glider`).
2. README/SKILL used to call `_project-tracker/` and `.claude/skills/` "git-ignored";
   they are NOT ignored — and as of 2026-06-27 they are **tracked** (committed `9a63878`), not untracked.
3. The cost-confirm dialog used to say "Placeholder rates"; it should now describe the
   defaults as published Gemini API rates, matching `ui/cost_estimator.py`.

## Verify against reality — do not just opine
- Open the plan, read each feature's steps AND its "Full implementation detail", and
  cross-check against the handoff packet for the same feature.
- Open the actual symbols the steps cite in `ui/static/app.js`, `ui/static/styles.css`,
  `ui/simple_flow.py` and confirm they exist as described (check the symbol, not just
  the line — line numbers drift).
- Run the suite: `python -m unittest discover -s ui/tests -v` (expected: all pass).
- Check factual claims with commands: `git status --ignored`, `git check-ignore -v`,
  and read the cited code/routes.

## Hunt these high-value failure modes first
1. **Cross-feature contract drift** — especially F14↔F13 (the pill selector contract),
   F11↔F12 (both edit `renderSimpleReview`), and F9↔F10 (both touch the cover-flow /
   `.cover-card` / `layoutCoverFlow`). Do the dependent features agree on names, ids
   (`#s-edit-scope`, `#s-cap`), and DOM shapes?
2. **Claims that aren't true** — the three fixes above, plus any "leave X untouched",
   "byte-identical", or "the engine already does Y" claim in the steps.
3. **Stale references** — symbol/line refs, or the concise steps vs the "full detail"
   vs the handoff packet disagreeing.
4. **Regressions** — any step that would break the free dry-run, the spend-gate /
   confirm-token flow, the silent-brand path, or reduced-motion handling.
5. **Feasibility** — e.g. the F12 hidden-`#s-cap` source-of-truth actually keeps
   `simpleGenerate`/`estimate` reads working; the F9 lock guard actually prevents the
   5s auto-resume.

## Output
Structured findings only. For each: an `id`, a `severity` (P1 blocks / P2 should-fix /
P3 minor), the exact `location` (file:line or plan section), the `claim`, `why` it's
wrong, the `evidence` you gathered, and a `suggested direction`. **Fix nothing — report
only.** Don't pad with non-issues; if something is genuinely fine, say so briefly; if
unsure, say so.
