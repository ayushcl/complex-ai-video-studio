# SKILLS

Initial baseline skill index - replaced/filled by the installer as needed.

## Skill Source Model

The canonical source for each LPML skill is:

```text
_project-tracker/skills/<name>/SKILL.md
```

Native tool folders are derived copies:

```text
.agents/skills/<name>/SKILL.md
.claude/skills/<name>/SKILL.md
```

Edit the canonical tracker source first, then refresh the native derived copies. Native files should
be stamped as derived from canonical and should not be edited directly unless an intentional
divergence is recorded here.

## Skill Index

LPML ships with two default skills. They both plan safe parallel work but serve different roles —
see "When to use which" below so they are not used interchangeably.

| Skill | Canonical path | Codex-native path | Claude-native path | Manual-only | When to use |
|---|---|---|---|---|---|
| `parallel-agent-planning` | `_project-tracker/skills/parallel-agent-planning/SKILL.md` | `.agents/skills/parallel-agent-planning/SKILL.md` | `.claude/skills/parallel-agent-planning/SKILL.md` | yes | Running parallel work **inside an installed LPML project** with tracker-state safety: the `_project-tracker/PACKET_ACTIVE` gate, packet agents forbidden from tracker-state writes, finaliser-only state updates, capture-then-delete cleanup, and `PACKET_RUNS.log`. Output: a packet run folder under `_project-tracker/packets/`. |
| `parallel-task-handoff` | `_project-tracker/skills/parallel-task-handoff/SKILL.md` | `.agents/skills/parallel-task-handoff/SKILL.md` | `.claude/skills/parallel-task-handoff/SKILL.md` | yes | Turning **any** plan/task into a handoff package of self-contained prompts (RUN_ORDER + CONTEXT_BRIEF + one prompt per packet, with exact file ownership) that the **user runs across multiple agents/chats themselves**. Output: a handoff folder of prompts. |

### When to use which

- Use **`parallel-task-handoff`** when you want the prompts delivered to you to drive the agents
  yourself (broad fan-out, any project).
- Use **`parallel-agent-planning`** when the parallel work runs inside this LPML project and must
  obey the tracker's packet lifecycle and state-safety rules.
- They compose: `parallel-agent-planning` may use `parallel-task-handoff`'s method to author its
  packet prompts, then wrap them in the `PACKET_ACTIVE` lifecycle.

## Native-Skill Refresh Rule

Native skill refresh: edit canonical `_project-tracker/skills/<name>/SKILL.md` first; then
regenerate/update native copies; stamp natives "derived from canonical — do not edit directly; edit the
canonical source and refresh"; record any intentional divergence in `_project-tracker/SKILLS.md`.

## Divergence Log

This section is preserved and merged across LPML updates. Record intentional skill-source or native-copy divergence here.

- None recorded.
