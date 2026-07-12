# Packet 09 — Diegetic Foreground Visualisation Layering

**Status:** Approved workaround
**Architect Category:** scene_mechanics
**Runtime Priority:** high

This packet captures the spatial layering technique developed during the CLOUDTECH UK session that solved the central character continuity problem of multi-scene videos with B-roll segments. Rather than cutting from a narrator scene to a separate abstract B-roll location and back, the technique places foreground visualisations as diegetic elements within the same continuous workspace as the subject. The subject remains visibly present throughout — softly defocused — while the foreground holds the focal subject role. Camera transitions become rack focus pulls between the layers rather than cuts to separate locations. This is the technique that allows Continuous Visible Presence Anchor (Packet 01) to actually be satisfied across content-led B-roll scenes.

---

## JSON Specification

```json
{
  "veo_specification_packet": {
    "packet_id": "diegetic-foreground-visualisation-layering",
    "packet_name": "Diegetic Foreground Visualisation Layering",
    "packet_version": "1.0.0",
    "status": "approved_workaround",
    "architect_category": "scene_mechanics",
    "runtime_priority": "high",
    "evidence": {
      "evidence_type": "failure_fix_pair",
      "source_extract": "Failure: independent abstract B-roll scenes (Scenes 2, 3, 4) cut to separate locations broke the extension chain's identity preservation. Latent textual anchor where the subject was described in B-roll prompts but not rendered in frame was insufficient. Fix: user proposal — 'How about the camera loses focus on her, but focuses on the abstract visualisation that appear, the abstract visualisation can then be part of the original scene?' Architect translation locked into final pack: 'In sharp foreground focus, a primary [foreground element] floats as a diegetic element in her workspace.' Three-layer focal depth on Scene 3: 'sharp foreground code panel, defocused presenter, and very soft background code columns'. Materialisation language locked at Scene 1 closing: 'In the final two seconds, very faint teal diagnostic particles and the softest hint of holographic elements begin to materialise peripherally at the edges of frame, out of focus and barely perceptible, signalling that something is about to appear without yet taking the frame.' Dissolution language locked at Scene 5 opening: 'The three foreground holographic webpages from the preceding shot dissolve gently away, fading cleanly out of the workspace air.' Transition language locked across the chain: 'Camera performs a slow methodical push-in following [foreground element]' — replacing what would otherwise be a hard cut to a separate B-roll location."
    },
    "packet_boundary": {
      "governs": [
        "The placement language for foreground visualisations as diegetic elements within the subject's continuous workspace",
        "The two- and three-layer focal depth structures (sharp foreground / defocused subject / optional very soft background)",
        "Rack focus transitions between layers as the replacement for hard cuts to separate B-roll locations",
        "Materialisation language for foreground elements appearing into a scene",
        "Dissolution language for foreground elements fading out of a scene",
        "The diegetic framing tokens that signal in-space rendering rather than overlay compositing"
      ],
      "does_not_govern": [
        "What the foreground content depicts (handled by Service-Specific Visualisation Vocabulary)",
        "Whether UI text is legible or non-literal (handled by Non-Literal UI and Webpage Rendering)",
        "Whether the subject is visibly present in frame (handled by Continuous Visible Presence Anchor)",
        "The setting itself or its restatement across the chain (handled by Continuous Workspace Restatement)",
        "Camera language outside the rack-focus transition mechanism (handled separately)",
        "Colour palette or lighting state (handled by Cool-Toned Architectural Palette Lock)"
      ]
    },
    "applicability": {
      "applies_when": [
        "A multi-scene video benefits from staying in one continuous spatial environment instead of cutting to separate B-roll locations",
        "The narrative requires illustrative or service-led visual content that would traditionally be handled by separate B-roll clips",
        "Character continuity must be preserved across content-led scenes (the subject must remain in frame even during illustrative beats)",
        "The deliverable supports a premium, design-led aesthetic where holographic or diegetic foreground elements fit the brand"
      ],
      "must_not_apply_when": [
        "The narrative explicitly requires a scene change to a different location",
        "The illustrative content requires depicting a real-world environment that cannot plausibly exist within the subject's workspace",
        "The aesthetic is documentary realism where holographic foreground elements would break the frame",
        "The user has explicitly mandated traditional cut-based B-roll for stylistic reasons"
      ]
    },
    "architect_integration": {
      "sequence_override": "none",
      "pre_subject_environment_preamble": [],
      "positive_absence_sentences": [],
      "positive_prompt_injections": {
        "setting_and_layout": [
          "Diegetic placement framing (mandatory): foreground elements must be described as 'floating as a diegetic [element type] in her workspace' or 'floating as diegetic semi-transparent panels in her workspace' — the word 'diegetic' is the key signal token, with 'semi-transparent' or 'holographic' as transparency qualifiers.",
          "Two-layer focal depth structure (default for B-roll scenes): sharp foreground / defocused subject. Composition sentence: 'Sharp focus on [foreground element] in the foreground. Subject softly defocused in the background throughout.'",
          "Three-layer focal depth structure (optional for richer scenes): sharp foreground / defocused subject / very soft background. Composition sentence: 'Sharp focus on [primary foreground element]. Subject softly defocused in the mid-plane between the foreground and deep background. [Background element] faintly visible behind her, extremely defocused.'",
          "Materialisation language (used at the end of the seed clip to signal an arriving foreground element): 'In the final two seconds, very faint [element character] begin to materialise peripherally at the edges of frame, out of focus and barely perceptible, signalling that something is about to appear without yet taking the frame.'",
          "Dissolution language (used at the start of any clip where a foreground element fades out): 'The [foreground element] from the preceding shot dissolves gently away, fading cleanly out of the workspace air.'",
          "Rack focus transition language (used at scene boundaries instead of cut language): 'The camera racks focus to the foreground, where [new element] now sits crisply in sharp focus' (rack into foreground) or 'As the foreground clears, the camera racks focus back to her. She comes into sharp focus' (rack back to subject)."
        ],
        "composition_and_screen_order": [
          "Subject screen position must remain stable across all clips in the chain — typically slightly left of centre using rule of thirds — even when the subject is defocused. This stability allows rack focus transitions to read cleanly because the subject's bokeh shape stays in the same screen region.",
          "Foreground element screen position should sit between camera and subject, occupying the focal plane the camera racks to. Avoid placing foreground elements behind the subject's screen position, as this disrupts the layering.",
          "Three-layer scenes should keep the deepest layer (background) extremely defocused — the operator note phrase is 'very soft' or 'extremely defocused and blurred by the shallow depth of field' — so the background reads as ambience rather than as a competing focal subject."
        ],
        "lighting": []
      },
      "negative_prompt_terms": [
        "foreground visualisation returning",
        "holographic elements remaining in foreground",
        "cut to separate location",
        "scene change to different setting",
        "split screen",
        "picture in picture overlay"
      ],
      "control_vocabulary": {
        "use": [
          "diegetic",
          "floating as a diegetic [element] in her workspace",
          "semi-transparent holographic [element]",
          "in sharp foreground focus",
          "softly defocused in the background",
          "softly defocused in the mid-plane",
          "extremely defocused and blurred by the shallow depth of field",
          "rack focus pull",
          "racks focus to the foreground",
          "racks focus back to her",
          "begin to materialise peripherally",
          "still out of focus and peripheral, not yet taking the frame",
          "dissolve gently away, fading cleanly out of the workspace air"
        ],
        "avoid": [
          "cut to abstract scene",
          "scene change",
          "transition to B-roll",
          "separate B-roll clip",
          "different location",
          "overlay graphic",
          "compositing layer",
          "post-production overlay (when describing in-scene rendering)",
          "lower third graphic",
          "title card insert",
          "split screen",
          "picture in picture",
          "foreground returning (after dissolution)",
          "elements remaining (when scene calls for clean rack-back)"
        ]
      }
    },
    "continuity_rules": {
      "extension_restatement": [
        "The diegetic placement framing must appear in every prompt that uses foreground visualisations — the 'floating as a diegetic [element] in her workspace' phrasing acts as a structural anchor that Veo interprets consistently across the chain",
        "The two- or three-layer focal depth structure must be declared explicitly in every relevant prompt — extension mode does not preserve focal layering automatically without explicit restatement",
        "Subject screen position must be restated in every clip to preserve the rack-focus geometry across transitions",
        "Materialisation language is used only at the seed clip's closing beat, never repeated mid-chain",
        "Dissolution language is used at the start of any clip where a previous foreground element exits, and must specify the element being dissolved by name to avoid ambiguity"
      ],
      "must_lock": [
        "The word 'diegetic' is the irreducible signal token — paraphrasing to 'in-scene' or 'within the space' weakens Veo's interpretation",
        "The 'in her workspace' (or equivalent setting-locked) phrasing must appear in every diegetic placement framing — without it, the foreground element drifts toward overlay treatment",
        "Subject screen position stability across the chain (typically slightly left of centre)",
        "The transparency qualifier ('semi-transparent' or 'holographic') on every foreground element to maintain the layered aesthetic and prevent foreground elements from rendering as solid objects that occlude the subject"
      ],
      "reset_strategy": [
        "If a foreground element is rendering as an opaque overlay rather than a diegetic in-space element, audit for missing 'diegetic' or 'holographic' tokens — these are the structural signals that drive Veo's interpretation",
        "If a rack focus transition is rendering as a hard cut, audit for missing 'racks focus' language and missing screen position stability between clips — both must be present",
        "If the subject is rendering with full focus when defocus was specified, audit the prompt for conflicting focus language and ensure the subject's defocus is restated in every relevant clip",
        "If the foreground element from a previous clip is persisting into a clip where it should have dissolved, the dissolution language must be explicit and must name the element — vague dissolution language ('the visualisation fades') is less reliable than specific naming ('the three foreground holographic webpages dissolve')"
      ]
    },
    "conflict_tags": [
      "requires_continuous_setting",
      "requires_continuous_visible_presence",
      "forbids_hard_cut_to_separate_location",
      "forbids_solid_opaque_foreground_elements"
    ],
    "operator_note_trigger": "Before approving any prompt with foreground visualisations, confirm the diegetic placement framing is present and uses the 'floating as a diegetic [element] in her workspace' structure. Confirm the focal depth structure (two-layer or three-layer) is explicitly declared. On rack focus transitions, confirm the subject's screen position matches the position in the previous and following clips. On dissolution beats, confirm the dissolving element is named explicitly.",
    "visual_acceptance_checks": [
      "Foreground visualisations render as semi-transparent or holographic elements within the workspace, not as opaque overlays",
      "Subject is visibly present in every clip with foreground visualisations, softly defocused but recognisable",
      "Subject's screen position is stable across the chain",
      "Rack focus transitions read as smooth focal shifts, not as hard cuts",
      "Foreground element materialisation at scene boundaries reads as elements arriving into the workspace, not as overlay graphics being inserted",
      "Foreground element dissolution at scene boundaries reads as elements leaving the workspace, not as overlay graphics being removed",
      "Three-layer scenes show clear focal separation between sharp foreground, defocused subject, and very soft background"
    ]
  }
}
```

