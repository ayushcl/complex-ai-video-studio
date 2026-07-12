# LPML Tracker Manual

This is the stable operating manual for Local Project Management Lite (LPML) after it is installed in a project.

Use it as the authority for how `_project-tracker/` works. Project-specific facts live in `CURRENT_STATE.md`, not here.

## Session Start Behaviour

At the start of each normal session:

1. Read `_project-tracker/TRACKER.md`.
2. Read `_project-tracker/CURRENT_STATE.md`.
3. Read the `CONSTRAINTS & LANDMINES` section inside `CURRENT_STATE.md` before acting.
4. Read `_project-tracker/NEXT_HANDOVER.md` only when the user explicitly asks to continue, resume, or pick up from a prior handover.

Native tool entrypoints coexist with this manual:

- Codex reads `AGENTS.md`, `agents.md`, and `AGENTS.override.md` according to native precedence.
- Claude Code reads `CLAUDE.md`; the installed default may import `AGENTS.md`.
- Treat native entrypoints as project rules and this file as the LPML operating manual.
- If a native entrypoint and LPML procedure conflict, stop and ask the user before overriding project governance.

Do not read `NEXT_HANDOVER.md` for ordinary new tasks. It is continuation context only.

## State Management

`_project-tracker/CURRENT_STATE.md` is the rolling source of truth for current project context.

Use `_project-tracker/LOCAL_ADDENDUM_PROMPT.md` for state updates. A valid update requires:

1. Read the old `CURRENT_STATE.md`.
2. Draft the new `CURRENT_STATE.md`.
3. Show a real old-vs-new diff.
4. Ask for explicit approval before removing or weakening any existing state, constraint, landmine, decision, blocker, or next action.
5. Write the updated state only after approval.
6. Record the session in a timestamped addendum.

If `_project-tracker/PACKET_ACTIVE` exists, do not write tracker state through normal session flow. Packet finalisation owns durable capture while packet mode is active.

## Addendum Rules

Addendums are immutable timestamped records under `_project-tracker/addendums/`.

- Name each addendum `ADDENDUM_<YYYY-MM-DDTHHMM>_<slug>.md` (timestamp from the system clock; short lowercase-hyphenated slug). The same convention applies to install-baseline addendums and packet-finaliser addendums.
- Create an addendum for durable session summaries, install baselines, rollback actions, and packet finalisation summaries.
- Never edit an old addendum except to correct a technical write failure immediately after creation.
- Never delete addendums during cleanup.
- Do not use addendums as the primary working state; update `CURRENT_STATE.md` after a diff-approved state change.
- Keep `_project-tracker/addendums/PACKET_RUNS.log` as the packet-run index.

## Handover Rules

`_project-tracker/NEXT_HANDOVER.md` is continuation-only.

- Read it only when the user asks to continue, resume, or hand off an active thread.
- It initialises the next LLM with context; it never commands immediate execution.
- Refresh it only when the user wants a continuation handover.
- Overwrite old handover content by default after useful information is captured in `CURRENT_STATE.md` or an addendum.
- Do not treat stale handover text as more authoritative than `CURRENT_STATE.md`.

## Constraints & Landmines

Durable do-not-repeat knowledge lives in the `CONSTRAINTS & LANDMINES` section of `_project-tracker/CURRENT_STATE.md`.

- Always read that section before acting.
- Put persistent hazards, forbidden approaches, fragile assumptions, migration warnings, and user preferences there.
- Do not leave safety-critical knowledge only in `NEXT_HANDOVER.md`, packet prompts, or status logs.
- When installing or merging LPML into an existing project, migrate obvious safety-critical constraints from prior governance files into `CURRENT_STATE.md`.

## Skill Source And Native Skill Rules

LPML ships two default skills — `parallel-agent-planning` (the in-system packet lifecycle) and
`parallel-task-handoff` (turn any plan into a handoff package of prompts the user runs themselves).
See `_project-tracker/SKILLS.md` for the index and "when to use which". Both follow the rules below.

The canonical skill source is:

```text
_project-tracker/skills/<name>/SKILL.md
```

Native skill copies are derived files:

```text
.agents/skills/<name>/SKILL.md
.claude/skills/<name>/SKILL.md
```

Rules:

- Edit the canonical tracker skill first.
- Treat `.agents/` and `.claude/` skill files as generated or derived copies.
- Stamp native copies with "derived from canonical — do not edit directly".
- Record intentional divergence in `_project-tracker/SKILLS.md`.
- Keep manual-only packet skills manual-only in native tool configuration.

**Native skill refresh:** edit canonical `_project-tracker/skills/<name>/SKILL.md` first; then
regenerate/update native copies; stamp natives "derived from canonical — do not edit directly";
record any intentional divergence in `_project-tracker/SKILLS.md`.

## Packet Rules And Lifecycle

Packets are temporary parallel-agent run folders under:

```text
_project-tracker/packets/<timestamp>_<slug>/
```

A packet run folder may include:

