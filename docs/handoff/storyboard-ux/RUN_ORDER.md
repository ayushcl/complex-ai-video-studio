# Run order — Storyboard-review UX (F9–F14)

Six features, one agent each, every agent on its **own branch/worktree** off
`core-features`. They share `ui/static/app.js` and `ui/static/styles.css`, so the
parallelism is at the **branch** level and merges are **sequenced** (an integrator
resolves the inevitable conflicts in the order below).

Each full prompt lives in its own file in
`C:\local-development\code\docs\handoff\storyboard-ux\`. Dispatch a packet by pasting its
launcher (below) into a fresh agent that has access to this repo.

## Launch sequence

### Wave 1 — dispatch all five in parallel (independent features)
- **F9 — Reel lock** → launcher:
  > Open and follow `C:\local-development\code\docs\handoff\storyboard-ux\09_reel-lock.md` exactly. You have NO memory of any prior conversation — rely only on that file and the files it names.
- **F10 — Full-width image** → launcher:
  > Open and follow `C:\local-development\code\docs\handoff\storyboard-ux\10_full-width-image.md` exactly. You have NO memory of any prior conversation — rely only on that file and the files it names.
- **F11 — Badges to bottom** → launcher:
  > Open and follow `C:\local-development\code\docs\handoff\storyboard-ux\11_review-badges-bottom.md` exactly. You have NO memory of any prior conversation — rely only on that file and the files it names.
- **F12 — Scene slider** → launcher:
  > Open and follow `C:\local-development\code\docs\handoff\storyboard-ux\12_scene-slider.md` exactly. You have NO memory of any prior conversation — rely only on that file and the files it names.
- **F13 — Adjust Your Scenes** → launcher:
  > Open and follow `C:\local-development\code\docs\handoff\storyboard-ux\13_adjust-your-scenes.md` exactly. You have NO memory of any prior conversation — rely only on that file and the files it names.

### Wave 2 — only after F9 and F13 are merged into core-features
> Note: F14 targets F13's **pill** scene selector. Until F13 merges, the live
> `ui/static/app.js` still has the old `<select id="s-edit-scope">` — that is expected, not
> a defect to fix on this branch.
- **F14 — Click-to-select** → launcher:
  > Open and follow `C:\local-development\code\docs\handoff\storyboard-ux\14_click-to-select.md` exactly. You have NO memory of any prior conversation — rely only on that file and the files it names.

## Merge sequence (integrator)
Because the branches edit the same files, merge them into `core-features` **one at a time**,
running `python -m unittest discover -s ui/tests -v` after each, in this order — chosen so
the tightly-coupled pairs land adjacently and conflicts are small:
1. **F9** (reel) → 2. **F10** (reel; expect conflicts with F9 in the cover-flow / `.cover-card`)
→ 3. **F11** (review) → 4. **F12** (review; expect conflicts with F11 in `renderSimpleReview`)
→ 5. **F13** (edit panel) → 6. **F14** (edit + `layoutCoverFlow`; needs F9 + F13).

If you would rather avoid in-file conflicts entirely, give each coupled pair to **one**
agent instead of two (F9+F10 together, F11+F12 together, F13+F14 together = three packets).
This package is split one-per-feature as requested; the pairing is the lower-conflict
alternative.

## Confirming a packet succeeded
- Its `results/<NN>_<feature>.md` file exists and reports tests green + QA done.
- `python -m unittest discover -s ui/tests -v` passes on its branch.
- A quick Simple-UI QA shows the feature's behaviour and no console errors, with the free
  dry-run / spend-gate unchanged.

## If a packet fails
Re-run just that packet's launcher on a fresh worktree branched off the **latest**
`core-features`. Don't hand-fix another agent's branch; the per-packet acceptance check and
the post-merge test run will catch a gap.
