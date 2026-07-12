"""Tests for ui/scene_images.py: scene concept images + first-frame extraction.

Run from the repo root with:
    python -m unittest discover -s ui/tests -p test_scene_images.py -v

Free by construction:
  * the paid image API (generate_scene_image) is MOCKED - no test ever hits the
    real google-genai endpoint or spends money;
  * extract_first_frame is exercised only when ffmpeg is on PATH (it really
    builds a tiny test clip with ffmpeg), and is skipped gracefully otherwise;
  * the caching helpers are pure path logic / local file checks.
"""

import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

import scene_images  # noqa: E402

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


# --------------------------------------------------------------------------- #
# (1) Caching path logic                                                       #
# --------------------------------------------------------------------------- #
class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_same_scene_makes_one_paid_call(self):
        """Many simultaneous requests for the SAME scene must collapse to a
        single paid render (per-scene lock), not one paid call per thread."""
        calls = []
        calls_lock = threading.Lock()

        def fake_generate(prompt, out_path, api_key, model=scene_images.DEFAULT_IMAGE_MODEL):
            with calls_lock:
                calls.append(out_path)
            time.sleep(0.05)  # widen the race window
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\n")
            return Path(out_path)

        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "job"
            barrier = threading.Barrier(8)
            results = []
            results_lock = threading.Lock()

            def attempt():
                barrier.wait()
                r = scene_images.generate_scene_image_cached(job_dir, 1, "a prompt", "key")
                with results_lock:
                    results.append(r)

            # Patch ONCE in the main thread (mock.patch is not thread-safe); the
            # threads just call the cached helper while the patch is active.
            with mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate):
                threads = [threading.Thread(target=attempt) for _ in range(8)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=10)

            self.assertEqual(len(calls), 1, msg=f"expected exactly one paid render, got {len(calls)}")
            self.assertEqual(sum(1 for r in results if not r["cached"]), 1)
            self.assertEqual(sum(1 for r in results if r["cached"]), 7)


