# Packet 01 — Continuous Visible Presence Anchor

**Status:** Candidate
**Architect Category:** continuity
**Runtime Priority:** critical

This packet captures the most important continuity discovery from the CLOUDTECH UK video session: a recurring human subject must remain visibly present in every Veo-extended clip — even softly defocused — to preserve identity through the extension chain. Removing the subject from frame and relying on textual description alone causes the chain to drift on re-render.

---

## JSON Specification

```json
{
  "veo_specification_packet": {
    "packet_id": "continuous-visible-presence-anchor",
    "packet_name": "Continuous Visible Presence Anchor",
    "packet_version": "1.0.0",
    "status": "approved_workaround",
    "architect_category": "continuity",
    "runtime_priority": "critical",
    "evidence": {
      "evidence_type": "failure_fix_pair",
      "source_extract": "User testing finding: 'the more the character stays in the frame, the more consistant and stable her appearence will be. The more she becomes obscured, small changes beging to creep in. So in essence, she needs to be in every scene, but some level of obscuring is completely fine, as long as it doesn't completely obscure her. Then Veo doesn't bother to render her, and when it picks back off, when it needs to rerender her, it doesn't always match the original character perfectly.' Failure: latent textual anchor with subject removed from frame across three B-roll clips drifted identity on Scene 5 re-render. Fix: keep subject visibly in every clip, defocused acceptable, and the extension chain holds identity."
    },
    "packet_boundary": {
      "governs": [
        "Whether and how a recurring subject must appear in every clip of an extension chain",
        "Acceptable obscuring techniques that preserve identity (defocus, background positioning)",
        "Forbidden obscuring techniques that cause identity drift (full removal, full silhouette only, full reflection only)"
      ],
      "does_not_govern": [
        "Foreground content design or visualisation selection",
        "Camera language, framing, or shot scale",
        "Wardrobe, hair, makeup, or identity block content",
        "Voice or audio specification"
      ]
    },
    "applicability": {
      "applies_when": [
        "A recurring human subject must persist across two or more chained Veo clips",
        "Veo extension mode is being used to generate the chain",
        "Identity continuity between scenes is a hard requirement (e.g. opening narrator returning for closing CTA)"
      ],
      "must_not_apply_when": [
        "The subject is genuinely absent from the narrative for that beat (different location, off-screen)",
        "The video is a single standalone Veo clip with no chain",
        "Each clip is independently generated as text-to-video with no extension dependency",
        "The narrative explicitly requires a full scene reset to a different setting and different cast"
      ]
    },
    "architect_integration": {
      "sequence_override": "none",
      "pre_subject_environment_preamble": [],
      "positive_absence_sentences": [],
      "positive_prompt_injections": {
        "setting_and_layout": [
          "kept continuously in frame to preserve identity",
          "softly defocused with a shallow depth of field"
        ],
        "composition_and_screen_order": [
          "present in the background of the frame slightly left of centre",
          "softly defocused in the background throughout",
          "her identity in the background bokeh is what anchors the extension chain",
          "clearly the same person from the opening shot, kept continuously present in frame to preserve identity"
        ],
        "lighting": []
      },
      "negative_prompt_terms": [
        "the presenter disappearing from frame",
        "subject removed from shot",
        "empty workspace without subject",
        "full silhouette only",
        "reflection only with no direct view"
      ],
      "control_vocabulary": {
        "use": [
          "kept continuously in frame to preserve identity",
          "softly defocused with a shallow depth of field",
          "present in the background",
          "clearly recognisable in the background bokeh",
          "calm posture, minimal natural movement",
          "softly defocused in the mid-plane"
        ],
        "avoid": [
          "off-camera",
          "absent from this shot",
          "implied presence",
          "narrator-free B-roll",
          "human-free scene",
          "the subject is not visible in this frame"
        ]
      }
    },
    "continuity_rules": {
      "extension_restatement": [
        "Every extension prompt must state that the subject remains in frame, e.g. 'The same [subject description] remains in the same [setting], present in the background of the frame, softly defocused with a shallow depth of field, kept continuously in frame to preserve identity.'",
        "The subject must occupy a stable screen position across the chain (e.g. always slightly left of centre) so the extension's visual state carries forward consistently",
        "Defocus level must be consistent across the chain — pick shallow DOF and keep it"
      ],
      "must_lock": [
        "Subject is visible in every frame of every chained clip",
        "Subject's screen position is stable across the chain",
        "Defocus level is consistent across the chain",
        "Subject's posture and movement are minimal during defocused beats so identity reads cleanly through bokeh"
      ],
      "reset_strategy": [
        "If subject must be absent for a beat, do not extend — use a full scene reset with a fresh text-to-video clip and accept that the chain restarts",
        "If subject identity drifts on a downstream extension, regenerate from the earliest visible drift point, not from the current clip — all downstream clips must be re-extended"
      ]
    },
    "conflict_tags": [
      "requires_extension_mode",
      "forbids_human_free_b_roll",
      "requires_shallow_dof"
    ],
    "operator_note_trigger": "Confirm subject is visibly present in every chained clip and identity is recognisable through any defocus before approving the chain. If subject is removed from any clip, flag for full scene reset rather than extension.",
    "visual_acceptance_checks": [
      "Subject is visible in frame at all times across every clip in the chain",
      "Subject's identity (face shape, hair, wardrobe silhouette) is recognisable through any defocus",
      "Subject's screen position is stable across the chain",
      "No clip in the chain is human-free",
      "Identity on the final clip's rack-focus return matches the seed clip"
    ]
  }
}
```

---

## Notes for the Architect

This packet is the keystone of the chain-based continuity strategy. It only works in combination with three other packets that should be present whenever this one is loaded:

- **Verbatim Identity Block Propagation** — the subject's textual description must be byte-identical in every prompt
- **Extension Chain Generation Order** — clips must be generated in strict sequence
- **Continuous Workspace Restatement** — the setting must also remain continuous

If any of those three are missing, this packet's continuity guarantee weakens.

The packet supersedes the earlier "latent textual anchor" approach (where the subject was described in B-roll prompts but not rendered in frame). That approach was tested in the same session and failed — Veo's extension mode is driven primarily by visible content in the preceding clip, not by textual claims about off-camera state.
