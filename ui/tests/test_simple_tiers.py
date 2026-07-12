"""Tests for the Phase-A render tiers wired into simple mode:

  * per-video-tier cost estimates (Standard / Quality / Ultra 4K),
  * human-readable scene summaries stored on author,
  * tiered storyboard generation: the FREE Basic tier needs NO confirm-token
    but respects the runaway cap; the PAID Standard/Premium tiers are refused
    without a valid confirm-token (and accepted with one),
  * the /api/simple/tiers endpoint.

Run from the repo root with:
    python -m unittest discover -s ui/tests -p test_simple_tiers.py -v

FREE BY CONSTRUCTION: every paid surface is mocked, so no test ever spends or
hits a real API -
  * the paid image primitive (scene_images.generate_scene_image) is mocked;
  * the cheap Gemini text call (storyboard._gemini_text, used for the moment
    split + the friendly summary) is mocked, so urllib is never invoked;
  * the live Popen spawn (--run) is faked.
The cap/token/cache logic runs against the real on-disk job tree in a temp dir.
"""

import io
import json
import shutil
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

import engine_bridge as bridge  # noqa: E402
import scene_images  # noqa: E402
import server as ui_server  # noqa: E402
import simple_flow  # noqa: E402
import storyboard as storyboard_mod  # noqa: E402
import video_tiers  # noqa: E402

from test_smoke import redirect_bridge_data, restore_bridge_data  # noqa: E402

