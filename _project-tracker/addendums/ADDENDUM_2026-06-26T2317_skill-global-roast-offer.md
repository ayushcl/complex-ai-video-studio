# ADDENDUM 2026-06-26T2317 — skill-global-roast-offer

**Timestamp:** 2026-06-26T2317
**Slug:** skill-global-roast-offer

## Summary
Carried out the user-authorized `NEXT_HANDOVER` task list: applied the roast's confirmed minor wording fixes to the F9-F14 storyboard-ux handoff packets (verified against the plan card + code, not blind-applied; the headline "P1" was confirmed a FALSE alarm and rejected); made the `implementation-plan-visual` skill a user-global skill and amended its adversarial-review step to OFFER the roast (never auto-run), with three run-methods; and attempted to push. Push remains BLOCKED - github.com auth resolves to account `oe-mattr`, which cannot access the repo. Per the user, the `implementation-plan-visual` skill is global-only and was NOT committed to the repo.

## Decisions made (with rationale)
- Rejected the roast's headline P1 ("F13 pill control doesn't exist in live code"). Rationale: F9-F14 are unbuilt; F14 is wave-2, gated on F9+F13 merging, so the live code legitimately still has the `<select id="s-edit-scope">`. Verified against the plan card and ui/static/app.js:1375.
- Added a one-line "expected pre-merge state" reminder to the F14 packet header and RUN_ORDER.md (user delegated this call). Rationale: cheaply pre-empts exactly the reviewer confusion that produced the false-alarm P1.
- Changed the skill's roast step from "always run" to "offer, never auto-run", with three methods: localised (internal agent), non-localised (generated prompt for a separate agent), skip. Rationale: the prior agent auto-ran the roast without asking; the user flagged that as wrong.
- Made `implementation-plan-visual` GLOBAL only and NOT committed (reverted the earlier repo commit). Rationale: explicit user instruction. The other two `.claude/skills/` copies (LPML-derived) were left untracked, not committed.
- Switched the push-auth approach to re-authenticating gh (not clearing GCM). Rationale: discovered gh - not GCM - is the github.com credential helper.

## Completed work
- F9-F14 handoff packet fixes (12_scene-slider.md, 14_click-to-select.md, RUN_ORDER.md) - commit `d004526`.
- Committed PLAN_REVIEW.md - commit `b5bb757`.
- Copied the skill to `C:\Users\connect\.claude\skills\implementation-plan-visual\` (byte-identical, verified) and amended its roast step in that global copy.
- Reverted the repo-side skill commit; removed the repo working-dir copy (global copy intact).

## Explored and rejected
- Clearing the Git Credential Manager github.com credential to force a fresh login - had NO effect, because gh (`credential.https://github.com.helper`) is the github.com credential provider, not GCM. The fix is `gh auth login` with an account that has repo access.

## Files changed / created this session
- Edited (committed): docs/handoff/storyboard-ux/12_scene-slider.md, 14_click-to-select.md, RUN_ORDER.md.
- Committed new: docs/handoff/storyboard-ux/PLAN_REVIEW.md.
- Global (uncommitted, outside repo): C:\Users\connect\.claude\skills\implementation-plan-visual\ (SKILL.md + references/template.html + references/review_prompt.md).
- Removed from repo working tree: .claude/skills/implementation-plan-visual/ (now global-only).
- Tracker: CURRENT_STATE.md regenerated (old archived to _project-tracker/archive/CURRENT_STATE_2026-06-26T2317.md); this addendum added.

## Needs a human decision
- Restore GitHub push access: `gh auth login` with an account that can access cloudtechuk/VEO-AUDIO-PRODUCTION-PIPELINE, then retry the push (5 commits queued).
- Whether to commit the other untracked governance/skill files (CLAUDE.md, AGENTS.md, _project-tracker/, .agents/, LPML-derived .claude/skills/ copies).
- Whether to remove the local-project-management-lite/ staging folder.

## Approved removals from CURRENT_STATE.md
- Verbose install-context sentence (preserved in ADDENDUM_2026-06-16T1827_lpml-install.md).
- Stale "Review the installed _project-tracker/ files" next action (done).
- "Keep local-project-management-lite/..." next action - relocated into Open Decisions (not lost).
