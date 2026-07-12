# VEO Ad Pipeline UI — Roadmap / deferred work

Ideas discussed and agreed but **not yet implemented**, parked here so they
aren't lost. This is the team-visible backlog that complements the code; items
graduate out of here into real work when picked up.

Last updated: 2026-06-14.

---

## Shipping now (Phase A) — for reference, not deferred
Real resolution-aware pricing; cover-flow carousel; human-readable per-scene
summaries; the free **Basic** image storyboard (Imagen) plus gated **Standard**
/ **Premium** image tiers with time-progression (several images per scene); and
the final-render tier selector (**Standard** = Fast @1080p, **Quality** =
standard @1080p, **Ultra 4K** = standard @4k).

---

## Deferred

### 1. Per-scene video generation + redo (engine track)
Generate the video one scene at a time and redo a single scene without
scrapping the sequence. Design already written: `ui/docs/per_scene_redo_design.md`.
The hard part is resume (re-uploading a saved clip to mint a fresh Veo URI to
continue the extension chain).

### 2. Draft = independent per-scene Lite clips in the carousel (Phase B)
A cheap draft video tier using **Lite** (`veo-3.1-lite-generate-preview`,
$0.05/s @720p — half of Fast, lower quality, **no Extension**). For multi-scene
jobs, generate each scene **independently** (one-shot, no extension chain) and
show the clips in the same cover-flow carousel as the image storyboard. This is
the *simpler half* of the per-scene track (independent generation needs no
resume). Tradeoff to remember: independent draft clips have **no inter-scene
visual continuity** — continuity only returns in the final extension render.

### 3. Credit-based business model
Map the tiers to credits instead of raw dollars:
- **Image storyboard:** Basic (Imagen) stays **FREE to the user** — the
  conversion hook (business absorbs ~$0.02/image). Standard/Premium image
  tiers consume credits.
- **Video render:** Standard / Quality / Ultra 4K each consume a different
  number of credits.
Design the current tier abstraction so a credit layer can sit on top without a
rewrite.

### 4. Music cost optimization (engine change)
Switch `generate_music.py` default from `lyria-3-pro-preview` ($0.08/song) to
`lyria-3-clip-preview` ($0.04/song, fixed 30s, trim/loop to fit) — halves the
music cost on every render. Engine change, so out of the UI's scope until
picked up.

---

## Product north star (context)
The **free, beautifully-presented storyboard** is the differentiator: most
video-gen products show you nothing until you pay. We hand the user a polished
cover-flow storyboard (free, Imagen) so that, having seen how good it looks,
they're strongly tempted to pay to generate the actual video. The storyboard is
the hook; the paid render is the conversion.
