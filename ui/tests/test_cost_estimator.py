"""Tests for the pure cost-estimator module (ui/cost_estimator.py).

Run from the repo root with:
    python -m unittest discover -s ui/tests -p test_cost_estimator.py -v

Free by construction: the module is pure (no network, no I/O, no engine
imports), so nothing here can ever spend or touch disk.

Pricing is now REAL (Gemini Developer API, 2026-06-09) and RESOLUTION-AWARE:
Veo is billed model -> resolution -> per-second-rate, images model ->
resolution -> per-image-rate, and music model -> flat-per-song. The tests pin
simple round rates in their own TEST_PRICING so the arithmetic is easy to verify
by hand, plus a few assertions against the real DEFAULT_PRICING numbers.
"""

import sys
import unittest
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

from cost_estimator import (  # noqa: E402
    estimate_cost,
    estimate_storyboard_cost,
    image_rate,
    DEFAULT_PRICING,
)


# A pricing dict with simple round rates so the arithmetic is easy to verify by
# hand. Resolution-aware: a tier resolves to (model, resolution) and the rate is
# looked up by that pair. (DEFAULT_PRICING carries the REAL numbers; tests pin
# their own.)
TEST_PRICING = {
    "veo_per_second": {
        "draft-model": {"720p": 0.10},
        "hq-model": {"1080p": 0.50, "4k": 0.90},
    },
    "tier_models": {
        "draft": {"model": "draft-model", "resolution": "720p"},
        "hq": {"model": "hq-model", "resolution": "1080p"},
    },
    "music_per_song": {"lyria-test": 0.25},
    "music_model": "lyria-test",
    "image_per_image": {
        "img-flat": {"flat": 0.05},
        "img-tiered": {"1024px": 0.20, "2048px": 0.40},
    },
    "image_preview_model": "img-flat",
    "image_preview_resolution": "flat",
    "currency": "USD",
}


class CostEstimatorMathTests(unittest.TestCase):
    def test_single_scene_draft(self):
        """One scene at the draft model/resolution: 6s seed only, flat music."""
        result = estimate_cost({"scene_count": 1, "max_scenes": 1}, "draft", TEST_PRICING)
        # 1 scene -> 6s of video; 6s * 0.10 = 0.60
        self.assertAlmostEqual(result["video"], 0.60)
        self.assertAlmostEqual(result["music"], 0.25)
        self.assertAlmostEqual(result["total"], 0.85)
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["breakdown"]["scenes_to_generate"], 1)
        self.assertEqual(result["breakdown"]["seconds_total"], 6)

    def test_multi_scene_draft(self):
        """Three scenes: 6 + 7 + 7 = 20s. 20 * 0.10 = 2.00, + 0.25 music."""
        result = estimate_cost({"scene_count": 3, "max_scenes": 3}, "draft", TEST_PRICING)
        self.assertEqual(result["breakdown"]["seconds_total"], 20)
        self.assertAlmostEqual(result["video"], 2.00)
        self.assertAlmostEqual(result["music"], 0.25)
        self.assertAlmostEqual(result["total"], 2.25)

    def test_draft_vs_hq_rate_difference(self):
        """Same job, hq model/resolution is 5x the draft per-second rate."""
        job = {"scene_count": 2, "max_scenes": 2}  # 6 + 7 = 13s
        draft = estimate_cost(job, "draft", TEST_PRICING)
        hq = estimate_cost(job, "hq", TEST_PRICING)
        self.assertEqual(draft["breakdown"]["seconds_total"], 13)
        self.assertEqual(hq["breakdown"]["seconds_total"], 13)
        self.assertAlmostEqual(draft["video"], 13 * 0.10)
        self.assertAlmostEqual(hq["video"], 13 * 0.50)
        self.assertAlmostEqual(hq["video"], draft["video"] * 5.0)
        self.assertEqual(draft["breakdown"]["veo_rate_per_second"], 0.10)
        self.assertEqual(hq["breakdown"]["veo_rate_per_second"], 0.50)

    def test_explicit_model_resolution_on_job_wins(self):
        """An explicit model+resolution on the job is resolution-aware and wins
        over the quality-tier mapping (e.g. an hq 4k generation costs more)."""
        job = {"scene_count": 1, "max_scenes": 1, "model": "hq-model", "resolution": "4k"}
        result = estimate_cost(job, "hq", TEST_PRICING)
        self.assertEqual(result["breakdown"]["veo_model"], "hq-model")
        self.assertEqual(result["breakdown"]["veo_resolution"], "4k")
        self.assertAlmostEqual(result["breakdown"]["veo_rate_per_second"], 0.90)
        self.assertAlmostEqual(result["video"], 6 * 0.90)  # 1 scene = 6s

    def test_spend_cap_limits_scenes(self):
        """A spend cap below the scene count caps the paid scenes (and seconds)."""
        result = estimate_cost({"scene_count": 5, "max_scenes": 2}, "draft", TEST_PRICING)
        self.assertEqual(result["breakdown"]["scenes_to_generate"], 2)
        self.assertEqual(result["breakdown"]["seconds_total"], 13)  # 6 + 7
        self.assertTrue(any("Spend cap limits" in a for a in result["assumptions"]))

    def test_custom_seed_duration(self):
        """Scene 1's inline duration_seconds drives the seed length. Note an
        inline-scenes job carries no explicit model, so the tier mapping is used."""
        job = {
            "scene_count": 2,
            "max_scenes": 2,
            "scenes": [{"prompt": "seed", "duration_seconds": 10}, {"prompt": "ext"}],
        }
        result = estimate_cost(job, "draft", TEST_PRICING)
        self.assertEqual(result["breakdown"]["seed_seconds"], 10)
        self.assertEqual(result["breakdown"]["seconds_total"], 17)  # 10 + 7

    def test_placeholder_seed_adds_image_preview(self):
        """A generated placeholder seed is counted as one image preview."""
        job = {"scene_count": 1, "max_scenes": 1, "seed_is_placeholder": True}
        result = estimate_cost(job, "draft", TEST_PRICING)
        self.assertEqual(result["breakdown"]["image_count"], 1)
        self.assertAlmostEqual(result["image"], 0.05)  # img-flat preview rate
        # total now includes the image preview: 0.60 video + 0.25 music + 0.05 image
        self.assertAlmostEqual(result["total"], 0.90)

    def test_total_is_sum_of_stages(self):
        job = {"scene_count": 4, "max_scenes": 4, "seed_is_placeholder": True}
        result = estimate_cost(job, "hq", TEST_PRICING)
        self.assertAlmostEqual(
            result["total"], result["video"] + result["music"] + result["image"]
        )


