"""Smoke tests for the operator UI.

Run from the repo root with:  python -m unittest discover -s ui/tests -v

Everything here is free: dry-runs go through the real run_from_packet.py
subprocess (which never spends without --run), and the live-run test mocks the
process spawn so no paid pipeline can ever start from the test suite.
"""

import io
import json
import os
import shutil
import sys
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

import cost_estimator  # noqa: E402
import engine_bridge as bridge  # noqa: E402
import simple_flow  # noqa: E402
import server as ui_server  # noqa: E402


def redirect_bridge_data(root: Path) -> dict:
    """Point the bridge's data tree at a disposable subtree so tests never
    pollute the operator's real saved packets / ledger / audit log."""
    original = {
        "DATA_DIR": bridge.DATA_DIR,
        "PACKETS_DIR": bridge.PACKETS_DIR,
        "VOICES_DIR": bridge.VOICES_DIR,
        "RUNS_LEDGER_PATH": bridge.RUNS_LEDGER_PATH,
        "AUDIT_LOG_PATH": bridge.AUDIT_LOG_PATH,
    }
    bridge.DATA_DIR = root
    bridge.PACKETS_DIR = root / "packets"
    bridge.VOICES_DIR = root / "voices"
    bridge.RUNS_LEDGER_PATH = root / "runs.json"
    bridge.AUDIT_LOG_PATH = root / "audit.jsonl"
    bridge.ensure_data_dirs()
    return original


def restore_bridge_data(original: dict) -> None:
    for key, value in original.items():
        setattr(bridge, key, value)


def make_fixtures(root: Path) -> dict:
    """Create dummy job assets under the repo root (path safety requires it).
    The adapter's dry-run only checks file existence, so empty stand-ins are
    enough and nothing is ever generated or spent."""
    root.mkdir(parents=True, exist_ok=True)
    storyboard = root / "storyboard.json"
    storyboard.write_text(json.dumps({"project_name": "smoke", "brand_name": "Test"}), encoding="utf-8")
    video = root / "existing_video.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")  # stand-in; only isfile() is checked on dry-run
    seed = root / "seed.png"
    seed.write_bytes(b"\x89PNG\r\n\x1a\n")
    scenes = root / "scenes.json"
    scenes.write_text(json.dumps({
        "scenes": [
            {"mode": "image", "seed_image": bridge.rel_path(seed), "duration_seconds": 6, "prompt": "Test seed prompt."},
            {"prompt": "Test extension prompt."},
        ]
    }), encoding="utf-8")
    voice = root / "prepared_voice.json"
    voice.write_text(json.dumps({"workspace_voice_id": "test-voice-id"}), encoding="utf-8")
    presenter_reference = root / "presenter_reference.jpeg"
    presenter_reference.write_bytes(b"\xff\xd8\xff\xd9")
    audition = root / "auditions" / "sample_a.mp3"
    audition.parent.mkdir(parents=True, exist_ok=True)
    audition.write_bytes(b"ID3\x03\x00\x00\x00")
    (root / "auditions" / "auditions_manifest.json").write_text(json.dumps({
        "auditions": [{"file": "sample_a.mp3", "workspace_voice_id": "voice-aaa", "label": "Sample A"}]
    }), encoding="utf-8")
    return {
        "storyboard": bridge.rel_path(storyboard),
        "video": bridge.rel_path(video),
        "scenes": bridge.rel_path(scenes),
        "voice": bridge.rel_path(voice),
        "presenter_reference": bridge.rel_path(presenter_reference),
        "auditions_dir": bridge.rel_path(audition.parent),
        "root": root,
    }


def silent_existing_packet(fx, allow_live=False):
    return {
        "job_id": "smoke-silent-existing",
        "content_path": "silent_brand",
        "video_source": "existing",
        "video_path": fx["video"],
        "scenes_path": None,
        "storyboard_path": fx["storyboard"],
        "voice": {"prepared_voice_path": None},
        "output_settings": {"output_dir": "ui/data/test_runs"},
        "spend_controls": {"allow_live_run": allow_live},
    }


