---
name: parallel-agent-planning
description: Create safe packets for parallel LLM agents without letting packet agents update shared tracker state.
disable-model-invocation: true
---

Derived from canonical `_project-tracker/skills/parallel-agent-planning/SKILL.md` — do not edit directly; edit the canonical source and refresh.

# Parallel Agent Planning

Use this skill when you need to split a project task into safe packets for multiple LLM agents. Produce a launchable packet plan only after you have checked file ownership, shared state, and collision risk. If safe parallelism does not exist, give a sequential plan.

This skill complements harness-native parallel handoff tooling. Use native tooling when available for launching or coordinating agents, but keep the collision-safety rules and LPML packet lifecycle below as the operating contract.

## Inputs

Start from the user's goal and the current project rules. Inspect only the context needed to plan safely:

- read the goal and expected outcome;
- read relevant project instructions and current state;
- identify files, folders, commands, and external systems likely to be touched;
- identify any active LPML packet run, `_project-tracker/PACKET_ACTIVE` marker, or active host parallel/handoff mechanism;
- read `_project-tracker/HOST_PROTECTED_PATHS.txt` at packet-seed time if it exists;
- identify whether the work is in a git project or needs the non-git fallback checks.

Do not create packet folders unless the user is actually invoking a packet run. For planning-only requests, produce the packet plan as text.

## Planning Workflow

1. Understand the goal.
   - Restate the outcome in one or two sentences.
   - List the concrete deliverables.
   - Note anything that must remain unchanged.

2. Inspect rules and current state.
   - Read the relevant entrypoint instructions.
   - Read `_project-tracker/TRACKER.md` and `_project-tracker/CURRENT_STATE.md` when LPML is installed.
   - Read `_project-tracker/NEXT_HANDOVER.md` only when the user asked to continue or resume prior work.
   - Check for `_project-tracker/PACKET_ACTIVE`. If it exists, do not seed a second packet run unless the user explicitly directs a recovery or finalisation flow.
   - Check for an active host parallel/handoff mechanism before seeding. Only one of the host's own parallel/handoff mechanism or LPML packets may be active at once.
   - At packet-seed time, read `_project-tracker/HOST_PROTECTED_PATHS.txt` if it exists. Add every non-empty entry to each packet's forbidden-files list.

3. Identify work packets.
   - Split the goal into packets with independent deliverables.
   - Give each packet a stable ID, short title, objective, owned outputs, forbidden outputs, likely commands, and acceptance criteria.
   - Keep packets small enough that an agent can complete and verify them without needing shared tracker writes.

4. Identify shared files and collision risks.
   - List every file or folder each packet may read or edit.
   - Mark shared-read files separately from shared-write files.
   - Treat generated files, config files, lockfiles, entrypoints, native skill files, and tracker state as collision-sensitive.
   - Never parallelise agents that edit the same file.

5. Group packets into lanes.
   - Put packets that edit disjoint files into the same parallel lane.
   - Put packets that depend on another packet's output into a later lane.
   - Put broad integration, formatting, state updates, and final checks into a sequential finaliser lane.
   - If no safe lane can contain more than one packet, give a sequential plan.

6. Decide parallel versus sequential.
   - Parallelise only when file ownership is disjoint and dependencies are clear.
   - Sequence work when packets share an editable file, share an unresolved design decision, require the same generated artifact, or need one result before another can start.
   - Prefer fewer, safer packets over many fragile ones.

7. Write one isolated prompt per packet.
   - Include the packet objective, context to read, files it OWNS, files it must NOT touch, allowed commands, verification steps, and acceptance criteria.
   - Tell packet agents to report results into the run `results/` folder or the requested handoff location.
   - Tell packet agents not to update shared tracker state.

8. Define per-packet verification.
   - Give each packet a local verification command or manual check.
   - Require a short result note listing files changed, tests run, skipped checks, and risks.
   - Require acceptance criteria to be satisfied before the packet is marked complete.

9. Define barriers and finaliser.
   - Set a barrier after each lane.
   - The finaliser reads all packet results, checks for forbidden tracker-file changes, resolves integration issues, writes durable state, and performs cleanup.
   - Only the finaliser updates tracker state.

10. Produce operator launch instructions.
    - List the lane order.
    - List which packet prompts can run simultaneously.
    - List barriers, result paths, finaliser prompt path, and what to do if a packet fails.

## Collision-Safety Core Rules

These rules are mandatory:

- Never parallelise agents that edit the same file.
- Each packet must state exactly what it OWNS and must NOT touch.
- Packet agents must not run the addendum prompt.
- Packet agents must not write `CURRENT_STATE.md`, `NEXT_HANDOVER.md`, `TRACKER.md`, `SKILLS.md`, entrypoints, or native skill files.
- Packet agents must not write `_project-tracker/CURRENT_STATE.md`, `_project-tracker/NEXT_HANDOVER.md`, `_project-tracker/TRACKER.md`, `_project-tracker/SKILLS.md`, `AGENTS.md`, `agents.md`, `CLAUDE.md`, `.agents/`, or `.claude/`.
- At packet-seed time, read `_project-tracker/HOST_PROTECTED_PATHS.txt` if it exists and add every non-empty entry to each packet's forbidden-files list. Do not hardcode project names or host-path guesses; the host-protected list comes from that file.
- packet agents may never write host state files.
- Only one packet system may be active at once: the host's own parallel/handoff mechanism and LPML packets must not run concurrently. Check before seeding.
- Only the finaliser updates tracker state.
- Every packet needs acceptance criteria.
- If no safe parallelism exists, give a sequential plan.