class CostEstimatorLabellingTests(unittest.TestCase):
    def test_result_is_labelled_approximate(self):
        result = estimate_cost({"scene_count": 1, "max_scenes": 1}, "draft", TEST_PRICING)
        self.assertTrue(result["approximate"])
        self.assertIsInstance(result["assumptions"], list)
        self.assertTrue(result["assumptions"], "expected a non-empty assumptions list")

    def test_default_pricing_is_flagged_as_default(self):
        """When the caller relies on DEFAULT_PRICING, the estimate must say so."""
        result = estimate_cost({"scene_count": 1, "max_scenes": 1}, "draft")
        self.assertTrue(result["breakdown"]["using_default_pricing"])
        self.assertTrue(any("REAL" in a for a in result["assumptions"]))

    def test_operator_pricing_not_flagged_as_default(self):
        result = estimate_cost({"scene_count": 1, "max_scenes": 1}, "draft", TEST_PRICING)
        self.assertFalse(result["breakdown"]["using_default_pricing"])
        self.assertTrue(any("operator-supplied" in a for a in result["assumptions"]))

    def test_default_pricing_has_expected_shape(self):
        self.assertIn("veo_per_second", DEFAULT_PRICING)
        self.assertIn("image_per_image", DEFAULT_PRICING)
        self.assertIn("music_per_song", DEFAULT_PRICING)
        self.assertIn("tier_models", DEFAULT_PRICING)
        # veo is keyed model -> resolution -> rate
        self.assertIsInstance(
            DEFAULT_PRICING["veo_per_second"]["veo-3.1-fast-generate-preview"], dict
        )


class CostEstimatorRealPricingTests(unittest.TestCase):
    """Pin a few of the REAL DEFAULT_PRICING numbers (the official page values)."""

    def test_real_veo_rates(self):
        veo = DEFAULT_PRICING["veo_per_second"]
        self.assertAlmostEqual(veo["veo-3.1-generate-preview"]["1080p"], 0.40)
        self.assertAlmostEqual(veo["veo-3.1-generate-preview"]["4k"], 0.60)
        self.assertAlmostEqual(veo["veo-3.1-fast-generate-preview"]["1080p"], 0.12)
        self.assertAlmostEqual(veo["veo-3.1-fast-generate-preview"]["720p"], 0.10)
        self.assertAlmostEqual(veo["veo-3.1-lite-generate-preview"]["720p"], 0.05)
        self.assertNotIn("4k", veo["veo-3.1-lite-generate-preview"])  # lite has no 4k

    def test_real_image_rates(self):
        img = DEFAULT_PRICING["image_per_image"]
        self.assertAlmostEqual(img["imagen-4.0-fast-generate-001"]["flat"], 0.02)
        self.assertAlmostEqual(img["gemini-3.1-flash-image"]["1024px"], 0.067)
        self.assertAlmostEqual(img["gemini-3-pro-image"]["1024px"], 0.134)
        self.assertAlmostEqual(img["gemini-3-pro-image"]["4096px"], 0.24)

    def test_real_music_rates(self):
        music = DEFAULT_PRICING["music_per_song"]
        self.assertAlmostEqual(music["lyria-3-pro-preview"], 0.08)
        self.assertAlmostEqual(music["lyria-3-clip-preview"], 0.04)

    def test_default_standard_tier_is_fast_1080p_real_rate(self):
        """The 'standard' video tier (fast @ 1080p) bills at 0.12/s; a 3-scene
        20s job is 2.40 video + 0.08 music under DEFAULT_PRICING."""
        job = {"scene_count": 3, "max_scenes": 3,
               "model": "veo-3.1-fast-generate-preview", "resolution": "1080p"}
        result = estimate_cost(job, "standard")
        self.assertAlmostEqual(result["breakdown"]["veo_rate_per_second"], 0.12)
        self.assertAlmostEqual(result["video"], 20 * 0.12)
        self.assertAlmostEqual(result["music"], 0.08)


