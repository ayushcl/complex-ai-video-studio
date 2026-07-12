"""Tests for the admin image-model selector + the edit-prompt/regenerate flow.

Run from the repo root with:
    python -m unittest discover -s ui/tests -p test_simple_edit.py -v

FREE BY CONSTRUCTION: every paid surface is mocked, so no test ever spends or
hits a real API -
  * the paid image primitive (scene_images.generate_scene_image) is mocked;
  * the prompt-rewrite text call (simple_flow._rewrite_scene_prompts) and the
    friendly-summary text call (storyboard._gemini_text) are mocked, so urllib
    is never invoked.
The settings/scenes.json/cache logic runs against the real on-disk job tree in a
temp dir.
"""

import io
import json
import shutil
import sys
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

import characters  # noqa: E402
import engine_bridge as bridge  # noqa: E402
import negative_library as nl  # noqa: E402
import scene_images  # noqa: E402
import server as ui_server  # noqa: E402
import simple_flow  # noqa: E402
import storyboard as storyboard_mod  # noqa: E402
import video_tiers  # noqa: E402

from test_smoke import redirect_bridge_data, restore_bridge_data  # noqa: E402

SAMPLE_DOC = """# Acme hero spot

Scene 1: A dark modern desk, warm copper light drifting through a glass prism.

Scene 2: The camera pulls back slowly to reveal the full workspace.

Scene 3: A close hold on the finished product, calm and confident.
"""


def _fake_image_writer():
    """Drop-in for scene_images.generate_scene_image: writes a tiny PNG and
    records the calls, instead of hitting the paid API."""
    calls = []
    lock = threading.Lock()

    def fake_generate(prompt, out_path, api_key, model=scene_images.DEFAULT_IMAGE_MODEL):
        with lock:
            calls.append({"prompt": prompt, "out_path": Path(out_path), "model": model})
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\n frame")
        return Path(out_path)

    return fake_generate, calls


# --------------------------------------------------------------------------- #
# (1) Admin image-model setting: roundtrip + validation                        #
# --------------------------------------------------------------------------- #
class ImageModelSettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.chdir(bridge.REPO_ROOT)
        cls.data_dir = bridge.REPO_ROOT / "ui" / "data" / f"test_data_{uuid.uuid4().hex[:8]}"
        cls._original_dirs = redirect_bridge_data(cls.data_dir)
        cls._original_env = bridge.ENV_PATH
        bridge.ENV_PATH = cls.data_dir / "env_test"

    @classmethod
    def tearDownClass(cls):
        bridge.ENV_PATH = cls._original_env
        restore_bridge_data(cls._original_dirs)
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def test_default_image_model(self):
        """A fresh settings load defaults image_model to the Basic model."""
        settings = bridge.load_settings()
        self.assertEqual(settings["image_model"], "gemini-2.5-flash-image")

    def test_image_model_options_match_image_tiers(self):
        """The allow-list IS the IMAGE_TIERS models (single source of truth)."""
        self.assertEqual(
            bridge.image_model_options(),
            [t["model"] for t in video_tiers.IMAGE_TIERS],
        )

    def test_image_model_roundtrip_and_persists(self):
        saved = bridge.save_settings({"image_model": "gemini-3.1-flash-image"})
        self.assertEqual(saved["image_model"], "gemini-3.1-flash-image")
        # persists across loads
        self.assertEqual(bridge.load_settings()["image_model"], "gemini-3.1-flash-image")
        # restore default for other tests in this class
        bridge.save_settings({"image_model": "gemini-2.5-flash-image"})

    def test_image_model_validated_against_allow_list(self):
        for bad in ("not-a-model", "imagen-4.0-fast-generate-001", "", "  "):
            with self.assertRaisesRegex(bridge.BridgeError, "image_model"):
                bridge.save_settings({"image_model": bad})
        # the rejected save left the prior (default) value intact
        self.assertEqual(bridge.load_settings()["image_model"], "gemini-2.5-flash-image")

    def test_all_three_tier_models_accepted(self):
        for model in ("gemini-2.5-flash-image", "gemini-3.1-flash-image", "gemini-3-pro-image"):
            saved = bridge.save_settings({"image_model": model})
            self.assertEqual(saved["image_model"], model)
        bridge.save_settings({"image_model": "gemini-2.5-flash-image"})


