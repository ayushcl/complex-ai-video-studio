# LPML Session-Wrap Prompt (`LOCAL_ADDENDUM_PROMPT.md`)

Run this at the end of a working session in an installed LPML project to capture the session
durably and update the rolling state safely. It is the only sanctioned way to update
`_project-tracker/CURRENT_STATE.md`. Work through the stages in order and **do not write any file
until the confirmation gate in Stage 3 is passed.**

See `_project-tracker/TRACKER.md` (§State Management) for the governing rules; this prompt enacts them.

## Stage 0 — Packet-active gate (do this FIRST)

- Check whether `_project-tracker/PACKET_ACTIVE` exists.
- **If it exists: STOP.** Do not write `CURRENT_STATE.md`, `NEXT_HANDOVER.md`, or any tracker state.
  Tell the user a packet run is active and that durable capture is owned by the packet **finaliser**
  (see TRACKER.md §Packet Rules And Lifecycle). Only continue this prompt once packet mode is finalised
  and `PACKET_ACTIVE` has been removed.

## Stage 1 — Orient

1. Read `_project-tracker/TRACKER.md` and `_project-tracker/CURRENT_STATE.md` (including its
   `CONSTRAINTS & LANDMINES` section).
2. Read `_project-tracker/NEXT_HANDOVER.md` **only if this session is a direct continuation**. If you
   are not certain, ask: "Is this a direct continuation of the previous session?" Do not read the
   handover for an ordinary new task.
3. Get the current date and time to the minute **from the system clock** (do not ask the user, do not
   guess). Use filesystem-safe ISO: `YYYY-MM-DDTHHMM`.
4. Choose a short 2–4 word lowercase-hyphenated slug for this session.

## Stage 2 — Build the proposed wrap (write nothing yet)

Review the whole session and draft a proposed wrap with these buckets:

- **Carried-forward facts** — what is now true about the project and belongs in `CURRENT_STATE.md`.
- **Completed work** — what was finished this session.
- **Decisions made** — each with a one-line rationale.
- **Needs a human decision** — open questions or changes that should not be auto-applied.
- **Explored and rejected** — paths tried and abandoned, each with the reason (so a later session does
  not repeat them).
- **Files changed** — what was created/edited this session.
- **Risks and blockers** — anything fragile or blocking.
- **Next actions** — concrete next steps.
- **New `CONSTRAINTS & LANDMINES`** — any durable do-not-repeat knowledge to add to that section of
  `CURRENT_STATE.md`.

## Stage 3 — Diff, removal approval, and confirmation gate

1. Draft the new `CURRENT_STATE.md` by **combining** the existing state with this session's confirmed
   results (see Stage 4 combine rule). Keep the existing section structure: Project Purpose, Current
   Status, Completed Work, Next Actions, Open Decisions, Blockers, Key Files, `CONSTRAINTS & LANDMINES`.
2. Show the user a **real old-vs-new diff** of `CURRENT_STATE.md` (added / removed / changed lines).
   - In a git project: `git diff --no-index -- <old> <new>` (or diff the working copy).
   - Non-git fallback: show the previous content and the proposed content side by side and mark every
     line you are removing or weakening.
3. **Require explicit approval for every removal or weakening** of an existing state item, constraint,
   landmine, decision, blocker, or next action. Do not drop anything silently.
4. Present the proposed addendum contents (the Stage 2 buckets) alongside the diff.
5. **Stop and wait for the user to confirm or adjust.** Write nothing until they confirm.

## Stage 4 — Write the artefacts (only after confirmation)

Write each to its place under `_project-tracker/`:

1. **Addendum (immutable):** write
   `_project-tracker/addendums/ADDENDUM_<YYYY-MM-DDTHHMM>_<slug>.md`
   containing: header (timestamp, slug, one-paragraph summary) and the confirmed Stage 2 buckets
   (decisions with rationale, completed work, explored-and-rejected, files changed, items needing a
   human decision). Never edit an existing addendum (except to fix an immediate write failure).
2. **Archive the previous state:** move the current `CURRENT_STATE.md` to
   `_project-tracker/archive/CURRENT_STATE_<YYYY-MM-DDTHHMM>.md` (copy then overwrite if a move is not
   available). Never delete it.
3. **Regenerate `CURRENT_STATE.md` by combining (not blind overwrite):**
   - carry forward all non-conflicting existing information;
   - integrate this session's confirmed changes;
   - where two items genuinely conflict (the same element set to two different values), surface the
     conflict to the user; use the **latest timestamp only as a same-element tie-breaker**, never as a
     blanket "newest replaces everything";
   - apply only removals the user approved in Stage 3.
4. **Handover (optional):** overwrite `_project-tracker/NEXT_HANDOVER.md` **only if the user wants a
   continuation handover.** If so, write a concise continuation briefing (project identity, where this
   session stopped, key decisions, what not to repeat, likely next options, blockers/risks, files to
   read first). It initialises the next LLM; it must not command immediate execution. If the user does
   not want a handover, leave `NEXT_HANDOVER.md` unchanged and say so.

## Stage 5 — Report

Give a concise summary: the addendum path written, that `CURRENT_STATE.md` was regenerated (with a note
of any approved removals), whether `NEXT_HANDOVER.md` was refreshed, and any items still needing a human
decision. No file/upload manifest is needed — everything is already on disk.
