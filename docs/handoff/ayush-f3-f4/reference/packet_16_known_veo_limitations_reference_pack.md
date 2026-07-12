# Packet 16 — Known Veo Limitations Reference Pack

**Status:** Approved workaround
**Architect Category:** constraints
**Runtime Priority:** medium

This packet is a reference list rather than a generation rule. It catalogues the known weaknesses of Veo discovered through the CLOUDTECH UK session and points the Architect to the specific packet in the library that provides the workaround for each. Unlike the other packets, this one does not contribute prompt content directly — it is a lookup index used at the triage and review stages to confirm that every known weakness in the library has a corresponding mitigation in the assembled prompt set. Its purpose is to make the library self-auditing.

---

## JSON Specification

```json
{
  "veo_specification_packet": {
    "packet_id": "known-veo-limitations-reference-pack",
    "packet_name": "Known Veo Limitations Reference Pack",
    "packet_version": "1.0.0",
    "status": "approved_workaround",
    "architect_category": "constraints",
    "runtime_priority": "medium",
    "evidence": {
      "evidence_type": "qa_check",
      "source_extract": "Session-wide accumulation of failure-fix pairs and limitation-aware decisions: (a) 'Each Veo call with the same text produces plausible but visibly different people' — confirmed empirically when independent text-to-video calls were tested for character consistency. (b) 'Subject removed from frame across multiple extension clips drifts on re-render' — confirmed when the latent textual anchor approach failed and the continuous defocused presence approach succeeded. (c) 'I found that putting in too many restricted items into the negative prompt actually triggers the saftety fitler bizarely' — user finding on safety filter overload. (d) 'Veo is genuinely bad at rendering legible UI — text comes out garbled, logos come out as fake brand impressions, layouts look like stock mockups' — Architect-stated limitation that drove the non-literal rendering technique. (e) Cogs render as industrial regardless of luxury framing — failure-fix replaced with magnifying glass after user feedback 'it looks like the cogs are dangerous'. (f) Anatomical and age-adjacent terms in negative prompts trigger safety filter — user instruction to delete those categories entirely without replacement. Together these limitations form a catalogue of known weaknesses, each cross-referenced to a specific packet in the library that provides the workaround."
    },
    "packet_boundary": {
      "governs": [
        "The reference catalogue of known Veo weaknesses identified through the CLOUDTECH UK session",
        "The cross-reference index from each weakness to the specific packet in the library that provides the workaround",
        "The QA discipline of confirming every applicable weakness has a corresponding mitigation in any assembled prompt set",
        "The triage and review-stage lookup function — used at the start and end of prompt construction, not during"
      ],
      "does_not_govern": [
        "Any individual prompt construction directly — this packet contributes no prompt content",
        "The actual workarounds — those live in the packets this one references",
        "Discovery of new Veo limitations beyond those catalogued here (this packet is a snapshot, not a discovery mechanism)",
        "Decisions about which workarounds to apply — those follow from the applicability rules of the referenced packets"
      ]
    },
    "applicability": {
      "applies_when": [
        "The Architect is reviewing an assembled prompt set before generation to confirm coverage of known weaknesses",
        "The Architect is triaging a new project and needs to identify which limitation-aware packets must be loaded",
        "A generation has produced an unexpected failure mode and the Architect needs to look up which packet should have prevented it",
        "Onboarding a new project or new Architect to the library — this packet is the index document"
      ],
      "must_not_apply_when": [
        "Constructing prompt content directly — this packet does not contribute content",
        "Deciding generation strategy on its own — the strategy follows from the referenced packets",
        "Cataloguing limitations newly discovered after the CLOUDTECH UK session — this packet is a snapshot and must be versioned forward when new limitations are added"
      ]
    },
    "architect_integration": {
      "sequence_override": "none",
      "pre_subject_environment_preamble": [],
      "positive_absence_sentences": [],
      "positive_prompt_injections": {
        "setting_and_layout": [],
        "composition_and_screen_order": [],
        "lighting": []
      },
      "negative_prompt_terms": [],
      "control_vocabulary": {
        "use": [
          "limitation reference",
          "workaround index",
          "cross-reference",
          "self-audit",
          "coverage check"
        ],
        "avoid": [
          "Veo cannot do (without specifying which limitation and which packet provides the workaround)",
          "this is a known issue (without cross-reference)",
          "we worked around this once (without packet citation)"
        ]
      }
    },
    "continuity_rules": {
      "extension_restatement": [],
      "must_lock": [
        "Every limitation in this catalogue must have a corresponding packet citation that provides the workaround",
        "When a new limitation is discovered, this packet must be updated in the same release as the new workaround packet — limitations and workarounds version together",
        "The catalogue is a snapshot, not a discovery mechanism — it documents what is known, not what might be discovered"
      ],
      "reset_strategy": [
        "If a limitation appears in generation that is not catalogued here, the issue is either a regression in Veo's behaviour or a previously-undiscovered limitation — both cases require a new failure-fix iteration and a corresponding new packet, after which this catalogue must be updated",
        "If a packet referenced by this catalogue is renamed, removed, or split, this catalogue must be updated in the same change to maintain index integrity",
        "If a workaround stops working (Veo's behaviour changes), the limitation entry must be flagged for re-investigation rather than treated as solved"
      ]
    },
    "conflict_tags": [
      "reference_pack",
      "applies_to_all_phases",
      "self_audit_index"
    ],
    "operator_note_trigger": "At the triage stage of any new project, scan this catalogue and confirm which limitations apply to the project's scope. Load the corresponding workaround packets. At the review stage of any assembled prompt set, scan this catalogue again and confirm every applicable limitation has its workaround present in the assembled set. Treat this as a self-audit checklist, not as a one-time onboarding read.",
    "visual_acceptance_checks": [
      "Every limitation in the catalogue has a packet citation that names the specific packet providing the workaround",
      "Every named packet in the catalogue exists in the current library version",
      "The catalogue version matches the library version it was generated against",
      "An assembled prompt set under review has every applicable limitation's workaround packet loaded"
    ]
  },
  "limitation_catalogue": [
    {
      "limitation_id": "independent-generation-identity-drift",
      "limitation_name": "Independent text-to-video calls produce visibly different people",
      "evidence_summary": "Each Veo call with identical text produces plausible but visibly different subjects. Confirmed during the CLOUDTECH UK session when independent generation of Scene 1 and Scene 5 was tested as a continuity strategy and failed.",
      "workaround_packet_id": "extension-chain-generation-order",
      "workaround_packet_name": "Packet 08 — Extension Chain Generation Order",
      "supporting_packets": [
        "Packet 01 — Continuous Visible Presence Anchor",
        "Packet 02 — Verbatim Identity Block Propagation"
      ],
      "scope_note": "Use extension mode rather than independent generation for any chain requiring identity continuity. The seed clip becomes the visual reference for all downstream clips."
    },
    {
      "limitation_id": "subject-removed-from-frame-drifts",
      "limitation_name": "Subject removed from frame across multiple extension clips drifts on re-render",
      "evidence_summary": "Veo's extension mode is driven primarily by visible content in the preceding clip, not by textual claims about off-camera state. When the subject is fully removed from frame across multiple B-roll clips, identity drifts on re-render despite verbatim textual anchoring.",
      "workaround_packet_id": "continuous-visible-presence-anchor",
      "workaround_packet_name": "Packet 01 — Continuous Visible Presence Anchor",
      "supporting_packets": [
        "Packet 09 — Diegetic Foreground Visualisation Layering"
      ],
      "scope_note": "Keep the subject visibly in every clip — defocused acceptable, full removal forbidden. Use diegetic foreground layering to deliver service-led B-roll content within the subject's continuous workspace rather than cutting away."
    },
    {
      "limitation_id": "negative-prompt-safety-filter-overload",
      "limitation_name": "Overloaded negative prompts trigger Veo's safety filter",
      "evidence_summary": "User testing finding: 'I found that putting in too many restricted items into the negative prompt actually triggers the saftety fitler bizarely.' The negative prompt array is part of the prompt context — loading it with anatomical, age-adjacent, NSFW, or security-sensitive vocabulary loads the same vocabulary into the model's interpretation, even though the explicit instruction is to exclude.",
      "workaround_packet_id": "negative-prompt-safety-filter-restraint",
      "workaround_packet_name": "Packet 04 — Negative Prompt Safety Filter Restraint",
      "supporting_packets": [
        "Packet 03 — Compliance-Aware Silhouette Description"
      ],
      "scope_note": "Negative prompts handle drift and aesthetic, not content safety. Safety is achieved via positive compliance language. Delete forbidden categories entirely rather than replacing with euphemisms."
    },
    {
      "limitation_id": "anatomical-and-age-terms-trigger-filter",
      "limitation_name": "Anatomical and age-adjacent terms trigger safety filter even in negative prompts",
      "evidence_summary": "User instruction: 'For the negative prompt block, please completely delete any NSFW terms, anatomical/body descriptions, age references (like minor or teenager), and hacking/security terms (like API keys or passwords). Do not replace them, just delete them.' These categories cannot appear anywhere in the prompt context, even when the explicit purpose is exclusion.",
      "workaround_packet_id": "negative-prompt-safety-filter-restraint",
      "workaround_packet_name": "Packet 04 — Negative Prompt Safety Filter Restraint",
      "supporting_packets": [
        "Packet 03 — Compliance-Aware Silhouette Description"
      ],
      "scope_note": "The four forbidden categories — anatomical, age-adjacent, NSFW, security-sensitive — must be deleted entirely from negative prompts. Substitute via positive compliance language using silhouette and tailoring vocabulary in the positive prompt."
    },
    {
      "limitation_id": "ui-text-legibility-unreliable",
      "limitation_name": "Veo cannot reliably render legible UI text or accurate brand impressions",
      "evidence_summary": "Architect-stated limitation: 'Veo is genuinely bad at rendering legible UI — text comes out garbled, logos come out as fake brand impressions, layouts look like stock mockups.' Confirmed across all UI generation iterations during the CLOUDTECH UK session.",
      "workaround_packet_id": "non-literal-ui-and-webpage-rendering",
      "workaround_packet_name": "Packet 11 — Non-Literal UI and Webpage Rendering",
      "supporting_packets": [
        "Packet 10 — Service-Specific Visualisation Vocabulary"
      ],
      "scope_note": "Render UI as the rhythm and shape of real interface copy without specific content. Mask remaining UI weaknesses with live micro-interactions. Use perspective composition for multi-panel displays. Maintain brand neutrality — no real logos, names, or products in synthetic UI."
    },
    {
      "limitation_id": "semantically-loaded-objects-resist-rebranding",
      "limitation_name": "Some objects carry inherent semantic loading that resists framing-based repurposing",
      "evidence_summary": "Cogs failure mode: even when framed as luxury watchmaker movements with premium rendering language, cogs continued to read as industrial or hazardous. User feedback: 'it looks like the cogs are dangerous.' Some objects (cogs, gears, factory machinery, certain weapons, certain religious iconography) cannot be repurposed into a different domain through framing alone.",
      "workaround_packet_id": "service-specific-visualisation-vocabulary",
      "workaround_packet_name": "Packet 10 — Service-Specific Visualisation Vocabulary",
      "supporting_packets": [],
      "scope_note": "Recognise semantically loaded objects at the design stage and substitute entirely rather than refining their rendering. The cogs were replaced with a magnifying glass — a different object with semantic alignment to audit work — and the issue resolved at the design level rather than at the rendering level."
    },
    {
      "limitation_id": "cliché-iconography-defaults",
      "limitation_name": "Veo defaults to cliché iconography for service categories with strong cinematic associations",
      "evidence_summary": "Code visualisations tip toward Matrix-rain hacker aesthetic without explicit guidance. Magnifying glass visualisations tip toward cartoon detective aesthetic without explicit guidance. Webpage visualisations tip toward stock-mockup aesthetic without explicit guidance. Each is a default the model reaches for unless steered away.",
      "workaround_packet_id": "service-specific-visualisation-vocabulary",
      "workaround_packet_name": "Packet 10 — Service-Specific Visualisation Vocabulary",
      "supporting_packets": [
        "Packet 11 — Non-Literal UI and Webpage Rendering"
      ],
      "scope_note": "Catalogue cliché iconography per service category and exclude explicitly. For code: avoid literal Matrix rain, push hacker-adjacent imagery to deep defocused background. For magnifying glass: avoid cartoon detective framing, use luxury jeweller's loupe instead. For webpages: avoid stock-mockup aesthetic, use perspective composition and live micro-interactions."
    },
    {
      "limitation_id": "verbatim-block-paraphrasing-causes-drift",
      "limitation_name": "Even small textual variations between prompts produce visible drift in Veo's output",
      "evidence_summary": "Across the CLOUDTECH UK session, paraphrasing identity blocks, voice blocks, audio blocks, or setting language between prompts in a chain produced visible drift on the corresponding generated attribute. The discipline of byte-identical propagation is not stylistic — it is functional.",
      "workaround_packet_id": "verbatim-identity-block-propagation",
      "workaround_packet_name": "Packet 02 — Verbatim Identity Block Propagation",
      "supporting_packets": [
        "Packet 05 — British RP Voice Identity Block",
        "Packet 06 — Audio Technical Bed Block",
        "Packet 13 — Continuous Workspace Restatement (not yet packetised)"
      ],
      "scope_note": "Treat every continuity-critical block as an immutable string asset. Propagate byte-identical across the chain. Permit only documented variations (energy modifier on closing scene voice block, override clauses at top of identity block for context shift)."
    },
    {
      "limitation_id": "static-framing-monotony",
      "limitation_name": "Static framing across all clips in a chain reads as monotonous regardless of content quality",
      "evidence_summary": "First iteration of the CLOUDTECH UK pack used slow methodical push-ins or lateral drifts in every clip but had no decisive boundary punctuation. Result read as monotonous despite strong content. Adding a single deliberate punch-in at one boundary brought the chain to life.",
      "workaround_packet_id": "punch-in-rhythm-beat",
      "workaround_packet_name": "Packet 12 — Punch-In Rhythm Beat",
      "supporting_packets": [
        "Packet 09 — Diegetic Foreground Visualisation Layering"
      ],
      "scope_note": "At least one rhythm beat per scene pair. Punch-in or rack focus shift, aligned with a content change. Two beats across a five-clip chain is the empirical sweet spot — zero is monotonous, every-boundary is restless."
    },
    {
      "limitation_id": "dialogue-overrun-rushed-delivery",
      "limitation_name": "Dialogue exceeding the per-clip word budget produces rushed delivery that breaks the voice profile",
      "evidence_summary": "Storyboard lines at 27-37 words per scene exceeded the 7-second clip ceiling at British RP pace and produced rushed, unnatural delivery on test renders. Compression to 14-16 words per 7-second clip resolved the issue.",
      "workaround_packet_id": "dialogue-compression-rule",
      "workaround_packet_name": "Packet 07 — Dialogue Compression Rule",
      "supporting_packets": [
        "Packet 05 — British RP Voice Identity Block"
      ],
      "scope_note": "Respect 14-16 words per 7-second clip at British RP pace (2.3 words per second). Compress at draft time, not at delivery time. Do not reach for faster pace as a workaround — that breaks the voice profile."
    },
    {
      "limitation_id": "quoted-speech-renders-as-quotation",
      "limitation_name": "Quotation marks around dialogue cause Veo to render the line as if quoting someone else",
      "evidence_summary": "Across early iterations, dialogue wrapped in quotation marks produced reading-aloud cadence and air-quote inflection rather than direct delivery. The colon convention ('Line delivered on camera: [exact line].') resolved the issue and was locked across all five prompts in the final pack.",
      "workaround_packet_id": "british-rp-voice-identity-block",
      "workaround_packet_name": "Packet 05 — British RP Voice Identity Block",
      "supporting_packets": [],
      "scope_note": "Use the colon convention for all spoken lines: 'Line delivered on camera: [line].' or 'Voiceover line, continuing from the preceding shot with identical voice identity: [line].' Never use quotation marks around dialogue."
    },
    {
      "limitation_id": "mid-chain-regeneration-cascade",
      "limitation_name": "Regenerating a single clip mid-chain does not propagate to downstream clips",
      "evidence_summary": "Veo's extension mechanism inherits visual state from the preceding clip in the chain. Independently regenerated clips do not propagate their state forward — subsequent clips still inherit from the original preceding clip. This causes visible discontinuity that compounds across the chain.",
      "workaround_packet_id": "extension-chain-generation-order",
      "workaround_packet_name": "Packet 08 — Extension Chain Generation Order",
      "supporting_packets": [],
      "scope_note": "When any clip in a chain is regenerated, all downstream clips must be re-extended from the regeneration point. Never patch mid-chain in isolation. Lock the seed clip before chaining begins to minimise the cost of late-stage regeneration."
    }
  ]
}
```

