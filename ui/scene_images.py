"""Scene concept images + post-generation real frames for the operator UI.

Self-contained module (the orchestrator wires it into the UI later). Three jobs:

  * generate_scene_image(prompt, out_path, api_key, model) - render ONE concept
    image for a scene prompt with the google-genai image model and save it.
    This is a PAID call, kept deliberately minimal: one image, one request, no
    retries, no batching. The key is read from the environment/.env by the
    caller (see scene_image_api_key) and is NEVER logged.
  * extract_first_frame(video_path, out_path) - pull the first real frame out of
    a generated video with ffmpeg. Free (local), used post-generation to show
    operators what the pipeline actually produced.
  * cached_scene_image_path(job_dir, scene_index) + generate_scene_image_cached()
    - a concept image is generated ONCE per scene and reused on every later
    request, so the preview grid never re-spends for an image it already has.

The google-genai client style mirrors run_veo_extension_chain.py and
generate_music.py: build a genai.Client(api_key=...), call the model, and read
the returned inline_data bytes. Stdlib + google-genai only (both already used by
the engine); no new pip dependencies.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

# Default image model for scene concept frames. Overridable per call.
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image"
# Placeholder markers also recognized by engine_bridge._key_is_set: a key whose
# value is one of these is treated as "not really configured".
_PLACEHOLDER_MARKERS = ("your-", "changeme", "xxxx")
# ffmpeg time offset for the "first frame". A hair past 0 dodges black leader
# frames some encoders emit at exactly t=0 while staying on the opening shot.
FIRST_FRAME_TIMESTAMP = "00:00:00.000"
FFMPEG_TIMEOUT_SECONDS = 120


class SceneImageError(Exception):
    """Operator-facing scene-image failure. The message is safe to show in the
    UI and never contains key material."""


# --------------------------------------------------------------------------- #
# API key (read from environment/.env via the existing engine pattern)         #
# --------------------------------------------------------------------------- #
def scene_image_api_key() -> str:
    """Return the Gemini key the same way the engine does: prefer the process
    environment, fall back to the repo .env (parsed by engine_bridge). Raises a
    SceneImageError - never echoing the value - when no usable key is set.

    Imported lazily so this module stays usable (e.g. extract_first_frame and
    the caching helpers) even if engine_bridge is unavailable."""
    value = os.environ.get("GEMINI_API_KEY") or ""
    if not _usable_key(value):
        try:
            import engine_bridge as bridge  # local import: avoids a hard dep

            value = bridge._env_file_values().get("GEMINI_API_KEY") or ""
        except Exception:
            value = value or ""
    if not _usable_key(value):
        raise SceneImageError(
            "No usable GEMINI_API_KEY is configured. Add one in Admin > Settings "
            "before generating scene concept images."
        )
    return value


def _usable_key(value: str) -> bool:
    return bool(value) and not any(marker in value.lower() for marker in _PLACEHOLDER_MARKERS)


# --------------------------------------------------------------------------- #
# Concept image generation (PAID - one image per call, kept minimal)           #
# --------------------------------------------------------------------------- #
def generate_scene_image(
    prompt: str,
    out_path,
    api_key: str,
    model: str = DEFAULT_IMAGE_MODEL,
    aspect_ratio: str = "16:9",
) -> Path:
    """Render ONE concept image for a scene prompt and save it to out_path.

    PAID: this makes a single google-genai image request. Kept minimal on
    purpose - one image, no retries, no batching - so a caller can never fan a
    grid of scenes out into a surprise spend. The key is passed in (read via
    scene_image_api_key) and is NEVER logged or echoed into the error message.
    Returns the Path written."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise SceneImageError("Scene prompt is empty; nothing to render.")
    if not api_key or not str(api_key).strip():
        # Guard, but never surface the (absent) value.
        raise SceneImageError("A Gemini API key is required to render a scene image.")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # google-genai client style, mirroring run_veo_extension_chain.py.
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        # Name the EXACT interpreter running this server so the operator installs
        # into the right Python (a common multi-Python pitfall on Windows: the
        # shell's `python` differs from the one the server runs under).
        raise SceneImageError(
            "The google-genai package is not installed for the Python running this server "
            f"({sys.executable}). Install it there: \"{sys.executable}\" -m pip install google-genai. ({exc})"
        )

    client = genai.Client(api_key=api_key)
    # Imagen models (imagen-*) only support the predict API (generate_images);
    # the gemini-*-image models use generate_content with IMAGE modality. Route
    # by model family so the cheap Imagen "Basic" tier works too.
    try:
        if _is_imagen(model):
            response = client.models.generate_images(
                model=model,
                prompt=prompt.strip(),
                config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio=aspect_ratio),
            )
            image_bytes = _first_imagen_image(response)
        else:
            response = client.models.generate_content(
                model=model,
                contents=prompt.strip(),
                config=_content_image_config(types, aspect_ratio),
            )
            image_bytes = _first_inline_image(response)
    except Exception as exc:  # network/quota/model-access: fail loud, no key in message
        raise SceneImageError(f"Scene image request failed: {exc}")

    if image_bytes is None:
        raise SceneImageError(
            "The image model returned no image (it may have been filtered or refused the prompt)."
        )
    out_path.write_bytes(image_bytes)
    return out_path


def _is_imagen(model: str) -> bool:
    return str(model).lower().lstrip("/").startswith(("imagen", "models/imagen"))


