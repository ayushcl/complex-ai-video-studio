# ADDENDUM 2026-06-16T1827 lpml-install

Timestamp: 2026-06-16T182719
Slug: lpml-install
Summary: First LPML install baseline for C:\local-development\code.

## Install Details

- LPML version: 0.2.0
- Governance classification: LIGHTLY_MANAGED
- Installer mode: first-install
- Archive folder: $archiveRel

## Files Installed

LPML root entrypoints, tracker files, canonical skills, native Codex skills, and native Claude skills were installed from local-project-management-lite/payload/ where no destination file existed.

## Files Merged

Existing .agents/ and .claude/ folders were preserved. Missing LPML skill files were added under their skills/ subfolders. Existing .claude/settings.local.json and .claude/launch.json were not modified.

## Files Archived

None. No existing project files were moved or archived.

## Files Skipped

- README.md - host project documentation, never touched by default.
- .env - host project local environment file.
- local-project-management-lite/ - staging folder remains separate.
- Existing source, script, test, run, media, and PDF files.

## Manual Review

None required for a destructive action. The git status command emitted a permission warning for C:\Users\connect\.config\git\ignore; it did not block installation.

## Baseline Project Status

The project is an Agency Swarm based VEO audio/video pipeline with a no-build operator UI, packet adapter, source scripts, test assets, and local .claude launch/settings files.

## Migrated Constraints

- Do not run ideo_generation_agency/proof_veo_call.py until ready for possible paid API usage and after confirming billing/model access. Source: README.md.
- The live Gemini smoke test should be run only after .env contains a valid GEMINI_API_KEY. Source: README.md.
- API keys are write-only through the operator UI and must not be displayed or returned. Source: ui/README.md.
- Live adapter execution requires both --run and spend_controls.allow_live_run: true. Source: ideo_generation_agency/run_from_packet.py.