---

## Notes for the Architect

This packet is structurally different from every other packet in the library. It does not contribute prompt content, it does not specify generation rules, and it does not interact with the standard architect phases. Instead, it acts as a self-audit index — a lookup table from "things Veo cannot do reliably" to "the packet that provides the workaround."

A few subtleties worth flagging:

The packet contains an extended `limitation_catalogue` field that is not part of the standard schema. This is a deliberate extension because the packet's value is in the catalogue itself, not in the standard architect_integration fields. The Architect should treat the catalogue as the primary content of this packet and the standard schema fields as metadata about how to use it.

Each catalogue entry follows a fixed structure: a stable id, a human-readable name, an evidence summary tied to specific session events, the primary workaround packet id and name, supporting packet references where multiple packets cooperate on the workaround, and a scope note that summarises the practical implication. This structure is what makes the catalogue navigable — the Architect can scan the limitation names, identify which apply to a project, and follow the citations directly to the packets that provide the workarounds.

The packet's role at the triage stage is to confirm packet selection. When a new project arrives, the Architect scans the catalogue and identifies which limitations apply to the project's scope (does it use voice? does it have UI? does it need character continuity?). For each applicable limitation, the corresponding workaround packet must be loaded into the project's working set.

The packet's role at the review stage is to confirm coverage. Once a prompt set is assembled, the Architect scans the catalogue again and confirms every applicable limitation has its workaround packet present in the assembled set. Missing coverage at this stage is the most common cause of late-stage failure that traces back to a known limitation rather than a novel issue.

