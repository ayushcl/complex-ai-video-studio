# Packet 02 — Verbatim Identity Block Propagation

**Status:** Approved workaround
**Architect Category:** continuity
**Runtime Priority:** critical

This packet captures the verbatim propagation discipline that emerged late in the CLOUDTECH UK session: any descriptive block governing identity, voice, audio, palette, or any other element that must persist across scenes must appear byte-identical in every prompt of the chain. Paraphrasing, shortening, or reordering between prompts causes drift on the corresponding generated attribute.

---

## JSON Specification

```json
{
  "veo_specification_packet": {
    "packet_id": "verbatim-identity-block-propagation",
    "packet_name": "Verbatim Identity Block Propagation",
    "packet_version": "1.0.0",
    "status": "approved_workaround",
    "architect_category": "continuity",
    "runtime_priority": "critical",
    "evidence": {
      "evidence_type": "exact_phrase",
      "source_extract": "User instruction: 'the description of the presenter must be equally as explicit and well defined in evry prompt as if we were stating it from the beginning.' Reinforced: 'we need to describe every detail we want consistant clearly and in high detail across every scene. This includes the style, theme, voiceover, effects, visual acuity, etc... So for persistance, every aspect must be descrtied in high level of detail.' Final pack carries the full Figure / Face / Hair / Wardrobe block byte-identical across all five chained prompts."
    },
    "packet_boundary": {
      "governs": [
        "Propagation discipline — what gets repeated and how across an extension chain",
        "The structural format of identity, voice, audio, and palette blocks (labelled subsections terminated with full stops)",
        "Placement order of the identity block within the assembled prompt",
        "Permitted scope of variation between repeated blocks (energy modifiers only, no structural changes)"
      ],
      "does_not_govern": [
        "The actual content of the identity block (handled by Compliance-Aware Silhouette Description and other content packets)",
        "Voice block content (handled by British RP Voice Identity Block)",
        "Audio bed content (handled by Audio Technical Bed Block)",
        "Whether the subject is visibly present in frame (handled by Continuous Visible Presence Anchor)"
      ]
    },
    "applicability": {
      "applies_when": [
        "Two or more chained or related Veo clips share a recurring subject, voice, palette, or aesthetic element",
        "Identity continuity is a hard requirement across the chain",
        "Veo extension mode is being used or scenes will be edited together as one continuous deliverable"
      ],
      "must_not_apply_when": [
        "A single standalone clip is being generated with no continuity requirement",
        "Each clip is intentionally a different subject, voice, or aesthetic (anthology piece)",
        "The user has explicitly approved a compressed or paraphrased identity block to fit token limits — in which case fall back to a documented compressed form, not freehand paraphrasing"
      ]
    },
    "architect_integration": {
      "sequence_override": "none",
      "pre_subject_environment_preamble": [],
      "positive_absence_sentences": [],
      "positive_prompt_injections": {
        "setting_and_layout": [
          "Identity block placement: immediately after the opening sentence establishing scene type and subject role, before setting and camera language."
        ],
        "composition_and_screen_order": [
          "Identity block structure: four labelled subsections — 'Figure.', 'Face.', 'Hair.', 'Wardrobe.' — each label terminated with a full stop, followed by the descriptive paragraph.",
          "Voice and audio identity blocks follow the same labelled-subsection format: 'Voice.' and 'Audio technical.' with full-stop terminators."
        ],
        "lighting": []
      },
      "negative_prompt_terms": [
        "different presenter",
        "different hair",
        "different face",
        "different makeup",
        "different setting",
        "different lighting",
        "different voice",
        "voice changing between clips",
        "wardrobe change"
      ],
      "control_vocabulary": {
        "use": [
          "Figure.",
          "Face.",
          "Hair.",
          "Wardrobe.",
          "Voice.",
          "Audio technical.",
          "Setting.",
          "Performance.",
          "Camera.",
          "Tone.",
          "Constraints."
        ],
        "avoid": [
          "as previously described",
          "same as before",
          "see prior prompt",
          "[abbreviated]",
          "...",
          "etc.",
          "see scene one",
          "matching the opening shot"
        ]
      }
    },
    "continuity_rules": {
      "extension_restatement": [
        "Every prompt in a chain must contain the full identity block byte-identical to the seed prompt — no paraphrasing, no shortening, no reordering of subsections, no synonym substitution",
        "Every prompt in a chain that uses voice must contain the full voice block byte-identical to the seed prompt",
        "Every prompt in a chain that uses native audio must contain the full audio technical block byte-identical to the seed prompt",
        "Override clauses for context shift are permitted at the top of the block (e.g. 'kept continuously in frame to preserve identity, softly defocused in the background') but the descriptive subsections themselves must remain byte-identical",
        "A single energy modifier on the closing scene's performance line is permitted (e.g. 'On this closing line her delivery carries slightly warmer, more engaged energy than the opening — an invitation rather than a pitch — while preserving the same identical voice identity throughout.') but the underlying voice block remains byte-identical"
      ],
      "must_lock": [
        "Identity block content (every word, every comma, every sentence order)",
        "Voice block content (every word, every comma, every sentence order)",
        "Audio technical block content (every word, every comma, every sentence order)",
        "Setting block content where setting is continuous",
        "Palette and lighting language where palette is continuous",
        "Aspect ratio and frame rate restatement on every prompt"
      ],
      "reset_strategy": [
        "If a paraphrased version of the block has accidentally been used in any chained prompt, regenerate that clip and all downstream clips with the corrected verbatim block",
        "If the user revises a block (e.g. updating a wardrobe detail), the new locked block must be propagated byte-identical into every prompt in the chain — not just the next one — and all clips regenerated",
        "If an architect must compress a block to fit a token limit, the compressed version becomes the new locked form and must itself be propagated byte-identical from that point forward"
      ]
    },
    "conflict_tags": [
      "requires_extension_mode",
      "requires_locked_subject",
      "forbids_paraphrasing"
    ],
    "operator_note_trigger": "Before approving any chain, diff the identity, voice, and audio blocks across all prompts and confirm they are byte-identical except for permitted top-of-block override clauses and the single permitted closing-scene energy modifier.",
    "visual_acceptance_checks": [
      "Identity block in every prompt of the chain is byte-identical to the seed prompt",
      "Voice block in every prompt of the chain (where voice is used) is byte-identical",
      "Audio technical block in every prompt of the chain (where audio is used) is byte-identical",
      "Setting and palette language is byte-identical where setting and palette are continuous",
      "Subject's appearance, voice, and acoustic environment match across all generated clips on playback"
    ]
  }
}
```

