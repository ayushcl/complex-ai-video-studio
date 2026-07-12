"""Tests for ui/storyboard.py: scene -> N time-ordered MOMENT images.

Run from the repo root with:
    python -m unittest discover -s ui/tests -p test_storyboard.py -v

Free by construction: BOTH paid/networked layers are MOCKED, so no test ever
hits a real API or spends money -
  * the cheap Gemini text call (moment-split + friendly summary) is mocked at
    storyboard._gemini_text, so urllib is never invoked;
  * the paid image primitive (scene_images.generate_scene_image) is mocked, so
    google-genai is never reached.
The caching/cap logic is exercised against the real on-disk cache in a tempdir.
"""

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

import scene_images  # noqa: E402
import storyboard  # noqa: E402


def _fake_image_writer(byte_tag=b"\x89PNG\r\n\x1a\n frame"):
    """A drop-in for scene_images.generate_scene_image that writes a tiny PNG
    stand-in and records its calls, instead of hitting the paid API."""
    calls = []
    lock = threading.Lock()

    def fake_generate(prompt, out_path, api_key, model=scene_images.DEFAULT_IMAGE_MODEL):
        with lock:
            calls.append({"prompt": prompt, "out_path": Path(out_path), "model": model})
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(byte_tag)
        return Path(out_path)

    return fake_generate, calls


# --------------------------------------------------------------------------- #
# (1) Moment split: AI path + fallbacks (Gemini text call mocked)              #
# --------------------------------------------------------------------------- #
class MomentPromptTests(unittest.TestCase):
    def test_ai_split_returns_n_moments(self):
        moments = ["dawn over the bay", "midday sun", "golden hour", "dusk lights"]
        raw = '{"moments": %s}' % storyboard.json.dumps(moments)
        with mock.patch.object(storyboard, "_gemini_text", return_value=raw) as gem:
            out = storyboard.moment_prompts("a coastal day", 4, "key")
        gem.assert_called_once()
        self.assertEqual(out["method"], "ai")
        self.assertEqual(out["moments"], moments)
        self.assertIsNone(out["warning"])

    def test_ai_split_truncates_extra_moments(self):
        raw = '{"moments": ["a", "b", "c", "d", "e"]}'
        with mock.patch.object(storyboard, "_gemini_text", return_value=raw):
            out = storyboard.moment_prompts("scene", 3, "key")
        self.assertEqual(out["moments"], ["a", "b", "c"])

    def test_ai_split_pads_short_moments(self):
        raw = '{"moments": ["a", "b"]}'
        with mock.patch.object(storyboard, "_gemini_text", return_value=raw):
            out = storyboard.moment_prompts("scene", 4, "key")
        self.assertEqual(len(out["moments"]), 4)
        self.assertEqual(out["moments"], ["a", "b", "b", "b"])

    def test_single_moment_makes_no_llm_call(self):
        """N == 1 is just the base prompt: no text call, no failure surface."""
        with mock.patch.object(storyboard, "_gemini_text") as gem:
            out = storyboard.moment_prompts("only one frame", 1, "key")
        gem.assert_not_called()
        self.assertEqual(out["moments"], ["only one frame"])
        self.assertEqual(out["method"], "single")

    def test_fallback_when_no_key(self):
        """No key -> N copies of the base prompt, no text call attempted."""
        with mock.patch.object(storyboard, "_gemini_text") as gem:
            out = storyboard.moment_prompts("base scene", 3, None)
        gem.assert_not_called()
        self.assertEqual(out["method"], "fallback")
        self.assertEqual(out["moments"], ["base scene", "base scene", "base scene"])
        self.assertIsNotNone(out["warning"])

    def test_fallback_when_llm_raises(self):
        """A failing text call falls back to N base-prompt copies, never raising."""
        with mock.patch.object(
            storyboard, "_gemini_text",
            side_effect=storyboard.StoryboardError("Gemini text request failed: boom"),
        ):
            out = storyboard.moment_prompts("base scene", 3, "key")
        self.assertEqual(out["method"], "fallback")
        self.assertEqual(out["moments"], ["base scene"] * 3)
        self.assertIn("boom", out["warning"])

    def test_fallback_when_llm_returns_unusable_json(self):
        with mock.patch.object(storyboard, "_gemini_text", return_value="not json at all"):
            out = storyboard.moment_prompts("base scene", 2, "key")
        self.assertEqual(out["method"], "fallback")
        self.assertEqual(out["moments"], ["base scene", "base scene"])

    def test_fallback_when_moments_empty(self):
        with mock.patch.object(storyboard, "_gemini_text", return_value='{"moments": []}'):
            out = storyboard.moment_prompts("base scene", 2, "key")
        self.assertEqual(out["method"], "fallback")

    def test_empty_scene_prompt_rejected(self):
        with self.assertRaises(storyboard.StoryboardError):
            storyboard.moment_prompts("   ", 3, "key")

    def test_bare_array_response_accepted(self):
        with mock.patch.object(storyboard, "_gemini_text", return_value='["x", "y"]'):
            out = storyboard.moment_prompts("scene", 2, "key")
        self.assertEqual(out["moments"], ["x", "y"])


