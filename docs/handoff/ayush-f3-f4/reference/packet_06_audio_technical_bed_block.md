# Packet 06 — Audio Technical Bed Block

**Status:** Approved workaround
**Architect Category:** style
**Runtime Priority:** medium

This packet captures the dedicated audio environment block developed during the CLOUDTECH UK session to lock the acoustic character of the voice across an extension chain. Without an explicit audio technical block, Veo introduces inconsistent reverb, room noise, ambient music with melody, or sound effects between clips even when the voice block itself is locked. The block specifies recording space character, acoustic exclusions, ambient bed behaviour, and music and SFX exclusions, and must be propagated byte-identical across every prompt where audio is generated.

---

## JSON Specification

```json
{
  "veo_specification_packet": {
    "packet_id": "audio-technical-bed-block",
    "packet_name": "Audio Technical Bed Block",
    "packet_version": "1.0.0",
    "status": "approved_workaround",
    "architect_category": "style",
    "runtime_priority": "medium",
    "evidence": {
      "evidence_type": "exact_phrase",
      "source_extract": "Locked block built and propagated verbatim across all five prompts: 'Audio technical. The voice is recorded clean and close as though captured on a professional broadcast microphone in a treated space, dry and intimate with no reverb tail, no echo, and no room noise. A minimal low-frequency ambient drone sits subtly underneath the voice throughout, barely audible, with no beats, no melody, and no vocal samples. No sound effects. No music with melody or rhythm.' Closing-scene variation permitted on drone behaviour: 'beginning to fade gently by the end of the clip'. Block was added in the same iteration that introduced the voice block, in response to user instruction to extend voice-level description discipline to the audio dimension."
    },
    "packet_boundary": {
      "governs": [
        "The structure and content of the audio technical block (recording space, acoustic exclusions, ambient bed, music exclusions, SFX exclusions)",
        "The placement of the audio technical block within the assembled prompt (immediately after the voice block and line delivery)",
        "The labelled-subsection format ('Audio technical.' label terminator) and its byte-identical propagation",
        "Permitted closing-scene variation on ambient bed behaviour (fade out)"
      ],
      "does_not_govern": [
        "Voice identity, accent, timbre, pitch, pace (handled by British RP Voice Identity Block)",
        "Dialogue word count or brand placement (handled by Dialogue Compression Rule)",
        "Line delivery framing convention (handled by British RP Voice Identity Block)",
        "Visual setting or environment (handled by Continuous Workspace Restatement)",
        "Mode selection (handled separately)"
      ]
    },
    "applicability": {
      "applies_when": [
        "Veo Complete Mode or Audio Mode is active",
        "A consistent acoustic environment must persist across two or more chained clips",
        "Voiceover continues across scenes and the audio bed must remain seamless",
        "The video requires a clean, dry, intimate vocal recording aesthetic appropriate for corporate, documentary, or editorial work"
      ],
      "must_not_apply_when": [
        "Veo Default Mode (silent video) is active",
        "The video has no spoken dialogue or voiceover at all",
        "The user has explicitly mandated a different acoustic profile (live ambient, on-location reverb, music-led piece) — in which case the block content changes but the structural rules in this packet still apply",
        "The video is a music-led piece where ambient drone exclusion would conflict with the brief"
      ]
    },
    "architect_integration": {
      "sequence_override": "none",
      "pre_subject_environment_preamble": [],
      "positive_absence_sentences": [],
      "positive_prompt_injections": {
        "setting_and_layout": [],
        "composition_and_screen_order": [
          "Audio technical block placement: immediately after the voice block and line delivery sentence, before the tone framing block. Block opens with 'Audio technical.' as a labelled subsection (full stop after the label).",
          "Audio technical block structure (mandatory order): recording space character → acoustic exclusions → ambient bed specification → music exclusions → SFX exclusions.",
          "Recording space anchor: 'recorded clean and close as though captured on a professional broadcast microphone in a treated space, dry and intimate' — this phrase acts as a context anchor for the model and should not be paraphrased.",
          "Acoustic exclusions sentence: 'with no reverb tail, no echo, and no room noise' — these three exclusions are mandatory and must appear together.",
          "Ambient bed specification: 'A minimal low-frequency ambient drone sits subtly underneath the voice throughout, barely audible' — the 'barely audible' qualifier is required to prevent the drone from competing with the voice.",
          "Music and vocal exclusions: 'with no beats, no melody, and no vocal samples' — these three exclusions are mandatory and must appear together.",
          "SFX exclusion sentence: 'No sound effects.' — short, declarative, mandatory.",
          "Music exclusion closing sentence: 'No music with melody or rhythm.' — reinforces the ambient-only audio bed.",
          "Closing scene permitted variation on ambient bed: append 'beginning to fade gently by the end of the clip' to the ambient bed specification sentence. No other variations permitted."
        ],
        "lighting": []
      },
      "negative_prompt_terms": [
        "music with melody",
        "music with beats",
        "vocal samples",
        "sound effects",
        "reverb",
        "echo",
        "room noise",
        "background chatter"
      ],
      "control_vocabulary": {
        "use": [
          "Audio technical.",
          "recorded clean and close",
          "as though captured on a professional broadcast microphone",
          "in a treated space",
          "dry and intimate",
          "no reverb tail",
          "no echo",
          "no room noise",
          "minimal low-frequency ambient drone",
          "sits subtly underneath the voice throughout",
          "barely audible",
          "no beats",
          "no melody",
          "no vocal samples",
          "No sound effects.",
          "No music with melody or rhythm.",
          "beginning to fade gently by the end of the clip"
        ],
        "avoid": [
          "background music (without ambient-only qualifier)",
          "atmospheric music (vague — implies melody)",
          "soundtrack (implies melodic music)",
          "score (implies melodic music)",
          "ambient track (vague — could imply melody)",
          "natural acoustics (implies untreated space)",
          "live recording (implies room noise and reverb)",
          "rich audio (implies music or SFX layering)",
          "immersive soundscape (implies SFX layering)",
          "as previously described (paraphrasing the audio block)",
          "same audio as before (paraphrasing the audio block)"
        ]
      }
    },
    "continuity_rules": {
      "extension_restatement": [
        "The full audio technical block must appear byte-identical in every prompt of the chain where audio is generated — paraphrasing or shortening causes drift on the corresponding generated audio bed (governed jointly with Verbatim Identity Block Propagation packet)",
        "Even on B-roll scenes where the speaker is not on camera but voiceover continues, the audio technical block must appear identically — the ambient bed must remain seamless across the chain",
        "The block's structural order (recording space → acoustic exclusions → ambient bed → music exclusions → SFX exclusions) must not be reordered between prompts",
        "The phrase 'continues seamlessly underneath the voice throughout' may replace 'sits subtly underneath the voice throughout' on extension prompts to reinforce continuity from the seed clip"
      ],
      "must_lock": [
        "The full audio technical block content (every word, every comma, every sentence order)",
        "The recording space anchor phrase",
        "The acoustic exclusions sentence (no reverb tail, no echo, no room noise)",
        "The ambient bed specification (minimal low-frequency drone, barely audible)",
        "The music and SFX exclusion sentences",
        "The placement of the audio technical block within the prompt structure"
      ],
      "reset_strategy": [
        "If the audio bed drifts on a downstream extension despite the block being present, audit the block for accidental paraphrasing or reordering — even small word changes cause drift",
        "If music with melody or rhythm appears in generated audio despite the exclusions, strengthen the exclusion sentences (e.g. add 'no instrumental music, no orchestral score, no rhythmic backing track') rather than removing them — but only as a last resort, since this risks tripping the safety filter restraint rule",
        "If room noise or reverb appears in generated audio despite the exclusions, audit the recording space anchor phrase — the 'treated space, dry and intimate' framing is doing critical context work and must be present",
        "If a prompt contains audio but no audio technical block, treat as a critical defect and add the block before generation"
      ]
    },
    "conflict_tags": [
      "requires_complete_or_audio_mode",
      "forbids_melodic_music",
      "forbids_paraphrasing"
    ],
    "operator_note_trigger": "Before approving any prompt with audio generation, confirm the audio technical block is present and byte-identical to the seed prompt's block. On the closing scene, if the fade-out variation is used, confirm it is appended to the ambient bed sentence and not inserted elsewhere in the block.",
    "visual_acceptance_checks": [
      "Audio technical block is present in every prompt with dialogue or voiceover",
      "Audio technical block is byte-identical across the chain (excluding permitted closing-scene fade-out variation)",
      "Generated audio bed across all clips is seamless and consistent on playback",
      "No reverb, echo, or room noise appears in generated voice across any clip",
      "Ambient drone is present, low-frequency, and barely audible — does not compete with voice",
      "No music with melody, beats, or vocal samples appears in generated audio",
      "No sound effects appear in generated audio",
      "Closing scene drone fades gently as specified, final beat reaches silence cleanly"
    ]
  }
}
```

