# Plans

Self-contained, interactive HTML implementation plans for this project.

Each plan is a single **dependency-free** `.html` file: open it directly in any
browser (it works offline), or use its built-in **Save / print as PDF** button.
Click a feature in the key to highlight exactly where it lands across the plan.

Plans are generated with the `implementation-plan-visual` skill (in
`.claude/skills/`), which turns a short feature outline into this format —
a colour-coded overview, a dependency / parallelization graph with build waves,
per-feature cards (concise steps plus an expandable, code-grounded
"full implementation detail"), and, when relevant, an input-format field-mapping
table.

## Contents

- `feature-implementation-plan.html` — the `core-features` feature pack (F1–F8):
  vertical 9:16, Simple-mode presenter jobs, reference likeness, identity blocks,
  negative-prompt library, KUNISYS storyboard-template importer, multi-voice, and
  a post-production end-card stage.

> Note: plans live here under `docs/` (a tracked folder) so they ship with the
> repo and reviewers get them on `git pull`. The LPML `_project-tracker/` folder
> is local scaffolding that is simply **untracked** (it is *not* git-ignored — it
> could be committed); `docs/` is just the clearer home for shareable plans.
