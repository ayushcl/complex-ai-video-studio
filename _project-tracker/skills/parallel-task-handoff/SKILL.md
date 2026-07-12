---
name: parallel-task-handoff
description: >-
  Turn a plan or task into a HANDOFF PACKAGE of self-contained prompts that
  multiple LLM agents — each with the same project/repo access but NO shared
  conversation context — can run in parallel. Use this whenever the user wants to
  fan work out across several agents or chats, asks to "break this into prompts I
  can run in parallel", wants parallel agents/subagents to implement a plan, or
  says to hand off / delegate / split up / parallelise a task across models —
  instead of implementing it inline yourself. Produces, in a handoff folder: a
  run-order guide, one self-contained prompt per work packet (with exact file
  ownership so parallel agents never collide), and any context/reference files the
  agents need because they cannot see this conversation. Prefer this whenever a
  task is large enough to split and the user wants to drive the agents themselves
  rather than have you do the work directly.
---

# Parallel Task Handoff

Convert a plan into prompts that independent agents can run in parallel, safely.
The hard part isn't splitting the work — it's that **each agent starts blank**: it
has the project files and your prompt, and nothing else. No memory of this
conversation, none of the decisions made in chat. So the whole job is making each
prompt *stand on its own*, and making the parallel work *not collide*.

## When to use this vs `parallel-agent-planning`

LPML ships two default parallel skills; keep them distinct:

- **`parallel-task-handoff`** (this skill) — turn ANY plan/task into a **handoff package** of
  self-contained prompts (a RUN_ORDER guide, a CONTEXT_BRIEF, and one prompt per packet, with exact
  file ownership) that **the user runs across multiple agents or chats themselves**. Use it for broad
  fan-out where the user drives the agents and wants the prompts delivered to them.
- **`parallel-agent-planning`** — the tracker's **in-system** packet lifecycle. Use it when running
  parallel work INSIDE an installed LPML project with tracker-state safety: the `_project-tracker/PACKET_ACTIVE`
  gate, packet agents forbidden from writing tracker state, finaliser-only state updates,
  capture-then-delete cleanup, and `PACKET_RUNS.log`.
- **They compose:** `parallel-agent-planning` may use this skill's method to author its packet prompts,
  then wrap them in the tracker's `PACKET_ACTIVE` lifecycle.

## The two failure modes this prevents

1. **Lost context.** An agent can't act on a decision it never saw. Anything that
   lives only in the conversation — which approach you chose, what a prior run
   found, why a value is what it is — must be written into the prompt or into a
   project file the prompt points at, or the agent will guess (and guessing is how
   the receipts lane once silently read filenames instead of documents).
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
  merge them into one packet/lane, or sequence them (one after the other).
- Shared *data/config* files the program writes at runtime get a single owner for
  edits; everyone else only reads.
Record this as a table the user can scan: packet → owns / must-not-touch.

### 3. Map dependencies → run order
Some packets must finish before others start (B consumes A's output). Produce the
launch sequence: which packets run **together (parallel)** and which are **gated**
behind earlier ones. Be honest about where the parallelism actually is — a chain
of phases A→B→C is a *run order*, not parallelism; the real fan-out is usually
*within* a phase (process N independent items at once).

### 4. Externalize the context (agents are blank)
Write a `CONTEXT_BRIEF.md` into the handoff folder with the chat-only knowledge the
agents need: current state, decisions made, what prior runs found, and pointers to
the authoritative files (the manual, the plan, the data). If a packet needs data
that won't fit in a prompt (a list, a mapping, prior results), write it to a file
and point the prompt at it. **Assume the agent reads only what you explicitly name.**

### 5. Write each packet's prompt (self-contained)
Use `references/prompt_template.md`. Every prompt has: a bootstrap (read the
project's manual + CONTEXT_BRIEF first), the scope, its **exact file ownership** and
the files it must NOT touch, the steps, objective acceptance criteria, and commit
discipline. State plainly: *"You have no memory of any prior conversation; rely
only on this prompt and the files it names."*

### 6. Write the RUN_ORDER guide
A short `RUN_ORDER.md`: the launch sequence (parallel vs gated), how to confirm each
packet succeeded, and what to do if one fails (usually: re-run just that packet; the
next phase's precondition check should catch a gap).

## Output

A handoff folder (default `<project>/_system/handoff/`, or wherever the user
prefers — ask if unsure) containing:
```
RUN_ORDER.md          # launch sequence + per-packet verification + failure handling
CONTEXT_BRIEF.md      # the chat-only context every blank agent needs
01_<packet>.md        # self-contained prompt
02_<packet>.md
...                   # plus any data/reference files the prompts point at
```

Inside an installed LPML project, the natural home for a tracker-governed run is
`_project-tracker/packets/<timestamp>_<slug>/` — in that case hand the packets to
`parallel-agent-planning` so they run under the `PACKET_ACTIVE` lifecycle and only the finaliser
updates tracker state.

## Hazards & rules (carry into every handoff)

- **Same file ⇒ same lane.** Never let parallel agents edit one file.
- **Git:** each agent commits only its own files with explicit paths (never
  `git add -A`); if the index is locked, wait and retry — never delete the lock.
- **Shared state files / servers / ports:** name who may write them. If an agent
  restarts a server or regenerates a derived file, note others may see churn —
  derived files are regenerable (not a correctness risk); primary records are.
- **Verify per packet.** Each agent runs the project's tests/verifier before
  reporting done, so a bad packet is caught locally, not at merge.
- **Model-agnostic prompts** when agents run on different models — say "open and
  view the file" rather than naming a specific tool.

## Reference
- `references/prompt_template.md` — the self-contained packet-prompt skeleton.
