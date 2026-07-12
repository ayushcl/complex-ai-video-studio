"""Tests for extension-chain continuity nudge helpers.

Run from the repo root with:
    python -m unittest discover -s ui/tests -p test_run_veo_extension_chain.py -v

Free by construction: these tests import pure helpers only and make no Veo
requests, no --run calls, and no network calls.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from video_generation_agency.run_veo_extension_chain import (  # noqa: E402
    EXTENSION_CONTINUITY_NEGATIVE_NUDGE,
    EXTENSION_PROMPT_PREFIX,
    _effective_scene_for_chain,
    _has_scene_seed_anchor,
    _merge_negative_prompt,
    _prefix_extension_prompt,
)


class SceneSeedAnchorTests(unittest.TestCase):
    def test_empty_scenes_are_not_anchored(self):
        self.assertFalse(_has_scene_seed_anchor([]))

    def test_missing_seed_image_is_not_anchored(self):
        self.assertFalse(_has_scene_seed_anchor([{}]))

    def test_whitespace_seed_image_is_not_anchored(self):
        self.assertFalse(_has_scene_seed_anchor([{"seed_image": "   "}]))

    def test_non_empty_seed_image_is_anchored(self):
        self.assertTrue(_has_scene_seed_anchor([{"seed_image": "x.png"}]))


class ExtensionPromptPrefixTests(unittest.TestCase):
    def test_prefixes_plain_prompt(self):
        self.assertEqual(
            _prefix_extension_prompt("foo"),
            f"{EXTENSION_PROMPT_PREFIX} foo",
        )

    def test_already_prefixed_prompt_is_unchanged(self):
        prompt = f"{EXTENSION_PROMPT_PREFIX} foo"
        self.assertEqual(_prefix_extension_prompt(prompt), prompt)

    def test_leading_whitespace_is_trimmed_before_prefix(self):
        self.assertEqual(
            _prefix_extension_prompt("   foo"),
            f"{EXTENSION_PROMPT_PREFIX} foo",
        )

    def test_empty_prompt_returns_prefix_without_trailing_space(self):
        self.assertEqual(_prefix_extension_prompt(""), EXTENSION_PROMPT_PREFIX)


class NegativePromptMergeTests(unittest.TestCase):
    def test_none_becomes_nudge(self):
        self.assertEqual(
            _merge_negative_prompt(None),
            EXTENSION_CONTINUITY_NEGATIVE_NUDGE,
        )

    def test_empty_string_becomes_nudge(self):
        self.assertEqual(
            _merge_negative_prompt(""),
            EXTENSION_CONTINUITY_NEGATIVE_NUDGE,
        )

    def test_existing_prompt_gets_comma_separated_nudge(self):
        self.assertEqual(
            _merge_negative_prompt("camera shake"),
            f"camera shake, {EXTENSION_CONTINUITY_NEGATIVE_NUDGE}",
        )

    def test_existing_nudge_is_not_duplicated(self):
        prompt = f"camera shake, {EXTENSION_CONTINUITY_NEGATIVE_NUDGE}"
        self.assertEqual(_merge_negative_prompt(prompt), prompt)


class EffectiveSceneForChainTests(unittest.TestCase):
    def test_scene_one_is_unchanged_when_anchored(self):
        scene = {"prompt": "foo", "negative_prompt": "camera shake"}
        self.assertIs(_effective_scene_for_chain(scene, 1, True), scene)

    def test_scene_two_is_unchanged_when_not_anchored(self):
        scene = {"prompt": "foo", "negative_prompt": "camera shake"}
        self.assertIs(_effective_scene_for_chain(scene, 2, False), scene)

    def test_scene_two_is_prefixed_and_negative_prompt_is_merged_when_anchored(self):
        scene = {"prompt": "foo", "negative_prompt": "camera shake"}
        effective = _effective_scene_for_chain(scene, 2, True)

        self.assertEqual(effective["prompt"], f"{EXTENSION_PROMPT_PREFIX} foo")
        self.assertEqual(
            effective["negative_prompt"],
            f"camera shake, {EXTENSION_CONTINUITY_NEGATIVE_NUDGE}",
        )

    def test_scene_two_anchored_call_does_not_mutate_original_scene(self):
        scene = {"prompt": "foo", "negative_prompt": "camera shake"}
        original = dict(scene)

        _effective_scene_for_chain(scene, 2, True)

        self.assertEqual(scene, original)
        self.assertEqual(scene["prompt"], "foo")
        self.assertEqual(scene["negative_prompt"], "camera shake")


if __name__ == "__main__":
    unittest.main()
