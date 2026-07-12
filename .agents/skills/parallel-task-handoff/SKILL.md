---
name: parallel-task-handoff
description: >-
  Turn a plan or task into a HANDOFF PACKAGE of self-contained prompts that
  multiple LLM agents — each with the same project/repo access but NO shared
  conversation context — can run in parallel. Use when the user wants to fan work
  out across several agents/chats, break a plan into prompts to run in parallel,
  or delegate/split/parallelise a task — instead of implementing it inline.
---

Derived from `_project-tracker/skills/parallel-task-handoff/SKILL.md` — do not edit directly; edit the canonical source and refresh.

# Parallel Task Handoff

Convert a plan into prompts that independent agents can run in parallel, safely.
The hard part isn't splitting the work — it's that **each agent starts blank**: it
has the project files and your prompt, and nothing else. No memory of this
conversation, none of the decisions made in chat. So the whole job is making each
prompt *stand on its own*, and making the parallel work *not collide*.

## When to use this vs `parallel-agent-planning`

- **`parallel-task-handoff`** (this skill) — turn ANY plan/task into a handoff package of
  self-contained prompts (RUN_ORDER + CONTEXT_BRIEF + one prompt per packet, with exact file
  ownership) that the user runs across multiple agents/chats themselves.
- **`parallel-agent-planning`** — the tracker's in-system packet lifecycle (`_project-tracker/PACKET_ACTIVE`
  gate, packet agents forbidden from tracker-state writes, finaliser-only updates, capture-then-delete,
  `PACKET_RUNS.log`). Use it for parallel work inside an installed LPML project.
- They compose: `parallel-agent-planning` may use this skill's method to author its packet prompts,
  then wrap them in the tracker's `PACKET_ACTIVE` lifecycle.

## The two failure modes this prevents

1. **Lost context.** An agent can't act on a decision it never saw. Anything that
   lives only in the conversation — which approach you chose, what a prior run
   found, why a value is what it is — must be written into the prompt or into a
   project file the prompt points at, or the agent will guess.
2. **Collisions.** Two agents editing the same file in parallel clobber each
   other; two committing to the same repo race on the git index lock. The fixes
   are disjoint **file ownership** and an explicit **run order**.

## Method

### 1. Break the plan into work packets
Each packet is a coherent unit one agent can own end to end. Prefer packets that
touch a *disjoint* set of files.

### 2. Build the file-ownership matrix (the safety core)
List, per packet, every file it will create or edit, then check for overlap:
- **No two parallel packets may edit the same file.** If two need the same file,
  merge them into one packet/lane, or sequence them.
- Shared *data/config* files written at runtime get a single owner for edits;
  everyone else only reads.
Record this as a table the user can scan: packet → owns / must-not-touch.

### 3. Map dependencies → run order
Some packets must finish before others start (B consumes A's output). Produce the
launch sequence: which packets run **together (parallel)** and which are **gated**
behind earlier ones. Be honest about where the parallelism actually is — a chain
of phases A→B→C is a *run order*, not parallelism; the real fan-out is usually
*within* a phase.

### 4. Externalize the context (agents are blank)
Write a `CONTEXT_BRIEF.md` with the chat-only knowledge agents need: current state,
decisions made, what prior runs found, and pointers to the authoritative files. If
a packet needs data that won't fit in a prompt, write it to a file and point the
prompt at it. **Assume the agent reads only what you explicitly name.**

### 5. Write each packet's prompt (self-contained)
Use `references/prompt_template.md`. Every prompt has: a bootstrap (read the
project's manual + CONTEXT_BRIEF first), the scope, its **exact file ownership** and
the files it must NOT touch, the steps, objective acceptance criteria, and commit
discipline. State plainly: *"You have no memory of any prior conversation; rely
only on this prompt and the files it names."*

### 6. Write the RUN_ORDER guide
A short `RUN_ORDER.md`: the launch sequence (parallel vs gated), how to confirm each
packet succeeded, and what to do if one fails (re-run just that packet).

## Hazards & rules (carry into every handoff)

- **Same file ⇒ same lane.** Never let parallel agents edit one file.
- **Git:** each agent commits only its own files with explicit paths (never
  `git add -A`); if the index is locked, wait and retry — never delete the lock.
- **Shared state files / servers / ports:** name who may write them. Derived files
  are regenerable (not a correctness risk); primary records are.
- **Verify per packet.** Each agent runs the project's tests/verifier before
  reporting done, so a bad packet is caught locally, not at merge.
- **Model-agnostic prompts** when agents run on different models — say "open and
  view the file" rather than naming a specific tool.

## Reference
- `references/prompt_template.md` — the self-contained packet-prompt skeleton.
