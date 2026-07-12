# CURRENT_STATE

## Project Purpose

This project is the VEO Audio Production Pipeline, an Agency Swarm based Maxiion/Kunisys video generation pipeline with an internal operator UI for packet-based video jobs.

The active production target is a 5-scene, 2-presenter, 9:16 vox-pop testimonial (the "Emerald" vox-pop); the feature roadmap (F1-F14) drives toward it. Feature work lands on the `core-features` integration branch.

## Current Status

LPML version 0.2.0 was installed on 2026-06-16T182719 (first install) and updated the same day (2026-06-16T2225).

Active development is on the `core-features` branch (the integration branch, built on the other developer's presenter-reference work). Two interactive HTML implementation plans and a parallel-task handoff package have been produced for the feature roadmap, plus a reusable plan-generating skill:

- `docs/plans/feature-implementation-plan.html` - the F1-F8 generation-pipeline plan.
- `docs/plans/storyboard-review-ux-plan.html` - the F9-F14 storyboard-review UX plan (authoritative "full implementation detail").
- `docs/handoff/storyboard-ux/` - one self-contained prompt per F9-F14 feature (`RUN_ORDER.md`, `CONTEXT_BRIEF.md`, `09_...`-`14_...`) plus `PLAN_REVIEW.md` (the adversarial "roast" prompt for the plan).
- The `implementation-plan-visual` skill (which generates those HTML plans) now lives as a USER-GLOBAL skill at `C:\Users\connect\.claude\skills\implementation-plan-visual\` and is deliberately NOT committed to the repo.

F9-F14 are still UNBUILT planned features; the live operator UI still has the pre-F13 `<select id="s-edit-scope">`. The operator UI is stdlib (`python ui/server.py`, port 8765); the test suite (`python -m unittest discover -s ui/tests -v`) was last reported at 227 green.

Local `core-features` is 5 commits ahead of `origin/core-features` (at `7d54e72`) and UNPUSHED - the GitHub remote is currently inaccessible to the authenticated account (see Blockers).

## Completed Work

- Existing project baseline observed from README.md, ui/README.md, and ideo_generation_agency/run_from_packet.py.
- LPML tracker files, root entrypoints, and native skill copies were installed without replacing existing project files; existing .agents/ and .claude/ folders were preserved.
- Shipped a presenter-reference cost-honesty fix (`ui/cost_estimator.py`, `ui/static/app.js`, tests) - commit `5e354f1`.
- Built the F1-F8 and F9-F14 interactive HTML plans under `docs/plans/`.
- Built the `implementation-plan-visual` skill (research-via-workflow then assemble from a self-contained HTML template; with an adversarial "roast" review step).
- Built the F9-F14 parallel-task handoff package under `docs/handoff/storyboard-ux/`.
- Fixed 3 external-review findings - commit `2509987`.
- Session 2026-06-26:
  - Applied the roast's confirmed minor fixes to the F9-F14 handoff packets ONLY (plan HTML + code untouched): de-hedged F14's pill references, made its acceptance assertions explicit, strengthened F12's hidden-`#s-cap` note, and added an "expected pre-merge state" reminder - commit `d004526`. The roast's headline P1 was verified a FALSE alarm and NOT acted on (F14 is wave-2, gated on F9+F13, so live code legitimately still has the `<select>`).
  - Committed the F9-F14 `PLAN_REVIEW.md` - commit `b5bb757`.
  - Made `implementation-plan-visual` a user-global skill (copied to `C:\Users\connect\.claude\skills\`, verified byte-identical) and amended its roast step so the adversarial review is OFFERED, never auto-run (three methods: localised internal agent / non-localised generated prompt / skip). Applied to the global copy only; deliberately NOT committed to the repo.

## Next Actions

- Push the 5 local `core-features` commits to `origin/core-features` once gh is re-authenticated with an account that can access the repo (see Blockers). Explicit-path commits only.
- Decide whether to commit the other untracked governance/skill files (`CLAUDE.md`, `AGENTS.md`, `_project-tracker/`, `.agents/`, and the LPML-derived `.claude/skills/` copies) - they are untracked-but-not-ignored, hence committable.
- Continue the F9-F14 build per `docs/handoff/storyboard-ux/RUN_ORDER.md` (Wave 1: F9-F13 in parallel; Wave 2: F14 after F9+F13 merge).
- Use `_project-tracker/LOCAL_ADDENDUM_PROMPT.md` for future durable state updates.

## Open Decisions

- Whether to remove the temporary `local-project-management-lite/` staging folder after review (carry-over; remove only after explicit user approval).
- Whether to use LPML packet workflows for future parallel work in this repository.
- Whether to commit the untracked governance/skill files listed under Next Actions.

## Blockers

- GitHub push blocked. `origin` is `https://github.com/cloudtechuk/VEO-AUDIO-PRODUCTION-PIPELINE`. `git push` uses `gh` (GitHub CLI) as the github.com credential helper, and gh is logged in as account `oe-mattr`, which cannot access the repo ("Repository not found"). Switching accounts requires `gh auth login` with an account that has access (NOT clearing the GCM credential - GCM is not consulted for github.com here). 5 commits are queued locally, ready to push once auth is fixed.

## Key Files

- README.md - project overview and setup notes.
- ui/README.md - operator UI workflow, spend gates, runtime notes, and smoke tests.
- ui/server.py - local operator UI server entrypoint (stdlib; port 8765).
- ui/static/app.js - Simple-mode UI logic (storyboard reel, edit panel, spend-cap, cost confirm).
- ui/cost_estimator.py - presenter-reference cost honesty.
- ui/simple_flow.py - Simple-mode backend (edit_scenes, _normalize_max_scenes).
- ideo_generation_agency/run_from_packet.py - packet adapter with dry-run default and live-run gates.
- ideo_generation_agency/run_full_chain.py - full chain runner used by the packet adapter.
- docs/plans/feature-implementation-plan.html - F1-F8 plan.
- docs/plans/storyboard-review-ux-plan.html - F9-F14 plan (authoritative full implementation detail).
- docs/handoff/storyboard-ux/ - F9-F14 parallel-task handoff package + PLAN_REVIEW.md.
- _project-tracker/TRACKER.md - LPML operating manual.
- _project-tracker/CURRENT_STATE.md - rolling project state.

## CONSTRAINTS & LANDMINES

- Do not run ideo_generation_agency/proof_veo_call.py until ready for possible paid API usage and after confirming billing/model access. Source: README.md.
- The live Gemini smoke test should be run only after .env contains a valid GEMINI_API_KEY. Source: README.md.
- The operator UI stores API keys in .env and treats them as write-only through the UI; do not display or return key material. Source: ui/README.md.
- ideo_generation_agency/run_from_packet.py dry-runs by default; live execution requires both the --run CLI flag and spend_controls.allow_live_run: true in the packet. Source: ideo_generation_agency/run_from_packet.py.
- Install Python packages into the same Python interpreter used to start the operator UI, or generation may fail with missing package errors. Source: ui/README.md.
- This machine has no Node / pip packages / ffmpeg installed, and `preview_screenshot` times out - use `preview_eval` / `preview_snapshot` for UI QA. Source: project memory + UI session notes.
- `git push` to github.com uses `gh` as the credential helper (config `credential.https://github.com.helper`), NOT Git Credential Manager. To switch the pushing account, re-auth gh (`gh auth login`); clearing the GCM credential has no effect on github.com. Source: this session.
- Commit by EXPLICIT path only (never `git add -A`). `.claude/skills/` (LPML-derived native copies), `.agents/`, `_project-tracker/`, `AGENTS.md`, and `CLAUDE.md` are untracked-but-not-ignored - do not sweep them into commits unintentionally. Source: handoff packets + this session.
- The `implementation-plan-visual` skill is GLOBAL only (`C:\Users\connect\.claude\skills\`), deliberately not committed to this repo. Source: this session (user instruction).
- Do not blind-apply reviewer ("roast") findings - verify each against the code, classify, and confirm impact with the user before editing. Source: implementation-plan-visual skill protocol.