SAMPLE_DOC = """# Acme hero spot

Scene 1: A dark modern desk, warm copper light drifting through a glass prism.

Scene 2: The camera pulls back slowly to reveal the full workspace.
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


class _Base(unittest.TestCase):
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

    def _author(self, name):
        return simple_flow.author_job({"text": SAMPLE_DOC, "job_name": name})["job"]["job_dir"]


# --------------------------------------------------------------------------- #
# (1) Per-video-tier estimates                                                 #
# --------------------------------------------------------------------------- #
class VideoTierEstimateTests(_Base):
    def test_estimate_accepts_video_tier_keys(self):
        job_dir = self._author("tier-est")
        for key in video_tiers.video_tier_keys():
            detail = simple_flow.estimate(job_dir, key, max_scenes=1)
            self.assertEqual(detail["tier"], key)
            tier = video_tiers.resolve_video_tier(key)
            self.assertEqual(detail["model"], tier["model"])
            self.assertEqual(detail["resolution"], tier["resolution"])
            self.assertIn("total", detail["estimate"])

    def test_higher_tiers_cost_more_for_same_job(self):
        """Standard (fast@1080p 0.12) < Quality (std@1080p 0.40) < Ultra 4K
        (std@4k 0.60) for the same scene count, under the REAL default pricing."""
        job_dir = self._author("tier-order")
        std = simple_flow.estimate(job_dir, "standard", max_scenes=2)["estimate"]["video"]
        quality = simple_flow.estimate(job_dir, "quality", max_scenes=2)["estimate"]["video"]
        ultra = simple_flow.estimate(job_dir, "ultra4k", max_scenes=2)["estimate"]["video"]
        self.assertLess(std, quality)
        self.assertLess(quality, ultra)

    def test_legacy_quality_keys_still_work(self):
        """The pre-existing draft/hq selectors must keep working (the frontend
        still uses them)."""
        job_dir = self._author("legacy-est")
        for q in ("draft", "hq"):
            detail = simple_flow.estimate(job_dir, q, max_scenes=1)
            self.assertEqual(detail["tier"], q)
            self.assertIn("total", detail["estimate"])

    def test_unknown_tier_refused(self):
        job_dir = self._author("bad-tier")
        with self.assertRaisesRegex(bridge.BridgeError, "tier must be one of"):
            simple_flow.estimate(job_dir, "supreme", max_scenes=1)


# --------------------------------------------------------------------------- #
# (2) Human-readable summary stored on author                                 #
# --------------------------------------------------------------------------- #
class SceneSummaryTests(_Base):
    def test_summary_stored_per_scene_heuristic(self):
        """With no Gemini key, author still stores one friendly summary per
        scene (heuristic fallback) on the job + in the response."""
        result = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "summary-heur"})
        summaries = result["scene_summaries"]
        self.assertEqual(len(summaries), result["job"]["scene_count"])
        self.assertTrue(all(isinstance(s, str) and s.strip() for s in summaries))
        # persisted on the job + survives a reopen for the carousel
        job = simple_flow.load_job(result["job"]["job_dir"])
        self.assertEqual(job["scene_summaries"], summaries)
        self.assertEqual(job["summary_method"], "fallback")
        reopened = simple_flow.open_job(result["job"]["job_dir"])
        self.assertEqual(reopened["scene_summaries"], summaries)

    def test_summary_uses_ai_when_key_set(self):
        """With a key set + AI extraction on, the friendly summary comes from the
        (mocked) text model. The text call is mocked, so nothing is networked."""
        bridge.set_env_key("GEMINI_API_KEY", "test-key-for-summary")
        try:
            with mock.patch.object(
                storyboard_mod, "_gemini_text",
                return_value="A calm, premium desk bathed in warm copper light.",
            ) as gem:
                result = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "summary-ai"})
            self.assertTrue(gem.called)
            self.assertEqual(result["job"]["summary_method"], "ai")
            self.assertTrue(all(
                s == "A calm, premium desk bathed in warm copper light."
                for s in result["scene_summaries"]
            ))
        finally:
            bridge.set_env_key("GEMINI_API_KEY", clear=True)


# --------------------------------------------------------------------------- #
# (3) Tiered storyboard generation: Basic ungated (capped) vs paid gated       #
# --------------------------------------------------------------------------- #
class StoryboardTierTests(_Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Storyboard generation needs a usable key (the image primitive is mocked
        # but scene_image_api_key() still checks one is configured).
        bridge.set_env_key("GEMINI_API_KEY", "test-key-for-storyboard")

    @classmethod
    def tearDownClass(cls):
        bridge.set_env_key("GEMINI_API_KEY", clear=True)
        super().tearDownClass()

    def test_basic_tier_needs_no_token_and_renders(self):
        """The FREE Basic tier generates WITHOUT a confirm-token. Every paid
        image call is mocked, so this never spends."""
        job_dir = self._author("sb-basic")
        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(storyboard_mod, "_gemini_text",
                               return_value='{"moments": ["m1", "m2"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = simple_flow.storyboard_generate(job_dir, "basic", images_per_scene=2)
        self.assertEqual(result["image_tier"], "basic")
        self.assertFalse(result["gated"])
        self.assertEqual(result["model"], "gemini-2.5-flash-image")
        # 2 scenes x 2 images = 4 frames, all rendered (mocked) via gemini-2.5-flash-image.
        self.assertEqual(result["total_images"], 4)
        self.assertEqual(result["rendered"], 4)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(c["model"] == "gemini-2.5-flash-image" for c in calls))
        # paths are repo-relative (servable via /api/media), and the files exist
        for scene in result["scenes"]:
            for moment in scene["moments"]:
                self.assertFalse(Path(moment["path"]).is_absolute())
                self.assertTrue((bridge.REPO_ROOT / moment["path"]).is_file())

    def test_basic_tier_respects_runaway_cap(self):
        """Even ungated, Basic cannot exceed MAX_STORYBOARD_IMAGES: a request
        whose scene_count x images_per_scene tops the cap is refused BEFORE any
        paid call, so a bug cannot loop the free path into runaway spend."""
        job_dir = self._author("sb-cap")  # 2 scenes
        # 2 scenes x 21 = 42 > 40 cap.
        over = (video_tiers.MAX_STORYBOARD_IMAGES // 2) + 1
        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            with self.assertRaisesRegex(bridge.BridgeError, "safety cap"):
                simple_flow.storyboard_generate(job_dir, "basic", images_per_scene=over)
        self.assertEqual(calls, [], "no paid image call may happen once the cap is exceeded")

    def test_paid_tier_refused_without_token(self):
        """A PAID image tier (Standard/Premium) must refuse with no token and
        with a bogus token, spending nothing."""
        job_dir = self._author("sb-paid-notoken")
        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(storyboard_mod, "_gemini_text",
                               return_value='{"moments": ["m1", "m2"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            for tier in ("standard", "premium"):
                with self.assertRaisesRegex(bridge.BridgeError, "confirmation token"):
                    simple_flow.storyboard_generate(job_dir, tier, images_per_scene=2)
                with self.assertRaisesRegex(bridge.BridgeError, "confirmation token"):
                    simple_flow.storyboard_generate(
                        job_dir, tier, images_per_scene=2, confirm_token="not-real")
        self.assertEqual(calls, [], "no paid render may happen without a valid token")

    def test_paid_tier_accepts_valid_token_and_burns_it(self):
        """Standard tier: a valid storyboard confirm-token unlocks the render and
        is single-use (a replay is refused). Image calls mocked -> no spend."""
        job_dir = self._author("sb-paid-ok")
        issued = simple_flow.issue_storyboard_confirmation(job_dir, "standard", images_per_scene=2)
        token = issued["confirm_token"]
        self.assertEqual(issued["image_tier"], "standard")
        self.assertIn("estimate", issued)

        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(storyboard_mod, "_gemini_text",
                               return_value='{"moments": ["m1", "m2"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            result = simple_flow.storyboard_generate(
                job_dir, "standard", images_per_scene=2, confirm_token=token)
            self.assertTrue(result["gated"])
            self.assertEqual(result["model"], "gemini-3.1-flash-image")
            self.assertEqual(result["rendered"], 4)
            self.assertTrue(all(c["model"] == "gemini-3.1-flash-image" for c in calls))

            # the token is single-use: replaying it is refused (nothing re-spent)
            before = len(calls)
            with self.assertRaisesRegex(bridge.BridgeError, "already used|unknown"):
                simple_flow.storyboard_generate(
                    job_dir, "standard", images_per_scene=2, confirm_token=token)
            self.assertEqual(len(calls), before)

    def test_storyboard_token_is_tier_bound(self):
        """A token minted for Standard cannot generate Premium (tier-bound)."""
        job_dir = self._author("sb-tierbound")
        token = simple_flow.issue_storyboard_confirmation(
            job_dir, "standard", images_per_scene=2)["confirm_token"]
        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(storyboard_mod, "_gemini_text",
                               return_value='{"moments": ["m1", "m2"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            with self.assertRaisesRegex(bridge.BridgeError, "does not match"):
                simple_flow.storyboard_generate(
                    job_dir, "premium", images_per_scene=2, confirm_token=token)
        self.assertEqual(calls, [])

    def test_minting_token_for_free_tier_refused(self):
        """The free Basic tier is ungated; minting a token for it is refused so
        the UI never gates the free path."""
        job_dir = self._author("sb-freetoken")
        with self.assertRaisesRegex(bridge.BridgeError, "ungated|free"):
            simple_flow.issue_storyboard_confirmation(job_dir, "basic", images_per_scene=2)

    def test_storyboard_estimate_distinguishes_billed_to(self):
        job_dir = self._author("sb-est")
        basic = simple_flow.estimate_storyboard(job_dir, "basic", images_per_scene=2)
        standard = simple_flow.estimate_storyboard(job_dir, "standard", images_per_scene=2)
        self.assertEqual(basic["estimate"]["billed_to"], "business")
        self.assertTrue(basic["free_to_user"])
        self.assertGreater(basic["estimate"]["total"], 0.0)  # real business cost
        self.assertEqual(standard["estimate"]["billed_to"], "user")
        self.assertFalse(standard["free_to_user"])


# --------------------------------------------------------------------------- #
# (4) HTTP endpoints: /api/simple/tiers + storyboard routes                    #
# --------------------------------------------------------------------------- #
class TierHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.chdir(bridge.REPO_ROOT)
        cls.data_dir = bridge.REPO_ROOT / "ui" / "data" / f"test_data_{uuid.uuid4().hex[:8]}"
        cls._original_dirs = redirect_bridge_data(cls.data_dir)
        cls._original_env = bridge.ENV_PATH
        bridge.ENV_PATH = cls.data_dir / "env_test"
        bridge.set_env_key("GEMINI_API_KEY", "test-key-http-storyboard")
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

    def test_tiers_endpoint_lists_video_and_image_tiers(self):
        status, data = self.request("GET", "/api/simple/tiers")
        self.assertEqual(status, 200)
        self.assertEqual([t["key"] for t in data["video"]], ["standard", "quality", "ultra4k"])
        self.assertEqual([t["key"] for t in data["image"]], ["basic", "standard", "premium"])
        # rates are present (REAL numbers)
        self.assertAlmostEqual(data["video"][0]["per_second_rate"], 0.12)
        self.assertAlmostEqual(data["image"][0]["per_image_rate"], 0.039)
        self.assertEqual(data["max_storyboard_images"], video_tiers.MAX_STORYBOARD_IMAGES)
        # the gating contract is carried in the data
        self.assertFalse(data["image"][0]["gated"])  # basic ungated
        self.assertTrue(data["image"][1]["gated"])    # standard gated

    def test_settings_endpoint_includes_tiers_and_real_pricing(self):
        status, data = self.request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertIn("tiers", data)
        self.assertIn("video", data["tiers"])
        veo = data["settings"]["pricing"]["veo_per_second"]
        self.assertAlmostEqual(veo["veo-3.1-generate-preview"]["4k"], 0.60)

    def test_storyboard_basic_over_http_no_token(self):
        """Basic tier over HTTP renders with no token. Image calls mocked."""
        job_dir = self._author("http-sb-basic")
        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(storyboard_mod, "_gemini_text",
                               return_value='{"moments": ["m1", "m2"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            status, data = self.request("POST", "/api/simple/storyboard",
                                        {"job_dir": job_dir, "image_tier": "basic",
                                         "images_per_scene": 2})
        self.assertEqual(status, 200, msg=str(data))
        self.assertEqual(data["total_images"], 4)
        self.assertEqual(len(calls), 4)

    def test_storyboard_paid_over_http_refused_without_token(self):
        job_dir = self._author("http-sb-paid")
        status, data = self.request("POST", "/api/simple/storyboard",
                                    {"job_dir": job_dir, "image_tier": "standard",
                                     "images_per_scene": 2})
        self.assertEqual(status, 400)
        self.assertIn("confirmation token", data["error"])

    def test_storyboard_confirm_token_then_generate_over_http(self):
        job_dir = self._author("http-sb-token")
        status, issued = self.request("POST", "/api/simple/storyboard/confirm-token",
                                      {"job_dir": job_dir, "image_tier": "premium",
                                       "images_per_scene": 2})
        self.assertEqual(status, 200, msg=str(issued))
        token = issued["confirm_token"]
        fake_generate, calls = _fake_image_writer()
        with mock.patch.object(storyboard_mod, "_gemini_text",
                               return_value='{"moments": ["m1", "m2"]}'), \
                mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
            status, data = self.request("POST", "/api/simple/storyboard",
                                        {"job_dir": job_dir, "image_tier": "premium",
                                         "images_per_scene": 2, "confirm_token": token})
        self.assertEqual(status, 200, msg=str(data))
        self.assertEqual(data["model"], "gemini-3-pro-image")
        self.assertEqual(len(calls), 4)


# --------------------------------------------------------------------------- #
# (5) Video generate by tier key still flows through the live-run gates        #
# --------------------------------------------------------------------------- #
class VideoTierGenerateTests(_Base):
    def test_generate_by_video_tier_threads_model_into_packet(self):
        """generate() with a VIDEO render-tier key threads that tier's
        model+resolution into the packet, while every spend gate stays intact.
        Only the live (--run) spawn is faked; the dry-run is the real adapter."""
        job_dir = self._author("gen-tier")

        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO("Run ID: tier_fake\n")
                self.stderr = io.StringIO("")
                self.returncode = 0
            def wait(self):
                return 0

        real_popen = bridge.subprocess.Popen

        def selective_popen(argv, *args, **kwargs):
            if "--run" in argv:
                return FakeProcess()
            return real_popen(argv, *args, **kwargs)

        tier = video_tiers.resolve_video_tier("quality")
        token = simple_flow.issue_confirmation(job_dir, "quality", max_scenes=1)["confirm_token"]
        with mock.patch.object(bridge.subprocess, "Popen", side_effect=selective_popen):
            outcome = simple_flow.generate(job_dir, "quality", confirm_token=token, max_scenes=1)
        self.assertEqual(outcome["tier"], "quality")
        packet = json.loads((bridge.REPO_ROOT / outcome["packet_path"]).read_text(encoding="utf-8"))
        self.assertEqual(packet["model"], tier["model"])
        self.assertEqual(packet["resolution"], tier["resolution"])
        self.assertTrue(packet["spend_controls"]["allow_live_run"])
        # wait for the fake run to settle
        for _ in range(50):
            if bridge.run_status(outcome["ui_run_id"])["status"] != "running":
                break
            time.sleep(0.1)
        job = simple_flow.load_job(job_dir)
        self.assertEqual(job["runs"]["quality"]["ui_run_id"], outcome["ui_run_id"])

    def test_generate_refuses_video_tier_without_token(self):
        job_dir = self._author("gen-tier-notoken")
        with self.assertRaisesRegex(bridge.BridgeError, "confirmation token"):
            simple_flow.generate(job_dir, "ultra4k", confirm_token="")


if __name__ == "__main__":
    unittest.main()