---

## Notes for the Architect

This packet is the acoustic counterpart to Packet 05 (British RP Voice Identity Block). Where that packet locks who is speaking, this packet locks the room they are speaking in and what is happening underneath them in the audio bed. Both packets must be propagated byte-identical across the chain, and both packets co-load alongside Verbatim Identity Block Propagation as a matter of course.

A few subtleties worth flagging:

The recording space anchor — "recorded clean and close as though captured on a professional broadcast microphone in a treated space, dry and intimate" — is doing significant context work for Veo's audio model. The phrase signals a specific aesthetic (broadcast, intimate, treated) that the model interprets as a recording style rather than as separate adjectives. Splitting the phrase or paraphrasing it consistently degraded the result during the CLOUDTECH UK iterations. Treat this phrase as a single immutable token.

The ambient bed specification has a subtle requirement that earned its place through testing: the "barely audible" qualifier prevents the drone from competing with the voice. Without that qualifier, Veo sometimes generated a drone at conversational volume, which made the voice harder to hear and broke the dry-and-intimate aesthetic the recording space anchor establishes. The qualifier is mandatory, not optional.

The block contains three discrete exclusion sentences in a deliberate sequence: acoustic exclusions ("no reverb tail, no echo, and no room noise"), then music exclusions ("with no beats, no melody, and no vocal samples"), then SFX exclusions ("No sound effects.") and finally a music exclusion closer ("No music with melody or rhythm."). This redundancy is deliberate. Each exclusion sentence acts on a different category of audio artefact, and the closing music exclusion sentence reinforces the ambient-only directive against late-stage classifier interpretation. Do not consolidate these into a single sentence to save tokens — the redundancy is functional.