class CachedPathTests(unittest.TestCase):
    def test_path_is_deterministic_per_scene(self):
        job_dir = Path("ui/data/simple/somejob")
        first = scene_images.cached_scene_image_path(job_dir, 1)
        again = scene_images.cached_scene_image_path(job_dir, 1)
        self.assertEqual(first, again)
        # under the job dir, in a scene_images subfolder, zero-padded, 1-based
        self.assertEqual(first.parent, job_dir / "scene_images")
        self.assertEqual(first.name, "scene_01.png")

    def test_distinct_scenes_get_distinct_paths(self):
        job_dir = Path("ui/data/simple/job")
        self.assertNotEqual(
            scene_images.cached_scene_image_path(job_dir, 1),
            scene_images.cached_scene_image_path(job_dir, 2),
        )
        self.assertEqual(
            scene_images.cached_scene_image_path(job_dir, 12).name, "scene_12.png"
        )

    def test_rejects_non_positive_or_non_int_index(self):
        job_dir = Path("ui/data/simple/job")
        for bad in (0, -1, "1", 1.0, True):
            with self.assertRaises(scene_images.SceneImageError):
                scene_images.cached_scene_image_path(job_dir, bad)

    def test_cached_generate_skips_paid_call_when_image_exists(self):
        """Second request for an already-rendered scene is FREE: the paid API is
        never invoked, the existing bytes are reused."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            target = scene_images.cached_scene_image_path(job_dir, 1)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"\x89PNG\r\n\x1a\n already-here")

            with mock.patch.object(scene_images, "generate_scene_image") as gen:
                result = scene_images.generate_scene_image_cached(
                    job_dir, 1, "a prompt", "fake-key"
                )
            gen.assert_not_called()
            self.assertTrue(result["cached"])
            self.assertEqual(result["path"], target)

    def test_cached_generate_renders_once_then_reuses(self):
        """First request renders (one paid call, mocked); the second reuses the
        file written by the first and makes no further calls."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            target = scene_images.cached_scene_image_path(job_dir, 2)

            def fake_generate(prompt, out_path, api_key, model=scene_images.DEFAULT_IMAGE_MODEL):
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\n rendered")
                return Path(out_path)

            with mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate) as gen:
                first = scene_images.generate_scene_image_cached(job_dir, 2, "p", "fake-key")
                self.assertFalse(first["cached"])
                self.assertEqual(gen.call_count, 1)
                self.assertTrue(target.is_file())

                second = scene_images.generate_scene_image_cached(job_dir, 2, "p", "fake-key")
                self.assertTrue(second["cached"])
                self.assertEqual(gen.call_count, 1)  # still one - no re-spend

    def test_cached_generate_ignores_empty_stale_file(self):
        """A zero-byte leftover must NOT count as a cache hit (it would yield a
        broken image); the renderer is called to produce real bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            target = scene_images.cached_scene_image_path(job_dir, 1)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"")  # empty stale file

            def fake_generate(prompt, out_path, api_key, model=scene_images.DEFAULT_IMAGE_MODEL):
                Path(out_path).write_bytes(b"real-bytes")
                return Path(out_path)

            with mock.patch.object(scene_images, "generate_scene_image", side_effect=fake_generate) as gen:
                result = scene_images.generate_scene_image_cached(job_dir, 1, "p", "fake-key")
            gen.assert_called_once()
            self.assertFalse(result["cached"])


# --------------------------------------------------------------------------- #
# (2) First-frame extraction (only when ffmpeg is on PATH; else skipped)        #
# --------------------------------------------------------------------------- #
@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not on PATH")
class FirstFrameTests(unittest.TestCase):
    def _make_test_video(self, path: Path) -> None:
        """Synthesize a 1-second test clip locally with ffmpeg's testsrc - no
        network, no API, no spend."""
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "testsrc=duration=1:size=160x120:rate=10",
                "-pix_fmt", "yuv420p",
                str(path),
            ],
            check=True,
            capture_output=True,
        )

    def test_extract_first_frame_writes_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            self._make_test_video(video)
            out = Path(tmp) / "frame.png"
            result = scene_images.extract_first_frame(video, out)
            self.assertEqual(result, out)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)

    def test_extract_first_frame_missing_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(scene_images.SceneImageError, "not found"):
                scene_images.extract_first_frame(Path(tmp) / "nope.mp4", Path(tmp) / "f.png")


class FirstFrameNoFfmpegTests(unittest.TestCase):
    def test_missing_ffmpeg_fails_loud(self):
        """When ffmpeg is absent, extraction raises a clear SceneImageError
        rather than silently doing nothing - independent of the real PATH."""
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"\x00\x00\x00\x18ftypmp42")  # stand-in
            with mock.patch.object(scene_images.shutil, "which", return_value=None):
                with self.assertRaisesRegex(scene_images.SceneImageError, "ffmpeg"):
                    scene_images.extract_first_frame(video, Path(tmp) / "f.png")


# --------------------------------------------------------------------------- #
# (3) Image API generation - MOCKED so no test ever hits the paid API          #
# --------------------------------------------------------------------------- #
class _FakeBlob:
    def __init__(self, data, mime_type="image/png"):
        self.data = data
        self.mime_type = mime_type


class _FakePart:
    def __init__(self, inline_data=None, text=None):
        self.inline_data = inline_data
        self.text = text


class _FakeContent:
    def __init__(self, parts):
        self.parts = parts


class _FakeCandidate:
    def __init__(self, parts):
        self.content = _FakeContent(parts)


class _FakeResponse:
    def __init__(self, parts):
        self.candidates = [_FakeCandidate(parts)]


class _FakeModels:
    def __init__(self, response):
        self._response = response
        self.calls = []        # generate_content kwargs (gemini image models)
        self.image_calls = []  # generate_images kwargs (Imagen predict path)

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._response

    def generate_images(self, **kwargs):
        self.image_calls.append(kwargs)
        return self._response


class _FakeClient:
    """Stand-in for genai.Client. Records that it was constructed with the key
    so the test can assert the call shape WITHOUT the key ever being logged by
    production code."""

    last_api_key = None

    def __init__(self, api_key=None):
        type(self).last_api_key = api_key
        self.models = None  # set by the test harness below


class ImageGenerationMockedTests(unittest.TestCase):
    def _patch_genai(self, response):
        """Install a fake google.genai module so generate_scene_image never
        reaches the network. Returns the fake models object for assertions."""
        fake_models = _FakeModels(response)

        def client_factory(api_key=None):
            client = _FakeClient(api_key=api_key)
            client.models = fake_models
            return client

        genai_mod = mock.MagicMock()
        genai_mod.Client.side_effect = client_factory
        types_mod = mock.MagicMock()
        google_mod = mock.MagicMock()
        google_mod.genai = genai_mod
        modules = {
            "google": google_mod,
            "google.genai": genai_mod,
            "google.genai.types": types_mod,
        }
        return mock.patch.dict(sys.modules, modules), fake_models

    def test_generates_and_saves_image_bytes(self):
        png = b"\x89PNG\r\n\x1a\n fake image bytes"
        response = _FakeResponse([_FakePart(inline_data=_FakeBlob(png))])
        patcher, fake_models = self._patch_genai(response)
        with tempfile.TemporaryDirectory() as tmp, patcher:
            out = Path(tmp) / "concept.png"
            result = scene_images.generate_scene_image("a calm desk", out, "secret-key-xyz")
            self.assertEqual(result, out)
            self.assertEqual(out.read_bytes(), png)
            # one minimal call, with the model + prompt; key reached the client
            self.assertEqual(len(fake_models.calls), 1)
            self.assertEqual(fake_models.calls[0]["model"], scene_images.DEFAULT_IMAGE_MODEL)
            self.assertEqual(_FakeClient.last_api_key, "secret-key-xyz")

    def test_imagen_model_uses_predict_generate_images_path(self):
        """Imagen models only support the predict API; generate_scene_image must
        route them to generate_images, not generate_content."""
        png = b"\x89PNG\r\n\x1a\n imagen bytes"

        class _Img:
            def __init__(self, b):
                self.image_bytes = b

        class _GenImg:
            def __init__(self, b):
                self.image = _Img(b)

        class _ImagenResp:
            def __init__(self, b):
                self.generated_images = [_GenImg(b)]

        patcher, fake_models = self._patch_genai(_ImagenResp(png))
        with tempfile.TemporaryDirectory() as tmp, patcher:
            out = Path(tmp) / "imagen.png"
            result = scene_images.generate_scene_image(
                "a calm desk", out, "secret-key-xyz", model="imagen-4.0-fast-generate-001")
            self.assertEqual(result, out)
            self.assertEqual(out.read_bytes(), png)
            # used the predict path (generate_images), NOT generate_content
            self.assertEqual(len(fake_models.image_calls), 1)
            self.assertEqual(len(fake_models.calls), 0)
            self.assertEqual(fake_models.image_calls[0]["model"], "imagen-4.0-fast-generate-001")

    def test_custom_model_is_passed_through(self):
        response = _FakeResponse([_FakePart(inline_data=_FakeBlob(b"img"))])
        patcher, fake_models = self._patch_genai(response)
        with tempfile.TemporaryDirectory() as tmp, patcher:
            scene_images.generate_scene_image("p", Path(tmp) / "x.png", "k", model="custom-image-model")
            self.assertEqual(fake_models.calls[0]["model"], "custom-image-model")

    def test_dict_style_inline_data_also_decoded(self):
        """Some SDK shapes expose parts as dicts; the reader handles both."""
        png = b"dict-image-bytes"
        response = _FakeResponse([{"inline_data": {"data": png}}])
        patcher, _ = self._patch_genai(response)
        with tempfile.TemporaryDirectory() as tmp, patcher:
            out = Path(tmp) / "c.png"
            scene_images.generate_scene_image("p", out, "k")
            self.assertEqual(out.read_bytes(), png)

    def test_no_image_in_response_fails_loud(self):
        """A text-only / filtered response must raise, not write an empty file."""
        response = _FakeResponse([_FakePart(text="I cannot do that.")])
        patcher, _ = self._patch_genai(response)
        with tempfile.TemporaryDirectory() as tmp, patcher:
            out = Path(tmp) / "c.png"
            with self.assertRaisesRegex(scene_images.SceneImageError, "no image"):
                scene_images.generate_scene_image("p", out, "k")
            self.assertFalse(out.exists())

    def test_empty_prompt_rejected_before_any_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(scene_images.SceneImageError, "empty"):
                scene_images.generate_scene_image("   ", Path(tmp) / "c.png", "k")

    def test_missing_key_rejected_before_any_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(scene_images.SceneImageError, "key"):
                scene_images.generate_scene_image("a prompt", Path(tmp) / "c.png", "")

    def test_request_failure_surfaces_without_key(self):
        """An API exception is wrapped in SceneImageError and the message never
        contains the key value."""
        response = _FakeResponse([_FakePart(inline_data=_FakeBlob(b"img"))])
        fake_models = _FakeModels(response)

        def boom(**kwargs):
            raise RuntimeError("upstream 500")

        fake_models.generate_content = boom

        def client_factory(api_key=None):
            client = _FakeClient(api_key=api_key)
            client.models = fake_models
            return client

        genai_mod = mock.MagicMock()
        genai_mod.Client.side_effect = client_factory
        modules = {
            "google": mock.MagicMock(genai=genai_mod),
            "google.genai": genai_mod,
            "google.genai.types": mock.MagicMock(),
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, modules):
            with self.assertRaises(scene_images.SceneImageError) as ctx:
                scene_images.generate_scene_image("p", Path(tmp) / "c.png", "super-secret-key")
            self.assertIn("request failed", str(ctx.exception))
            self.assertNotIn("super-secret-key", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