def _content_image_config(types, aspect_ratio: str):
    """GenerateContentConfig for a gemini image model, requesting a widescreen
    frame so storyboard images fit the 16:9 carousel card. Falls back gracefully
    on older SDKs that lack ImageConfig (the image just renders at the model's
    default aspect, which object-fit:cover still handles)."""
    try:
        return types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        )
    except (AttributeError, TypeError):
        return types.GenerateContentConfig(response_modalities=["IMAGE"])


def _first_imagen_image(response) -> bytes | None:
    """Pull the first image payload out of an Imagen generate_images (predict)
    response. The SDK returns generated_images[i].image.image_bytes; tolerate
    attribute- and dict-style shapes."""
    images = getattr(response, "generated_images", None)
    if images is None and isinstance(response, dict):
        images = response.get("generated_images") or response.get("generatedImages")
    if not images:
        return None
    first = images[0]
    image = getattr(first, "image", None)
    if image is None and isinstance(first, dict):
        image = first.get("image")
    if image is None:
        return None
    data = getattr(image, "image_bytes", None)
    if data is None and isinstance(image, dict):
        data = image.get("image_bytes") or image.get("imageBytes")
    return data


def _first_inline_image(response) -> bytes | None:
    """Pull the first inline image payload out of a genai generate_content
    response. Tolerates both attribute-style (SDK objects) and dict-style parts,
    matching the inline_data handling in generate_music.py."""
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return None
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    if not parts:
        return None
    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline is None and isinstance(part, dict):
            inline = part.get("inline_data") or part.get("inlineData")
        if inline is None:
            continue
        data = getattr(inline, "data", None)
        if data is None and isinstance(inline, dict):
            data = inline.get("data")
        if data:
            return data
    return None


# --------------------------------------------------------------------------- #
# First-frame extraction (FREE - ffmpeg, post-generation real frames)          #
# --------------------------------------------------------------------------- #
def extract_first_frame(video_path, out_path) -> Path:
    """Save the first frame of a generated video as an image using ffmpeg.

    Free (local). Used post-generation to show operators a real frame the
    pipeline produced. Raises SceneImageError when ffmpeg is missing, the input
    is absent, or ffmpeg fails - so the caller fails loud rather than silently
    skipping. Returns the Path written."""
    if shutil.which("ffmpeg") is None:
        raise SceneImageError("ffmpeg is required to extract a video frame but was not found on PATH.")

    video_path = Path(video_path)
    if not video_path.is_file():
        raise SceneImageError(f"Video file not found: {video_path}")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        FIRST_FRAME_TIMESTAMP,
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(out_path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise SceneImageError("ffmpeg is required to extract a video frame but was not found on PATH.")
    except subprocess.TimeoutExpired:
        raise SceneImageError("ffmpeg timed out extracting the first frame.")

    if completed.returncode != 0 or not out_path.is_file():
        detail = (completed.stderr or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit code {completed.returncode}"
        raise SceneImageError(f"ffmpeg could not extract a frame from {video_path.name}: {tail}")
    return out_path


# --------------------------------------------------------------------------- #
# Caching: one concept image per scene, reused thereafter                      #
# --------------------------------------------------------------------------- #
def cached_scene_image_path(job_dir, scene_index: int) -> Path:
    """The deterministic on-disk path for scene `scene_index`'s concept image,
    inside `job_dir`. Pure path logic (no I/O, no spend): the same job_dir +
    scene_index always maps to the same file, so a concept image is generated
    once and reused on every later request. scene_index is 1-based (scene 1 is
    the image seed), matching the engine's scene numbering."""
    if not isinstance(scene_index, int) or isinstance(scene_index, bool) or scene_index < 1:
        raise SceneImageError("scene_index must be a positive integer (scenes are 1-based).")
    return Path(job_dir) / "scene_images" / f"scene_{scene_index:02d}.png"


# Per-target locks so concurrent requests for the SAME scene collapse to a
# single paid render. Without this, two requests can both miss the cache and
# both call the paid image API. Keyed by the resolved target path; the registry
# itself is guarded by _scene_locks_guard.
_scene_locks: dict = {}
_scene_locks_guard = threading.Lock()


def _lock_for(target: Path) -> threading.Lock:
    key = str(target.resolve())
    with _scene_locks_guard:
        lock = _scene_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _scene_locks[key] = lock
        return lock


def generate_scene_image_cached(
    job_dir,
    scene_index: int,
    prompt: str,
    api_key: str,
    model: str = DEFAULT_IMAGE_MODEL,
) -> dict:
    """Return scene `scene_index`'s concept image, generating it (PAID) only if
    it does not already exist on disk. The cache key is the deterministic path
    from cached_scene_image_path, so a second call for the same scene is FREE -
    it never re-hits the paid image API.

    Concurrency-safe: the check-then-generate runs under a per-target lock, so
    simultaneous requests for the same scene make at most ONE paid call (the
    others re-read the cache the winner just wrote).

    Returns {"path": Path, "cached": bool}: cached=True means the existing image
    was reused (no spend); cached=False means a new paid render was made."""
    target = cached_scene_image_path(job_dir, scene_index)
    if target.is_file() and target.stat().st_size > 0:
        return {"path": target, "cached": True}
    with _lock_for(target):
        # Re-check inside the lock: a concurrent caller may have just rendered it.
        if target.is_file() and target.stat().st_size > 0:
            return {"path": target, "cached": True}
        generate_scene_image(prompt, target, api_key, model=model)
        return {"path": target, "cached": False}
