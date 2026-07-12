# Context brief — Storyboard-review UX (F9–F14)

You are one of several agents implementing a set of UI features. **You have no
memory of the conversation that produced this package.** Rely only on the files
named here (all paths are absolute).

## What the project is
The VEO Audio Production Pipeline. The operator UI lives in `C:\local-development\code\ui\`:
- `ui/static/app.js` — the operator UI logic (vanilla JS, no framework): the rotating storyboard reel (cover-flow), the Simple-mode review renderer, the edit-prompts panel.
- `ui/static/index.html`, `ui/static/styles.css` — markup and styling.
- `ui/server.py` — a stdlib HTTP server (run with `python ui/server.py`, port 8765).
- `ui/simple_flow.py` — the backend that authors jobs and runs the gated pipeline.

Read `C:\local-development\code\AGENTS.md` and `C:\local-development\code\CLAUDE.md` first — they are the project rules.

## What you are building
Six UX refinements to the **Simple-mode storyboard-review screen**, numbered F9–F14.
The authoritative plan, with a code-grounded **"Full implementation detail"** for each
feature, is:
`C:\local-development\code\docs\plans\storyboard-review-ux-plan.html`
Open it in a browser (or read the source) and find your feature's `FEAT-NN` card.

## Branch model (read this twice)
- The integration branch is **`core-features`**. It currently exists **locally**; the
  GitHub remote has been intermittently unreachable, so **branch off the local
  `core-features`**, and if `git push` is refused, commit locally and say so in your
  results file — the integrator will push.
- **One feature branch per feature** (e.g. `feature/reel-lock`).

## ⚠ The collision rule — this is the whole point
These six features are **NOT file-disjoint**. Every one of them edits
`ui/static/app.js`, and all of them edit `ui/static/styles.css`. Several touch the
**same functions** (e.g. F10 and F14 both edit `layoutCoverFlow`; F11 and F12 both edit
`renderSimpleReview`; F9 and F10 both touch the cover-flow card; F13 and F14 both touch
the edit-scope selector).

Therefore:
1. **Work in your own isolated checkout**, so you never share a working tree with
   another agent. Use a git worktree:
   `git worktree add ../wt-<feature> -b feature/<name> core-features`
   then work inside `../wt-<feature>`. (A separate clone is equally fine.)
2. **Stay inside your feature's scope.** Each packet lists the exact symbols/classes you
   may edit. Do **not** reformat, refactor, or "tidy" code another feature owns — that is
   what turns a clean merge into a painful one.
3. Conflicts are resolved **at merge time**, in the order in `RUN_ORDER.md` — not by
   editing each other's branches.

## Dependencies
- **F14 depends on F9 and F13** — start F14 only after both are merged into `core-features`.
- F9, F10, F11, F12, F13 are otherwise independent and can be developed in parallel (each on its own branch).

## Hard constraints (every feature)
- Changes are **vanilla JS/CSS, additive, presentational**. Do **not** change the backend
  (`ui/simple_flow.py`, `ui/server.py`), the free dry-run, the storyboard render, or the
  **confirm-token / spend-gate** flow. The Simple-mode silent path must keep working.
- Honour `@media (prefers-reduced-motion: reduce)`.

## How to verify (every feature)
- Run the real test suite from `C:\local-development\code`:
  `python -m unittest discover -s ui/tests -v` — it must stay green.
- QA live: `python ui/server.py` (port 8765), reach the Simple-mode review screen, run a
  FREE storyboard preview. Drive QA with **preview_eval / preview_snapshot** — note that
  **`preview_screenshot` times out on this machine**, so do not rely on it.

## Reporting (required)
Write your outcome to a durable file — do not rely on a chat reply surviving:
`C:\local-development\code\docs\handoff\storyboard-ux\results\<NN>_<feature>.md`
Record: the files + symbols you changed, the test output, the QA result, and anything the
integrator must know (e.g. "push refused, committed locally").