# --------------------------------------------------------------------------- #
# (2) Storyboard user path uses the configured model with NO token             #
# --------------------------------------------------------------------------- #
class StoryboardUserPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.chdir(bridge.REPO_ROOT)
        cls.data_dir = bridge.REPO_ROOT / "ui" / "data" / f"test_data_{uuid.uuid4().hex[:8]}"
        cls._original_dirs = redirect_bridge_data(cls.data_dir)
        cls._original_env = bridge.ENV_PATH
        bridge.ENV_PATH = cls.data_dir / "env_test"
        bridge.set_env_key("GEMINI_API_KEY", "test-key-userpath")

    @classmethod
    def tearDownClass(cls):
        bridge.set_env_key("GEMINI_API_KEY", clear=True)
        bridge.ENV_PATH = cls._original_env
        restore_bridge_data(cls._original_dirs)
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def _author(self, name):
        return simple_flow.author_job({"text": SAMPLE_DOC, "job_name": name})["job"]["job_dir"]

    def test_user_path_no_tier_no_token_uses_configured_model(self):
        """With NO image_tier and NO token, the storyboard renders with the
        admin-configured image model, ungated."""
        bridge.save_settings({"image_model": "gemini-3.1-flash-image"})
        try:
            job_dir = self._author("sb-userpath")
            fake_generate, calls = _fake_image_writer()
            with mock.patch.object(storyboard_mod, "_gemini_text",
                                   return_value='{"moments": ["m1"]}'), \
                    mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
                result = simple_flow.storyboard_generate(job_dir, images_per_scene=1)
            self.assertIsNone(result["image_tier"])
            self.assertFalse(result["gated"])
            self.assertTrue(result["free_to_user"])
            self.assertEqual(result["model"], "gemini-3.1-flash-image")
            # 3 scenes x 1 image, all rendered via the configured model
            self.assertEqual(result["total_images"], 3)
            self.assertEqual(len(calls), 3)
            self.assertTrue(all(c["model"] == "gemini-3.1-flash-image" for c in calls))
        finally:
            bridge.save_settings({"image_model": "gemini-2.5-flash-image"})

    def test_empty_string_tier_is_user_path(self):
        """An empty-string image_tier (how the HTTP layer may pass a missing
        field) is treated as the default user path, not an unknown tier error."""
        job_dir = self._author("sb-emptytier")
        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(storyboard_mod, "_gemini_text",
                               return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = simple_flow.storyboard_generate(job_dir, "", images_per_scene=1)
        self.assertIsNone(result["image_tier"])
        self.assertEqual(result["model"], "gemini-2.5-flash-image")
        self.assertEqual(len(calls), 3)

    def test_user_path_respects_runaway_cap(self):
        """Even ungated, the user path cannot exceed MAX_STORYBOARD_IMAGES."""
        job_dir = self._author("sb-usercap")  # 3 scenes
        over = (video_tiers.MAX_STORYBOARD_IMAGES // 3) + 1  # 3 scenes x over > cap
        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            with self.assertRaisesRegex(bridge.BridgeError, "safety cap"):
                simple_flow.storyboard_generate(job_dir, images_per_scene=over)
        self.assertEqual(calls, [])

    def test_legacy_gated_tier_still_requires_token(self):
        """Passing an explicit PAID tier still goes through the gated path: a
        missing token is refused, spending nothing."""
        job_dir = self._author("sb-legacy-gate")
        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(storyboard_mod, "_gemini_text",
                               return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            with self.assertRaisesRegex(bridge.BridgeError, "confirmation token"):
                simple_flow.storyboard_generate(job_dir, "standard", images_per_scene=1)
        self.assertEqual(calls, [])

    def test_storyboard_estimate_user_path_billed_to_business(self):
        """The no-tier estimate reflects the configured model and is billed to
        the business (free to the user)."""
        bridge.save_settings({"image_model": "gemini-3-pro-image"})
        try:
            job_dir = self._author("sb-userest")
            est = simple_flow.estimate_storyboard(job_dir, images_per_scene=1)
            self.assertIsNone(est["image_tier"])
            self.assertEqual(est["model"], "gemini-3-pro-image")
            self.assertTrue(est["free_to_user"])
            self.assertEqual(est["estimate"]["billed_to"], "business")
            self.assertGreater(est["estimate"]["total"], 0.0)
        finally:
            bridge.save_settings({"image_model": "gemini-2.5-flash-image"})


# --------------------------------------------------------------------------- #
# (3) edit_scenes: rewrite + regenerate, scope handling, fail-loud             #
# --------------------------------------------------------------------------- #
class EditScenesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.chdir(bridge.REPO_ROOT)
        cls.data_dir = bridge.REPO_ROOT / "ui" / "data" / f"test_data_{uuid.uuid4().hex[:8]}"
        cls._original_dirs = redirect_bridge_data(cls.data_dir)
        cls._original_env = bridge.ENV_PATH
        bridge.ENV_PATH = cls.data_dir / "env_test"
        bridge.set_env_key("GEMINI_API_KEY", "test-key-edit")

    @classmethod
    def tearDownClass(cls):
        bridge.set_env_key("GEMINI_API_KEY", clear=True)
        bridge.ENV_PATH = cls._original_env
        restore_bridge_data(cls._original_dirs)
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def _author(self, name):
        return simple_flow.author_job({"text": SAMPLE_DOC, "job_name": name})["job"]["job_dir"]

    def _scenes_on_disk(self, job_dir):
        job = simple_flow.load_job(job_dir)
        data = json.loads((bridge.REPO_ROOT / job["scenes_path"]).read_text(encoding="utf-8"))
        return data["scenes"]

    def _scenes_path(self, job_dir):
        return bridge.REPO_ROOT / simple_flow.load_job(job_dir)["scenes_path"]

    def _rewrite_returning(self, mapping):
        """A fake _rewrite_scene_prompts that maps each input prompt to a new one
        via `mapping` (prefixing 'EDITED: ' so the change is detectable), keeping
        count + order."""
        def fake(scenes, instruction, api_key):
            return [{"prompt": "EDITED: " + str(s.get("prompt", "")).strip(),
                     "negative_prompt": s.get("negative_prompt")} for s in scenes]
        return fake

    def test_edit_single_scene_only_targets_that_scene(self):
        job_dir = self._author("edit-one")
        before = self._scenes_on_disk(job_dir)
        self.assertEqual(len(before), 3)
        fake_generate, calls = _fake_image_writer()

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=self._rewrite_returning({})), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "Friendly edited summary.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = simple_flow.edit_scenes(job_dir, 2, "make it brighter")

        self.assertEqual(result["scope"], 2)
        self.assertEqual(result["edited_indices"], [2])
        # only scene 2's prompt changed on disk; 1 and 3 are untouched
        after = self._scenes_on_disk(job_dir)
        self.assertEqual(after[0]["prompt"], before[0]["prompt"])
        self.assertEqual(after[2]["prompt"], before[2]["prompt"])
        self.assertTrue(after[1]["prompt"].startswith("EDITED: "))
        # exactly one scene re-rendered (one image), via the configured model
        self.assertEqual(len(result["scenes"]), 1)
        self.assertEqual(result["scenes"][0]["scene_index"], 2)
        self.assertEqual(result["rendered"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "gemini-2.5-flash-image")
        # the affected summary was refreshed + persisted on the job
        job = simple_flow.load_job(job_dir)
        self.assertEqual(job["scene_summaries"][1], "Friendly edited summary.")

    def test_edit_all_scenes_rewrites_and_rerenders_every_scene(self):
        job_dir = self._author("edit-all")
        before = self._scenes_on_disk(job_dir)
        fake_generate, calls = _fake_image_writer()

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=self._rewrite_returning({})), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "All edited.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = simple_flow.edit_scenes(job_dir, "all", "add a cinematic mood")

        self.assertEqual(result["scope"], "all")
        self.assertEqual(result["edited_indices"], [1, 2, 3])
        after = self._scenes_on_disk(job_dir)
        self.assertTrue(all(s["prompt"].startswith("EDITED: ") for s in after))
        # scene 1's seed_image / mode / duration must survive the rewrite
        self.assertEqual(after[0].get("seed_image"), before[0].get("seed_image"))
        self.assertEqual(after[0].get("mode"), before[0].get("mode"))
        self.assertEqual(after[0].get("duration_seconds"), before[0].get("duration_seconds"))
        # every scene re-rendered (one image each)
        self.assertEqual(len(result["scenes"]), 3)
        self.assertEqual(result["rendered"], 3)
        self.assertEqual(len(calls), 3)

    def test_edit_rewrite_is_exactly_one_llm_call(self):
        """The rewrite must be a SINGLE Gemini text call for the whole scope."""
        job_dir = self._author("edit-onecall")
        fake_generate, _ = _fake_image_writer()
        with mock.patch.object(simple_flow, "_rewrite_scene_prompts",
                               side_effect=self._rewrite_returning({})) as rewrite, \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "x", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            simple_flow.edit_scenes(job_dir, "all", "tweak")
        self.assertEqual(rewrite.call_count, 1)

    def test_edit_regenerates_images_deletes_stale_first(self):
        """Editing a scene deletes its stale cached image then re-renders, so the
        reel shows the new prompt's image (not the old cached one)."""
        job_dir = self._author("edit-regen")
        fake_generate, calls = _fake_image_writer()
        # First, render scene 2 via the user path so a cached image exists.
        with mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            simple_flow.storyboard_generate(job_dir, images_per_scene=1)
        first_round = len(calls)
        self.assertGreater(first_round, 0)

        # Now edit scene 2: the stale image is deleted + a fresh render happens.
        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=self._rewrite_returning({})), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "x", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = simple_flow.edit_scenes(job_dir, 2, "brighter")
        # a NEW paid render happened for the edited scene (cache was cleared)
        self.assertEqual(result["rendered"], 1)
        self.assertEqual(len(calls), first_round + 1)
        # the new moment image exists on disk and is repo-relative
        moment = result["scenes"][0]["moments"][0]
        self.assertFalse(Path(moment["path"]).is_absolute())
        self.assertTrue((bridge.REPO_ROOT / moment["path"]).is_file())
        # the rewritten prompt drove the render
        self.assertEqual(calls[-1]["prompt"], result["scenes"][0]["prompt"])

    def test_edit_fails_loud_on_llm_error_and_changes_nothing(self):
        """On an LLM rewrite failure, edit_scenes raises and mutates NOTHING:
        scenes.json, summaries, and cached images are unchanged, no paid render."""
        job_dir = self._author("edit-failloud")
        before = self._scenes_on_disk(job_dir)
        before_summaries = list(simple_flow.load_job(job_dir)["scene_summaries"])
        fake_generate, calls = _fake_image_writer()

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts",
                               side_effect=simple_flow.AuthorError("Gemini request failed: boom")), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            with self.assertRaisesRegex(bridge.BridgeError, "nothing was changed"):
                simple_flow.edit_scenes(job_dir, 1, "rewrite please")

        self.assertEqual(self._scenes_on_disk(job_dir), before)
        self.assertEqual(simple_flow.load_job(job_dir)["scene_summaries"], before_summaries)
        self.assertEqual(calls, [], "no paid render may happen when the rewrite fails")

    def test_edit_rejects_bad_scope(self):
        job_dir = self._author("edit-badscope")
        for bad in ("everything", 0, 99, -1, "0"):
            with self.assertRaises(bridge.BridgeError):
                simple_flow.edit_scenes(job_dir, bad, "x")

    def test_edit_rejects_empty_instruction(self):
        job_dir = self._author("edit-noinstr")
        with self.assertRaisesRegex(bridge.BridgeError, "instruction"):
            simple_flow.edit_scenes(job_dir, "all", "   ")

    def test_edit_does_not_touch_video_gates(self):
        """Editing must not create a packet, must not start a run, and must not
        flip any spend authorization."""
        job_dir = self._author("edit-nogates")
        fake_generate, _ = _fake_image_writer()
        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=self._rewrite_returning({})), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "x", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate), \
                mock.patch.object(bridge, "start_live_run",
                                  side_effect=AssertionError("edit must never start a live run")):
            simple_flow.edit_scenes(job_dir, "all", "tweak")
        # no packet files were written into the job dir
        job = simple_flow.load_job(job_dir)
        job_path = bridge.REPO_ROOT / job["job_dir"]
        self.assertEqual(list(job_path.glob("packet_*.json")), [])

    def test_edit_without_cast_uses_existing_rewrite_shape(self):
        job_dir = self._author("edit-nocast-regression")
        before = self._scenes_on_disk(job_dir)
        expected = json.loads(json.dumps(before))
        expected[1]["prompt"] = "EDITED: " + before[1]["prompt"]
        expected_bytes = (
            json.dumps({"scenes": expected}, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        seen_payload = []
        fake_generate, _ = _fake_image_writer()

        def fake_rewrite(scenes, instruction, api_key):
            seen_payload.append([dict(scene) for scene in scenes])
            return [{"prompt": "EDITED: " + scenes[0]["prompt"],
                     "negative_prompt": scenes[0].get("negative_prompt")}]

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=fake_rewrite), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "Friendly edited summary.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = simple_flow.edit_scenes(job_dir, 2, "make it brighter")

        self.assertEqual(seen_payload[0][0]["prompt"], before[1]["prompt"])
        self.assertEqual(self._scenes_path(job_dir).read_bytes(), expected_bytes)
        self.assertEqual(result["scenes"][0]["prompt"], expected[1]["prompt"])

    def test_edit_scene_one_reapplies_f5_normalization(self):
        job_dir = self._author("edit-f5-scene-one")
        reframe = nl.positive_reframe()
        fake_generate, _ = _fake_image_writer()

        def fake_rewrite(scenes, instruction, api_key):
            return [{"prompt": "Scene one rewritten",
                     "negative_prompt": "rewrite tried to add a negative"}]

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=fake_rewrite), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "Scene one edited.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = simple_flow.edit_scenes(job_dir, 1, "rewrite scene one")

        after = self._scenes_on_disk(job_dir)
        self.assertNotIn("negative_prompt", after[0])
        self.assertEqual(after[0]["prompt"].count(reframe), 1)
        self.assertEqual(result["scenes"][0]["prompt"], after[0]["prompt"])

    def test_edit_scene_one_f5_normalization_is_idempotent(self):
        job_dir = self._author("edit-f5-scene-one-twice")
        reframe = nl.positive_reframe()
        fake_generate, _ = _fake_image_writer()

        def fake_rewrite(scenes, instruction, api_key):
            return [{"prompt": scenes[0]["prompt"],
                     "negative_prompt": "rewrite tried to add a negative"}]

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=fake_rewrite), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "Scene one edited.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            simple_flow.edit_scenes(job_dir, 1, "first rewrite")
            simple_flow.edit_scenes(job_dir, 1, "second rewrite")

        after = self._scenes_on_disk(job_dir)
        self.assertNotIn("negative_prompt", after[0])
        self.assertEqual(after[0]["prompt"].count(reframe), 1)

    def test_edit_preserves_existing_scene_two_plus_negative(self):
        fake_generate, _ = _fake_image_writer()

        def fake_rewrite(scenes, instruction, api_key):
            return [{"prompt": "EDITED: " + scenes[0]["prompt"],
                     "negative_prompt": None}]

        job_dir = self._author("edit-f5-composed-negative")
        before = self._scenes_on_disk(job_dir)
        composed_negative = before[1]["negative_prompt"]
        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=fake_rewrite), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "Scene two edited.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            simple_flow.edit_scenes(job_dir, 2, "rewrite scene two")
        after = self._scenes_on_disk(job_dir)
        self.assertEqual(after[1].get("negative_prompt"), composed_negative)

        custom_doc = json.dumps({
            "scenes": [
                {"prompt": "Scene one seed."},
                {"prompt": "Scene two product.", "negative_prompt": "operator custom negative"},
            ]
        })
        custom_job = simple_flow.author_job(
            {"text": custom_doc, "job_name": "edit-f5-custom-negative"}
        )["job"]["job_dir"]
        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=fake_rewrite), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "Scene two edited.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            simple_flow.edit_scenes(custom_job, 2, "rewrite scene two")
        custom_after = self._scenes_on_disk(custom_job)
        self.assertEqual(custom_after[1].get("negative_prompt"), "operator custom negative")

    def test_edit_scene_one_preserves_f4_block_bytes_with_f5_normalization(self):
        job_dir = self._author("edit-f5-f4-bytes")
        block = "Figure. Ava stays byte-identical, every comma locked."
        characters.save_characters(
            job_dir,
            [{"name": "Ava", "block": block}],
            {"Ava": [1]},
        )
        characters.apply_characters_to_job(job_dir)
        expected_block = ("\n\n[character: Ava]\n" + block).encode("utf-8")
        fake_generate, _ = _fake_image_writer()

        def fake_rewrite(scenes, instruction, api_key):
            return [{"prompt": "Scene one rewritten",
                     "negative_prompt": "rewrite tried to add a negative"}]

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=fake_rewrite), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "Scene one edited.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            simple_flow.edit_scenes(job_dir, 1, "rewrite scene one")

        after = self._scenes_on_disk(job_dir)
        self.assertIn(expected_block, after[0]["prompt"].encode("utf-8"))
        self.assertEqual(after[0]["prompt"].count(nl.positive_reframe()), 1)
        self.assertNotIn("negative_prompt", after[0])

    def test_edit_scene_one_library_absent_is_f5_noop(self):
        job_dir = self._author("edit-f5-library-absent")
        scenes_path = self._scenes_path(job_dir)
        data = json.loads(scenes_path.read_text(encoding="utf-8"))
        data["scenes"][0]["prompt"] = "Scene one rewritten without reframe"
        data["scenes"][0]["negative_prompt"] = "keep scene one negative"
        scenes_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        fake_generate, _ = _fake_image_writer()

        def fake_rewrite(scenes, instruction, api_key):
            return [{"prompt": "Scene one rewritten without reframe",
                     "negative_prompt": "keep scene one negative"}]

        original_library = simple_flow.negative_library
        simple_flow.negative_library = None
        try:
            with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=fake_rewrite), \
                    mock.patch.object(storyboard_mod, "human_readable_summary",
                                      return_value={"summary": "Scene one edited.", "method": "ai", "warning": None}), \
                    mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                    mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
                simple_flow.edit_scenes(job_dir, 1, "rewrite scene one")
        finally:
            simple_flow.negative_library = original_library

        after = self._scenes_on_disk(job_dir)
        self.assertEqual(after[0].get("negative_prompt"), "keep scene one negative")
        self.assertNotIn(nl.positive_reframe(), after[0]["prompt"])

    def test_edit_strips_character_blocks_before_rewrite_then_reinjects(self):
        job_dir = self._author("edit-character-safe")
        before = self._scenes_on_disk(job_dir)
        block = "Figure. Ava stays byte-identical, every comma locked."
        characters.save_characters(
            job_dir,
            [{"name": "Ava", "block": block}],
            {"Ava": "all"},
        )
        characters.apply_characters_to_job(job_dir)
        applied = self._scenes_on_disk(job_dir)
        self.assertIn(block.encode("utf-8"), applied[0]["prompt"].encode("utf-8"))

        seen_payload = []
        summary_inputs = []
        fake_generate, calls = _fake_image_writer()

        def fake_rewrite(scenes, instruction, api_key):
            seen_payload.append([dict(scene) for scene in scenes])
            return [{"prompt": "MANGLED HUMAN TEXT ONLY",
                     "negative_prompt": scenes[0].get("negative_prompt")}]

        def fake_summary(prompt, api_key):
            summary_inputs.append(prompt)
            return {"summary": "Summary saw: " + prompt, "method": "ai", "warning": None}

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=fake_rewrite), \
                mock.patch.object(storyboard_mod, "human_readable_summary", side_effect=fake_summary), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = simple_flow.edit_scenes(job_dir, 1, "paraphrase the scene")

        after = self._scenes_on_disk(job_dir)
        self.assertNotIn("[character: Ava]", seen_payload[0][0]["prompt"])
        self.assertNotIn(block, seen_payload[0][0]["prompt"])
        self.assertIn(block.encode("utf-8"), after[0]["prompt"].encode("utf-8"))
        self.assertEqual(after[0].get("seed_image"), before[0].get("seed_image"))
        self.assertEqual(after[0].get("duration_seconds"), before[0].get("duration_seconds"))
        self.assertNotIn(block, simple_flow.load_job(job_dir)["scene_summaries"][0])
        self.assertNotIn(block, summary_inputs[0])
        self.assertNotIn(block, calls[0]["prompt"])
        self.assertEqual(result["scenes"][0]["prompt"], after[0]["prompt"])

    def test_edit_unassigned_scene_leaves_other_scene_blocks_untouched(self):
        job_dir = self._author("edit-unassigned-scene")
        block = "Figure. Ava stays byte-identical for scene one only."
        characters.save_characters(
            job_dir,
            [{"name": "Ava", "block": block}],
            {"Ava": [1]},
        )
        characters.apply_characters_to_job(job_dir)
        before = self._scenes_on_disk(job_dir)
        fake_generate, _ = _fake_image_writer()

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=self._rewrite_returning({})), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "Scene two edited.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            simple_flow.edit_scenes(job_dir, 2, "make scene two brighter")

        after = self._scenes_on_disk(job_dir)
        self.assertEqual(after[0]["prompt"].encode("utf-8"), before[0]["prompt"].encode("utf-8"))
        self.assertIn(block.encode("utf-8"), after[0]["prompt"].encode("utf-8"))
        self.assertNotIn(block, after[1]["prompt"])


