# Ayush F3/F4 Handoff Prompt

Use this prompt when continuing the implementation of Feature 3 and Feature 4.

## Prompt

Ayush, before doing any F3/F4 work, update your working branch from the latest GitHub `main` so the reference packet files below exist locally.

Recommended start:

```powershell
git fetch origin
git switch <your-f3-or-f4-branch>
git merge origin/main
```

If your branch already has local work, merge or rebase from `origin/main` using your normal workflow, then resolve conflicts before implementation. Do not start from an old branch snapshot; the F3/F4 reference material was added to `main` specifically for this work.

Project root on this machine:

```text
C:\local-development\code
```

Authoritative implementation plan:

```text
docs/plans/feature-implementation-plan.html
```

Feature 3 is `FEAT-03-REFERENCE-LIKENESS`: reference-image likeness plus extend-chain continuity. Its goal is to anchor the subject from one reference or seed and keep that subject consistent through strict sequential extensions.

Feature 4 is `FEAT-04-IDENTITY-BLOCKS`: verbatim identity-block propagation. Its goal is to define named characters once and inject their description byte-identical into every scene where they appear, without letting LLM rewrites paraphrase those blocks.

Read the reference files from:

```text
docs/handoff/ayush-f3-f4/reference/
```

Same folder as an absolute path:

```text
C:\local-development\code\docs\handoff\ayush-f3-f4\reference
```

## How The Reference Files Map To F3

Read these first for Feature 3:

```text
docs/handoff/ayush-f3-f4/reference/packet_08_extension_chain_generation_order.md
docs/handoff/ayush-f3-f4/reference/packet_01_continuous_visible_presence_anchor.md
docs/handoff/ayush-f3-f4/reference/packet_04_negative_prompt_safety_filter_restraint.md
```

Use `packet_08_extension_chain_generation_order.md` as the workflow law. Scene 1 is the seed/text-to-video clip; later scenes are extensions of the immediately preceding clip. No parallel generation, no out-of-order generation, and any mid-chain regeneration invalidates downstream clips.

Use `packet_01_continuous_visible_presence_anchor.md` as the subject-continuity law. F3 should not rely on text alone when the subject disappears. The recurring subject must remain visibly present in every chained clip; defocus is acceptable, full removal is not.

Use `packet_04_negative_prompt_safety_filter_restraint.md` as the safety guardrail for the F3 negative-prompt nudge. F3 may bias extension scenes away from subject dropout, but do not overload negative prompts with anatomical, age-adjacent, NSFW, or sensitive security terms. Keep negative prompts for drift/aesthetic failures; safety belongs in positive prompt language.

Optional F3 support:

```text
docs/handoff/ayush-f3-f4/reference/packet_09_diegetic_foreground_visualisation_layering.md
docs/handoff/ayush-f3-f4/reference/packet_16_known_veo_limitations_reference_pack.md
```

Use `packet_09_diegetic_foreground_visualisation_layering.md` if F3 needs continuity across B-roll or foreground visualisation scenes. It explains how to keep the subject visible while foreground content takes focus.

Use `packet_16_known_veo_limitations_reference_pack.md` as a QA checklist. It summarizes known identity-drift and safety-filter failure modes and points to the packet that mitigates each one.

## How The Reference Files Map To F4

Read these first for Feature 4:

```text
docs/handoff/ayush-f3-f4/reference/packet_02_verbatim_identity_block_propagation.md
docs/handoff/ayush-f3-f4/reference/packet_03_compliance_aware_silhouette_description.md
docs/handoff/ayush-f3-f4/reference/packet_04_negative_prompt_safety_filter_restraint.md
docs/handoff/ayush-f3-f4/reference/veo_app_compliant_body_diversity_prompting.txt
```

Use `packet_02_verbatim_identity_block_propagation.md` as the core F4 contract. Identity blocks are immutable strings. No paraphrasing, no shortening, no synonym swaps, no reordered subsections. The implementation should make byte-identical injection testable.

Use `packet_03_compliance_aware_silhouette_description.md` for the content shape of human figure/body description inside character blocks. It translates risky anatomical phrasing into compliant silhouette, tailoring, wardrobe, and professional-tone language.

Use `packet_04_negative_prompt_safety_filter_restraint.md` whenever F4 creates or preserves negative prompt terms around identity drift. Do not move sensitive safety language into negative prompts.

Use `veo_app_compliant_body_diversity_prompting.txt` as the broader source reference behind packet 03. Treat packet 03 as the smaller implementation-facing summary, and this file as the expanded vocabulary/policy reference when a character block needs careful body or appearance wording.

Conditional F4 support:

```text
docs/handoff/ayush-f3-f4/reference/packet_05_british_rp_voice_identity_block.md
docs/handoff/ayush-f3-f4/reference/packet_06_audio_technical_bed_block.md
```

Only pull these into the active implementation if F4 is explicitly storing voice/audio identity blocks in the cast panel now. If voice/audio are being deferred to later voice work, leave these as reference only. The same byte-identical rule from packet 02 applies if they are included.

## Implementation Notes

For F3, keep the engine behavior additive. The important implementation shape from the plan is:

- allow one reference image to ride a generated Simple-mode chain;
- keep scene 1 as the reference/seed anchor;
- keep later scenes as strict sequential extensions;
- relax seed-image requirements only when a valid reference exists;
- mirror any in-memory continuity nudge in dry-run output;
- do not mutate `scenes.json` just to add extension-scene negative prompt terms.

For F4, keep the character system engine-invisible. The important implementation shape from the plan is:

- create `ui/characters.py` as the single source of truth for literal block injection;
- persist cast data as `characters.json` inside the Simple job directory;
- store scene assignments separately from `scenes.json`;
- rewrite only scene `prompt` fields when applying character blocks;
- strip injected blocks before LLM edit rewrites;
- re-inject blocks after rewrite and before committing edited scenes;
- prove byte-identical behavior with tests.

Do not treat these reference packets as new product copy to display to operators. They are implementation and prompt-engineering evidence for the feature behavior.

## Minimum Verification Expected

Run the repo UI test suite after implementation:

```powershell
python -m unittest discover -s ui/tests -v
```

For F3, include tests that a Simple generated packet with a reference image validates, derives the expected reference-image command behavior, and still refuses seedless/reference-less generated jobs for free.

For F4, include tests that identity blocks are injected byte-identically, that strip/re-inject is idempotent, that assignments validate scene indices, and that edit rewrites never send or mutate the verbatim block text.