```text
_project-tracker/packets/<timestamp>_<slug>/
├── PACKET_MODE
├── RUN_PLAN.md
├── LANE_MAP.md
├── SHARED_FILES.md
├── packet-01_prompt.md
├── packet-02_prompt.md
├── finaliser_prompt.md
└── results/
```

Packet lifecycle:

```text
IDLE
SEED
RUN
FINALISING
FINALISED
```

Lifecycle meanings:

- `IDLE`: no packet run is active; normal tracker state updates are allowed.
- `SEED`: the planning agent prepares packets, assigns outputs, and creates `_project-tracker/PACKET_ACTIVE`.
- `RUN`: packet agents work only on assigned outputs.
- `FINALISING`: the finaliser reads results, checks forbidden changes, and captures durable summary.
- `FINALISED`: durable capture is complete; `_project-tracker/PACKET_ACTIVE` is removed and the packet folder is deleted or archived after confirmation.

During packet mode:

- Packet agents must not update tracker state.
- Packet agents must not write `CURRENT_STATE.md`, `NEXT_HANDOVER.md`, `TRACKER.md`, `LOCAL_ADDENDUM_PROMPT.md`, `SKILLS.md`, addendums, native entrypoints, or native skill files.
- `_project-tracker/PACKET_ACTIVE` gates state writes.
- `LOCAL_ADDENDUM_PROMPT.md` must refuse state writes while `_project-tracker/PACKET_ACTIVE` exists.
- Packet agents write only to assigned outputs.

Finalisation steps:

1. Read packet results.
2. Run the forbidden tracker-file change check.
3. Capture durable summary in a timestamped addendum.
4. Append one line to `_project-tracker/addendums/PACKET_RUNS.log`.
5. Remove `_project-tracker/PACKET_ACTIVE`.
6. Delete or archive the packet run folder after confirmation.

## Cleanup Rules

Use capture-then-delete for temporary packet material: write durable summary and append the packet log before deleting or archiving the packet folder.

Permanent records:

```text
_project-tracker/CURRENT_STATE.md
_project-tracker/addendums/
_project-tracker/addendums/PACKET_RUNS.log
_project-tracker/archive/
_project-tracker/LPML_VERSION
```

Temporary or cleanup-eligible records:

```text
_project-tracker/packets/<run-id>/
_project-tracker/status/<session-log>.md
_project-tracker/NEXT_HANDOVER.md old content
local-project-management-lite/ staging folder after successful install
```

Cleanup rules:

- Never delete addendums during routine cleanup.
- Delete packet run folders only after durable capture, unless the user chooses to archive them.
- Overwrite old handover content by default after useful information is captured.
- Archive or delete status logs only after useful information is captured in an addendum or `CURRENT_STATE.md`.
- Do not delete native skill files during cleanup.
- Remove the `local-project-management-lite/` staging folder only after the user confirms the install looks correct.

## Archive Rules And Manifest

Archive before changing existing project-management files. Never delete existing project governance during installation, update, repair, rollback, or cleanup.

Write install archives under:

```text
_project-tracker/archive/pre-lite-install/<timestamp>/
```

Archive self-nesting guard:

- never archive `_project-tracker/archive/pre-lite-install/` into itself;
- never archive the staging folder `local-project-management-lite/` as part of installation;
- never re-run installation on an already-installed project without explicit update/repair mode.

`ARCHIVE_MANIFEST.md` format:

```text
Install timestamp:
LPML version:
Governance classification:
Installer mode:

Actions:
| Original path | Action | New/archive path | Reason | Notes |

Manual review items:
| Path | Reason | User decision |

Skipped items:
| Path | Reason |
```

## `PACKET_RUNS.log` Format

One line per packet run:

```text
<timestamp> | <run-id> | <objective> | <final addendum path> | <result kept/deleted/archived> | <notes>
```

## Forbidden Tracker-File Change Check

Forbidden tracker-file change check (git projects):

```text
git status --short
git diff -- _project-tracker/ AGENTS.md agents.md CLAUDE.md .agents/ .claude/
```
Finaliser must FAIL LOUDLY if packet agents modified forbidden tracker/entrypoint files.
Non-git fallback: compare pre-run mtimes/sizes/checksums of forbidden paths; inspect manually;
ask the user before finalising.

## Rollback And Uninstall Rules

Do not uninstall by deleting LPML files in place. Preserve rollback evidence.

**Rollback/uninstall:** read the relevant `ARCHIVE_MANIFEST.md` → show what would be restored →
confirm → restore archived backups → move current LPML files into a rollback archive (never
delete) → report conflicts.

Rollback and uninstall flow:

1. Locate the relevant `_project-tracker/archive/**/ARCHIVE_MANIFEST.md`.
2. Show the user what would be restored, moved, skipped, or left for manual review.
3. Ask for confirmation.
4. Restore archived entrypoint backups and management files.
5. Move current LPML files into a rollback archive rather than deleting them.
6. Report conflicts and unresolved manual review items.

## Already-Installed Guard Rules

If `_project-tracker/LPML_VERSION` exists, classify the project as `ALREADY_LPML`.