---

## Notes for the Architect

This packet is the spatial design technique that resolves the central tension of the CLOUDTECH UK session. The original storyboard called for narrator-led scenes (1 and 5) and abstract B-roll scenes (2, 3, 4). The natural production pattern would be to cut between them as separate locations. That pattern broke character continuity in the extension chain because the subject was removed from frame for three clips and Veo's extension mechanism lost identity over that gap.

The breakthrough came from a user proposal — "How about the camera loses focus on her, but focuses on the abstract visualisation that appear, the abstract visualisation can then be part of the original scene?" — which reframed the problem entirely. Instead of cutting away from the subject, the camera stays on the subject's space and racks focus to foreground elements that appear within it. The subject never leaves the frame. Veo's extension mechanism never loses her.

A few subtleties worth flagging:

The word "diegetic" is doing critical work in this packet. It is the irreducible signal token that tells Veo the foreground element exists within the same physical space as the subject, rather than being composited on top in post. Paraphrasing to "in-scene" or "within the space" measurably weakens the interpretation — Veo sometimes renders such elements as flat overlays that occlude the workspace rather than as elements within it. The Architect should treat "diegetic" as a load-bearing word and never substitute it.

The transparency qualifier — "semi-transparent" or "holographic" — is the second load-bearing element. It prevents Veo from rendering the foreground as an opaque object that would block the subject's bokeh from showing through. The two qualifiers can be used interchangeably depending on context: "semi-transparent panels" works for webpage and dashboard elements; "holographic mechanism" works for tools and instruments; "holographic structure" works for architectural assemblies. All three flavours appeared in the final CLOUDTECH UK pack.

