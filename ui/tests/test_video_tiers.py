"""Tests for the pure render-tier data module (ui/video_tiers.py).

Run from the repo root with:
    python -m unittest discover -s ui/tests -p test_video_tiers.py -v

Free by construction: the module is pure (no network, no I/O, no engine
imports), so nothing here can ever spend or touch disk. These tests pin the
tier->model/resolution/rate mappings, the lookup behaviour (including the
unknown-key error), and the spend-safety contract carried in the data: every
video tier and the paid image tiers are gated, the FREE Basic image tier is
intentionally ungated, and the runaway guard constant exists.
"""

import sys
import unittest
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

from video_tiers import (  # noqa: E402
    VIDEO_TIERS,
    IMAGE_TIERS,
    MAX_STORYBOARD_IMAGES,
    UnknownTierError,
    resolve_video_tier,
    resolve_image_tier,
    video_tier_keys,
    image_tier_keys,
)


class VideoTierLookupTests(unittest.TestCase):
    def test_standard_maps_to_fast_model_1080p(self):
        tier = resolve_video_tier("standard")
        self.assertEqual(tier["model"], "veo-3.1-fast-generate-preview")
        self.assertEqual(tier["resolution"], "1080p")
        self.assertAlmostEqual(tier["per_second_rate"], 0.12)

    def test_quality_maps_to_standard_model_1080p(self):
        tier = resolve_video_tier("quality")
        self.assertEqual(tier["model"], "veo-3.1-generate-preview")
        self.assertEqual(tier["resolution"], "1080p")
        self.assertAlmostEqual(tier["per_second_rate"], 0.40)

    def test_ultra4k_maps_to_standard_model_4k(self):
        tier = resolve_video_tier("ultra4k")
        self.assertEqual(tier["model"], "veo-3.1-generate-preview")
        self.assertEqual(tier["resolution"], "4k")
        self.assertAlmostEqual(tier["per_second_rate"], 0.60)

    def test_unknown_video_tier_raises(self):
        with self.assertRaises(UnknownTierError):
            resolve_video_tier("nope")

    def test_unknown_video_tier_is_also_keyerror(self):
        """UnknownTierError subclasses KeyError so existing handlers catch it."""
        with self.assertRaises(KeyError):
            resolve_video_tier("nope")

    def test_unknown_video_tier_message_lists_valid_keys(self):
        try:
            resolve_video_tier("nope")
        except UnknownTierError as exc:
            for key in ("standard", "quality", "ultra4k"):
                self.assertIn(key, str(exc))
        else:
            self.fail("expected UnknownTierError")


class ImageTierLookupTests(unittest.TestCase):
    def test_basic_maps_to_nano_banana_cheap_faithful(self):
        tier = resolve_image_tier("basic")
        self.assertEqual(tier["model"], "gemini-2.5-flash-image")
        self.assertEqual(tier["resolution"], "1024px")
        self.assertAlmostEqual(tier["per_image_rate"], 0.039)
        # still the free-to-user, ungated tier
        self.assertTrue(tier["free_to_user"])
        self.assertFalse(tier["gated"])

    def test_standard_maps_to_flash_image_1024(self):
        tier = resolve_image_tier("standard")
        self.assertEqual(tier["model"], "gemini-3.1-flash-image")
        self.assertEqual(tier["resolution"], "1024px")
        self.assertAlmostEqual(tier["per_image_rate"], 0.067)

    def test_premium_maps_to_pro_image_1024(self):
        tier = resolve_image_tier("premium")
        self.assertEqual(tier["model"], "gemini-3-pro-image")
        self.assertEqual(tier["resolution"], "1024px")
        self.assertAlmostEqual(tier["per_image_rate"], 0.134)

    def test_unknown_image_tier_raises(self):
        with self.assertRaises(UnknownTierError):
            resolve_image_tier("nope")

    def test_unknown_image_tier_message_lists_valid_keys(self):
        try:
            resolve_image_tier("nope")
        except UnknownTierError as exc:
            for key in ("basic", "standard", "premium"):
                self.assertIn(key, str(exc))
        else:
            self.fail("expected UnknownTierError")


class GatingContractTests(unittest.TestCase):
    """The spend-safety contract is carried in the tier data. The FREE Basic
    image tier is intentionally ungated; the paid Standard/Premium image tiers
    are gated. (Video tiers are always gated and carry no ungated path.)"""

    def test_basic_image_tier_is_ungated(self):
        self.assertFalse(resolve_image_tier("basic")["gated"])

    def test_basic_image_tier_is_free_to_user(self):
        self.assertTrue(resolve_image_tier("basic")["free_to_user"])

    def test_standard_image_tier_is_gated(self):
        self.assertTrue(resolve_image_tier("standard")["gated"])

    def test_premium_image_tier_is_gated(self):
        self.assertTrue(resolve_image_tier("premium")["gated"])

    def test_only_basic_image_tier_is_ungated(self):
        ungated = [t["key"] for t in IMAGE_TIERS if not t["gated"]]
        self.assertEqual(ungated, ["basic"])

    def test_every_paid_image_tier_is_gated(self):
        """Any image tier that bills the user must be gated; only the
        free-to-user tier may be ungated."""
        for tier in IMAGE_TIERS:
            if not tier["free_to_user"]:
                self.assertTrue(
                    tier["gated"],
                    f"paid image tier {tier['key']!r} must be gated",
                )


class RunawayGuardTests(unittest.TestCase):
    def test_max_storyboard_images_is_a_positive_int(self):
        self.assertIsInstance(MAX_STORYBOARD_IMAGES, int)
        self.assertGreater(MAX_STORYBOARD_IMAGES, 0)


class TierDataShapeTests(unittest.TestCase):
    def test_video_tiers_have_expected_keys_in_order(self):
        self.assertEqual(video_tier_keys(), ["standard", "quality", "ultra4k"])

    def test_image_tiers_have_expected_keys_in_order(self):
        self.assertEqual(image_tier_keys(), ["basic", "standard", "premium"])

    def test_every_video_tier_has_the_required_fields(self):
        for tier in VIDEO_TIERS:
            for field in ("key", "label", "model", "resolution", "per_second_rate"):
                self.assertIn(field, tier, f"video tier {tier.get('key')!r} missing {field}")
            self.assertIsInstance(tier["per_second_rate"], (int, float))

    def test_every_image_tier_has_the_required_fields(self):
        for tier in IMAGE_TIERS:
            for field in ("key", "label", "model", "per_image_rate", "gated"):
                self.assertIn(field, tier, f"image tier {tier.get('key')!r} missing {field}")
            self.assertIsInstance(tier["per_image_rate"], (int, float))
            self.assertIsInstance(tier["gated"], bool)

    def test_tier_keys_are_unique(self):
        for tiers in (VIDEO_TIERS, IMAGE_TIERS):
            keys = [t["key"] for t in tiers]
            self.assertEqual(len(keys), len(set(keys)), "tier keys must be unique")

    def test_resolve_returns_the_stored_dict_by_reference(self):
        """The lookup returns the live tier dict (read-only reference data),
        so it is identical to the entry in the ordered list."""
        self.assertIs(resolve_video_tier("standard"), VIDEO_TIERS[0])
        self.assertIs(resolve_image_tier("basic"), IMAGE_TIERS[0])


if __name__ == "__main__":
    unittest.main()
