# Packet 04 — Negative Prompt Safety Filter Restraint

**Status:** Approved workaround
**Architect Category:** constraints
**Runtime Priority:** critical

This packet captures the counter-intuitive negative prompt discipline discovered late in the CLOUDTECH UK session. Overloaded negative prompts containing too many restricted terms — particularly anatomical, age-adjacent, NSFW, and security-sensitive language — can themselves trigger Veo's safety filter, even when the positive prompt is fully compliant. The negative prompt is for controlling drift and aesthetic failure, not for content safety; safety is handled by the positive prompt's compliance language.

---

## JSON Specification

```json
{
  "veo_specification_packet": {
    "packet_id": "negative-prompt-safety-filter-restraint",
    "packet_name": "Negative Prompt Safety Filter Restraint",
    "packet_version": "1.0.0",
    "status": "approved_workaround",
    "architect_category": "constraints",
    "runtime_priority": "critical",
    "evidence": {
      "evidence_type": "failure_fix_pair",
      "source_extract": "User finding: 'I found that putting in too many restricted items into the negative prompt actually triggers the saftety fitler bizarely.' User instruction: 'For the negative prompt block, please completely delete any NSFW terms, anatomical/body descriptions, age references (like minor or teenager), and hacking/security terms (like API keys or passwords). Do not replace them, just delete them. Keep the rest of the negative prompt exactly the same.' Failure: prompts with sprawling negative arrays containing terms like 'narrow chest', 'flat chest', 'minor', 'teenager', 'API keys', 'passwords' began triggering safety filter rejections despite compliant positive prompts. Fix: deleted forbidden categories entirely, retained only drift-control and aesthetic-control entries — generation rate stabilised."
    },
    "packet_boundary": {
      "governs": [
        "What categories of terms may appear in the negative prompt array",
        "What categories of terms must never appear in the negative prompt array",
        "The construction principle that negative prompts control drift and aesthetic failure, not content safety",
        "The deletion rule (delete forbidden categories, do not replace with euphemisms)"
      ],
      "does_not_govern": [
        "Positive prompt content (handled by Compliance-Aware Silhouette Description and other content packets)",
        "Positive absence sentences in the main prompt body",
        "The constraints block at the end of the positive prompt",
        "Whether content safety is achieved (achieved via positive compliance language, not negatives)"
      ]
    },
    "applicability": {
      "applies_when": [
        "Constructing or revising any negative prompt array for a Veo generation",
        "A previously-working prompt has begun triggering safety filter rejections after negative prompt expansion",
        "An Architect is tempted to add anatomical or age-adjacent exclusions to reinforce compliance"
      ],
      "must_not_apply_when": [
        "Constructing positive prompt content (different rules govern positive language)",
        "Constructing the positive prompt's constraints block (handled by Compliance-Aware Silhouette Description)",
        "Constructing positive absence sentences (different rules govern those)"
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
          "different presenter",
          "different hair",
          "different face",
          "different makeup",
          "different setting",
          "different lighting",
          "different voice",
          "voice changing between clips",
          "wardrobe change",
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
          "synthesised text-to-speech artefacts",
          "narrow eyes",
          "sleepy eyes",
          "half-closed eyes",
          "tired expression",
          "stern expression",
          "flat expression",
          "closed mouth",
          "pursed lips",
          "serious face",
          "frown",
          "dull gaze",
          "frumpy appearance",
          "dowdy styling",
          "older woman",
          "non-English appearance",
          "dark hair",
          "brown hair",
          "black hair",
          "red hair",
          "short hair",
          "bob",
          "tight updo",
          "brown eyes",
          "green eyes",
          "hazel eyes",
          "tanned skin",
          "dark complexion",
          "angular jaw",
          "harsh features",
          "puff sleeves",
          "sheer organza",
          "ornamental buttons",
          "ruffles",
          "loose fitting clothing",
          "casual wear",
          "warm tones",
          "golden light",
          "orange light",
          "yellow cast",
          "saturated colours",
          "corporate lobby",
          "glass boardroom",
          "open-plan office",
          "branded signage",
          "logos",
          "readable text",
          "rendered text",
          "legible code",
          "legible UI",
          "captions",
          "subtitles",
          "burned-in subtitles",
          "on-screen text",
          "watermarks",
          "second person",
          "any other people",
          "passersby",
          "figures in background",
          "silhouettes",
          "reflections of people",
          "stock photography look",
          "bouncy animation",
          "handheld shake",
          "harsh direct flash",
          "dark environment",
          "cluttered background",
          "music with melody",
          "music with beats",
          "vocal samples",
          "sound effects",
          "reverb",
          "echo",
          "room noise",
          "background chatter"
        ],
        "avoid": [
          "any anatomical body part name",
          "any body part size descriptor",
          "any sexual or sexualised adjective",
          "minor",
          "teenager",
          "underage",
          "childlike",
          "child appearance",
          "any age-adjacent term",
          "API keys",
          "passwords",
          "credentials",
          "exploit",
          "vulnerability",
          "any security-sensitive token",
          "explicit",
          "nudity",
          "nude",
          "naked",
          "lingerie",
          "underwear",
          "any NSFW token",
          "any term describing the absence of clothing",
          "any term describing the visibility of skin in private areas"
        ]
      }
    },
    "continuity_rules": {
      "extension_restatement": [
        "The negative prompt array does not need to be byte-identical across the chain — unlike positive identity blocks — but it must follow the same construction rules in every prompt of the chain",
        "Drift-control terms (different presenter, different voice, wardrobe change) must appear in every chained prompt to reinforce continuity",
        "Aesthetic-control terms (warm tones, saturated colours, bouncy animation) must appear in every chained prompt to reinforce palette and motion lock"
      ],
      "must_lock": [
        "The deletion rule: forbidden category terms are deleted entirely, never replaced with euphemisms or coded language",
        "The construction principle: negative prompts handle drift and aesthetic, not safety",
        "The category boundaries: anatomical, age-adjacent, NSFW, and security-sensitive terms are forbidden categories regardless of intent"
      ],
      "reset_strategy": [
        "If a prompt is flagged despite a compliant positive prompt, audit the negative array first for any token from the avoid list — the issue is more often in the negatives than in the positives",
        "If the user asks for stronger safety enforcement, do not expand the negative prompt — instead strengthen the positive constraints block, the tail clause, and the tone framing block (governed by Compliance-Aware Silhouette Description)",
        "If a previously-working prompt breaks after negative prompt expansion, revert to the smaller negative array — the addition was the cause"
      ]
    },
    "conflict_tags": [
      "forbids_anatomical_terms",
      "forbids_age_adjacent_terms",
      "forbids_security_terms",
      "forbids_nsfw_terms",
      "applies_to_all_phases"
    ],
    "operator_note_trigger": "Before submitting any prompt to Veo, scan the negative prompt array for any token in the avoid list. If found, delete entirely without replacement. If a previously-working prompt has begun triggering safety filter rejections, the negative array is the most likely cause — audit it before adjusting the positive prompt.",
    "visual_acceptance_checks": [
      "Negative prompt array contains zero anatomical body part names",
      "Negative prompt array contains zero age-adjacent terms (minor, teenager, childlike, etc.)",
      "Negative prompt array contains zero NSFW or sexualised terms",
      "Negative prompt array contains zero security-sensitive tokens",
      "Every term in the negative prompt array is justifiable as drift control or aesthetic control",
      "Prompt generates without safety filter rejection"
    ]
  }
}
```

