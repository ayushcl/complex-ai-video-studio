# CURRENT_STATE

## Project Purpose

This project is the VEO Audio Production Pipeline, an Agency Swarm based Maxiion/Kunisys video generation pipeline with an internal operator UI for packet-based video jobs.

## Current Status

LPML version 0.2.0 was installed on 2026-06-16T182719 as a first install. The project already had source code, scripts, an internal operator UI, local tool configuration folders, and the LPML staging folder. No prior _project-tracker installation was present.

## Completed Work

- Existing project baseline observed from README.md, ui/README.md, and ideo_generation_agency/run_from_packet.py.
- LPML tracker files, root entrypoints, and native skill copies were installed without replacing existing project files.
- Existing .agents/ and .claude/ folders were preserved and only missing LPML skill files were added below them.

## Next Actions

- Review the installed _project-tracker/ files and native skill copies.
- Keep local-project-management-lite/ until the install is confirmed, then remove it only after explicit user approval.
- Use _project-tracker/LOCAL_ADDENDUM_PROMPT.md for future durable state updates.

## Open Decisions

- Whether to remove the temporary local-project-management-lite/ staging folder after review.
- Whether to use LPML packet workflows for future parallel work in this repository.

## Blockers

None recorded by the installer.

## Key Files

- README.md - project overview and setup notes.
- ui/README.md - operator UI workflow, spend gates, runtime notes, and smoke tests.
- ui/server.py - local operator UI server entrypoint.
- ideo_generation_agency/run_from_packet.py - packet adapter with dry-run default and live-run gates.
- ideo_generation_agency/run_full_chain.py - full chain runner used by the packet adapter.
- _project-tracker/TRACKER.md - LPML operating manual.
- _project-tracker/CURRENT_STATE.md - rolling project state.

## CONSTRAINTS & LANDMINES

- Do not run ideo_generation_agency/proof_veo_call.py until ready for possible paid API usage and after confirming billing/model access. Source: README.md.
- The live Gemini smoke test should be run only after .env contains a valid GEMINI_API_KEY. Source: README.md.
- The operator UI stores API keys in .env and treats them as write-only through the UI; do not display or return key material. Source: ui/README.md.
- ideo_generation_agency/run_from_packet.py dry-runs by default; live execution requires both the --run CLI flag and spend_controls.allow_live_run: true in the packet. Source: ideo_generation_agency/run_from_packet.py.
- Install Python packages into the same Python interpreter used to start the operator UI, or generation may fail with missing package errors. Source: ui/README.md.
