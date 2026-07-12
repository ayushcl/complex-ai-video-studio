"""Tests for simple mode: document parsing, authoring, settings, key storage,
and the draft/HQ generation gates.

Run from the repo root with:  python -m unittest discover -s ui/tests -v

Everything is free: authoring uses the heuristic path (no Gemini key in the
test environment), dry-runs go through the real adapter without --run, and
generation tests mock the process spawn.
"""

import io
import json
import shutil
import struct
import sys
import threading
import time
import unittest
import urllib.request
import uuid
import zipfile
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

import cost_estimator  # noqa: E402
import docparse  # noqa: E402
import engine_bridge as bridge  # noqa: E402
import simple_flow  # noqa: E402
import server as ui_server  # noqa: E402

from test_smoke import redirect_bridge_data, restore_bridge_data  # noqa: E402

SAMPLE_DOC = """# Acme hero spot

Scene 1: A dark modern desk, warm copper light drifting through a glass prism,
premium and calm, near-black interior.

Scene 2: The camera pulls back slowly to reveal the full workspace, the light
settling into a confident hold.
"""


def make_docx(text: str) -> bytes:
    """Minimal but valid .docx: one paragraph per input line."""
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines()
    )
    document = f'<?xml version="1.0"?><w:document {ns}><w:body>{paragraphs}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def make_pdf(lines) -> bytes:
    """Minimal PDF with one FlateDecode content stream of Tj text operators."""
    content = b"BT /F1 12 Tf 50 700 Td " + b" ".join(
        b"(" + line.encode("latin-1") + b") Tj 0 -20 Td" for line in lines
    ) + b" ET"
    compressed = zlib.compress(content)
    return (
        b"%PDF-1.4\n1 0 obj\n<< /Length " + str(len(compressed)).encode()
        + b" /Filter /FlateDecode >>\nstream\n" + compressed
        + b"\nendstream\nendobj\ntrailer\n<<>>\n%%EOF\n"
    )


