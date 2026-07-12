# Packet 05 — British RP Voice Identity Block

**Status:** Approved workaround
**Architect Category:** continuity
**Runtime Priority:** high

This packet captures the dedicated voice description block developed during the CLOUDTECH UK session to lock voice identity across an extension chain in Complete or Audio Mode. Without a structured voice block, Veo's audio generation drifts between accents, timbres, and delivery styles even when the same line is spoken in adjacent clips. The block specifies accent, tone, timbre, pitch, pace, articulation, warmth, delivery style, and explicit exclusions, and must be propagated byte-identical across every prompt in the chain.

---

## JSON Specification

```json
{
  "veo_specification_packet": {
    "packet_id": "british-rp-voice-identity-block",
    "packet_name": "British RP Voice Identity Block",
    "packet_version": "1.0.0",
    "status": "approved_workaround",
    "architect_category": "continuity",
    "runtime_priority": "high",
    "evidence": {
      "evidence_type": "exact_phrase",
      "source_extract": "User instruction: 'as these prompts all contain voiceover, we need to use the same detailed prompt method that we are using to describe the narrator, as we are to her voice. Can you please update the prompts with this detailed consistant voiceover style and tone across all 5 prompts.' Locked block built and propagated verbatim: 'She speaks in a clear, polished British Received Pronunciation adult female voice. Her tone is warm, bright, and confident, with the composed authority of a senior consultant and the approachable energy of a peer rather than a pitch. Her timbre is naturally feminine, light but grounded, with soft warmth in the lower register and clarity in the upper register. Her pitch is in a comfortable mid-range without being high or breathy. Her pace is measured and natural at roughly two and a third words per second, unhurried but forward-moving, with clean articulation on consonants and relaxed vowels. She speaks with genuine engagement, subtle warmth in inflection, and natural rising and falling phrasing rather than a flat newsreader cadence. She does not whisper, narrate dramatically, or perform; she speaks as a professional welcoming a client into a conversation. Her delivery is smooth, dignified, and trustworthy, with no vocal fry, no upspeak, no breathiness, and no American or regional inflection.'"
    },
    "packet_boundary": {
      "governs": [
        "The structure and content of the voice description block (accent, tone, timbre, pitch, pace, articulation, delivery, exclusions)",
        "The placement of the voice block within the assembled prompt (after camera and composition, before line delivery)",
        "Permitted variation on the closing scene's voice block (single energy modifier sentence with mandatory preserving clause)",
        "The labelled-subsection format ('Voice.' label terminator) and its byte-identical propagation"
      ],
      "does_not_govern": [
        "Dialogue word count or compression (handled by Dialogue Compression Rule)",
        "Audio recording environment, ambient bed, music exclusions (handled by Audio Technical Bed Block)",
        "Line delivery notation conventions for actual spoken text (handled by Dialogue Compression Rule)",
        "Subject visual identity (handled by Compliance-Aware Silhouette Description and Verbatim Identity Block Propagation)",
        "Mode selection (handled by Mode Handling — not yet packetised)"
      ]
    },
    "applicability": {
      "applies_when": [
        "Veo Complete Mode or Audio Mode is active and a single voice identity must persist across two or more chained clips",
        "The same speaker delivers dialogue in non-adjacent scenes (e.g. opening narrator returning for closing CTA)",
        "Voiceover continues across B-roll scenes where the speaker is not on camera but voice continuity is required"
      ],
      "must_not_apply_when": [
        "Veo Default Mode (silent video) is active",
        "Each clip uses a different speaker by design (multi-narrator piece, character dialogue scenes)",
        "The video has no spoken dialogue or voiceover at all",
        "The user has explicitly mandated a different accent or voice profile (in which case the block content changes but the structural rules in this packet still apply)"
      ]
    },
    "architect_integration": {
      "sequence_override": "none",
      "pre_subject_environment_preamble": [],
      "positive_absence_sentences": [],
      "positive_prompt_injections": {
        "setting_and_layout": [],
        "composition_and_screen_order": [
          "Voice block placement: after the camera and composition section, before the line delivery sentence. Block opens with 'Voice.' as a labelled subsection (full stop after the label).",
          "Voice block structure (mandatory order): accent → tone → timbre → pitch → pace → articulation → delivery style → exclusions.",
          "Mandatory exclusions sentence at end of voice block: 'no vocal fry, no upspeak, no breathiness, and no American or regional inflection' (or the equivalent for non-RP voices).",
          "Line delivery follows the voice block as a separate sentence using the 'colon convention': 'Line delivered on camera: [exact line].' or 'Voiceover line, continuing from the preceding shot with identical voice identity: [exact line].' — never quotation marks for speech.",
          "Closing scene permitted variation: a single energy modifier sentence appended to the voice block (e.g. 'On this closing line her delivery carries slightly warmer, more engaged energy than the opening — an invitation rather than a pitch — while preserving the same identical voice identity throughout.'). The closing clause 'while preserving the same identical voice identity throughout' is mandatory whenever an energy modifier is used."
        ],
        "lighting": []
      },
      "negative_prompt_terms": [
        "different voice",
        "voice changing between clips",
        "American accent",
        "Australian accent",
        "Irish accent",
        "Scottish accent",
        "regional British accent",
        "cockney accent",
        "estuary accent",
        "breathy voice",
        "whispered voice",
        "vocal fry",
        "upspeak",
        "rising terminal inflection",
        "nasal voice",
        "flat newsreader cadence",
        "dramatic narration",
        "theatrical voice",
        "autotuned voice",
        "robotic voice",
        "synthesised text-to-speech artefacts"
      ],
      "control_vocabulary": {
        "use": [
          "Voice.",
          "British Received Pronunciation adult female voice",
          "British Received Pronunciation adult male voice",
          "warm, bright, and confident",
          "composed authority of a senior consultant",
          "approachable energy of a peer rather than a pitch",
          "naturally feminine timbre, light but grounded",
          "soft warmth in the lower register and clarity in the upper register",
          "comfortable mid-range pitch",
          "measured and natural pace at roughly two and a third words per second",
          "unhurried but forward-moving",
          "clean articulation on consonants and relaxed vowels",
          "genuine engagement, subtle warmth in inflection",
          "natural rising and falling phrasing",
          "smooth, dignified, and trustworthy delivery",
          "speaks as a professional welcoming a client into a conversation",
          "Line delivered on camera:",
          "Voiceover line, continuing from the preceding shot with identical voice identity:",
          "while preserving the same identical voice identity throughout"
        ],
        "avoid": [
          "voice (without dedicated block)",
          "narrator says (without delivery framing)",
          "she speaks (without timbre and pace specification)",
          "speaks confidently (vague delivery)",
          "professional voice (vague timbre)",
          "British accent (vague — must specify Received Pronunciation or named regional)",
          "quotation marks around spoken lines",
          "as previously described (paraphrasing the voice block)",
          "same voice as before (paraphrasing the voice block)"
        ]
      }
    },
    "continuity_rules": {
      "extension_restatement": [
        "The full voice block must appear byte-identical in every prompt of the chain where dialogue or voiceover is present — paraphrasing or shortening causes drift on the corresponding generated audio (governed jointly with Verbatim Identity Block Propagation packet)",
        "Even on B-roll scenes where the speaker is not on camera, the voice block must appear if voiceover continues — the line delivery sentence then uses the 'Voiceover line, continuing from the preceding shot with identical voice identity:' framing instead of the 'Line delivered on camera:' framing",
        "The block's structural order (accent → tone → timbre → pitch → pace → articulation → delivery → exclusions) must not be reordered between prompts"
      ],
      "must_lock": [
        "The full voice block content (every word, every comma, every sentence order)",
        "The accent specification (e.g. 'British Received Pronunciation adult female voice')",
        "The exclusions sentence at end of block",
        "The line delivery framing convention (colon, never quotation marks)",
        "The placement of the voice block within the prompt structure"
      ],
      "reset_strategy": [
        "If voice drifts on a downstream extension despite the voice block being present, audit the block for accidental paraphrasing or reordering — even small word changes cause drift",
        "If the closing scene's energy modifier sentence is causing voice drift, remove the modifier and rely on the standard block — the modifier is optional, the block is mandatory",
        "If a prompt contains dialogue but no voice block, treat as a critical defect and add the block before generation"
      ]
    },
    "conflict_tags": [
      "requires_complete_or_audio_mode",
      "requires_locked_speaker",
      "forbids_quotation_marks_for_speech",
      "forbids_paraphrasing"
    ],
    "operator_note_trigger": "Before approving any prompt with dialogue or voiceover, confirm the voice block is present and byte-identical to the seed prompt's voice block. Confirm the line delivery uses the colon convention, never quotation marks. On the closing scene, if an energy modifier is used, confirm the mandatory preserving clause is appended.",
    "visual_acceptance_checks": [
      "Voice block is present in every prompt with dialogue or voiceover",
      "Voice block is byte-identical across the chain (excluding permitted closing-scene energy modifier)",
      "Line delivery uses the colon convention, never quotation marks",
      "Generated voice across all clips reads as the same speaker on playback",
      "No accent drift between clips",
      "No timbre, pitch, or pace drift between clips",
      "Closing scene voice identity matches opening scene voice identity"
    ]
  }
}
```