# --------------------------------------------------------------------------- #
# (2) Image-count cap (engineering safety rail, not a user gate)               #
# --------------------------------------------------------------------------- #
class ImageCountCapTests(unittest.TestCase):
    def test_clamps_above_cap(self):
        capped = storyboard.clamp_image_count(storyboard.MAX_STORYBOARD_IMAGES + 25)
        self.assertEqual(capped, storyboard.MAX_STORYBOARD_IMAGES)

    def test_passes_through_under_cap(self):
        self.assertEqual(storyboard.clamp_image_count(5), 5)

    def test_rejects_zero_and_negative(self):
        for bad in (0, -1, -100):
            with self.assertRaises(storyboard.StoryboardError):
                storyboard.clamp_image_count(bad)

    def test_rejects_non_numeric_and_bool(self):
        for bad in ("abc", None, 1.5, True, False):
            with self.assertRaises(storyboard.StoryboardError):
                storyboard.clamp_image_count(bad)

    def test_accepts_clean_numeric_string(self):
        self.assertEqual(storyboard.clamp_image_count("4"), 4)

    def test_cap_enforced_end_to_end_limits_paid_calls(self):
        """A request for far more images than the cap must render at most
        MAX_STORYBOARD_IMAGES frames - the runaway-spend safety rail. The rail
        must hold AT THE ORCHESTRATION BOUNDARY even when the splitter itself is
        replaced (it gets the already-clamped count). Both the split and the
        image API are mocked, so this is free."""
        cap = storyboard.MAX_STORYBOARD_IMAGES
        seen_counts = []

        # An adversarial splitter: returns whatever N it is handed AND tries to
        # over-produce on top. generate_storyboard must still cap both the count
        # it asks for and the frames it renders.
        def greedy_split(scene_prompt, n, api_key):
            seen_counts.append(n)
            return {"moments": [f"m{i}" for i in range(n + 500)], "method": "ai", "warning": None}

        fake_generate, calls = _fake_image_writer()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(storyboard, "moment_prompts", side_effect=greedy_split), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = storyboard.generate_storyboard(
                Path(tmp) / "job", 1, "a big scene", cap + 999, "key",
            )
        # The splitter was asked for the CLAMPED count, not the wild request...
        self.assertEqual(seen_counts, [cap])
        # ...and no more than `cap` paid renders happened, even though the
        # splitter tried to over-produce.
        self.assertEqual(len(calls), cap)
        self.assertEqual(len(result["moments"]), cap)

    def test_real_split_never_exceeds_cap(self):
        """Through the REAL moment_prompts, an over-cap N yields at most `cap`
        moments even when the model returns more."""
        cap = storyboard.MAX_STORYBOARD_IMAGES
        raw = '{"moments": %s}' % storyboard.json.dumps([f"f{i}" for i in range(cap + 50)])
        with mock.patch.object(storyboard, "_gemini_text", return_value=raw):
            out = storyboard.moment_prompts("scene", cap + 50, "key")
        self.assertEqual(len(out["moments"]), cap)