- Refuse reinstall unless the user explicitly asks for update or repair mode.
- Do not re-archive an already-installed LPML project as if it were unmanaged.
- Read the installed `LPML_VERSION`, `TRACKER.md`, `CURRENT_STATE.md`, and latest relevant archive manifest before proposing update or repair.
- In update or repair mode, show a diff-aware plan and ask for confirmation before file operations.
- Preserve existing addendums, archive records, `CURRENT_STATE.md`, and user-modified entrypoints.

## Operating Priority

When working in an installed LPML project:

1. Preserve project governance.
2. Read current state before acting.
3. Keep durable state in `CURRENT_STATE.md`.
4. Keep immutable history in `addendums/`.
5. Keep packet work temporary until finalised.
6. Ask before removing, weakening, or overwriting existing rules.

## Coexisting with another PM system

Use this section when installed LPML sits alongside a host project-management or governance system.
The host's own manual remains authoritative for normal work.

Before normal work:

1. Check `_project-tracker/PACKET_ACTIVE`.
2. If `_project-tracker/PACKET_ACTIVE` exists, follow these `TRACKER.md` packet rules and the active packet prompt.
3. If `_project-tracker/PACKET_ACTIVE` does not exist, continue with the host's own manual.

Coexistence rules:

- One packet system active at a time. Only one of [host's own parallel/handoff mechanism | LPML packets] may be active at once.
- Do not seed or run LPML packets while the host's own parallel/handoff mechanism is active.
- Do not start the host's own parallel/handoff mechanism while `_project-tracker/PACKET_ACTIVE` exists.
- Host-owned files are off-limits to packet agents.
- On governed projects, the installer writes host protected globs to `_project-tracker/HOST_PROTECTED_PATHS.txt`, one glob per line.
- Packet seed and finalisation read `_project-tracker/HOST_PROTECTED_PATHS.txt` and add every entry to each packet's forbidden-files list.
- If `_project-tracker/HOST_PROTECTED_PATHS.txt` is absent, no host protected paths are added; all normal tracker and packet forbidden-file rules still apply.
- The install plan shows `DO NOT TOUCH (forbidden to archive/move):` with the derived host-protected paths. If any archive or move set includes one, stop and re-confirm before continuing.
- In coexistent projects, host manuals and entrypoints are host-owned. LPML manages only its integration block delimited by `<!-- LPML:integration:start -->` and `<!-- LPML:integration:end -->`.

## Updating LPML

Use update or repair mode for an already-installed LPML project. The target version for this release is `0.2.0`.

Version compare:

- Versions are semver `MAJOR.MINOR.PATCH`; template `VERSION` and installed `_project-tracker/LPML_VERSION` each hold one bare version line.
- `installed == template` means up to date; repair only.
- `template > installed` means update.
- `template < installed` means warn only: installed LPML is newer than this template. Do nothing unless the user explicitly forces it.
- Missing, empty, legacy, or unparseable `_project-tracker/LPML_VERSION` means update mode: back up what exists, refresh system files, and generate missing state. Ask if genuinely ambiguous.

Update flow:

1. Build a diff-aware plan from `TEMPLATE_MANIFEST` class, not from `CHANGELOG.md`. System files refresh, state files preserve, host-owned files are never touched.
2. Back up current LPML system files to `_project-tracker/archive/pre-lite-update/<ts>/`.
3. Check `_project-tracker/.lpml-baseline.json` (`{ "version": "...", "files": { "<relpath>": "<sha256>" } }`) before overwriting any system file.
4. If a system file checksum matches its baseline, refresh it. If it differs from baseline, treat it as a conflict: back it up, show the diff, and ask whether to keep mine, take new, or merge.
5. Refresh system/reference files, add new system files, preserve state/accumulating files, re-derive native skills from canonical, and bump `_project-tracker/LPML_VERSION` to the template `VERSION`.
6. Write an update addendum and `_project-tracker/archive/pre-lite-update/<ts>/UPDATE_MANIFEST.md`.
7. Re-apply the host integration block idempotently: replace the region from `<!-- LPML:integration:start -->` through `<!-- LPML:integration:end -->` if present; otherwise append one marked block. Never edit host content outside those markers.

`UPDATE_MANIFEST.md` schema:

```text
LPML update — <from-version> → <to-version>
Timestamp:
Backup: _project-tracker/archive/pre-lite-update/<ts>/

| File | Class | Action | Backup path | Notes |
Action ∈ refreshed | preserved | added | conflict-asked:<resolution> | skipped
```

Repair:

- Repair triggers when `installed == template` and the user asks for repair, or when a `TEMPLATE_MANIFEST` system file is missing, empty, or checksum-broken against `_project-tracker/.lpml-baseline.json`.
- Present a plan of missing/broken system files, ask for one confirmation, restore only those files from template, and re-derive native skills from canonical.
- Never touch state during repair.
- Write a short repair note to `_project-tracker/addendums/`.

Rollback:

- Roll back updates against `_project-tracker/archive/pre-lite-update/<ts>/`.
- Read the matching `UPDATE_MANIFEST.md`, show what would be restored, skipped, or left for manual review, and ask for confirmation.
- Restore archived backups, preserve rollback evidence, and report conflicts. Never delete update archives during rollback.
