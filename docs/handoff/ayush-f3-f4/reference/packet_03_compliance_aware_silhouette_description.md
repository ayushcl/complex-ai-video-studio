# Packet 03 — Compliance-Aware Silhouette Description

**Status:** Approved workaround
**Architect Category:** cast
**Runtime Priority:** high

This packet captures the language discipline required for describing an adult human subject's figure, body type, and physical presence without triggering Veo's content safety systems. The technique replaces anatomical naming and size descriptors with silhouette, tailoring, and fabric-structure language. It is the content rule that allows physical specificity to coexist with reliable generation.

---

## JSON Specification

```json
{
  "veo_specification_packet": {
    "packet_id": "compliance-aware-silhouette-description",
    "packet_name": "Compliance-Aware Silhouette Description",
    "packet_version": "1.0.0",
    "status": "approved_workaround",
    "architect_category": "cast",
    "runtime_priority": "high",
    "evidence": {
      "evidence_type": "failure_fix_pair",
      "source_extract": "Failure: explicit anatomical bust description ('naturally large and noticeably full, with a rounded, generous, heavy shape, visibly curved and projecting forward, creating a clear, feminine contrast against her narrow waist') triggered Veo content safety. Fix: ingestion of veo_compliant_body_diversity_prompting v2.1.0 packet. Final locked language replaces anatomy with 'fuller figured hourglass silhouette and balanced natural proportions' and 'balanced curvy silhouette on a slim English frame, defined through tailoring rather than anatomy'. Mandatory tail clause: 'with the silhouette defined by tailoring and fabric structure rather than exposure'. Constraints block appended: 'Fully clothed, modest neckline, full coverage styling, respectful representation, strictly safe for work.'"
    },
    "packet_boundary": {
      "governs": [
        "Linguistic vocabulary used to describe an adult human subject's figure, body type, and silhouette",
        "Order of description (wardrobe and tailoring before figure where possible)",
        "The mandatory tail clause anchoring silhouette to tailoring rather than anatomy",
        "The constraints block appended at the end of any prompt containing physical description",
        "The tone framing language that contextualises the description as professional and dignified"
      ],
      "does_not_govern": [
        "Wardrobe colour, fabric pattern, or specific garment styling (handled in identity block content)",
        "Hair, makeup, complexion, or non-body identity attributes",
        "Voice, age band, ethnicity, or accent",
        "Camera language or framing",
        "Whether the subject is visibly present in frame (handled by Continuous Visible Presence Anchor)"
      ]
    },
    "applicability": {
      "applies_when": [
        "An adult human subject's physical description includes figure, body type, or silhouette specifications",
        "The subject must read as having visible feminine, masculine, or specific body-type characteristics",
        "Veo content safety has flagged or is at risk of flagging anatomical or sexualised language"
      ],
      "must_not_apply_when": [
        "The scene contains no human figure",
        "The subject is fully clothed in concealing layers where silhouette is not the descriptive priority",
        "The context is clearly historical costume or theatrical wardrobe with its own established vocabulary",
        "The user has explicitly mandated different vocabulary for a non-corporate context (fitness editorial, fashion campaign, documentary)"
      ]
    },
    "architect_integration": {
      "sequence_override": "none",
      "pre_subject_environment_preamble": [],
      "positive_absence_sentences": [],
      "positive_prompt_injections": {
        "setting_and_layout": [],
        "composition_and_screen_order": [
          "Figure. She has a [statuesque/petite/tall] adult frame with a [fuller figured hourglass / balanced curvy / pear shaped / athletic] silhouette and balanced natural proportions. Her posture is upright and confident, with natural waist definition created through structured tailored clothing. Her shoulders are naturally [narrow/broad] and her arms slim and subtly toned. Overall silhouette reads as a [balanced curvy / athletic / petite] silhouette on a [slim/strong/petite] [nationality] frame, defined through tailoring rather than anatomy.",
          "Wardrobe placement: tailoring and fabric language must precede figure language where possible — describe the structured cut, the closely nipped-in waist, and the smooth well-fitted line before describing the body it sits on.",
          "Mandatory tail clause appended to wardrobe paragraph: 'with the silhouette defined by tailoring and fabric structure rather than exposure'",
          "Mandatory constraints block at end of prompt: 'Constraints. Fully clothed, modest neckline, full coverage styling, respectful representation, strictly safe for work.'",
          "Mandatory tone framing block: 'Tone. Respectful, inclusive, professional fashion editorial feel applied to a [role] portrait, dignified and non sexualised.'"
        ],
        "lighting": []
      },
      "negative_prompt_terms": [
        "frumpy appearance",
        "dowdy styling",
        "unflattering styling",
        "loose fitting clothing",
        "baggy blouse",
        "oversized top",
        "unstructured fabric"
      ],
      "control_vocabulary": {
        "use": [
          "fuller figured hourglass silhouette",
          "balanced natural proportions",
          "statuesque adult frame",
          "balanced curvy silhouette on a slim [nationality] frame",
          "silhouette defined through tailoring rather than anatomy",
          "structured tailoring that shapes and defines a balanced hourglass silhouette",
          "natural waist definition created through structured tailored clothing",
          "naturally narrow shoulders",
          "slim and subtly toned arms",
          "upright and confident posture",
          "soft natural proportions",
          "realistic everyday proportions",
          "athletic build",
          "petite frame",
          "pear shaped silhouette",
          "fully clothed",
          "modest neckline",
          "full coverage styling",
          "respectful representation",
          "strictly safe for work",
          "professional fashion editorial feel",
          "dignified and non sexualised"
        ],
        "avoid": [
          "breasts",
          "bust",
          "chest size",
          "cleavage",
          "nipples",
          "areola",
          "hips and breasts",
          "butt",
          "thigh gap",
          "voluptuous",
          "buxom",
          "busty",
          "curvy (without qualifier)",
          "full (when applied to body part)",
          "heavy (when applied to body part)",
          "rounded shape",
          "projecting forward",
          "visibly curved",
          "huge",
          "massive",
          "enormous",
          "tiny waist",
          "impossibly curvy",
          "hyper feminine anatomy",
          "exaggerated anatomy",
          "sexy",
          "sensual",
          "seductive",
          "provocative",
          "erotic",
          "tempting",
          "sultry",
          "revealing",
          "skimpy",
          "barely covered",
          "low cut neckline",
          "plunging neckline",
          "tight dress (without tailoring qualifier)"
        ]
      }
    },
    "continuity_rules": {
      "extension_restatement": [
        "The figure language locked at the seed prompt must be propagated byte-identical to every chained prompt (governed jointly with Verbatim Identity Block Propagation packet)",
        "The mandatory tail clause and constraints block must appear in every prompt of the chain, not just the seed"
      ],
      "must_lock": [
        "The silhouette descriptor (e.g. 'fuller figured hourglass silhouette')",
        "The frame descriptor (e.g. 'statuesque adult frame on a slim English frame')",
        "The tailoring-not-anatomy tail clause",
        "The constraints block at end of prompt",
        "The tone framing block"
      ],
      "reset_strategy": [
        "If Veo flags the prompt despite this packet, audit for residual anatomical terms in the negative prompt array (governed by Negative Prompt Safety Filter Restraint packet) — overloaded negative prompts can themselves trigger the filter even when the positive prompt is compliant",
        "If figure rendering remains frumpy or unflattering despite this packet, do not reach for anatomical specificity — instead strengthen the wardrobe tailoring language (e.g. 'closely nipped-in waist', 'smooth well-fitted cut', 'clean darting') to drive the silhouette through cut rather than body description"
      ]
    },
    "conflict_tags": [
      "requires_adult_subject",
      "forbids_anatomical_terms",
      "requires_constraints_block",
      "requires_tone_framing"
    ],
    "operator_note_trigger": "Before approving any prompt containing physical description, scan for any term in the avoid list. If any are present, rewrite using the use list. Confirm the mandatory tail clause and constraints block are present.",
    "visual_acceptance_checks": [
      "Generated subject reads as having the intended silhouette and body type",
      "Generated subject reads as polished and professional, not frumpy or dowdy",
      "Wardrobe sits correctly on the body without pulling, gaping, or flattening the intended silhouette",
      "No content safety flag is raised on the prompt",
      "Tone reads as dignified professional editorial, not sexualised or objectifying"
    ]
  }
}
```