def simple_artifact_text(prompt: str = "A clean product shot on a modern desk.") -> str:
    return json.dumps({
        "scenes": [{"prompt": prompt}],
        "storyboard": {"project_name": "smoke", "brand_name": "Test"},
    })


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(bridge.REPO_ROOT)
        cls.data_dir = bridge.REPO_ROOT / "ui" / "data" / f"test_data_{uuid.uuid4().hex[:8]}"
        cls._original_dirs = redirect_bridge_data(cls.data_dir)
        cls.fixture_dir = cls.data_dir / "fixtures"
        cls.fx = make_fixtures(cls.fixture_dir)

    @classmethod
    def tearDownClass(cls):
        restore_bridge_data(cls._original_dirs)
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    # ---- packet building ------------------------------------------------ #
    def test_form_never_emits_start_stage(self):
        packet = bridge.build_packet_from_form({
            "content_path": "silent_brand", "video_source": "existing",
            "video_path": self.fx["video"], "storyboard_path": self.fx["storyboard"],
        })
        self.assertNotIn("start_stage", packet)
        self.assertFalse(packet["spend_controls"]["allow_live_run"])

    def test_silent_brand_carries_no_voice(self):
        packet = bridge.build_packet_from_form({
            "content_path": "silent_brand", "video_source": "existing",
            "video_path": self.fx["video"], "storyboard_path": self.fx["storyboard"],
            "prepared_voice_path": self.fx["voice"],  # must be dropped for silent
        })
        self.assertIsNone(packet["voice"]["prepared_voice_path"])

    def test_generate_defaults_spend_cap_low(self):
        packet = bridge.build_packet_from_form({
            "content_path": "silent_brand", "video_source": "generate",
            "scenes_path": self.fx["scenes"], "storyboard_path": self.fx["storyboard"],
        })
        self.assertEqual(packet["max_scenes"], 1)

    def test_presenter_generate_carries_optional_reference_image(self):
        packet = bridge.build_packet_from_form({
            "content_path": "presenter", "video_source": "generate",
            "scenes_path": self.fx["scenes"], "storyboard_path": self.fx["storyboard"],
            "prepared_voice_path": self.fx["voice"],
            "presenter_reference_image_path": self.fx["presenter_reference"],
        })
        self.assertEqual(
            packet["presenter_reference_image_path"],
            self.fx["presenter_reference"],
        )

    def test_silent_generate_carries_asset_reference_image(self):
        packet = bridge.build_packet_from_form({
            "content_path": "silent_brand", "video_source": "generate",
            "scenes_path": self.fx["scenes"], "storyboard_path": self.fx["storyboard"],
            "presenter_reference_image_path": self.fx["presenter_reference"],
        })
        self.assertEqual(
            packet["presenter_reference_image_path"],
            self.fx["presenter_reference"],
        )

    def test_existing_has_no_generation_params(self):
        packet = bridge.build_packet_from_form({
            "content_path": "silent_brand", "video_source": "existing",
            "video_path": self.fx["video"], "storyboard_path": self.fx["storyboard"],
            "max_scenes": 5, "model": "x", "resolution": "4k", "aspect_ratio": "16:9",
        })
        self.assertIsNone(packet["max_scenes"])
        self.assertIsNone(packet["model"])
        self.assertIsNone(packet["scenes_path"])
        self.assertNotIn("aspect_ratio", packet)

    def test_simple_author_defaults_aspect_ratio_to_vertical(self):
        with mock.patch.object(simple_flow, "_gemini_key_for_text", return_value=None):
            result = simple_flow.author_job({
                "text": simple_artifact_text("A vertical default aspect test scene."),
                "job_name": f"smoke-aspect-default-{uuid.uuid4().hex[:8]}",
            })
        job = result["job"]
        packet = simple_flow._packet_for(job, "standard", {}, authorized=False)
        self.assertEqual(job["aspect_ratio"], "9:16")
        self.assertEqual(packet["aspect_ratio"], "9:16")

    def test_simple_author_carries_landscape_aspect_ratio_to_packet(self):
        with mock.patch.object(simple_flow, "_gemini_key_for_text", return_value=None):
            result = simple_flow.author_job({
                "text": simple_artifact_text("A landscape aspect test scene."),
                "job_name": f"smoke-aspect-landscape-{uuid.uuid4().hex[:8]}",
                "aspect_ratio": "16:9",
            })
        job = result["job"]
        packet = simple_flow._packet_for(job, "standard", {}, authorized=False)
        self.assertEqual(job["aspect_ratio"], "16:9")
        self.assertEqual(packet["aspect_ratio"], "16:9")

    def test_simple_presenter_author_yields_presenter_packet(self):
        with mock.patch.object(simple_flow, "_gemini_key_for_text", return_value=None):
            result = simple_flow.author_job({
                "text": simple_artifact_text("A presenter speaking to camera."),
                "content_path": "presenter",
                "prepared_voice_path": self.fx["voice"],
            })
        job = result["job"]
        self.assertEqual(job["content_path"], "presenter")
        packet = simple_flow._packet_for(job, "standard", {}, authorized=False)
        self.assertEqual(packet["content_path"], "presenter")
        self.assertEqual(packet["voice"]["prepared_voice_path"], job["prepared_voice_path"])
        review = bridge.structured_review(packet)
        self.assertTrue(review["valid"], msg=review.get("error"))

    def test_simple_silent_author_unchanged_when_no_content_path(self):
        with mock.patch.object(simple_flow, "_gemini_key_for_text", return_value=None):
            result = simple_flow.author_job({
                "text": simple_artifact_text("A silent brand montage."),
            })
        job = result["job"]
        self.assertNotIn("content_path", job)
        packet = simple_flow._packet_for(job, "standard", {}, authorized=False)
        self.assertEqual(packet["content_path"], "silent_brand")
        self.assertIsNone(packet["voice"]["prepared_voice_path"])

    def test_simple_reference_estimate_forces_presenter_reference_tier(self):
        with mock.patch.object(simple_flow, "_gemini_key_for_text", return_value=None):
            result = simple_flow.author_job({
                "text": simple_artifact_text("A reference-led product reveal."),
                "job_name": f"smoke-reference-estimate-{uuid.uuid4().hex[:8]}",
                "reference_image_path": self.fx["presenter_reference"],
            })
        job = result["job"]
        self.assertEqual(job["reference_image_path"], self.fx["presenter_reference"])
        est = simple_flow.estimate(job["job_dir"], "standard")
        self.assertEqual(est["resolution"], "720p")
        self.assertEqual(est["model"], bridge.adapter().PRESENTER_REFERENCE_MODEL)

    def test_invalid_aspect_rejected_by_simple_and_form_builder(self):
        with self.assertRaisesRegex(bridge.BridgeError, "aspect_ratio"):
            simple_flow.author_job({"aspect_ratio": "1:1"})
        with self.assertRaisesRegex(bridge.BridgeError, "aspect_ratio"):
            bridge.build_packet_from_form({
                "content_path": "silent_brand", "video_source": "generate",
                "scenes_path": self.fx["scenes"], "storyboard_path": self.fx["storyboard"],
                "aspect_ratio": "1:1",
            })

    def test_build_packet_from_form_aspect_ratio_generate_and_existing(self):
        default_packet = bridge.build_packet_from_form({
            "content_path": "silent_brand", "video_source": "generate",
            "scenes_path": self.fx["scenes"], "storyboard_path": self.fx["storyboard"],
        })
        self.assertEqual(default_packet["aspect_ratio"], "9:16")

        landscape_packet = bridge.build_packet_from_form({
            "content_path": "silent_brand", "video_source": "generate",
            "scenes_path": self.fx["scenes"], "storyboard_path": self.fx["storyboard"],
            "aspect_ratio": "16:9",
        })
        self.assertEqual(landscape_packet["aspect_ratio"], "16:9")

        existing_packet = bridge.build_packet_from_form({
            "content_path": "silent_brand", "video_source": "existing",
            "video_path": self.fx["video"], "storyboard_path": self.fx["storyboard"],
            "aspect_ratio": "16:9",
        })
        self.assertNotIn("aspect_ratio", existing_packet)

    def test_run_from_packet_derives_aspect_ratio_only_for_generate(self):
        adapter = bridge.adapter()
        packet = silent_existing_packet(self.fx)
        packet.update({
            "video_source": "generate",
            "video_path": None,
            "scenes_path": self.fx["scenes"],
            "model": "veo-3.1-fast-generate-preview",
            "resolution": "1080p",
            "max_scenes": 1,
        })

        adapter.validate_packet(packet)
        argv, start_stage = adapter.build_command(packet)
        self.assertEqual(start_stage, "video")
        self.assertIn("--aspect-ratio", argv)
        self.assertEqual(argv[argv.index("--aspect-ratio") + 1], "9:16")

        packet["aspect_ratio"] = "16:9"
        adapter.validate_packet(packet)
        argv, start_stage = adapter.build_command(packet)
        self.assertEqual(start_stage, "video")
        self.assertEqual(argv[argv.index("--aspect-ratio") + 1], "16:9")

        existing_argv, existing_start_stage = adapter.build_command(silent_existing_packet(self.fx))
        self.assertEqual(existing_start_stage, "extract")
        self.assertNotIn("--aspect-ratio", existing_argv)

    def test_extension_call_forces_eight_second_duration(self):
        from video_generation_agency import run_veo_extension_chain as runner

        seed_scene = {
            "prompt": "Test seed prompt.",
            "duration_seconds": 6,
            "negative_prompt": "seed-negative",
        }
        extension_scene = {
            "prompt": "Test extension prompt.",
            "negative_prompt": "extension-negative",
        }

        self.assertEqual(runner.EXTENSION_DURATION_SECONDS, 8)
        for aspect_ratio in ("9:16", "16:9"):
            _, seed_config = runner.build_config(
                seed_scene,
                include_duration=True,
                resolution="720p",
                aspect_ratio=aspect_ratio,
            )
            _, extension_config = runner.build_config(
                extension_scene,
                include_duration=False,
                resolution="720p",
                aspect_ratio=aspect_ratio,
                extension_duration_seconds=runner.EXTENSION_DURATION_SECONDS,
            )

            self.assertEqual(seed_config["duration_seconds"], 6)
            self.assertEqual(
                extension_config["duration_seconds"],
                runner.EXTENSION_DURATION_SECONDS,
            )

    def test_existing_video_ignores_manual_aspect_ratio_in_adapter_and_review(self):
        adapter = bridge.adapter()
        packet = silent_existing_packet(self.fx)
        packet["aspect_ratio"] = "1:1"

        warnings = adapter.validate_packet(packet)
        argv, start_stage = adapter.build_command(packet)
        review = bridge.structured_review(packet)

        self.assertEqual(warnings, [])
        self.assertEqual(start_stage, "extract")
        self.assertNotIn("--aspect-ratio", argv)
        self.assertTrue(review["valid"], msg=review.get("error"))
        self.assertIsNone(review["aspect_ratio"])

    # ---- structured review (adapter functions in-process) --------------- #
    def test_structured_review_valid_silent_existing(self):
        review = bridge.structured_review(silent_existing_packet(self.fx))
        self.assertTrue(review["valid"])
        self.assertEqual(review["start_stage"], "extract")
        self.assertIn("--skip-sts", review["derived_command"])
        self.assertNotIn("--run", review["derived_argv"])

    def test_structured_review_presenter_existing_derives_sts(self):
        packet = silent_existing_packet(self.fx)
        packet["content_path"] = "presenter"
        packet["voice"] = {"prepared_voice_path": self.fx["voice"]}
        review = bridge.structured_review(packet)
        self.assertTrue(review["valid"])
        self.assertEqual(review["start_stage"], "sts")

    def test_structured_review_generate_derives_video_and_flags_experimental(self):
        packet = silent_existing_packet(self.fx)
        packet.update({"video_source": "generate", "video_path": None,
                       "scenes_path": self.fx["scenes"], "max_scenes": 1,
                       "content_path": "presenter",
                       "voice": {"prepared_voice_path": self.fx["voice"]}})
        review = bridge.structured_review(packet)
        self.assertTrue(review["valid"])
        self.assertEqual(review["start_stage"], "video")
        self.assertTrue(review["experimental"])

    def test_presenter_reference_derives_fixed_fast_reference_command(self):
        packet = silent_existing_packet(self.fx)
        packet.update({
            "video_source": "generate", "video_path": None,
            "scenes_path": self.fx["scenes"], "max_scenes": 1,
            "content_path": "presenter", "model": "some-other-model",
            "resolution": "4k",
            "presenter_reference_image_path": self.fx["presenter_reference"],
            "voice": {"prepared_voice_path": self.fx["voice"]},
        })
        review = bridge.structured_review(packet)
        self.assertTrue(review["valid"])
        self.assertEqual(review["model"], "veo-3.1-fast-generate-preview")
        self.assertEqual(review["resolution"], "720p")
        self.assertIn("--presenter-reference-image", review["derived_argv"])
        self.assertIn("veo-3.1-fast-generate-preview", review["derived_argv"])

    def test_adapter_rejects_reference_image_on_existing_video(self):
        packet = silent_existing_packet(self.fx)
        packet["presenter_reference_image_path"] = self.fx["presenter_reference"]
        review = bridge.structured_review(packet)
        self.assertFalse(review["valid"])
        self.assertIn("requires video_source 'generate'", review["error"])

    def test_structured_review_rejects_missing_storyboard(self):
        packet = silent_existing_packet(self.fx)
        packet["storyboard_path"] = "ui/data/does_not_exist.json"
        review = bridge.structured_review(packet)
        self.assertFalse(review["valid"])
        self.assertIn("storyboard", review["error"])

    def test_structured_review_rejects_voice_on_silent(self):
        packet = silent_existing_packet(self.fx)
        packet["voice"] = {"prepared_voice_path": self.fx["voice"]}
        review = bridge.structured_review(packet)
        self.assertFalse(review["valid"])

    # ---- path safety ----------------------------------------------------- #
    def test_safe_path_rejects_escape(self):
        with self.assertRaises(bridge.BridgeError):
            bridge.safe_path("../outside.txt")
        with self.assertRaises(bridge.BridgeError):
            bridge.safe_path("C:/Windows/system32/drivers/etc/hosts")

    # ---- scenes inspection ------------------------------------------------ #
    def test_inspect_scenes_reports_seed_and_cap(self):
        info = bridge.inspect_scenes(self.fx["scenes"], max_scenes=1)
        self.assertEqual(info["scene_count"], 2)
        self.assertEqual(info["effective_scenes"], 1)
        self.assertTrue(info["seed_image_exists"])
        self.assertEqual(info["issues"], [])

    def test_inspect_scenes_rejects_media_file_with_clear_message(self):
        seed = self.fixture_dir / "seed.png"
        with self.assertRaisesRegex(bridge.BridgeError, "media file"):
            bridge.inspect_scenes(bridge.rel_path(seed))

    def test_read_json_rejects_binary_with_clear_message(self):
        seed = self.fixture_dir / "seed.png"
        with self.assertRaisesRegex(bridge.BridgeError, "not a text file"):
            bridge.read_json_file(seed, "Scenes file")

    def test_inspect_scenes_flags_missing_seed(self):
        bad = self.fixture_dir / "scenes_bad.json"
        bad.write_text(json.dumps([{"prompt": "no seed"}]), encoding="utf-8")
        info = bridge.inspect_scenes(bridge.rel_path(bad))
        self.assertTrue(any("seed_image" in issue for issue in info["issues"]))

    # ---- dry-run through the real adapter -------------------------------- #
    def test_dry_run_passes_and_spends_nothing(self):
        saved = bridge.save_packet(silent_existing_packet(self.fx), "smoke-dryrun")
        result = bridge.dry_run(saved["path"])
        self.assertTrue(result["ok"], msg=result["stderr"])
        self.assertEqual(result["returncode"], 0)
        self.assertIn("PACKET VALIDATED", result["stdout"])
        self.assertIn("DRY-RUN", result["stdout"])
        self.assertNotIn("EXECUTING LIVE", result["stdout"])

    def test_dry_run_rejects_bad_packet(self):
        packet = silent_existing_packet(self.fx)
        packet["storyboard_path"] = "ui/data/missing.json"
        saved = bridge.save_packet(packet, "smoke-bad")
        result = bridge.dry_run(saved["path"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["returncode"], 2)
        self.assertIn("PACKET REJECTED", result["stderr"])

    # ---- live-run gates --------------------------------------------------- #
    def test_live_refuses_wrong_confirmation(self):
        saved = bridge.save_packet(silent_existing_packet(self.fx, allow_live=True), "smoke-live")
        bridge.dry_run(saved["path"])
        with self.assertRaisesRegex(bridge.BridgeError, "confirmation"):
            bridge.start_live_run(saved["path"], confirm="yes")

    def test_live_refuses_without_dry_run(self):
        saved = bridge.save_packet(silent_existing_packet(self.fx, allow_live=True), "smoke-nodry")
        with self.assertRaisesRegex(bridge.BridgeError, "dry-run"):
            bridge.start_live_run(saved["path"], confirm=bridge.CONFIRM_PHRASE)

    def test_live_refuses_unauthorized_packet(self):
        saved = bridge.save_packet(silent_existing_packet(self.fx, allow_live=False), "smoke-noauth")
        bridge.dry_run(saved["path"])
        with self.assertRaisesRegex(bridge.BridgeError, "allow_live_run"):
            bridge.start_live_run(saved["path"], confirm=bridge.CONFIRM_PHRASE)

    def test_live_refuses_stale_packet_bytes(self):
        packet = silent_existing_packet(self.fx, allow_live=True)
        saved = bridge.save_packet(packet, "smoke-stale")
        bridge.dry_run(saved["path"])
        # Mutate the packet after the dry-run: live must refuse.
        packet["job_id"] = "tampered"
        (bridge.REPO_ROOT / saved["path"]).write_text(json.dumps(packet), encoding="utf-8")
        with self.assertRaisesRegex(bridge.BridgeError, "changed since"):
            bridge.start_live_run(saved["path"], confirm=bridge.CONFIRM_PHRASE)

    def test_live_spawns_adapter_with_run_flag_when_all_gates_pass(self):
        saved = bridge.save_packet(silent_existing_packet(self.fx, allow_live=True), "smoke-spawn")
        bridge.dry_run(saved["path"])

        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO("Run ID: full_fake\nRun directory: ui/data/test_runs/full_fake\n")
                self.stderr = io.StringIO("")
                self.returncode = 0
            def wait(self):
                return 0

        with mock.patch.object(bridge.subprocess, "Popen", return_value=FakeProcess()) as popen:
            result = bridge.start_live_run(saved["path"], confirm=bridge.CONFIRM_PHRASE)
            argv = popen.call_args[0][0]

        self.assertIn("--run", argv)
        self.assertIn("--packet", argv)
        self.assertTrue(str(argv[1]).endswith("run_from_packet.py"))
        # Wait for the watcher thread to settle so later tests see a finished run.
        for _ in range(50):
            if bridge.run_status(result["ui_run_id"])["status"] != "running":
                break
            time.sleep(0.1)
        status = bridge.run_status(result["ui_run_id"])
        self.assertEqual(status["status"], "succeeded")
        self.assertEqual(status["engine_run_id"], "full_fake")

    def test_live_concurrent_requests_spawn_exactly_one_run(self):
        """Racing confirmed live requests must never duplicate spend: the
        gate-check -> registration sequence is atomic, so exactly one of N
        simultaneous requests spawns and the rest are refused."""
        saved = bridge.save_packet(silent_existing_packet(self.fx, allow_live=True), "smoke-race")
        bridge.dry_run(saved["path"])

        release = threading.Event()

        class BlockingFakeProcess:
            def __init__(self):
                self.stdout = io.StringIO("Run ID: full_race\n")
                self.stderr = io.StringIO("")
                self.returncode = 0
            def wait(self):
                release.wait(timeout=30)
                return 0

        outcomes = []
        barrier = threading.Barrier(8)

        def attempt():
            barrier.wait()
            try:
                outcomes.append(("ok", bridge.start_live_run(saved["path"], confirm=bridge.CONFIRM_PHRASE)))
            except bridge.BridgeError as exc:
                outcomes.append(("refused", str(exc)))

        with mock.patch.object(bridge.subprocess, "Popen", side_effect=lambda *a, **k: BlockingFakeProcess()) as popen:
            threads = [threading.Thread(target=attempt) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            spawned = popen.call_count
        release.set()

        self.assertEqual(spawned, 1, msg=f"expected exactly one spawn, outcomes: {outcomes}")
        self.assertEqual(sum(1 for kind, _ in outcomes if kind == "ok"), 1)
        self.assertEqual(sum(1 for kind, _ in outcomes if kind == "refused"), 7)
        # Let the single fake run settle so later tests see no running run.
        ok_result = next(result for kind, result in outcomes if kind == "ok")
        for _ in range(50):
            if bridge.run_status(ok_result["ui_run_id"])["status"] != "running":
                break
            time.sleep(0.1)

    # ---- voice selection --------------------------------------------------- #
    def test_voice_select_requires_listening(self):
        with self.assertRaisesRegex(bridge.BridgeError, "listen"):
            bridge.select_voice({"workspace_voice_id": "v", "listened": False})

    def test_voice_select_requires_voice_id(self):
        with self.assertRaisesRegex(bridge.BridgeError, "workspace_voice_id"):
            bridge.select_voice({"listened": True, "workspace_voice_id": ""})

    def test_voice_select_writes_prepared_voice(self):
        sample = f"{self.fx['auditions_dir']}/sample_a.mp3"
        result = bridge.select_voice({
            "sample_path": sample,
            "workspace_voice_id": "voice-aaa",
            "label": "Sample A",
            "listened": True,
        })
        prepared = json.loads((bridge.REPO_ROOT / result["prepared_voice_path"]).read_text(encoding="utf-8"))
        self.assertEqual(prepared["workspace_voice_id"], "voice-aaa")
        self.assertTrue(prepared["listened_confirmed"])
        self.assertEqual(prepared["source_sample"], sample)

    def test_auditions_listed_alphabetically_with_metadata(self):
        listing = bridge.list_auditions(self.fx["auditions_dir"])
        self.assertEqual(len(listing["samples"]), 1)
        sample = listing["samples"][0]
        self.assertEqual(sample["workspace_voice_id"], "voice-aaa")
        self.assertEqual(sample["label"], "Sample A")


class CostEstimatorPresenterTests(unittest.TestCase):
    """The pure cost estimator must cost a presenter-reference job at the FORCED
    Veo 3.1 Fast / 720p / 8s the engine actually bills, not the operator's pick
    or the scenes-file duration. Pure: no disk, no network, no bridge fixtures."""

    def test_presenter_reference_forces_fast_720p_8s_seed(self):
        job = {
            "scene_count": 1, "max_scenes": 1,
            # The operator "picked" an expensive tier and a short seed; reference
            # mode must override BOTH for the estimate.
            "model": "veo-3.1-generate-preview", "resolution": "4k",
            "scenes": [{"duration_seconds": 6}],
            "presenter_reference_image_path": "presenter_reference.jpeg",
        }
        result = cost_estimator.estimate_cost(job, "hq")
        bd = result["breakdown"]
        self.assertEqual(bd["veo_model"], cost_estimator.PRESENTER_REFERENCE_MODEL)
        self.assertEqual(bd["veo_resolution"], cost_estimator.PRESENTER_REFERENCE_RESOLUTION)
        self.assertEqual(bd["seed_seconds"], cost_estimator.PRESENTER_REFERENCE_SEED_SECONDS)
        # Single scene => total seconds == the forced 8s seed, billed at the
        # fast-720p rate (0.10/s), not the 4k rate (0.60/s) the operator picked.
        self.assertEqual(bd["seconds_total"], 8)
        self.assertEqual(bd["veo_rate_per_second"], 0.10)
        self.assertAlmostEqual(result["video"], 8 * 0.10, places=4)

    def test_no_presenter_reference_keeps_operator_model_and_default_seed(self):
        """Guard against regressing the normal path: with no reference image the
        operator's model/resolution win and the seed falls back to 6s."""
        job = {
            "scene_count": 1, "max_scenes": 1,
            "model": "veo-3.1-generate-preview", "resolution": "4k",
        }
        bd = cost_estimator.estimate_cost(job, "hq")["breakdown"]
        self.assertEqual(bd["veo_model"], "veo-3.1-generate-preview")
        self.assertEqual(bd["veo_resolution"], "4k")
        self.assertEqual(bd["seed_seconds"], cost_estimator.DEFAULT_SEED_SECONDS)


class HttpApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(bridge.REPO_ROOT)
        cls.data_dir = bridge.REPO_ROOT / "ui" / "data" / f"test_data_{uuid.uuid4().hex[:8]}"
        cls._original_dirs = redirect_bridge_data(cls.data_dir)
        cls.fixture_dir = cls.data_dir / "fixtures"
        cls.fx = make_fixtures(cls.fixture_dir)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.ApiHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        restore_bridge_data(cls._original_dirs)
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def request(self, method, path, body=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(payload)
            except json.JSONDecodeError:
                return exc.code, {"raw": payload}

    def make_simple_character_job(self, name="http-characters"):
        job_dir = self.data_dir / "simple" / f"{name}_{uuid.uuid4().hex[:8]}"
        job_dir.mkdir(parents=True, exist_ok=True)
        scenes = {
            "scenes": [
                {
                    "prompt": "Scene one. Host enters frame.",
                    "seed_image": "ui/data/seed.png",
                    "duration_seconds": 6,
                },
                {
                    "prompt": "Scene two. Product detail close-up.",
                    "duration_seconds": 7,
                },
            ]
        }
        (job_dir / "scenes.json").write_text(
            json.dumps(scenes, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return bridge.rel_path(job_dir)

    def simple_characters_path(self, job_dir):
        return f"/api/simple/characters?dir={urllib.parse.quote(job_dir, safe='')}"

    def read_simple_job_scenes(self, job_dir):
        path = bridge.safe_path(job_dir) / "scenes.json"
        return json.loads(path.read_text(encoding="utf-8"))["scenes"]

    def test_health(self):
        status, data = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data["adapter_exists"])
        # The health payload must never contain key material.
        self.assertNotIn("GEMINI_API_KEY", json.dumps(data))

    def test_index_served(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=30) as resp:
            html = resp.read().decode("utf-8")
        self.assertIn("Video Ad Pipeline", html)
        self.assertIn('id="s-reference-zone"', html)
        self.assertIn('id="s-seed-zone"', html)
        self.assertIn('id="s-seed-advanced"', html)
        self.assertIn("Run live", html)

    def test_simple_characters_get_absent_file_returns_empty_doc(self):
        job_dir = self.make_simple_character_job("http-chars-empty")

        status, data = self.request("GET", self.simple_characters_path(job_dir))

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["characters"], [])
        self.assertEqual(data["assignments"], {})

    def test_simple_characters_post_valid_cast_applies_and_round_trips(self):
        job_dir = self.make_simple_character_job("http-chars-valid")
        ava_block = "Figure. Ava exact commas, spacing, and case."
        bo_block = "Wardrobe. Bo exact commas, spacing, and case."

        status, data = self.request("POST", "/api/simple/characters", {
            "job_dir": job_dir,
            "characters": [
                {"name": "Ava", "block": ava_block},
                {"name": "Bo", "block": bo_block},
            ],
            "assignments": {"Ava": "all", "Bo": [2]},
        })

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["changed"])
        self.assertEqual(data["assignments"], {"Ava": "all", "Bo": [2]})
        self.assertIn(ava_block, data["prompts"][0]["prompt"])
        self.assertIn(ava_block, data["prompts"][1]["prompt"])
        self.assertNotIn(bo_block, data["prompts"][0]["prompt"])
        self.assertIn(bo_block, data["prompts"][1]["prompt"])

        scenes = self.read_simple_job_scenes(job_dir)
        self.assertIn(ava_block.encode("utf-8"), scenes[0]["prompt"].encode("utf-8"))
        self.assertIn(bo_block.encode("utf-8"), scenes[1]["prompt"].encode("utf-8"))
        self.assertNotIn(bo_block.encode("utf-8"), scenes[0]["prompt"].encode("utf-8"))

        status, persisted = self.request("GET", self.simple_characters_path(job_dir))
        self.assertEqual(status, 200)
        self.assertEqual(persisted["characters"], data["characters"])
        self.assertEqual(persisted["assignments"], data["assignments"])

    def test_simple_characters_post_unknown_assignment_returns_400(self):
        job_dir = self.make_simple_character_job("http-chars-unknown")

        status, data = self.request("POST", "/api/simple/characters", {
            "job_dir": job_dir,
            "characters": [{"name": "Ava", "block": "Figure. Ava."}],
            "assignments": {"Ghost": "all"},
        })

        self.assertEqual(status, 400)
        self.assertIn("unknown character", data["error"].lower())

    def test_simple_characters_post_duplicate_and_over_cap_return_400(self):
        cases = [
            {
                "characters": [
                    {"name": "Ava", "block": "Figure. One."},
                    {"name": "Ava", "block": "Figure. Two."},
                ],
                "assignments": {},
                "message": "duplicate",
            },
            {
                "characters": [
                    {"name": f"Character {index}", "block": f"Figure. Character {index}."}
                    for index in range(9)
                ],
                "assignments": {},
                "message": "more than 8",
            },
        ]

        for case in cases:
            with self.subTest(message=case["message"]):
                job_dir = self.make_simple_character_job("http-chars-invalid")
                status, data = self.request("POST", "/api/simple/characters", {
                    "job_dir": job_dir,
                    "characters": case["characters"],
                    "assignments": case["assignments"],
                })

                self.assertEqual(status, 400)
                self.assertIn(case["message"], data["error"].lower())

    def test_simple_characters_missing_job_dir_returns_400(self):
        status, data = self.request("GET", "/api/simple/characters")
        self.assertEqual(status, 400)
        self.assertIn("dir", data["error"])

        status, data = self.request("POST", "/api/simple/characters", {
            "characters": [{"name": "Ava", "block": "Figure. Ava."}],
            "assignments": {"Ava": "all"},
        })
        self.assertEqual(status, 400)
        self.assertIn("job_dir", data["error"])

    def test_dryrun_endpoint_free_pass(self):
        status, saved = self.request("POST", "/api/packet/save",
                                     {"packet": silent_existing_packet(self.fx), "name": "http-smoke"})
        self.assertEqual(status, 200)
        status, result = self.request("POST", "/api/dryrun", {"path": saved["path"]})
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"], msg=result.get("stderr"))
        self.assertIn("DRY-RUN", result["stdout"])
        self.assertEqual(result["structured"]["start_stage"], "extract")

    def test_dryrun_endpoint_shows_validation_errors(self):
        packet = silent_existing_packet(self.fx)
        packet["video_path"] = "ui/data/nope.mp4"
        status, saved = self.request("POST", "/api/packet/save", {"packet": packet, "name": "http-bad"})
        status, result = self.request("POST", "/api/dryrun", {"path": saved["path"]})
        self.assertEqual(status, 200)
        self.assertFalse(result["ok"])
        self.assertIn("PACKET REJECTED", result["stderr"])

    def test_live_run_refused_without_gates(self):
        status, saved = self.request("POST", "/api/packet/save",
                                     {"packet": silent_existing_packet(self.fx), "name": "http-live"})
        status, result = self.request("POST", "/api/run/live",
                                      {"path": saved["path"], "confirm": "SPEND"})
        self.assertEqual(status, 400)
        self.assertIn("refused", result["error"].lower())

    def test_media_path_traversal_refused(self):
        status, result = self.request("GET", "/api/media?path=..%2F..%2Fsecrets.txt")
        self.assertEqual(status, 400)
        self.assertIn("refused", result["error"].lower())

    def test_media_refuses_secret_extensions(self):
        status, result = self.request("GET", "/api/media?path=.env.example")
        self.assertEqual(status, 400)

    def test_packet_authorize_roundtrip(self):
        status, saved = self.request("POST", "/api/packet/save",
                                     {"packet": silent_existing_packet(self.fx), "name": "http-auth"})
        status, result = self.request("POST", "/api/packet/authorize",
                                      {"path": saved["path"], "allow": True})
        self.assertEqual(status, 200)
        self.assertTrue(result["packet"]["spend_controls"]["allow_live_run"])
        status, result = self.request("POST", "/api/packet/authorize",
                                      {"path": saved["path"], "allow": False})
        self.assertFalse(result["packet"]["spend_controls"]["allow_live_run"])

    def test_pasted_packet_text_save(self):
        text = json.dumps(silent_existing_packet(self.fx))
        status, saved = self.request("POST", "/api/packet/save",
                                     {"packet_text": text, "name": "http-paste"})
        self.assertEqual(status, 200)
        self.assertIn("/packets/", saved["path"])

    def test_auditions_endpoint(self):
        status, data = self.request("GET", f"/api/auditions?dir={self.fx['auditions_dir']}")
        self.assertEqual(status, 200)
        self.assertEqual(data["samples"][0]["workspace_voice_id"], "voice-aaa")


if __name__ == "__main__":
    unittest.main()