class DocParseTests(unittest.TestCase):
    def test_text_and_markdown(self):
        self.assertIn("Scene 1", docparse.extract_text(SAMPLE_DOC.encode("utf-8"), ".md"))
        self.assertIn("Scene 1", docparse.extract_text(SAMPLE_DOC.encode("utf-8"), ".txt"))

    def test_docx_extraction(self):
        text = docparse.extract_text(make_docx(SAMPLE_DOC), ".docx")
        self.assertIn("Scene 1: A dark modern desk", text)
        self.assertIn("Scene 2: The camera pulls back", text)

    def test_pdf_extraction(self):
        text = docparse.extract_text(make_pdf(["Scene 1: copper light", "Scene 2: pull back"]), ".pdf")
        self.assertIn("Scene 1: copper light", text)
        self.assertIn("Scene 2: pull back", text)

    def test_pdf_image_only_fails_loudly(self):
        with self.assertRaisesRegex(docparse.DocParseError, "Could not extract"):
            docparse.extract_text(b"%PDF-1.4\nno text streams here\n%%EOF", ".pdf")

    def test_unsupported_extension(self):
        with self.assertRaisesRegex(docparse.DocParseError, "Unsupported"):
            docparse.extract_text(b"x", ".exe")

    def test_docx_flate_bomb_refused(self):
        """A docx whose document.xml inflates past the cap must raise a clean
        DocParseError, not MemoryError."""
        huge = b"<x>" + b"A" * (docparse.MAX_DOCX_XML_BYTES + 1024) + b"</x>"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", huge)
        # The compressed bomb is tiny (well under MAX_DOC_BYTES) but inflates huge.
        self.assertLess(len(buffer.getvalue()), docparse.MAX_DOC_BYTES)
        with self.assertRaisesRegex(docparse.DocParseError, "too large"):
            docparse.extract_text(buffer.getvalue(), ".docx")

    def test_docx_doctype_refused(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", "<!DOCTYPE x><x/>")
        with self.assertRaisesRegex(docparse.DocParseError, "document-type"):
            docparse.extract_text(buffer.getvalue(), ".docx")

    def test_pdf_flate_bomb_refused(self):
        """A PDF FlateDecode stream that inflates past the cap is refused."""
        bomb = zlib.compress(b"(" * (docparse.MAX_PDF_INFLATED_BYTES + 4096))
        data = (b"%PDF-1.4\nstream\n" + bomb + b"\nendstream\n%%EOF")
        self.assertLess(len(data), docparse.MAX_DOC_BYTES)
        with self.assertRaisesRegex(docparse.DocParseError, "unreasonable size|too much content"):
            docparse.extract_text(data, ".pdf")

    def test_pdf_regex_is_linear_on_adversarial_input(self):
        """Repeated unclosed '(' must not blow up: bounded quantifiers keep the
        scan linear. This would take many seconds with the old unbounded * regex."""
        content = b"BT " + b"\\(" * 60000 + b" ET"
        data = b"%PDF-1.4\nstream\n" + zlib.compress(content) + b"\nendstream\n%%EOF"
        started = time.monotonic()
        try:
            docparse.extract_text(data, ".pdf")
        except docparse.DocParseError:
            pass  # "no text" is fine; we only care it returned promptly
        self.assertLess(time.monotonic() - started, 5.0, "PDF parse took too long - backtracking regression")

    def test_scene_split_markers(self):
        scenes = docparse.split_scenes(SAMPLE_DOC)
        self.assertEqual(len(scenes), 2)
        self.assertIn("dark modern desk", scenes[0])

    def test_scene_split_falls_back_to_single(self):
        scenes = docparse.split_scenes("Just one flowing description with no markers at all.")
        self.assertEqual(len(scenes), 1)

    def test_heuristic_author_shapes(self):
        result = docparse.heuristic_author(SAMPLE_DOC, "acme-hero")
        self.assertEqual(result["method"], "heuristic")
        self.assertEqual(len(result["scenes"]), 2)
        for scene in result["scenes"]:
            self.assertTrue(scene["prompt"].strip())
            self.assertTrue(scene["negative_prompt"])
        storyboard = result["storyboard"]
        self.assertEqual(storyboard["scene"]["spoken_line"], "")
        self.assertIn("vocals", storyboard["music_direction"]["avoid"])

    def test_direct_scenes_json_recognized(self):
        scenes, storyboard = docparse.try_parse_artifact_json(
            json.dumps({"scenes": [{"prompt": "hello"}]}))
        self.assertEqual(len(scenes), 1)
        self.assertIsNone(storyboard)


class SimpleFlowTests(unittest.TestCase):
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

    # ---- authoring ------------------------------------------------------- #
    def test_author_from_text_heuristic(self):
        result = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "acme hero"})
        job = result["job"]
        self.assertEqual(job["scene_count"], 2)
        self.assertEqual(job["method"], "heuristic")
        self.assertTrue(job["seed_is_placeholder"])
        # artifacts on disk and engine-shaped
        scenes = json.loads((bridge.REPO_ROOT / job["scenes_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(scenes["scenes"]), 2)
        self.assertTrue(scenes["scenes"][0]["seed_image"].endswith("seed_placeholder.png"))
        self.assertTrue((bridge.REPO_ROOT / scenes["scenes"][0]["seed_image"]).is_file())
        # the draft-shaped packet validates through the adapter's own functions
        self.assertTrue(result["review"]["valid"], msg=result["review"].get("error"))
        self.assertEqual(result["review"]["start_stage"], "video")
        # no key configured -> the warning explains the basic parser was used
        self.assertTrue(any("basic parser" in w for w in result["warnings"]))

    def test_author_from_uploaded_docx(self):
        saved = simple_flow.save_upload("brief.docx", make_docx(SAMPLE_DOC))
        result = simple_flow.author_job({"source_path": saved["path"], "job_name": "docx-job"})
        self.assertEqual(result["job"]["scene_count"], 2)

    def test_author_rejects_empty(self):
        with self.assertRaisesRegex(bridge.BridgeError, "Paste a description"):
            simple_flow.author_job({})

    def test_author_accepts_direct_scenes_json(self):
        doc = json.dumps({"scenes": [{"prompt": "Direct scene one."}, {"prompt": "Direct scene two."}]})
        result = simple_flow.author_job({"text": doc, "job_name": "direct"})
        self.assertEqual(result["job"]["method"], "json")
        self.assertEqual(result["job"]["scene_count"], 2)

    def test_f5_negative_library_applied_on_disk(self):
        import negative_library

        reframe = negative_library.positive_reframe()
        composed = negative_library.compose_negative(negative_library.DEFAULT_GROUPS)

        doc = json.dumps({
            "scenes": [
                {"prompt": "Scene one seed.", "negative_prompt": "should be dropped"},
                {"prompt": "Scene two.", "negative_prompt": ""},
                {"prompt": "Scene three.", "negative_prompt": "operator custom negative"},
            ]
        })
        result = simple_flow.author_job({"text": doc, "job_name": "f5-neglib"})
        job = result["job"]

        scenes_path = bridge.REPO_ROOT / job["scenes_path"]
        with open(scenes_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        scenes = data["scenes"] if isinstance(data, dict) else data

        self.assertGreaterEqual(len(scenes), 3)
        self.assertEqual(len(result["negative_applied"]), len(scenes))
        self.assertEqual(result["negative_applied"][0]["mode"], "positive")
        self.assertEqual(result["negative_applied"][1]["mode"], "library")
        self.assertGreaterEqual(result["negative_applied"][1]["count"], 1)
        self.assertEqual(result["negative_applied"][2]["mode"], "custom")
        self.assertNotIn("negative_prompt", scenes[0])
        self.assertIn(reframe, scenes[0]["prompt"])
        self.assertEqual(scenes[1].get("negative_prompt"), composed)
        self.assertEqual(scenes[2].get("negative_prompt"), "operator custom negative")

    def test_direct_json_bogus_seed_replaced_with_placeholder(self):
        """An inline seed_image pointing nowhere must NOT survive to the packet:
        it gets a placeholder + warning, so the bad seed can't reach a paid run."""
        doc = json.dumps({"scenes": [{"prompt": "Scene one.", "seed_image": "no/such/image.png"}]})
        result = simple_flow.author_job({"text": doc, "job_name": "bogus-seed"})
        scenes = json.loads((bridge.REPO_ROOT / result["job"]["scenes_path"]).read_text(encoding="utf-8"))
        self.assertTrue(scenes["scenes"][0]["seed_image"].endswith("seed_placeholder.png"))
        self.assertTrue(any("placeholder" in w for w in result["warnings"]))

    def test_open_job_reflects_real_validity(self):
        """Reopening a job whose artifacts were deleted must report invalid,
        not a fabricated valid:true."""
        result = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "reopen-test"})
        job_dir = result["job"]["job_dir"]
        self.assertTrue(simple_flow.open_job(job_dir)["review"]["valid"])
        (bridge.REPO_ROOT / result["job"]["storyboard_path"]).unlink()
        reopened = simple_flow.open_job(job_dir)
        self.assertFalse(reopened["review"]["valid"])

    def test_upload_rejects_bad_type(self):
        with self.assertRaisesRegex(bridge.BridgeError, "Unsupported"):
            simple_flow.save_upload("evil.exe", b"MZ")

    # ---- generation gates (simple mode: server-issued confirmation token) -- #
    def test_generate_refuses_without_token(self):
        """A blind/accidental POST with no valid token must be refused, spending
        nothing - the token (not a typed phrase) is the simple-mode gate."""
        result = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "gate-test"})
        job_dir = result["job"]["job_dir"]
        with self.assertRaisesRegex(bridge.BridgeError, "confirmation token"):
            simple_flow.generate(job_dir, "draft", confirm_token="")
        with self.assertRaisesRegex(bridge.BridgeError, "confirmation token"):
            simple_flow.generate(job_dir, "draft", confirm_token="not-a-real-token")

    def test_generate_rejects_bad_quality_and_cap(self):
        result = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "cap-test"})
        job_dir = result["job"]["job_dir"]
        with self.assertRaisesRegex(bridge.BridgeError, "quality"):
            simple_flow.issue_confirmation(job_dir, "ultra")
        with self.assertRaisesRegex(bridge.BridgeError, "quality"):
            simple_flow.generate(job_dir, "ultra", confirm_token="x")
        with self.assertRaisesRegex(bridge.BridgeError, "between 1 and"):
            simple_flow.issue_confirmation(job_dir, "draft", max_scenes=99)

    def test_estimate_returns_breakdown(self):
        result = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "estimate-test"})
        detail = simple_flow.estimate(result["job"]["job_dir"], "draft", max_scenes=2)
        self.assertEqual(detail["quality"], "draft")
        self.assertEqual(detail["max_scenes"], 2)
        est = detail["estimate"]
        for key in ("video", "music", "total", "currency", "approximate", "breakdown"):
            self.assertIn(key, est)
        self.assertTrue(est["approximate"])
        self.assertAlmostEqual(est["total"], est["video"] + est["music"] + est["image"])
        # hq tier costs more per second than draft for the same job
        hq = simple_flow.estimate(result["job"]["job_dir"], "hq", max_scenes=2)["estimate"]
        self.assertGreater(hq["video"], est["video"])

    def test_token_is_single_use_and_job_bound(self):
        """A token unlocks exactly the job+quality+cap it was minted for: it
        cannot generate a different job or a different quality, and it burns on
        first use so it cannot be replayed."""
        job_a = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "job-a"})["job"]["job_dir"]
        job_b = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "job-b"})["job"]["job_dir"]

        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO("Run ID: full_fake\n")
                self.stderr = io.StringIO("")
                self.returncode = 0
            def wait(self):
                return 0

        real_popen = bridge.subprocess.Popen

        def selective_popen(argv, *args, **kwargs):
            if "--run" in argv:
                return FakeProcess()
            return real_popen(argv, *args, **kwargs)

        # Token for job A / draft / cap 1.
        issued = simple_flow.issue_confirmation(job_a, "draft", max_scenes=1)
        token = issued["confirm_token"]

        # Same token cannot generate job B (job-bound).
        with self.assertRaisesRegex(bridge.BridgeError, "does not match"):
            simple_flow.generate(job_b, "draft", confirm_token=token, max_scenes=1)
        # Nor a different quality (hq) on job A.
        with self.assertRaisesRegex(bridge.BridgeError, "does not match"):
            simple_flow.generate(job_a, "hq", confirm_token=token, max_scenes=1)

        # Correct binding consumes the token once.
        with mock.patch.object(bridge.subprocess, "Popen", side_effect=selective_popen):
            outcome = simple_flow.generate(job_a, "draft", confirm_token=token, max_scenes=1)
        for _ in range(50):
            if bridge.run_status(outcome["ui_run_id"])["status"] != "running":
                break
            time.sleep(0.1)
        # Reusing the burned token is refused (single-use) - nothing re-spent.
        with self.assertRaisesRegex(bridge.BridgeError, "already used|unknown"):
            simple_flow.generate(job_a, "draft", confirm_token=token, max_scenes=1)

    def test_generate_draft_then_hq_models_and_gates(self):
        result = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "model-test"})
        job_dir = result["job"]["job_dir"]

        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO("Run ID: full_fake\n")
                self.stderr = io.StringIO("")
                self.returncode = 0
            def wait(self):
                return 0

        settings = bridge.load_settings()
        real_popen = bridge.subprocess.Popen

        def selective_popen(argv, *args, **kwargs):
            # Only the live spawn (--run) is faked; the dry-run subprocess
            # inside generate() runs the real adapter (free by design).
            if "--run" in argv:
                return FakeProcess()
            return real_popen(argv, *args, **kwargs)

        for quality, expected in (("draft", settings["draft"]), ("hq", settings["hq"])):
            token = simple_flow.issue_confirmation(job_dir, quality, max_scenes=1)["confirm_token"]
            with mock.patch.object(bridge.subprocess, "Popen", side_effect=selective_popen) as popen:
                outcome = simple_flow.generate(job_dir, quality, confirm_token=token, max_scenes=1)
                argv = next(c.args[0] for c in popen.call_args_list if "--run" in c.args[0])
            self.assertIn("--run", argv)
            packet = json.loads((bridge.REPO_ROOT / outcome["packet_path"]).read_text(encoding="utf-8"))
            self.assertEqual(packet["model"], expected["model"])
            self.assertEqual(packet["resolution"], expected["resolution"])
            self.assertEqual(packet["max_scenes"], 1)
            self.assertEqual(packet["content_path"], "silent_brand")
            self.assertTrue(packet["spend_controls"]["allow_live_run"])
            # wait for the fake run to settle so the next start is allowed
            for _ in range(50):
                if bridge.run_status(outcome["ui_run_id"])["status"] != "running":
                    break
                time.sleep(0.1)
            job = simple_flow.load_job(job_dir)
            self.assertEqual(job["runs"][quality]["ui_run_id"], outcome["ui_run_id"])

    # ---- settings + keys ----------------------------------------------------- #
    def test_settings_roundtrip_and_validation(self):
        saved = bridge.save_settings({"draft": {"model": "test-model", "resolution": "720p"}})
        self.assertEqual(saved["draft"]["model"], "test-model")
        self.assertEqual(bridge.load_settings()["draft"]["model"], "test-model")
        with self.assertRaisesRegex(bridge.BridgeError, "resolution"):
            bridge.save_settings({"hq": {"resolution": "8k"}})

    def test_settings_pricing_defaults_to_cost_estimator(self):
        """A fresh settings load carries the cost_estimator placeholder pricing."""
        settings = bridge.load_settings()
        self.assertIn("pricing", settings)
        self.assertEqual(
            settings["pricing"]["veo_per_second"],
            cost_estimator.DEFAULT_PRICING["veo_per_second"],
        )

    def test_settings_pricing_roundtrips(self):
        saved = bridge.save_settings({
            "pricing": {
                "veo_per_second": {"veo-3.1-fast-generate-preview": {"720p": 0.20}},
                "music_per_song": {"lyria-3-pro-preview": 0.40},
                "image_per_image": {"imagen-4.0-fast-generate-001": {"flat": 0.07}},
                "currency": "EUR",
            }
        })
        self.assertEqual(saved["pricing"]["veo_per_second"]["veo-3.1-fast-generate-preview"]["720p"], 0.20)
        self.assertEqual(saved["pricing"]["music_per_song"]["lyria-3-pro-preview"], 0.40)
        self.assertEqual(saved["pricing"]["currency"], "EUR")
        # other (unspecified) default rates are preserved by the merge
        self.assertEqual(saved["pricing"]["veo_per_second"]["veo-3.1-generate-preview"]["1080p"], 0.40)
        # persists across loads
        reloaded = bridge.load_settings()
        self.assertEqual(reloaded["pricing"]["veo_per_second"]["veo-3.1-fast-generate-preview"]["720p"], 0.20)
        self.assertEqual(reloaded["pricing"]["image_per_image"]["imagen-4.0-fast-generate-001"]["flat"], 0.07)

    def test_settings_pricing_rejects_bad_rates(self):
        for bad in ("not-a-number", -1, float("inf")):
            with self.assertRaisesRegex(bridge.BridgeError, "pricing"):
                bridge.save_settings({"pricing": {"music_per_song": {"lyria-3-pro-preview": bad}}})
        with self.assertRaisesRegex(bridge.BridgeError, "pricing"):
            bridge.save_settings({
                "pricing": {"veo_per_second": {"veo-3.1-fast-generate-preview": {"720p": -5}}}
            })

    def test_estimate_uses_operator_pricing(self):
        """The estimate reflects operator-set rates, not the defaults."""
        # draft maps to veo-3.1-fast-generate-preview @ 720p (engine_bridge
        # default settings); override exactly that rate.
        bridge.save_settings({
            "pricing": {"veo_per_second": {"veo-3.1-fast-generate-preview": {"720p": 1.00}},
                        "music_per_song": {"lyria-3-pro-preview": 0.50}}
        })
        try:
            result = simple_flow.author_job({"text": SAMPLE_DOC, "job_name": "priced"})
            detail = simple_flow.estimate(result["job"]["job_dir"], "draft", max_scenes=1)
            # 1 scene -> ~6s seed only; 6 * 1.00 = 6.00 video, + 0.50 music.
            self.assertAlmostEqual(detail["estimate"]["video"], 6.00)
            self.assertAlmostEqual(detail["estimate"]["music"], 0.50)
            self.assertFalse(detail["estimate"]["breakdown"]["using_default_pricing"])
        finally:
            bridge.save_settings({"pricing": cost_estimator.DEFAULT_PRICING})

    def test_env_key_set_clear_and_never_leaked(self):
        outcome = bridge.set_env_key("GEMINI_API_KEY", "test-secret-value-123")
        self.assertTrue(outcome["configured"])
        self.assertNotIn("test-secret-value-123", json.dumps(outcome))
        self.assertIn("GEMINI_API_KEY=test-secret-value-123", bridge.ENV_PATH.read_text(encoding="utf-8"))
        # health/capabilities never contain the value
        self.assertNotIn("test-secret-value-123", json.dumps(bridge.health()))
        # audit log records the event but never the value
        audit_text = bridge.AUDIT_LOG_PATH.read_text(encoding="utf-8")
        self.assertIn("env_key_set", audit_text)
        self.assertNotIn("test-secret-value-123", audit_text)
        outcome = bridge.set_env_key("GEMINI_API_KEY", clear=True)
        self.assertFalse(outcome["configured"])

    def test_env_key_rejects_unknown_name(self):
        with self.assertRaisesRegex(bridge.BridgeError, "Unknown key"):
            bridge.set_env_key("PATH", "evil")

    def test_capabilities_shape(self):
        caps = bridge.capabilities()
        for name in ("dry_run", "veo_generation", "music", "voice_sts", "assemble", "ai_extraction"):
            self.assertIn(name, caps["capabilities"])


class SimpleHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.chdir(bridge.REPO_ROOT)
        cls.data_dir = bridge.REPO_ROOT / "ui" / "data" / f"test_data_{uuid.uuid4().hex[:8]}"
        cls._original_dirs = redirect_bridge_data(cls.data_dir)
        cls._original_env = bridge.ENV_PATH
        bridge.ENV_PATH = cls.data_dir / "env_test"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.ApiHandler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
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

    def test_upload_author_generate_refusal_chain(self):
        status, upload = self.request("POST", "/api/simple/upload?name=brief.md",
                                      raw=SAMPLE_DOC.encode("utf-8"))
        self.assertEqual(status, 200)
        status, authored = self.request("POST", "/api/simple/author",
                                        {"source_path": upload["path"], "job_name": "http-simple"})
        self.assertEqual(status, 200, msg=str(authored))
        self.assertEqual(authored["job"]["scene_count"], 2)
        self.assertTrue(authored["review"]["valid"])
        job_dir = authored["job"]["job_dir"]
        # generation with no confirm_token must refuse, spending nothing
        status, refused = self.request("POST", "/api/simple/generate",
                                       {"job_dir": job_dir, "quality": "draft"})
        self.assertEqual(status, 400)
        self.assertIn("confirmation token", refused["error"])
        # a bogus token is equally refused
        status, refused = self.request("POST", "/api/simple/generate",
                                       {"job_dir": job_dir, "quality": "draft", "confirm_token": "bogus"})
        self.assertEqual(status, 400)
        self.assertIn("confirmation token", refused["error"])

    def test_estimate_endpoint_returns_breakdown(self):
        status, upload = self.request("POST", "/api/simple/upload?name=brief.md",
                                      raw=SAMPLE_DOC.encode("utf-8"))
        status, authored = self.request("POST", "/api/simple/author",
                                        {"source_path": upload["path"], "job_name": "http-estimate"})
        job_dir = authored["job"]["job_dir"]
        # GET form
        status, get_est = self.request(
            "GET", f"/api/simple/estimate?dir={job_dir}&quality=draft&max_scenes=1")
        self.assertEqual(status, 200, msg=str(get_est))
        self.assertEqual(get_est["quality"], "draft")
        self.assertIn("total", get_est["estimate"])
        self.assertTrue(get_est["estimate"]["approximate"])
        # POST form
        status, post_est = self.request("POST", "/api/simple/estimate",
                                        {"job_dir": job_dir, "quality": "hq", "max_scenes": 2})
        self.assertEqual(status, 200, msg=str(post_est))
        self.assertEqual(post_est["max_scenes"], 2)

    def test_confirm_token_then_generate_endpoint(self):
        """End-to-end over HTTP: author -> mint token -> generate with token.
        The live spawn is mocked so nothing is ever paid."""
        status, upload = self.request("POST", "/api/simple/upload?name=brief.md",
                                      raw=SAMPLE_DOC.encode("utf-8"))
        status, authored = self.request("POST", "/api/simple/author",
                                        {"source_path": upload["path"], "job_name": "http-token"})
        job_dir = authored["job"]["job_dir"]

        status, issued = self.request("POST", "/api/simple/confirm-token",
                                      {"job_dir": job_dir, "quality": "draft", "max_scenes": 1})
        self.assertEqual(status, 200, msg=str(issued))
        token = issued["confirm_token"]
        self.assertTrue(token)
        self.assertIn("estimate", issued)

        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO("Run ID: http_fake\n")
                self.stderr = io.StringIO("")
                self.returncode = 0
            def wait(self):
                return 0

        real_popen = bridge.subprocess.Popen

        def selective_popen(argv, *args, **kwargs):
            if "--run" in argv:
                return FakeProcess()
            return real_popen(argv, *args, **kwargs)

        with mock.patch.object(bridge.subprocess, "Popen", side_effect=selective_popen):
            status, gen = self.request("POST", "/api/simple/generate",
                                       {"job_dir": job_dir, "quality": "draft",
                                        "confirm_token": token, "max_scenes": 1})
        self.assertEqual(status, 200, msg=str(gen))
        self.assertIn("ui_run_id", gen)
        for _ in range(50):
            if bridge.run_status(gen["ui_run_id"])["status"] != "running":
                break
            time.sleep(0.1)
        # the token is single-use: replaying it over HTTP is refused
        status, replay = self.request("POST", "/api/simple/generate",
                                      {"job_dir": job_dir, "quality": "draft",
                                       "confirm_token": token, "max_scenes": 1})
        self.assertEqual(status, 400)

    def test_settings_endpoint_has_no_secrets(self):
        bridge.set_env_key("GEMINI_API_KEY", "super-secret-abc")
        try:
            status, data = self.request("GET", "/api/settings")
            self.assertEqual(status, 200)
            self.assertTrue(data["keys"]["GEMINI_API_KEY"])
            self.assertNotIn("super-secret-abc", json.dumps(data))
        finally:
            bridge.set_env_key("GEMINI_API_KEY", clear=True)

    def test_key_endpoint_roundtrip(self):
        status, data = self.request("POST", "/api/settings/key",
                                    {"name": "ELEVENLABS_API_KEY", "value": "elv-test"})
        self.assertEqual(status, 200)
        self.assertTrue(data["configured"])
        self.assertNotIn("elv-test", json.dumps(data))
        status, data = self.request("POST", "/api/settings/key",
                                    {"name": "ELEVENLABS_API_KEY", "clear": True})
        self.assertFalse(data["configured"])

    def test_models_endpoint(self):
        status, data = self.request("POST", "/api/settings/models",
                                    {"hq": {"model": "veo-x", "resolution": "1080p"}})
        self.assertEqual(status, 200)
        self.assertEqual(data["settings"]["hq"]["model"], "veo-x")

    def test_settings_endpoint_includes_pricing(self):
        status, data = self.request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertIn("pricing", data["settings"])
        self.assertIn("veo_per_second", data["settings"]["pricing"])

    def test_settings_pricing_roundtrips_over_http(self):
        status, data = self.request("POST", "/api/settings/models", {
            "pricing": {"veo_per_second": {"veo-3.1-generate-preview": {"1080p": 0.33, "4k": 1.11}},
                        "music_per_song": {"lyria-3-pro-preview": 0.22}, "currency": "GBP"}
        })
        self.assertEqual(status, 200, msg=str(data))
        pricing = data["settings"]["pricing"]
        self.assertEqual(pricing["veo_per_second"]["veo-3.1-generate-preview"]["1080p"], 0.33)
        self.assertEqual(pricing["veo_per_second"]["veo-3.1-generate-preview"]["4k"], 1.11)
        self.assertEqual(pricing["currency"], "GBP")
        # reflected on the GET settings endpoint too
        status, fetched = self.request("GET", "/api/settings")
        self.assertEqual(fetched["settings"]["pricing"]["music_per_song"]["lyria-3-pro-preview"], 0.22)


if __name__ == "__main__":
    unittest.main()