---

## Notes for the Architect

This packet is the structural law that makes every other identity-related packet actually work. The Compliance-Aware Silhouette Description and British RP Voice Identity Block packets define *what* the blocks contain — this packet defines *how* those blocks must be inserted into every prompt in a chain.

Three subtleties worth flagging:

The "byte-identical" rule is genuinely strict. In the CLOUDTECH UK session, even small variations like swapping one adjective or reordering a sentence within a subsection produced visible drift in Veo's output. The architect should treat the block as an immutable string asset, not as descriptive content to be re-written each time.

The permitted override clauses at the top of the block are the only place where context-specific language is allowed. Examples include "kept continuously in frame to preserve identity, softly defocused in the background" for B-roll scenes, and "exact same appearance as she has had throughout" for the rack-focus return scene. These clauses sit *before* the labelled subsections, never inside them.

The single permitted variation on the closing scene's voice block is an energy modifier sentence — not a re-description of the voice. The CLOUDTECH UK final pack used "On this closing line her delivery carries slightly warmer, more engaged energy than the opening — an invitation rather than a pitch — while preserving the same identical voice identity throughout." The closing clause "while preserving the same identical voice identity throughout" is mandatory whenever an energy modifier is used.

This packet must be loaded alongside any of the content packets it propagates — Compliance-Aware Silhouette Description, British RP Voice Identity Block, Audio Technical Bed Block, Continuous Workspace Restatement, and Cool-Toned Architectural Palette Lock. The conflict tag `forbids_paraphrasing` is the architect's signal to never compress or rephrase those blocks.
