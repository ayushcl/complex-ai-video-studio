# Self-contained packet-prompt template

Fill every bracket. If a bracket would need knowledge from the current
conversation, that knowledge must instead be written into `CONTEXT_BRIEF.md` or a
data file the prompt names — the agent cannot see the conversation.

```
You are operating in <PROJECT ROOT>. You have NO memory of any prior conversation —
rely only on this prompt and the files it names. FIRST read <the project's operating
manual, e.g. agents.md> and <HANDOFF FOLDER>/CONTEXT_BRIEF.md, then <any state files
the manual requires before this kind of work>.

GUARDRAILS (from the manual): <the project's discipline rules — read-only inputs,
never overwrite outputs (version them), log moves, reconcile, rules deactivate
never delete, etc.>.

YOU OWN — only create/edit these files:
  <explicit file list / new files>
DO NOT TOUCH — other agents own these (editing them causes collisions):
  <explicit file list / globs>
READ FOR CONTEXT — do not edit:
  <files, folders, or data the packet must consult>

TASK: <the packet goal, concretely and completely — an agent with no other context
must be able to act on this alone>.

STEPS:
1. <...>
2. <...>

ACCEPTANCE — all must hold before you report done:
  <objective, checkable conditions; run the project's verifier/tests>.

COMMIT: commit ONLY your own files, by explicit path (never `git add -A`):
  <vcs> add <your files> ; then commit "<packet-id> <summary>".
  If the index is locked, wait a few seconds and retry — never delete the lock.

REPORT BACK: <what to summarise — files changed, results/metrics, anything you had
to defer or flag for the operator>.
```

## Checklist before you ship a prompt
- Could a blank agent execute this with only the named files? If not, add the
  missing context to CONTEXT_BRIEF.md or a data file.
- Does any file in "YOU OWN" appear in another parallel packet's "YOU OWN"? If so,
  re-partition or sequence them.
- Are the acceptance checks objective (a script/verifier can confirm them)?
- Is the commit scoped to this packet's files only?