# --------------------------------------------------------------------------- #
# (4) HTTP: /api/settings exposes image_model + options; edit-scenes route      #
# --------------------------------------------------------------------------- #
class EditHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.chdir(bridge.REPO_ROOT)
        cls.data_dir = bridge.REPO_ROOT / "ui" / "data" / f"test_data_{uuid.uuid4().hex[:8]}"
        cls._original_dirs = redirect_bridge_data(cls.data_dir)
        cls._original_env = bridge.ENV_PATH
        bridge.ENV_PATH = cls.data_dir / "env_test"
        bridge.set_env_key("GEMINI_API_KEY", "test-key-http-edit")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.ApiHandler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        bridge.set_env_key("GEMINI_API_KEY", clear=True)
        bridge.ENV_PATH = cls._original_env
        restore_bridge_data(cls._original_dirs)
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def request(self, method, path, body=None, raw=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _author(self, name):
        status, upload = self.request("POST", "/api/simple/upload?name=brief.md",
                                      raw=SAMPLE_DOC.encode("utf-8"))
        status, authored = self.request("POST", "/api/simple/author",
                                        {"source_path": upload["path"], "job_name": name})
        return authored["job"]["job_dir"]

    def test_settings_exposes_image_model_and_options(self):
        status, data = self.request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertIn("image_model", data["settings"])
        self.assertEqual(data["settings"]["image_model"], "gemini-2.5-flash-image")
        self.assertEqual(
            data["image_model_options"],
            ["gemini-2.5-flash-image", "gemini-3.1-flash-image", "gemini-3-pro-image"],
        )

    def test_models_endpoint_sets_image_model(self):
        status, data = self.request("POST", "/api/settings/models",
                                    {"image_model": "gemini-3.1-flash-image"})
        self.assertEqual(status, 200, msg=str(data))
        self.assertEqual(data["settings"]["image_model"], "gemini-3.1-flash-image")
        # invalid model is refused
        status, data = self.request("POST", "/api/settings/models",
                                    {"image_model": "imagen-4.0-fast-generate-001"})
        self.assertEqual(status, 400)
        self.assertIn("image_model", data["error"])
        # restore default
        self.request("POST", "/api/settings/models", {"image_model": "gemini-2.5-flash-image"})

    def test_edit_scenes_route(self):
        job_dir = self._author("http-edit")
        fake_generate, calls = _fake_image_writer()

        def fake_rewrite(scenes, instruction, api_key):
            return [{"prompt": "EDITED: " + str(s.get("prompt", "")).strip(),
                     "negative_prompt": None} for s in scenes]

        with mock.patch.object(simple_flow, "_rewrite_scene_prompts", side_effect=fake_rewrite), \
                mock.patch.object(storyboard_mod, "human_readable_summary",
                                  return_value={"summary": "Edited.", "method": "ai", "warning": None}), \
                mock.patch.object(storyboard_mod, "_gemini_text", return_value='{"moments": ["m1"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            status, data = self.request("POST", "/api/simple/edit-scenes",
                                        {"job_dir": job_dir, "scope": 1,
                                         "instruction": "make it warmer"})
        self.assertEqual(status, 200, msg=str(data))
        self.assertEqual(data["edited_indices"], [1])
        self.assertEqual(len(data["scenes"]), 1)
        self.assertTrue(data["scenes"][0]["prompt"].startswith("EDITED: "))
        self.assertTrue(data["scenes"][0]["moments"][0]["path"])


if __name__ == "__main__":
    unittest.main()