---

## Notes for the Architect

This packet captures one of the most counter-intuitive findings of the CLOUDTECH UK session and one of the most important. The reflexive instinct of any Architect — particularly one trained on safety-first prompt engineering principles — is to add more exclusions to the negative prompt to reinforce compliance. This packet says: do the opposite.

A few subtleties worth flagging:

The negative prompt array is read by the same model that processes the positive prompt. It is not a separate filter system — it is part of the prompt context. When that array contains anatomical terms, age-adjacent terms, or NSFW vocabulary, the model interprets the entire prompt as being about those concepts, even though the explicit instruction is to *exclude* them. The result is that a fully clothed, dignified, professional scene gets flagged because the negative prompt has loaded the context with sexualised vocabulary.

This is why the deletion rule is strict — "delete entirely without replacement." Replacing with euphemisms (e.g. swapping "flat chest" for "boyish silhouette") still loads the context with body-focused language. The only safe move is to remove the term entirely and rely on the positive prompt's compliance language to handle the requirement.

The control vocabulary's `use` list is deliberately exhaustive. It documents every category of negative term that *is* safe to include — drift control across identity, voice, accent, expression, wardrobe, palette, setting, composition, audio, and aesthetic failure modes. The Architect can pull from this list freely to construct the negative array for any given scene. The `avoid` list documents the categories that must never appear regardless of how they are worded.

The packet's `negative_prompt_terms` array is intentionally empty. This packet does not contribute terms to the negative array — it governs the *construction rules* for the array. The Architect uses the `use` vocabulary to populate the array based on the specific scene's drift-control needs.

The reset strategy carries the diagnostic logic: if a previously-working prompt starts failing after a negative prompt expansion, the expansion is the cause. This is the empirical finding from the user's own testing during the CLOUDTECH UK session.

This packet co-loads with Compliance-Aware Silhouette Description (which handles the positive-prompt compliance work this packet relies on) and Verbatim Identity Block Propagation (which carries the drift-control discipline forward across the chain). The conflict tag `applies_to_all_phases` flags that this packet's rules apply universally to any prompt construction, regardless of architect phase.

Ready for Packet 05 — British RP Voice Identity Block — when you give the word.
