# VEO Extension Chain — 6-Scene Multi-Hop Milestone (Fast)

**Status:** Proven (technical milestone). Fast-model proof of concept — validates the multi-hop
framework, but is *not* a hero-ready deliverable.

## What this proves

Veo 3.1 scene extension chains reliably across multiple hops. A single seed clip was extended
five consecutive times, carrying a coherent visual state (desk, laptop position, overall lighting)
across all five extension boundaries into one continuous ~43-second clip. This validates the
multi-hop extension framework that the production video pipeline depends on. Prior to this we had
only proven a single extension hop.

## Run details

- Model: `veo-3.1-fast-generate-preview`
- Structure: text seed (Scene 1) + 5 sequential `video=` extensions (Scenes 2–6)
- Runner: `video_generation_agency/run_veo_extension_chain.py`
- Final output: `veo_chain_runs/latest/final_silent.mp4`
- Duration: 43.08s (8s seed + 5 × 7s hops)
- Format: 1280×720, 24 fps, H.264, video-only (audio stripped via FFmpeg `-an`)
- All six generations completed in one controlled run — no retries, no mode switches.
- Per-scene combined outputs grew cumulatively (1.0M → 2.5M → 3.6M → 4.7M → 5.6M → 6.6M),
  consistent with each extension call returning the full combined clip rather than only the new seconds.

## QA verdict: PARTIAL PASS

Mechanically successful; three issues prevent using it as-is as a hero background.

Continuity across the five seams:

- 8s (1→2): excellent — transition invisible, hand enters naturally
- 15s (2→3): excellent — lighting holds
- 22s (3→4): good — clean
- 29s (4→5): poor — the glass prism morphs/thickens at the seam
- 36s (5→6): boundary smooth, but the following action (abrupt screen-off) feels disconnected

Defects:

1. Apple logo on the laptop lid in Scene 1 — a prompt-adherence issue, not an extension-tech issue.
2. Prism geometry morph at the 29s seam — partly Fast-model fidelity, partly seam-induced.
3. Scene 6 fails to loop — ends with paper on the desk and an abrupt screen-off, so it cannot return
   to the empty opening state. Trimming cannot fix this; it is a prompt/structure matter.

## Fast-model limitations observed

Refracted desk light rendered as a liquid/resin texture rather than crisp caustics, and glass
geometry was unstable across a later hop. A Standard-model rerun is expected to lock geometry and
render caustics correctly — but only after the prompt/structure fixes below, so Standard is not paid
for twice.

## Open items

- **Billing basis unconfirmed.** Whether each extension call is billed per new ~7s or per the full
  combined output it returns (the difference is roughly $17 vs $61-equivalent on Standard for a chain
  this length). To be read from an actual bill on the next paid run.
- **Standard-model fidelity pass not yet run.**
- **Reference-image seed (MAXIION A01) not yet proven** — blocked by the Gemini project monthly spend
  cap at time of writing.

## Disposition

The three defects are directly addressed in the MAXIION A01–A06 prompt rewrite: an anti-paper growth
beat (A03) to remove the loop-breaking paper, a purpose-built looping landing plate (A06) with held
negative space, a controlled copper flash transition replacing the explosive one, and brand-safety
blocks (no real logos, no readable on-screen text).

Multi-hop extension is proven. The remaining work is prompt/structure refinement plus a single
Standard-quality fidelity pass once A01 is proven and the chain holds on Fast.
