# Packet 08 — Extension Chain Generation Order

**Status:** Approved workaround
**Architect Category:** continuity
**Runtime Priority:** critical

This packet captures the production sequence and chain integrity rules for generating multi-clip videos through Veo's extension mode. It documents what the extension mechanism preserves, what it loses, and the strict generation ordering required for the chain to hold. The packet defines the seed clip's role as the visual reference for all downstream clips, the cost of mid-chain regeneration, and the approval gate that must occur before chaining begins.

---

## JSON Specification

```json
{
  "veo_specification_packet": {
    "packet_id": "extension-chain-generation-order",
    "packet_name": "Extension Chain Generation Order",
    "packet_version": "1.0.0",
    "status": "approved_workaround",
    "architect_category": "continuity",
    "runtime_priority": "critical",
    "evidence": {
      "evidence_type": "exact_phrase",
      "source_extract": "User confirmation that contradicted earlier assumption: 'You are wrong, I've tested this with VEO, and as long as you are extending the clips, it does rememebr them.' Final pack operator notes across the chain: 'Extension from Scene 1' (Scene 2), 'Extension from Scene 2' (Scene 3), 'Extension from Scene 3' (Scene 4), 'Extension from Scene 4' (Scene 5). Generation type field across the pack: Scene 1 = 'text_to_video', Scenes 2 to 5 = 'extension'. Strategy note: 'Generate strictly in sequence: Scene 1 first, then extend Scene 2 from Scene 1, Scene 3 from Scene 2, Scene 4 from Scene 3, Scene 5 from Scene 4. Do not regenerate mid-chain without re-running everything downstream.' Approval gate documented: 'Lock Scene 1 first with the v7 compliance-pass prompt. Approve the take. Export a clean front-facing still.'"
    },
    "packet_boundary": {
      "governs": [
        "The strict generation order for chained Veo clips (seed clip first, then sequential extensions)",
        "The seed clip's role as visual reference for all downstream clips in the chain",
        "What extension mode preserves (visible content, lighting, colour state, subject identity when subject is visible)",
        "What extension mode loses (subject identity when subject is removed from frame, continuity when visible content changes too dramatically)",
        "The mid-chain regeneration cost (downstream clips must be re-extended)",
        "The approval gate at the seed clip before chain commitment",
        "The generation type field per clip (text_to_video for seed, extension for downstream)"
      ],
      "does_not_govern": [
        "Whether the subject is visibly present in each clip (handled by Continuous Visible Presence Anchor)",
        "Identity, voice, audio block content (handled by content packets)",
        "Verbatim propagation of blocks across prompts (handled by Verbatim Identity Block Propagation)",
        "Setting and palette restatement (handled by Continuous Workspace Restatement and Cool-Toned Architectural Palette Lock)",
        "Foreground content design or visualisation selection",
        "Camera language or rhythm beats"
      ]
    },
    "applicability": {
      "applies_when": [
        "A multi-clip video uses Veo extension mode for any reason — continuity, visual consistency, audio bed continuity, or scene-to-scene flow",
        "Two or more chained clips share a recurring subject, voice, palette, or aesthetic element",
        "The deliverable will be edited together as one continuous piece rather than as discrete clips",
        "Identity continuity between non-adjacent scenes (e.g. opening narrator returning for closing CTA) is a hard requirement"
      ],
      "must_not_apply_when": [
        "Each clip is independently generated as text-to-video with no extension dependency",
        "The video is a single standalone Veo clip with no chain",
        "The deliverable is an anthology piece with intentionally separate aesthetics per clip",
        "The user has explicitly mandated a different continuity strategy (reference image generation, first-frame conditioning, dual-track generation, character training)"
      ]
    },
    "architect_integration": {
      "sequence_override": "environment_first",
      "pre_subject_environment_preamble": [
        "Generation order discipline: clips must be generated in strict sequence. Scene 1 (the seed clip) is generated first as text_to_video. Each subsequent scene is generated as an extension of the immediately preceding clip. Skipping ahead in the chain or generating clips out of order is forbidden.",
        "Generation type per clip: Scene 1 = text_to_video. Scenes 2 onward = extension."
      ],
      "positive_absence_sentences": [],
      "positive_prompt_injections": {
        "setting_and_layout": [
          "Extension framing sentence (mandatory opening on every non-seed prompt): 'Extend from the previous shot.' This sentence must be the first sentence of the prompt, before any other content. It signals to the Architect (and to any generation system reading the prompt as input) that this clip inherits its visual state from the preceding clip in the chain."
        ],
        "composition_and_screen_order": [],
        "lighting": []
      },
      "negative_prompt_terms": [],
      "control_vocabulary": {
        "use": [
          "Extend from the previous shot.",
          "text_to_video (for seed clip)",
          "extension (for downstream clips)",
          "seed clip",
          "downstream clip",
          "chain integrity",
          "approval gate",
          "lock the seed",
          "regenerate from earliest visible drift point"
        ],
        "avoid": [
          "starting from scratch (for any clip after the seed)",
          "independent generation (for any clip in the chain)",
          "fresh take (for any clip after the seed)",
          "skip ahead in the chain",
          "generate scenes in parallel",
          "regenerate just this one clip (mid-chain)",
          "patch this scene later"
        ]
      }
    },
    "continuity_rules": {
      "extension_restatement": [
        "The 'Extend from the previous shot.' opening sentence must appear at the start of every prompt for clips 2 through N in the chain",
        "Every prompt in the chain must declare its generation type explicitly (text_to_video for seed, extension for downstream)",
        "What extension mode preserves and what it loses must be respected at the prompt-design level — content packets must work with the extension mechanism, not against it"
      ],
      "must_lock": [
        "Generation order: strict sequential, no parallel generation, no out-of-order generation",
        "Seed clip role: Scene 1 is the visual reference for all downstream clips and must be approved before chaining begins",
        "Mid-chain regeneration cost: regenerating any clip in the chain invalidates all downstream clips, which must be re-extended",
        "What extension preserves: visible content, lighting, colour state, subject identity (when subject is visible in frame)",
        "What extension loses: subject identity if subject is removed from visible frame across clips"
      ],
      "reset_strategy": [
        "If the seed clip drifts on first generation (presenter doesn't match the description, palette is wrong, framing is off), regenerate the seed before chaining — the cost of re-rolling the seed is one clip; the cost of re-rolling after the chain is committed is the entire chain",
        "If a downstream clip drifts identity, regenerate from the earliest visible drift point — not from the current clip — and re-extend all downstream clips from that point",
        "If a downstream clip drifts setting or palette, audit the prompt for missing setting restatement (governed by Continuous Workspace Restatement) before regenerating the chain",
        "If multiple clips drift in the same way, the issue is in the seed clip's visual state — regenerate the seed and rebuild the chain rather than patching individual downstream clips",
        "Never attempt to 'fix' a mid-chain clip by patching it in isolation — the visual state of that fix will not propagate to subsequent extensions, and the chain will compound the inconsistency"
      ]
    },
    "conflict_tags": [
      "requires_extension_mode",
      "forbids_independent_generation",
      "forbids_parallel_generation",
      "forbids_out_of_order_generation"
    ],
    "operator_note_trigger": "Before generating the chain, confirm Scene 1 is locked and approved. Before generating any downstream clip, confirm the immediately preceding clip is locked and approved. If any clip in the chain is regenerated, re-extend all downstream clips from the regeneration point — do not attempt to splice or patch.",
    "visual_acceptance_checks": [
      "Scene 1 generation type is text_to_video; all downstream scenes are extension",
      "Every non-seed prompt opens with 'Extend from the previous shot.'",
      "Generation order in the production pipeline is strictly sequential (Scene 1, then 2, then 3, etc.)",
      "No clip in the chain was generated before its preceding clip was approved",
      "Any regenerated clip triggered re-extension of all downstream clips, not isolated patching",
      "Visible content, lighting, colour state, and subject identity carry forward consistently across the chain on playback"
    ]
  }
}
```