# --------------------------------------------------------------------------- #
# (3) End-to-end storyboard generation: N moments -> N cached images           #
# --------------------------------------------------------------------------- #
class GenerateStoryboardTests(unittest.TestCase):
    def test_n_moments_produce_n_cached_images(self):
        moments = ["frame one", "frame two", "frame three"]
        raw = '{"moments": %s}' % storyboard.json.dumps(moments)
        fake_generate, calls = _fake_image_writer()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(storyboard, "_gemini_text", return_value=raw), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            job_dir = Path(tmp) / "job"
            result = storyboard.generate_storyboard(job_dir, 1, "a scene", 3, "key")

            self.assertEqual(len(result["moments"]), 3)
            self.assertEqual(result["rendered"], 3)
            self.assertEqual(result["reused"], 0)
            self.assertEqual(result["method"], "ai")
            self.assertEqual(len(calls), 3)
            # Every moment image exists on disk, at the deterministic per-moment path.
            for entry in result["moments"]:
                self.assertTrue(entry["path"].is_file())
                self.assertGreater(entry["path"].stat().st_size, 0)
            paths = [e["path"] for e in result["moments"]]
            self.assertEqual(len(set(paths)), 3, "each moment must have a distinct cached path")
            self.assertEqual(
                paths[0], storyboard.cached_moment_image_path(job_dir, 1, 1)
            )

    def test_second_call_reuses_cache_no_respend(self):
        """A second storyboard render of the same scene re-reads the cached
        frames the first wrote and makes NO further paid calls."""
        moments = ["a", "b"]
        raw = '{"moments": %s}' % storyboard.json.dumps(moments)
        fake_generate, calls = _fake_image_writer()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(storyboard, "_gemini_text", return_value=raw), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            job_dir = Path(tmp) / "job"
            first = storyboard.generate_storyboard(job_dir, 2, "scene", 2, "key")
            self.assertEqual(first["rendered"], 2)
            self.assertEqual(len(calls), 2)

            second = storyboard.generate_storyboard(job_dir, 2, "scene", 2, "key")
            self.assertEqual(second["reused"], 2)
            self.assertEqual(second["rendered"], 0)
            self.assertEqual(len(calls), 2, "no re-spend on the second render")

    def test_chosen_image_model_is_passed_through(self):
        """The caller's IMAGE tier model must reach the paid primitive (never a
        hardcoded tier)."""
        raw = '{"moments": ["a", "b"]}'
        fake_generate, calls = _fake_image_writer()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(storyboard, "_gemini_text", return_value=raw), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            storyboard.generate_storyboard(
                Path(tmp) / "job", 1, "scene", 2, "key", model="gemini-3-pro-image",
            )
        self.assertTrue(calls)
        self.assertTrue(all(c["model"] == "gemini-3-pro-image" for c in calls))

    def test_fallback_split_still_renders_n_images(self):
        """When the split falls back (no key path simulated via a raising text
        call), the storyboard STILL produces N images, all from the base prompt."""
        fake_generate, calls = _fake_image_writer()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(storyboard, "_gemini_text",
                                  side_effect=storyboard.StoryboardError("down")), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = storyboard.generate_storyboard(Path(tmp) / "job", 1, "base scene", 3, "key")
        self.assertEqual(result["method"], "fallback")
        self.assertEqual(len(result["moments"]), 3)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(c["prompt"] == "base scene" for c in calls))

    def test_missing_key_refused_before_any_spend(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(storyboard.StoryboardError, "key"):
                storyboard.generate_storyboard(Path(tmp) / "job", 1, "scene", 2, "")

    def test_paid_layer_failure_surfaces_as_storyboard_error(self):
        raw = '{"moments": ["a", "b"]}'

        def boom(prompt, out_path, api_key, model=scene_images.DEFAULT_IMAGE_MODEL):
            raise scene_images.SceneImageError("the image model refused the prompt")

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(storyboard, "_gemini_text", return_value=raw), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=boom):
            with self.assertRaisesRegex(storyboard.StoryboardError, "refused"):
                storyboard.generate_storyboard(Path(tmp) / "job", 1, "scene", 2, "key")

    def test_concurrent_same_storyboard_renders_each_frame_once(self):
        """Simultaneous storyboard requests for the same scene must collapse to
        ONE paid render PER frame (scene_images' per-target lock), never one per
        thread - the double-spend guard."""
        moments = ["a", "b", "c"]
        raw = '{"moments": %s}' % storyboard.json.dumps(moments)

        import time as _time
        calls = []
        calls_lock = threading.Lock()

        def slow_generate(prompt, out_path, api_key, model=scene_images.DEFAULT_IMAGE_MODEL):
            with calls_lock:
                calls.append(Path(out_path))
            _time.sleep(0.03)  # widen the race window
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\n")
            return Path(out_path)

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(storyboard, "_gemini_text", return_value=raw), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=slow_generate):
            job_dir = Path(tmp) / "job"
            barrier = threading.Barrier(6)
            errors = []

            def attempt():
                try:
                    barrier.wait()
                    storyboard.generate_storyboard(job_dir, 1, "scene", 3, "key")
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=attempt) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)

            self.assertEqual(errors, [], msg=f"unexpected errors: {errors}")
            # Exactly 3 paid renders total (one per distinct frame), not 6 x 3.
            self.assertEqual(len(calls), 3, msg=f"expected one render per frame, got {len(calls)}")
            self.assertEqual(len(set(calls)), 3)