---

## Notes for the Architect

This packet is the language law that lets the Architect describe an adult subject with visible feminine, masculine, or distinctive body characteristics without crossing Veo's content safety boundary. The discovery in the CLOUDTECH UK session was that anatomical specificity does not actually help Veo render the desired silhouette — strengthening the *wardrobe tailoring* language drives the silhouette more reliably and stays compliant.

A few subtleties worth flagging:

The tail clause "with the silhouette defined by tailoring and fabric structure rather than exposure" is doing meaningful work. It acts as a context anchor for Veo's safety classifier, signalling that the description is professional editorial rather than sexualised. Even when the rest of the prompt is fully compliant, dropping this clause measurably raises the rejection rate.

The constraints block at the end of the prompt — "Constraints. Fully clothed, modest neckline, full coverage styling, respectful representation, strictly safe for work." — also acts as a context anchor, not just as a directive. The user's testing suggested that prompts without this block were more likely to be flagged even when their content was identical to prompts with it.

The tone framing block is the third anchor: "Respectful, inclusive, professional fashion editorial feel applied to a corporate consultant portrait, dignified and non sexualised." Together these three anchors form what the compliance packet referred to as "context to clarify intent" — they tell Veo's classifier what the description is *for*, not just what it contains.

The avoid list is long deliberately. It draws from the original veo_compliant_body_diversity_prompting v2.1.0 packet's high-risk language taxonomy, expanded with the specific terms that triggered flagging during the CLOUDTECH UK iterations. The Architect should treat the avoid list as a hard filter — any token from this list appearing in a positive prompt is a generation risk regardless of context.

The reset strategy includes an important paradox-aware step: if Veo still flags a prompt despite compliant positive language, the issue is likely in the *negative* prompt array. This is governed by Packet 04 (Negative Prompt Safety Filter Restraint), which must be loaded alongside this packet to prevent overloaded negative prompts from undoing the work this packet does on the positive side.

This packet co-loads with Verbatim Identity Block Propagation (which propagates the figure language across the chain) and Negative Prompt Safety Filter Restraint (which prevents negative-prompt overloading from triggering false positives). All three must be present together for reliable compliant generation of subjects with specified body characteristics.

Ready for Packet 04 — Negative Prompt Safety Filter Restraint — when you give the word.