The two- and three-layer focal depth structures are tools for different scene complexity levels. Two-layer (sharp foreground / defocused subject) is the default for most B-roll beats and works for scenes like the magnifying glass over wireframe (Scene 2) and the holographic webpages (Scene 4). Three-layer (sharp foreground / defocused subject / very soft background) was used in Scene 3 to create the developer environment ambience — the subtle background code columns provide depth and atmosphere without competing with the primary foreground code panel. Three-layer scenes are richer but require more careful focus declaration; two-layer scenes are simpler and more reliably reproduced.

The materialisation and dissolution language are the bookend mechanisms that make the chain feel continuous. The seed clip closes with foreground elements just beginning to materialise peripherally. Each downstream clip opens with an explicit dissolution of the previous foreground (where applicable) and sometimes a fresh materialisation. The closing rack-back clip uses dissolution language to clear the foreground entirely before racking focus back to the subject. Without these bookends, foreground elements either appear too abruptly or persist into clips where they should have left.

The rack focus transition is the substitute for hard cuts. The phrase "the camera racks focus to the foreground" or "the camera racks focus back to her" tells Veo to perform a focal-plane shift rather than a scene change. Subject screen position must remain stable across the transition for the rack to read cleanly — if the subject is positioned slightly left of centre in one clip and dead centre in the next, the rack transition reads as a jolt even with focus correctly handled.

This packet is closely coupled to several others. It assumes Continuous Visible Presence Anchor (Packet 01) is in force — without continuous presence, there is nothing to rack focus to. It assumes Continuous Workspace Restatement (Packet 13) is in force — without setting continuity, the diegetic framing has no consistent space to anchor to. It cooperates with Service-Specific Visualisation Vocabulary (Packet 10) which dictates *what* the foreground elements depict, while this packet dictates *how* they sit in the scene.

The runtime priority is `high` rather than `critical` because the packet's failure mode is less catastrophic than the continuity packets — a clip that renders foreground as an overlay rather than a diegetic element is aesthetically off but recoverable. Compare to Packet 01 (Continuous Visible Presence Anchor) where a failure means the subject is missing from the chain and identity drift is locked in.

Ready for Packet 10 — Service-Specific Visualisation Vocabulary — when you give the word.