---

## Notes for the Architect

This packet is the workflow law that makes every other continuity packet actually work. Continuous Visible Presence Anchor (Packet 01), Verbatim Identity Block Propagation (Packet 02), British RP Voice Identity Block (Packet 05), and Audio Technical Bed Block (Packet 06) all assume that the chain is being generated in order through Veo's extension mode. If that workflow assumption breaks, every one of those packets stops working as designed.

A few subtleties worth flagging:

The most important rule in this packet is the mid-chain regeneration cost. When the user (or the Architect) decides a downstream clip needs revision, the natural instinct is to regenerate just that clip in isolation. This does not work in extension mode. Veo's extension mechanism inherits visual state from the preceding clip in the chain. If a mid-chain clip is regenerated independently, the regenerated version's visual state will not propagate to subsequent clips — the next clip in the chain still inherits from the *original* preceding clip, not from the regenerated version. The result is a discontinuity that compounds across the rest of the chain. The only correct fix is to re-extend all downstream clips from the regeneration point.

The approval gate at the seed clip is operationally important. Generating the entire chain before approving Scene 1 is the most expensive mistake an Architect can make. If Scene 1 has any drift — wrong wardrobe, wrong age, wrong palette, wrong framing — that drift propagates into every downstream clip, and the entire chain has to be regenerated. The right discipline is: generate Scene 1, approve it, then chain. The cost of re-rolling a single clip is small. The cost of re-rolling a five-clip chain is large.

The `sequence_override` field is set to `environment_first` because this packet's `Extend from the previous shot.` sentence must appear before any subject or content language in the assembled prompt. The Architect should treat this as a structural override on the standard prompt assembly order — the extension declaration is the highest-priority opening, before identity blocks, before setting blocks, before camera blocks. This is the only packet so far that uses the `environment_first` override.

The control vocabulary's `avoid` list contains the natural-language phrases that an Architect or user might reach for to describe a fix or revision. "Just regenerate this clip" reads as innocuous but breaks chain integrity. "Fresh take" reads as a clean slate but undoes the extension chain. "Patch this scene later" reads as low-cost but compounds drift. The Architect must recognise these phrases as workflow violations and translate them into the correct extension-aware operations.

The reset strategy carries the most operationally important guidance in the packet: regenerate from the *earliest visible drift point*, not from the current clip. If Scene 4 has drifted, the issue may have started in Scene 3's visual state, which means Scene 4's regeneration as an extension of Scene 3 will inherit the same drift. The Architect must work backwards through the chain to find the earliest clip where the drift becomes visible and rebuild from there.

This packet co-loads with every continuity packet in the library. Continuous Visible Presence Anchor depends on the chain holding. Verbatim Identity Block Propagation depends on the order being correct. Voice and Audio packets depend on extension mode preserving audio state. Without this packet, none of those packets deliver their guarantees.

The runtime priority is `critical` because the cost of getting this wrong is the highest of any packet — a workflow error here invalidates an entire chain and forces full regeneration. Compare to Packet 06 (Audio Technical Bed Block) which is `medium` because audio drift is recoverable per-clip. Workflow drift is not recoverable per-clip; it requires rebuilding the chain.

Ready for Packet 09 — Diegetic Foreground Visualisation Layering — when you give the word.