# --------------------------------------------------------------------------- #
# (4) Per-moment cached path logic                                             #
# --------------------------------------------------------------------------- #
class MomentPathTests(unittest.TestCase):
    def test_path_is_deterministic_and_under_scene_images(self):
        job_dir = Path("ui/data/simple/job")
        first = storyboard.cached_moment_image_path(job_dir, 1, 1)
        again = storyboard.cached_moment_image_path(job_dir, 1, 1)
        self.assertEqual(first, again)
        self.assertEqual(first.parent, job_dir / "scene_images")
        self.assertEqual(first.name, "scene_01_moment_01.png")

    def test_distinct_moments_distinct_paths(self):
        job_dir = Path("ui/data/simple/job")
        a = storyboard.cached_moment_image_path(job_dir, 1, 1)
        b = storyboard.cached_moment_image_path(job_dir, 1, 2)
        c = storyboard.cached_moment_image_path(job_dir, 2, 1)
        self.assertEqual(len({a, b, c}), 3)
        self.assertEqual(
            storyboard.cached_moment_image_path(job_dir, 3, 12).name,
            "scene_03_moment_12.png",
        )

    def test_rejects_bad_indices(self):
        job_dir = Path("ui/data/simple/job")
        for scene, moment in ((0, 1), (1, 0), (-1, 1), (1, -1), (True, 1), (1, 1.0), ("1", 1)):
            with self.assertRaises(storyboard.StoryboardError):
                storyboard.cached_moment_image_path(job_dir, scene, moment)


# --------------------------------------------------------------------------- #
# (5) Friendly, non-technical summary: AI path + fallbacks                     #
# --------------------------------------------------------------------------- #
class SummaryTests(unittest.TestCase):
    def test_ai_summary_returned_and_tidied(self):
        with mock.patch.object(
            storyboard, "_gemini_text",
            return_value='  "A calm sunrise over a quiet harbour."\n',
        ) as gem:
            out = storyboard.human_readable_summary("a long technical scene prompt", "key")
        gem.assert_called_once()
        self.assertEqual(out["method"], "ai")
        self.assertEqual(out["summary"], "A calm sunrise over a quiet harbour.")
        self.assertIsNone(out["warning"])

    def test_summary_fallback_no_key(self):
        with mock.patch.object(storyboard, "_gemini_text") as gem:
            out = storyboard.human_readable_summary("Scene 2: a misty forest at dawn", None)
        gem.assert_not_called()
        self.assertEqual(out["method"], "fallback")
        # leading "Scene N:" marker stripped by the fallback
        self.assertEqual(out["summary"], "a misty forest at dawn")
        self.assertIsNotNone(out["warning"])

    def test_summary_fallback_when_llm_raises(self):
        with mock.patch.object(
            storyboard, "_gemini_text",
            side_effect=storyboard.StoryboardError("Gemini text request failed: timeout"),
        ):
            out = storyboard.human_readable_summary("a vivid scene", "key")
        self.assertEqual(out["method"], "fallback")
        self.assertIn("a vivid scene", out["summary"])

    def test_summary_fallback_when_llm_empty(self):
        with mock.patch.object(storyboard, "_gemini_text", return_value="   "):
            out = storyboard.human_readable_summary("a vivid scene", "key")
        self.assertEqual(out["method"], "fallback")

    def test_summary_fallback_trims_long_prompt(self):
        long_prompt = "word " * 200
        out = storyboard.human_readable_summary(long_prompt, None)
        self.assertLessEqual(len(out["summary"]), storyboard._SUMMARY_FALLBACK_CHARS + 3)
        self.assertTrue(out["summary"].endswith("..."))

    def test_empty_prompt_rejected(self):
        with self.assertRaises(storyboard.StoryboardError):
            storyboard.human_readable_summary("   ", "key")


if __name__ == "__main__":
    unittest.main()