class CostEstimatorRobustnessTests(unittest.TestCase):
    def test_missing_scene_fields_default_to_one_scene(self):
        result = estimate_cost({}, "draft", TEST_PRICING)
        self.assertEqual(result["breakdown"]["scenes_to_generate"], 1)
        self.assertTrue(any("assumed 1 scene" in a for a in result["assumptions"]))

    def test_unknown_quality_with_no_model_falls_back_to_zero_rate(self):
        """An unknown tier with no model mapping and no explicit job model has no
        priced rate; the video cost is treated as 0 and the assumption says so."""
        result = estimate_cost({"scene_count": 1, "max_scenes": 1}, "mystery", TEST_PRICING)
        self.assertEqual(result["breakdown"]["veo_rate_per_second"], 0.0)
        self.assertAlmostEqual(result["video"], 0.0)
        self.assertTrue(any("No per-second Veo rate" in a for a in result["assumptions"]))

    def test_uncapped_job_uses_full_scene_count(self):
        result = estimate_cost({"scene_count": 3}, "draft", TEST_PRICING)
        self.assertEqual(result["breakdown"]["scenes_to_generate"], 3)
        self.assertTrue(any("no spend cap" in a.lower() for a in result["assumptions"]))

    def test_unknown_resolution_for_known_model_uses_stand_in(self):
        job = {"scene_count": 1, "max_scenes": 1, "model": "hq-model", "resolution": "9000p"}
        result = estimate_cost(job, "hq", TEST_PRICING)
        # falls back to one of the model's priced resolutions
        self.assertGreater(result["breakdown"]["veo_rate_per_second"], 0.0)
        self.assertTrue(any("stand-in" in a for a in result["assumptions"]))


class ImageRateLookupTests(unittest.TestCase):
    def test_flat_model_rate(self):
        self.assertAlmostEqual(image_rate(TEST_PRICING, "img-flat", "flat"), 0.05)

    def test_tiered_model_resolution(self):
        self.assertAlmostEqual(image_rate(TEST_PRICING, "img-tiered", "2048px"), 0.40)

    def test_unknown_model_is_zero(self):
        self.assertAlmostEqual(image_rate(TEST_PRICING, "no-such-model", "1024px"), 0.0)

    def test_missing_resolution_uses_stand_in(self):
        # falls back to one of the model's priced resolutions, never raising
        self.assertGreater(image_rate(TEST_PRICING, "img-tiered", "5000px"), 0.0)


class StoryboardCostTests(unittest.TestCase):
    def test_paid_tier_count_times_rate_billed_to_user(self):
        result = estimate_storyboard_cost(6, "img-tiered", "1024px", TEST_PRICING)
        self.assertEqual(result["images_count"], 6)
        self.assertAlmostEqual(result["per_image_rate"], 0.20)
        self.assertAlmostEqual(result["total"], 6 * 0.20)
        self.assertEqual(result["billed_to"], "user")
        self.assertFalse(result["free_to_user"])

    def test_free_tier_has_real_cost_billed_to_business(self):
        """The FREE Basic tier still has a REAL per-image cost; the estimate must
        report it AND say it is billed to the business, not the user."""
        result = estimate_storyboard_cost(
            6, "img-flat", "flat", TEST_PRICING, free_to_user=True)
        self.assertAlmostEqual(result["per_image_rate"], 0.05)
        self.assertAlmostEqual(result["total"], 6 * 0.05)  # real cost, not zero
        self.assertGreater(result["total"], 0.0)
        self.assertEqual(result["billed_to"], "business")
        self.assertTrue(result["free_to_user"])
        self.assertTrue(any("business cost" in a for a in result["assumptions"]))

    def test_real_default_storyboard_pricing(self):
        """Under DEFAULT_PRICING: Standard image tier (flash @ 1024px) = 0.067."""
        result = estimate_storyboard_cost(10, "gemini-3.1-flash-image", "1024px")
        self.assertAlmostEqual(result["per_image_rate"], 0.067)
        self.assertAlmostEqual(result["total"], round(10 * 0.067, 4))

    def test_zero_images_is_zero(self):
        result = estimate_storyboard_cost(0, "img-flat", "flat", TEST_PRICING)
        self.assertEqual(result["images_count"], 0)
        self.assertAlmostEqual(result["total"], 0.0)


if __name__ == "__main__":
    unittest.main()