---

## Notes for the Architect

This packet is the audio counterpart to Compliance-Aware Silhouette Description. Where that packet specifies how to describe the visible subject, this packet specifies how to describe the audible subject. Both packets must be propagated byte-identical across the chain (governed by Verbatim Identity Block Propagation), and both packets carry their own internal structural rules.

A few subtleties worth flagging:

The block's structural order — accent first, then tone, timbre, pitch, pace, articulation, delivery, exclusions — is not arbitrary. It mirrors how a casting director or voice coach would describe a voice on a brief, and Veo appears to interpret it more reliably in this order. Reordering subsections between prompts (for example, putting pace before timbre in one clip and after timbre in another) caused measurable drift during the CLOUDTECH UK iterations.

The exclusions sentence at the end of the block is doing dual work. It tells the generator what to avoid, and it acts as a context anchor signalling that the voice profile is professional and grounded rather than performative or stylised. Dropping the exclusions sentence raised the rate of vocal fry and upspeak artefacts even when the rest of the block was intact.

The colon convention for line delivery — "Line delivered on camera: [exact line]." — is one of the strongest findings of the session. Quotation marks around dialogue caused Veo to render the line as if the character were quoting someone else, sometimes with reading-aloud cadence and air-quote inflection. The colon convention reads as a direct delivery instruction. This is captured as a hard rule via `forbids_quotation_marks_for_speech` in the conflict tags.

The closing-scene energy modifier is the only permitted variation on the voice block, and even that variation must include the mandatory preserving clause "while preserving the same identical voice identity throughout." Without that clause, Veo interprets the energy modifier as a request for a slightly different voice rather than the same voice with slightly different delivery.

The packet boundary deliberately separates voice identity from audio environment. The recording space character, ambient drone, and music exclusions are all governed by Packet 06 (Audio Technical Bed Block), which loads alongside this packet. Together they form the complete audio specification, but they remain modular so the Architect can swap one without rewriting the other — for example, generating the same speaker in a different acoustic space.

This packet co-loads with Verbatim Identity Block Propagation (which propagates the voice block across the chain), Audio Technical Bed Block (which handles the acoustic environment), and Dialogue Compression Rule (which governs line word count and brand placement). All four together comprise the full audio architecture for an extension chain with continuous voice.

Ready for Packet 06 — Audio Technical Bed Block — when you give the word.