The catalogue is explicitly a snapshot, not a discovery mechanism. New limitations discovered after the CLOUDTECH UK session will not appear here until this packet is versioned forward. The `must_lock` rule states that limitations and workarounds version together — when a new workaround packet is added to the library, this catalogue must be updated in the same release to cite it. Otherwise the index drifts out of sync with the library and stops being trustworthy.

The catalogue contains twelve entries. Most reference a single primary workaround packet, with one or more supporting packets where multiple packets cooperate. A few entries reference Packet 13 (Continuous Workspace Restatement) which was not yet packetised at the time of compilation — that reference will resolve when Packet 13 is built. Until then, the verbatim-block-paraphrasing entry's full coverage is incomplete.

The runtime priority is `medium` because this packet is operational at the triage and review stages rather than during prompt construction. Skipping the audit during a project does not break generation directly — it just removes the safety net that catches missing workarounds. The cost is paid in late-stage regeneration when a known limitation surfaces in output.

This packet has the conflict tag `applies_to_all_phases` because its lookup function operates across every architect phase. It also carries `reference_pack` and `self_audit_index` to flag that this is a meta-packet rather than a content-contributing packet. The Architect should treat these tags as signals that the packet's role in any project is administrative rather than constructive.

---

## Library completion summary

The current library is now twelve packets in scope plus this reference index:

01. Continuous Visible Presence Anchor — `critical`, continuity
02. Verbatim Identity Block Propagation — `critical`, continuity
03. Compliance-Aware Silhouette Description — `high`, cast
04. Negative Prompt Safety Filter Restraint — `critical`, constraints
05. British RP Voice Identity Block — `high`, continuity
06. Audio Technical Bed Block — `medium`, style
07. Dialogue Compression Rule — `high`, scene_mechanics
08. Extension Chain Generation Order — `critical`, continuity
09. Diegetic Foreground Visualisation Layering — `high`, scene_mechanics
10. Service-Specific Visualisation Vocabulary — `high`, style
11. Non-Literal UI and Webpage Rendering — `high`, constraints
12. Punch-In Rhythm Beat — `medium`, scene_mechanics
16. Known Veo Limitations Reference Pack — `medium`, constraints (this pack)

Outstanding items from the original triage:
- Packet 13 (Continuous Workspace Restatement) was identified at triage and is referenced by other packets but has not yet been compiled
- Packet 14 (Cool-Toned Architectural Palette Lock) was identified at triage and has not yet been compiled
- Packet 15 (Single-Subject Cast Lock) was identified at triage and has not yet been compiled — a different Packet 15 from the originally-shelved Iteration and Testing Discipline pack
- Packet 15 (Iteration and Testing Discipline, original numbering) was shelved by user instruction for inclusion in the eventual video creation agent prompt rather than as a standalone data pack

The library is functional in its current state for projects matching the CLOUDTECH UK scope. For projects with different scope, the missing packets (13, 14, the new 15) may need compilation before the library provides full coverage.