The closing-scene fade variation is the only permitted change to the block. The variation is "beginning to fade gently by the end of the clip" appended to the ambient bed sentence, producing: "A minimal low-frequency ambient drone sits subtly underneath the voice throughout, barely audible, with no beats, no melody, and no vocal samples, beginning to fade gently by the end of the clip." This is the exact phrasing locked in the final CLOUDTECH UK Scene 5 prompt. Other variations (different fade timing, fade-out from earlier in the clip, hard cut to silence) were not tested and are not part of this packet.

The reset strategy includes an important warning: if music with melody appears despite the exclusions, the instinct is to add more exclusion terms. Resist that instinct — it tips toward overloading the negative prompt domain (governed by Packet 04, Negative Prompt Safety Filter Restraint) and can trigger the safety filter paradox. The recording space anchor phrase doing its job is more reliable than expanded exclusions.

This packet co-loads with British RP Voice Identity Block (or whatever voice block applies to the project), Verbatim Identity Block Propagation (which carries this block byte-identical across the chain), and Dialogue Compression Rule (which governs the actual line word count). All four together comprise the full audio architecture.

The runtime priority is `medium` rather than `high` because audio drift is less project-killing than visual identity drift — a slight reverb tail change between clips is noticeable but recoverable, whereas a different face on the closing CTA is unrecoverable. That said, audio drift compounds quickly across a chain, so the discipline still matters.

Ready for Packet 07 — Dialogue Compression Rule — when you give the word.