## Packet Run Layout

When the user invokes an LPML packet run, create one run folder:

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

Also create the project-level active marker:

```text
_project-tracker/PACKET_ACTIVE
```

Use `PACKET_MODE` to name the run ID, objective, current lifecycle state, start time, finaliser, and operator notes.

Use `RUN_PLAN.md` for the objective, packet list, acceptance criteria, lane order, barriers, and fallback sequential plan.

Use `LANE_MAP.md` for the parallel lanes, packet IDs, dependencies, and launch order.

Use `SHARED_FILES.md` for all shared-read files, all shared-write risks, forbidden tracker and entrypoint paths, host-protected entries from `_project-tracker/HOST_PROTECTED_PATHS.txt`, and the pre-run forbidden-file snapshot or check plan.

Use one `packet-##_prompt.md` per packet. Each prompt must be isolated enough to give to a separate agent.

Use `finaliser_prompt.md` for the finaliser instructions, including result collection, forbidden-file checks, durable addendum writing, `PACKET_RUNS.log`, marker removal, and run-folder cleanup.

Use `results/` for packet result notes, test output summaries, screenshots or artifacts when relevant, and finaliser notes.

## Packet Lifecycle

Use this lifecycle:

```text
IDLE
SEED
RUN
FINALISING
FINALISED
```

- `IDLE`: no active packet run exists.
- `SEED`: create the run folder, packet prompts, finaliser prompt, and `_project-tracker/PACKET_ACTIVE`.
- `RUN`: packet agents work only inside their owned files and result notes.
- `FINALISING`: the finaliser reads results, checks forbidden paths, integrates allowed outputs, writes durable state, and prepares cleanup.
- `FINALISED`: durable addendum and packet log are written, `PACKET_ACTIVE` is removed, and the run folder is deleted or archived after confirmation.

During packet mode:

- packet agents must not update tracker state;
- packet agents must write only to assigned outputs;
- `_project-tracker/PACKET_ACTIVE` must exist while packet work is active;
- `LOCAL_ADDENDUM_PROMPT.md` must refuse state writes while `PACKET_ACTIVE` exists.

Finalisation must:

1. read packet results;
2. check for forbidden tracker-file changes;
3. capture durable summary in an addendum;
4. append one line to `_project-tracker/addendums/PACKET_RUNS.log`;
5. remove `_project-tracker/PACKET_ACTIVE`;
6. delete or archive the packet run folder after confirmation.

## Required Checks And Formats

Preferred forbidden tracker-file change check in git projects:

```text
git status --short
git diff -- _project-tracker/ AGENTS.md agents.md CLAUDE.md .agents/ .claude/
```

The finaliser must fail loudly if packet agents modified forbidden tracker or entrypoint files.

Non-git fallback:

- compare file modification times captured before packet run;
- compare file sizes and checksums if available;
- inspect the forbidden paths manually;
- ask the user for confirmation before finalising.

Append one packet-log line in this exact format:

```text
<timestamp> | <run-id> | <objective> | <final addendum path> | <result kept/deleted/archived> | <notes>
```

Native skill refresh:

- edit canonical `_project-tracker/skills/parallel-agent-planning/SKILL.md` first;
- regenerate or intentionally update native derived files after;
- stamp native files with a note that they are derived from the canonical source;
- record intentional divergence in `_project-tracker/SKILLS.md`.

## Packet Prompt Template

Use this structure for each packet prompt:

```text
# Packet <id>: <title>

You are running one isolated LPML packet.

Objective:
<specific objective>

Read first:
- <required context files>

OWNED files and outputs:
- <paths this packet may edit>

DO NOT TOUCH:
- _project-tracker/CURRENT_STATE.md
- _project-tracker/NEXT_HANDOVER.md
- _project-tracker/TRACKER.md
- _project-tracker/SKILLS.md
- _project-tracker/LOCAL_ADDENDUM_PROMPT.md
- _project-tracker/addendums/
- _project-tracker/packets/<run-id>/ except your assigned result note
- AGENTS.md
- agents.md
- CLAUDE.md
- .agents/
- .claude/
- <host-protected entries from _project-tracker/HOST_PROTECTED_PATHS.txt, if present>
- <packet-specific forbidden files>

Rules:
- Do not run the addendum prompt.
- Do not update tracker state.
- Edit only the owned files.
- Stop and report if you need a forbidden file changed.

Acceptance criteria:
- <criterion>

Verification:
- <command or manual check>

Result note:
Write <results/path>. Include files changed, verification run, skipped checks, risks, and whether acceptance criteria passed.
```

## Finaliser Prompt Requirements

The finaliser prompt must tell the finaliser to:

- verify every packet result exists;
- review files changed by each packet;
- fail loudly if any packet changed forbidden tracker, entrypoint, or native skill files;
- run the forbidden tracker-file check;
- integrate only allowed outputs;
- run final verification;
- write a timestamped addendum under `_project-tracker/addendums/`;
- append one `PACKET_RUNS.log` line;
- remove `_project-tracker/PACKET_ACTIVE`;
- ask whether to delete or archive the run folder;
- delete or archive the run folder only after confirmation.

## Output Shape

Return:

- objective summary;
- safe parallelism decision;
- packet table with ID, title, lane, OWNED files, MUST NOT touch files, verification, and acceptance criteria;
- lane map;
- shared files and collision risks;
- packet prompts or paths to packet prompts;
- finaliser prompt or path to the finaliser prompt;
- operator launch instructions;
- fallback sequential plan when needed.
