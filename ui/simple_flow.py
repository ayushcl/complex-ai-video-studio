"""Simple mode: document in -> JSON artifacts -> draft video -> high-quality video.

The flow wraps the same engine path as the admin console (run_from_packet.py,
all spend gates intact). What it adds:

  * document understanding: extract text from .txt/.md/.json/.docx/.pdf
    (ui/docparse.py, stdlib only), then author scenes.json + storyboard.json
    either with one small Gemini text call (when a key is configured and AI
    extraction is enabled in settings) or a deterministic heuristic fallback -
    so the app works with zero API keys, just with plainer results.
  * draft-first generation: the draft packet uses the cheap/fast model, the
    high-quality packet swaps in the HQ model at the same prompts. Models and
    resolutions come from admin settings.
  * a server-issued, single-use confirmation TOKEN replaces the typed SPEND
    phrase for simple mode. The token is minted by issue_confirmation() bound
    to exactly one job_dir+quality+max_scenes+estimate; generate() consumes it
    and refuses any request without a valid, unexpired, matching token. This
    REPLACES the typing only - it does not weaken the underlying gates: the
    full sequence still runs server-side (write packet -> fresh dry-run ->
    start_live_run, which requires allow_live_run plus its own adapter gates),
    and a blind/accidental POST with no valid token spends nothing. (The admin
    console keeps the typed SPEND phrase - it is the expert surface.)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import struct
import threading
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path

import characters
import cost_estimator
import docparse
try:
    import negative_library
except Exception:
    negative_library = None
import engine_bridge as bridge
import scene_images
import storyboard as storyboard_mod
import video_tiers

# Legacy simple-mode quality keys (draft = the cheap/fast model, hq = the
# high-quality model). These map to a model+resolution via Admin Settings and
# remain supported so the existing two-button draft/HQ flow keeps working.
QUALITIES = ("draft", "hq")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_ASPECT_RATIO = "9:16"
VALID_ASPECT_RATIOS = ("9:16", "16:9")
GEMINI_AUTHOR_MODEL = "gemini-3.1-flash-lite"  # same family the music brief uses
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _resolve_video_selection(tier: str, settings: dict) -> dict:
    """Resolve a video-generation selector to a concrete model + resolution.

    `tier` may be a legacy quality ("draft"/"hq", resolved via Admin Settings)
    OR a Phase-A VIDEO render-tier key ("standard"/"quality"/"ultra4k", resolved
    via video_tiers - the single source of truth for the tier->model mapping).
    Raises BridgeError on anything else (never silently picking a price).

    Returns {"key", "model", "resolution", "label", "per_second_rate"|None}."""
    if not isinstance(tier, str) or not tier.strip():
        raise bridge.BridgeError(
            f"tier must be one of {QUALITIES} or {tuple(video_tiers.video_tier_keys())}."
        )
    key = tier.strip()
    if key in QUALITIES:
        chosen = settings[key]
        return {
            "key": key,
            "model": chosen["model"],
            "resolution": chosen["resolution"],
            "label": key,
            "per_second_rate": None,
        }
    try:
        vt = video_tiers.resolve_video_tier(key)
    except video_tiers.UnknownTierError:
        raise bridge.BridgeError(
            f"tier must be one of {QUALITIES} or {tuple(video_tiers.video_tier_keys())}, got: {tier!r}."
        )
    return {
        "key": vt["key"],
        "model": vt["model"],
        "resolution": vt["resolution"],
        "label": vt["label"],
        "per_second_rate": vt["per_second_rate"],
    }


def simple_dir() -> Path:
    return bridge.DATA_DIR / "simple"


def uploads_dir() -> Path:
    return bridge.DATA_DIR / "uploads"


# --------------------------------------------------------------------------- #
# Uploads                                                                      #
# --------------------------------------------------------------------------- #
def save_upload(filename: str, data: bytes) -> dict:
    extension = Path(filename or "").suffix.lower()
    if extension not in docparse.SUPPORTED_EXTENSIONS:
        raise bridge.BridgeError(
            f"Unsupported file type {extension or '(none)'!r}. Accepted: .txt, .md, .json, .docx, .pdf."
        )
    if len(data) > docparse.MAX_DOC_BYTES:
        raise bridge.BridgeError("Document is too large (20 MB cap).")
    if not data:
        raise bridge.BridgeError("Uploaded file is empty.")
    uploads_dir().mkdir(parents=True, exist_ok=True)
    stem = bridge.slugify(Path(filename).stem) or "document"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = uploads_dir() / f"{stem}_{stamp}{extension}"
    path.write_bytes(data)
    bridge.audit("simple_upload", path=bridge.rel_path(path), bytes=len(data))
    return {"path": bridge.rel_path(path), "extension": extension, "bytes": len(data)}


def save_image_upload(filename: str, data: bytes) -> dict:
    """Store one validated image under a server-generated repo-relative path."""
    extension = Path(filename or "").suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        raise bridge.BridgeError(
            f"Unsupported image type {extension or '(none)'!r}. "
            f"Accepted: {', '.join(sorted(IMAGE_EXTENSIONS))}."
        )
    if not data:
        raise bridge.BridgeError("Uploaded image is empty.")
    if len(data) > IMAGE_UPLOAD_MAX_BYTES:
        raise bridge.BridgeError("Image is too large (10 MB cap).")

    signatures_ok = {
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".webp": len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }
    if not signatures_ok[extension]:
        raise bridge.BridgeError(f"Uploaded file is not a valid {extension} image.")

    upload_root = bridge.safe_path("ui/data/uploads")
    upload_root.mkdir(parents=True, exist_ok=True)
    safe_stem = bridge.slugify(Path(filename).stem) or "image"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = bridge.safe_path(
        f"ui/data/uploads/{stamp}_{safe_stem}{extension}"
    )
    with destination.open("xb") as handle:
        handle.write(data)
    path = bridge.rel_path(destination)
    bridge.audit("simple_image_upload", path=path, bytes=len(data))
    return {"path": path}


# --------------------------------------------------------------------------- #
# Placeholder seed image (stdlib PNG writer)                                   #
# --------------------------------------------------------------------------- #
def write_placeholder_seed(path: Path, title: str) -> None:
    """A tasteful dark gradient seed so generate jobs can run without the
    operator supplying an image. A real seed image gives far better results;
    the author step warns about this."""
    width, height = 1280, 720
    hue_seed = sum(title.encode("utf-8")) % 3
    # three palettes: deep blue/cyan, indigo/violet, charcoal/amber
    glows = [(40, 120, 190), (110, 80, 200), (190, 120, 45)][hue_seed]
    rows = []
    for y in range(height):
        row = bytearray([0])
        ny = y / height
        for x in range(width):
            nx = x / width
            dx, dy = (nx - 0.68) * 1.4, (ny - 0.4) * 1.1
            glow = math.exp(-(dx * dx + dy * dy) * 6.0) * (1.0 if ny < 0.7 else max(0.0, 1.0 - (ny - 0.7) / 0.3))
            row += bytes((
                min(255, int(8 + glow * glows[0])),
                min(255, int(8 + glow * glows[1])),
                min(255, int(10 + glow * glows[2])),
            ))
        rows.append(bytes(row))

    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b"")
    )


# --------------------------------------------------------------------------- #
# Gemini authoring (stdlib urllib; falls back to heuristic on ANY failure)    #
# --------------------------------------------------------------------------- #
class AuthorError(Exception):
    pass


_AUTHOR_SYSTEM_PROMPT = """You convert a client's scene/storyboard document into JSON artifacts for an automated SILENT brand-video pipeline (no speech; instrumental music is the entire audio layer).
Output ONLY a valid JSON object with this exact shape, no prose or fences:
{"job_name": "short-kebab-case-name", "scenes": [{"prompt": "...", "negative_prompt": "..."}], "storyboard": {"project_name": "...", "brand_name": "...", "region": "...", "target_duration_seconds": 0, "format": "...", "scene": {"description": "...", "spoken_line": "", "mood": "..."}, "music_direction": {"intent": "...", "instrumentation": "...", "energy": "...", "vocal_policy": "instrumental only, no vocals", "fade": "...", "avoid": ["..."]}, "notes": "..."}, "warnings": ["..."]}
Rules:
- Each scene prompt is a vivid, self-contained video-generation prompt faithfully built from the document. Scene 1 is generated from a still seed image; scenes 2+ each extend the previous shot by about 7 seconds. Preserve the document's palette, style, camera and mood instructions. Prefer positive description over stacked negatives. No em-dashes in prompts.
- negative_prompt: things to keep out of frame (readable text, watermarks, logos, faces if the document implies it, distortion, low quality), plus anything the document explicitly forbids.
- The storyboard steers MUSIC ONLY. scene.spoken_line is always "" (silent pipeline). Derive mood/energy/instrumentation from the document's tone; phrase instrumentation in specific original terms; the avoid list must include vocals, lyrics, and any reference to a specific artist or song.
- format states that the music is the sole audio layer.
- If the document has numbered scenes, keep their order and count. If it has no clear scenes, write one strong scene. Put anything ambiguous you had to decide into warnings."""


def gemini_author(text: str, job_name: str, api_key: str) -> dict:
    body = {
        "systemInstruction": {"parts": [{"text": _AUTHOR_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text":
            f"Suggested job name: {job_name}\n\nClient document:\n{text[:60000]}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }
    request = urllib.request.Request(
        GEMINI_URL.format(model=GEMINI_AUTHOR_MODEL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise AuthorError(f"Gemini request failed: {exc}")

    try:
        parts = payload["candidates"][0]["content"]["parts"]
        raw = "".join(part.get("text", "") for part in parts).strip()
        result = json.loads(raw)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise AuthorError(f"Gemini returned an unusable response: {exc}")

    scenes = result.get("scenes")
    storyboard = result.get("storyboard")
    if not isinstance(scenes, list) or not scenes or not isinstance(storyboard, dict):
        raise AuthorError("Gemini response missing scenes/storyboard.")
    default_negative = "readable text, watermarks, logos, distortion, low quality"
    if negative_library is not None:
        try:
            default_negative = negative_library.compose_negative(negative_library.DEFAULT_GROUPS)
        except Exception:
            pass
    cleaned = []
    for scene in scenes:
        if isinstance(scene, dict) and str(scene.get("prompt", "")).strip():
            cleaned.append({
                "prompt": str(scene["prompt"]).strip(),
                "negative_prompt": str(scene.get("negative_prompt") or "").strip()
                    or default_negative,
            })
    if not cleaned:
        raise AuthorError("Gemini produced no usable scene prompts.")
    return {
        "scenes": cleaned,
        "storyboard": storyboard,
        "job_name": str(result.get("job_name") or job_name),
        "warnings": [str(w) for w in result.get("warnings") or [] if str(w).strip()],
        "method": "ai",
    }


# --------------------------------------------------------------------------- #
# Edit-prompt rewrite (one cheap Gemini text call; same client style as       #
# gemini_author). Used by edit_scenes - on ANY failure it raises so the       #
# caller fails loud and changes nothing.                                       #
# --------------------------------------------------------------------------- #
_EDIT_SYSTEM_PROMPT = """You revise video-generation scene prompts for an automated SILENT brand-video pipeline.
You are given a JSON array of one or more scene objects (each has "prompt" and may have "negative_prompt") and a plain-language instruction from the operator.
Rewrite ONLY the "prompt" (and "negative_prompt" when the instruction clearly calls for it) of EACH scene by applying the instruction, while PRESERVING each scene's core structure, subject, continuity, and ordering. Do not merge, drop, reorder, add, or renumber scenes: return EXACTLY as many scenes as you were given, in the same order.
Keep each prompt a vivid, self-contained video-generation prompt. No readable text, watermarks, logos, em-dashes, or speech (the pipeline is silent). Prefer positive description over stacked negatives.
Output ONLY a valid JSON object of the exact shape {"scenes": [{"prompt": "...", "negative_prompt": "..."}, ...]} with no prose and no code fences."""


def _rewrite_scene_prompts(scenes: list, instruction: str, api_key: str) -> list:
    """One Gemini text call (gemini-3.1-flash-lite, same stdlib-urllib client
    style as gemini_author) that rewrites the given scenes' prompts by applying
    `instruction`, preserving count + order. Returns the rewritten prompt dicts
    [{"prompt", "negative_prompt"|None}, ...] aligned 1:1 with the input. Raises
    AuthorError on ANY transport/decode/shape failure so the caller can fail
    loud and change nothing. The key is the x-goog-api-key header, never logged."""
    if not api_key or not str(api_key).strip():
        raise AuthorError("A Gemini API key is required to rewrite scene prompts.")
    payload_scenes = [
        {"prompt": str(s.get("prompt", "")), "negative_prompt": s.get("negative_prompt")}
        for s in scenes
    ]
    user_text = (
        f"Operator instruction:\n{str(instruction).strip()[:4000]}\n\n"
        f"Scenes to revise (apply the instruction to every one, keep the same count and order):\n"
        f"{json.dumps({'scenes': payload_scenes}, ensure_ascii=False)[:40000]}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": _EDIT_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }
    request = urllib.request.Request(
        GEMINI_URL.format(model=GEMINI_AUTHOR_MODEL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result_payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise AuthorError(f"Gemini request failed: {exc}")

    try:
        parts = result_payload["candidates"][0]["content"]["parts"]
        raw = "".join(part.get("text", "") for part in parts).strip()
        result = json.loads(raw)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise AuthorError(f"Gemini returned an unusable response: {exc}")

    rewritten = result.get("scenes") if isinstance(result, dict) else result
    if not isinstance(rewritten, list) or len(rewritten) != len(scenes):
        raise AuthorError(
            f"Gemini returned {len(rewritten) if isinstance(rewritten, list) else 'no'} scene(s); "
            f"expected exactly {len(scenes)}."
        )
    out = []
    for index, item in enumerate(rewritten):
        if not isinstance(item, dict):
            raise AuthorError(f"Rewritten scene {index + 1} is not an object.")
        prompt = str(item.get("prompt", "")).strip()
        if not prompt:
            raise AuthorError(f"Rewritten scene {index + 1} has an empty prompt.")
        negative = str(item.get("negative_prompt") or "").strip() or None
        out.append({"prompt": prompt, "negative_prompt": negative})
    return out


# --------------------------------------------------------------------------- #
# Author: document -> artifacts on disk -> validated draft-shaped packet      #
# --------------------------------------------------------------------------- #
def _valid_inline_seed(value) -> bool:
    """True only for a non-empty string path to an existing in-repo image."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        path = bridge.safe_path(value)
    except bridge.BridgeError:
        return False
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def _validated_image_path(value, label: str) -> str:
    """Validate one existing in-repo image and return its normalized path."""
    path = bridge.safe_path(value)
    if not path.is_file():
        raise bridge.BridgeError(f"{label} not found: {value}")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise bridge.BridgeError(f"{label} must be one of {sorted(IMAGE_EXTENSIONS)}.")
    return bridge.rel_path(path)


def _derive_job_name(text: str, explicit: str | None) -> str:
    if explicit and explicit.strip():
        return bridge.slugify(explicit)
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    first_line = re.sub(r"^#+\s*", "", first_line)
    words = bridge.slugify(" ".join(first_line.split()[:6]))
    return words or f"video-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _gemini_key_for_text() -> str | None:
    """The Gemini key to use for an optional small text call, or None when no
    usable key is configured. Read from .env/env; never logged or returned."""
    if not bridge._key_is_set("GEMINI_API_KEY"):
        return None
    return bridge._env_file_values().get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")


def _author_scene_summaries(prompts: list, settings: dict) -> tuple:
    """A short, friendly, NON-technical summary per scene prompt for the review
    carousel. Calls storyboard.human_readable_summary with the Gemini key when a
    key is set AND AI extraction is enabled; otherwise the heuristic fallback
    (which needs no key). Returns (list_of_summaries, method) where method is
    "ai" if any summary came from the model, else "fallback". Never raises - a
    per-scene failure degrades to the local fallback for that scene."""
    api_key = _gemini_key_for_text() if settings.get("ai_extraction") else None
    summaries = []
    any_ai = False
    for prompt in prompts:
        try:
            result = storyboard_mod.human_readable_summary(prompt, api_key)
        except storyboard_mod.StoryboardError:
            # Empty/odd prompt: keep a (trimmed) stand-in rather than failing.
            result = {"summary": str(prompt or "").strip()[:240], "method": "fallback"}
        summaries.append(result["summary"])
        if result.get("method") == "ai":
            any_ai = True
    return summaries, ("ai" if any_ai else "fallback")


def _normalize_scene1(scene, reframe=None):
    if not isinstance(scene, dict):
        return False
    if reframe is None:
        if negative_library is None:
            return False
        try:
            reframe = negative_library.positive_reframe()
        except Exception:
            return False
    scene.pop("negative_prompt", None)
    prompt = str(scene.get("prompt", "")).rstrip()
    if reframe and reframe not in prompt:
        if prompt and not prompt.endswith((".", "!", "?")):
            prompt = prompt + "."
        prompt = (prompt + " " + reframe).strip()
    scene["prompt"] = prompt
    return True


def _apply_negative_library(scenes):
    """F5: apply the negative-prompt library to authored scenes, IN PLACE.

    Scene 1 (scenes[0]): drop any negative_prompt (the reference/asset call
      rejects it) and fold the positive reframe into its prompt.
    Scenes 2+ (scenes[1:]): fill negative_prompt with the composed default
      ONLY when the scene has none (operator-supplied negatives are kept).
    No-op if the library is unavailable, so authoring never breaks.
    Returns a per-scene summary list (used by a later UI step; ignore for now).
    """
    if negative_library is None or not scenes:
        return []
    try:
        composed = negative_library.compose_negative(negative_library.DEFAULT_GROUPS)
        reframe = negative_library.positive_reframe()
    except Exception:
        return []  # any library failure -> leave scenes untouched (no-op)

    summary = []
    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            summary.append({"scene": idx + 1, "mode": "skipped"})
            continue
        if idx == 0:
            _normalize_scene1(scene, reframe=reframe)
            summary.append({"scene": 1, "mode": "positive"})
        else:
            existing = str(scene.get("negative_prompt", "") or "").strip()
            if not existing:
                scene["negative_prompt"] = composed
                applied = composed
                mode = "library"
            else:
                applied = existing
                mode = "custom"
            count = len([f for f in applied.split(",") if f.strip()])
            summary.append({"scene": idx + 1, "mode": mode, "count": count})
    return summary


def author_job(payload: dict) -> dict:
    """Turn a pasted/uploaded document into on-disk artifacts + a validated
    job. Free except for one small optional Gemini text call (see settings)."""
    warnings = []

    seed_input = str(payload.get("seed_image_path") or "").strip()
    reference_input = str(payload.get("reference_image_path") or "").strip()
    aspect_ratio = str(payload.get("aspect_ratio") or DEFAULT_ASPECT_RATIO).strip()
    if aspect_ratio not in VALID_ASPECT_RATIOS:
        raise bridge.BridgeError("aspect_ratio must be one of: 9:16, 16:9")
    if seed_input and reference_input:
        raise bridge.BridgeError(
            "reference_image_path and seed_image_path are mutually exclusive; "
            "choose one asset reference or one first-frame seed."
        )
    seed_rel = _validated_image_path(seed_input, "Seed image") if seed_input else None
    reference_rel = (
        _validated_image_path(reference_input, "Reference image")
        if reference_input
        else None
    )

    if payload.get("source_path"):
        source = bridge.safe_path(payload["source_path"])
        if not source.is_file():
            raise bridge.BridgeError(f"Document not found: {payload['source_path']}")
        try:
            text = docparse.extract_text(source.read_bytes(), source.suffix)
        except docparse.DocParseError as exc:
            raise bridge.BridgeError(str(exc))
        source_label = bridge.rel_path(source)
    elif str(payload.get("text") or "").strip():
        text = str(payload["text"]).strip()
        source_label = "(pasted text)"
    else:
        raise bridge.BridgeError("Paste a description or upload a document first.")

    job_name = _derive_job_name(text, payload.get("job_name"))

    # Direct JSON artifacts (the operator pasted a scenes/storyboard file).
    direct_scenes, direct_storyboard = docparse.try_parse_artifact_json(text)

    settings = bridge.load_settings()
    method = "heuristic"
    if direct_scenes:
        scenes = [
            {"prompt": str(s.get("prompt", "")).strip(),
             "negative_prompt": str(s.get("negative_prompt") or "").strip() or None,
             # Only carry a seed_image through if it's a real in-repo image
             # file; a bogus inline path would otherwise pass the free dry-run
             # and only fail AFTER the operator typed SPEND.
             **({"seed_image": s["seed_image"]} if _valid_inline_seed(s.get("seed_image")) else {}),
             **({"duration_seconds": s["duration_seconds"]} if s.get("duration_seconds") else {})}
            for s in direct_scenes if isinstance(s, dict) and str(s.get("prompt", "")).strip()
        ]
        if direct_scenes and direct_scenes[0].get("seed_image") and not _valid_inline_seed(direct_scenes[0].get("seed_image")):
            warnings.append(
                f"Scene 1 seed_image {direct_scenes[0].get('seed_image')!r} was not a valid in-repo image; "
                "a generated placeholder is used instead - replace it before generating for best results."
            )
        if not scenes:
            raise bridge.BridgeError("The pasted scenes JSON contains no usable prompts.")
        scenes = [{k: v for k, v in s.items() if v is not None} for s in scenes]
        storyboard = direct_storyboard or docparse.heuristic_author(
            "\n\n".join(s["prompt"] for s in scenes), job_name)["storyboard"]
        method = "json"
    else:
        authored = None
        if settings.get("ai_extraction") and bridge._key_is_set("GEMINI_API_KEY"):
            api_key = bridge._env_file_values().get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
            try:
                authored = gemini_author(text, job_name, api_key)
                method = "ai"
                warnings.extend(authored["warnings"])
                job_name = bridge.slugify(authored["job_name"]) or job_name
            except AuthorError as exc:
                warnings.append(f"AI extraction unavailable ({exc}); used the basic parser instead - review the results.")
        if authored is None:
            authored = docparse.heuristic_author(text, job_name)
            if method != "ai" and not settings.get("ai_extraction"):
                warnings.append("AI extraction is turned off in settings; the basic parser was used.")
            elif method != "ai" and not bridge._key_is_set("GEMINI_API_KEY"):
                warnings.append("No Gemini key configured, so the basic parser was used - add one in Admin > Settings for smarter extraction.")
        scenes = authored["scenes"]
        storyboard = authored["storyboard"]

    negative_applied = _apply_negative_library(scenes)  # F5: scene-1 positive reframe + scenes 2+ composed negative

    # Job directory + seed image.
    slug = job_name
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_dir = simple_dir() / f"{slug}_{stamp}"
    job_dir.mkdir(parents=True, exist_ok=True)

    if reference_rel:
        # Asset-reference mode must not also carry a literal first-frame seed.
        scenes[0].pop("seed_image", None)
    elif not seed_rel and not scenes[0].get("seed_image"):
        placeholder = job_dir / "seed_placeholder.png"
        write_placeholder_seed(placeholder, slug)
        seed_rel = bridge.rel_path(placeholder)
        warnings.append(
            "No seed image supplied - a generated gradient placeholder seeds scene 1. "
            "A real brand image will give far better results."
        )
    if seed_rel:
        scenes[0]["seed_image"] = seed_rel
    scenes[0].setdefault("mode", "image")
    scenes[0].setdefault("duration_seconds", 6)

    scenes_path = job_dir / "scenes.json"
    scenes_path.write_text(json.dumps({"scenes": scenes}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    storyboard_path = job_dir / "storyboard.json"
    storyboard_path.write_text(json.dumps(storyboard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Friendly, non-technical summary per scene so the carousel can show
    # human-readable text. Uses one cheap Gemini text call per scene when a key
    # is set (and AI extraction is on); otherwise a local heuristic fallback.
    scene_summaries, summary_method = _author_scene_summaries(
        [s["prompt"] for s in scenes], settings)
    if summary_method == "ai":
        warnings.append("Friendly scene descriptions were written by AI for the review carousel.")

    content_path = (payload.get("content_path") or "silent_brand").strip() or "silent_brand"
    if content_path not in ("silent_brand", "presenter"):
        raise bridge.BridgeError(f"Invalid content_path: {content_path!r}")

    prepared_voice_rel = None
    if content_path == "presenter":
        raw_voice = payload.get("prepared_voice_path")
        if not raw_voice:
            raise bridge.BridgeError("Presenter jobs require a picked voice (prepared_voice_path).")
        voice_abs = bridge.safe_path(raw_voice)
        if not voice_abs.is_file():
            raise bridge.BridgeError("prepared_voice_path does not point to a file.")
        prepared_voice_rel = bridge.rel_path(voice_abs)

    job = {
        "slug": slug,
        "job_dir": bridge.rel_path(job_dir),
        "created_at": bridge.utc_now(),
        "source": source_label,
        "method": method,
        "scene_count": len(scenes),
        "max_scenes": len(scenes),
        "aspect_ratio": aspect_ratio,
        "scenes_path": bridge.rel_path(scenes_path),
        "storyboard_path": bridge.rel_path(storyboard_path),
        "seed_image": scenes[0].get("seed_image"),
        "reference_image_path": reference_rel,
        "seed_is_placeholder": seed_rel is not None and seed_rel.endswith("seed_placeholder.png"),
        "scene_summaries": scene_summaries,
        "summary_method": summary_method,
        "runs": {},
    }
    if content_path == "presenter":
        job.update({
            "content_path": "presenter",
            "prepared_voice_path": prepared_voice_rel,
        })
    _write_job(job)

    review = bridge.structured_review(_packet_for(job, "draft", settings, authorized=False))
    bridge.audit("simple_authored", job_dir=job["job_dir"], method=method, scenes=len(scenes))
    return {
        "job": job,
        "review": review,
        "warnings": warnings,
        "scene_prompts": [s["prompt"][:280] for s in scenes],
        "scene_summaries": scene_summaries,
        "negative_applied": negative_applied,
    }


# --------------------------------------------------------------------------- #
# Jobs on disk                                                                 #
# --------------------------------------------------------------------------- #
def _job_path(job_dir: Path) -> Path:
    return job_dir / "job.json"


def _write_job(job: dict) -> None:
    job_dir = bridge.safe_path(job["job_dir"])
    with _job_path(job_dir).open("w", encoding="utf-8") as handle:
        json.dump(job, handle, indent=2)
        handle.write("\n")


def load_job(job_dir_rel: str) -> dict:
    job_dir = bridge.safe_path(job_dir_rel)
    return bridge.read_json_file(_job_path(job_dir), "Job")


def open_job(job_dir_rel: str) -> dict:
    """Reopen a saved job with a REAL validity review (not a fabricated one),
    so a job whose artifacts were since edited/deleted shows red, not green."""
    job = load_job(job_dir_rel)
    review = bridge.structured_review(_packet_for(job, "draft", bridge.load_settings(), authorized=False))
    scene_prompts = []
    try:
        scenes_data = bridge.read_json_file(bridge.safe_path(job["scenes_path"]), "Scenes")
        scenes = scenes_data.get("scenes") if isinstance(scenes_data, dict) else scenes_data
        if isinstance(scenes, list):
            scene_prompts = [str(s.get("prompt", ""))[:280] for s in scenes if isinstance(s, dict)]
    except bridge.BridgeError:
        pass
    return {
        "job": job,
        "review": review,
        "warnings": [],
        "scene_prompts": scene_prompts,
        "scene_summaries": job.get("scene_summaries") or [],
    }


def list_jobs(limit: int = 20) -> list:
    root = simple_dir()
    if not root.is_dir():
        return []
    jobs = []
    for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        job_file = _job_path(child)
        if job_file.is_file():
            try:
                jobs.append(json.loads(job_file.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
    return jobs


# --------------------------------------------------------------------------- #
# Generate (draft / high quality) - full gate sequence, server side           #
# --------------------------------------------------------------------------- #
def _packet_for(job: dict, quality: str, settings: dict, authorized: bool) -> dict:
    selection = _resolve_video_selection(quality, settings)
    return {
        "job_id": f"{job['slug']}-{selection['key']}",
        "content_path": job.get("content_path", "silent_brand"),
        "video_source": "generate",
        "video_path": None,
        "scenes_path": job["scenes_path"],
        "presenter_reference_image_path": job.get("reference_image_path"),
        "storyboard_path": job["storyboard_path"],
        "model": selection["model"],
        "resolution": selection["resolution"],
        "aspect_ratio": job.get("aspect_ratio") or DEFAULT_ASPECT_RATIO,
        "max_scenes": int(job.get("max_scenes") or job["scene_count"]),
        "voice": {"prepared_voice_path": job.get("prepared_voice_path") if job.get("content_path") == "presenter" else None},
        "accent_dialect": None,
        "output_settings": {"output_dir": "runs", "final_video_name": "final_video.mp4"},
        "spend_controls": {
            "allow_live_run": bool(authorized),
            "notes": f"Simple-mode {selection['key']} generation; authorized via single-use confirmation token in the UI."
            if authorized else f"Simple-mode {selection['key']} packet (not yet authorized).",
        },
        "metadata": {
            "client": "",
            "campaign": job["slug"],
            "notes": f"Authored from {job.get('source')} via {job.get('method')} extraction.",
        },
    }


def _normalize_max_scenes(job: dict, max_scenes) -> int:
    """Resolve and validate the spend cap against the job's scene count.
    Returns the effective max_scenes (defaulting to the job's stored cap)."""
    scene_count = int(job.get("scene_count") or 0)
    if max_scenes is None:
        resolved = int(job.get("max_scenes") or scene_count or 1)
    else:
        try:
            resolved = int(max_scenes)
        except (TypeError, ValueError):
            raise bridge.BridgeError("max_scenes must be a whole number.")
    if scene_count and not 1 <= resolved <= scene_count:
        raise bridge.BridgeError(f"max_scenes must be between 1 and {scene_count}.")
    if resolved < 1:
        raise bridge.BridgeError("max_scenes must be at least 1.")
    return resolved


# --------------------------------------------------------------------------- #
# Cost estimate (pure; never spends, never gates)                              #
# --------------------------------------------------------------------------- #
def estimate(job_dir_rel: str, quality: str, max_scenes=None) -> dict:
    """A rough, operator-facing spend estimate for one generation, using the
    pure cost_estimator plus the operator's Admin-Settings pricing. This NEVER
    spends and NEVER gates a run - it only labels a number a human can check.

    `quality` may be a legacy quality ("draft"/"hq") or a VIDEO render-tier key
    ("standard"/"quality"/"ultra4k"); the estimate reflects the chosen tier's
    model + resolution (the Veo rate is resolution-aware)."""
    settings = bridge.load_settings()
    selection = _resolve_video_selection(quality, settings)  # validates + maps the tier
    job = load_job(job_dir_rel)
    resolved_max = _normalize_max_scenes(job, max_scenes)
    pricing = settings.get("pricing") or cost_estimator.DEFAULT_PRICING
    # Reference-image jobs are force-locked by the adapter to the presenter-reference model/res/8s
    # (run_from_packet build_command). Mirror that here so the quote matches the real spend instead
    # of the selected tier. Source the constants from the adapter via bridge.adapter() - single
    # source of truth, no drift between estimate and execution.
    eff_model = selection["model"]
    eff_resolution = selection["resolution"]
    _ref = job.get("reference_image_path")
    if _ref:
        _adapter = bridge.adapter()
        eff_model = _adapter.PRESENTER_REFERENCE_MODEL
        eff_resolution = _adapter.PRESENTER_REFERENCE_RESOLUTION
    estimate_job = {
        "scene_count": job.get("scene_count"),
        "max_scenes": resolved_max,
        "seed_is_placeholder": bool(job.get("seed_is_placeholder")),
        # The exact model + resolution this generation bills at, so the estimate
        # is resolution-aware rather than tier-keyed.
        "model": eff_model,
        "resolution": eff_resolution,
    }
    # NOTE: estimate_job intentionally carries NO inline "scenes" list, so seed_duration_seconds is
    # honored by cost_estimator._seed_seconds (inline scenes would otherwise take precedence). If a
    # future change adds "scenes" here, this 8s lock must be revisited.
    if _ref:
        estimate_job["seed_duration_seconds"] = 8
    breakdown = cost_estimator.estimate_cost(estimate_job, selection["key"], pricing)
    return {
        "job_dir": job["job_dir"],
        "quality": quality,
        "tier": selection["key"],
        "model": eff_model,
        "resolution": eff_resolution,
        "max_scenes": resolved_max,
        "scene_count": job.get("scene_count"),
        "estimate": breakdown,
    }


# --------------------------------------------------------------------------- #
# Server-issued confirmation tokens (replace the typed SPEND for simple mode)  #
# --------------------------------------------------------------------------- #
# token -> {"binding": <sha256 of job+quality+max_scenes+total>, "job_dir": ...,
#           "quality": ..., "max_scenes": ..., "estimate_total": ..., "at": ...,
#           "expires_at": ...}. In-memory on purpose (like the dry-run registry):
# a server restart invalidates every outstanding token, forcing a fresh confirm.
_confirm_tokens: dict = {}
_confirm_lock = threading.Lock()
CONFIRM_TOKEN_TTL_SECONDS = 300


def _confirm_binding(job_dir_rel: str, quality: str, max_scenes: int, estimate_total) -> str:
    """A stable fingerprint of exactly what was confirmed. A token only unlocks
    the job+quality+cap+cost it was minted for; anything else is a mismatch."""
    payload = json.dumps(
        {"job_dir": job_dir_rel, "quality": quality,
         "max_scenes": int(max_scenes), "estimate_total": estimate_total},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _purge_expired_tokens(now: float) -> None:
    """Best-effort eviction of expired tokens. Caller holds _confirm_lock."""
    for token in [t for t, e in _confirm_tokens.items() if e["expires_at"] <= now]:
        _confirm_tokens.pop(token, None)


def issue_confirmation(job_dir_rel: str, quality: str, max_scenes=None) -> dict:
    """Mint a short, single-use confirmation token bound to exactly this
    job_dir + quality + max_scenes + current estimate. The operator confirms a
    specific, costed action; generate() then consumes the token instead of a
    typed phrase. The token never authorizes spend by itself - it stands in for
    the human's deliberate confirmation, and every underlying gate still runs."""
    _resolve_video_selection(quality, bridge.load_settings())  # validates the tier
    job = load_job(job_dir_rel)
    job_dir_rel = job["job_dir"]  # canonical repo-relative form
    resolved_max = _normalize_max_scenes(job, max_scenes)
    detail = estimate(job_dir_rel, quality, resolved_max)
    estimate_total = detail["estimate"].get("total")
    binding = _confirm_binding(job_dir_rel, quality, resolved_max, estimate_total)

    token = secrets.token_urlsafe(24)
    now = time.time()
    with _confirm_lock:
        _purge_expired_tokens(now)
        _confirm_tokens[token] = {
            "binding": binding,
            "job_dir": job_dir_rel,
            "quality": quality,
            "max_scenes": resolved_max,
            "estimate_total": estimate_total,
            "at": bridge.utc_now(),
            "expires_at": now + CONFIRM_TOKEN_TTL_SECONDS,
        }
    bridge.audit("simple_confirm_token_issued", job_dir=job_dir_rel,
                 quality=quality, max_scenes=resolved_max, estimate_total=estimate_total)
    return {
        "confirm_token": token,
        "expires_in_seconds": CONFIRM_TOKEN_TTL_SECONDS,
        "job_dir": job_dir_rel,
        "quality": quality,
        "max_scenes": resolved_max,
        "estimate": detail["estimate"],
    }


def _consume_confirmation(token: str, job_dir_rel: str, quality: str, max_scenes: int) -> None:
    """Validate + atomically burn a confirmation token. Refuses (raising
    BridgeError, so nothing is spent) when the token is absent, already used,
    expired, or does not match this exact job+quality+max_scenes+estimate.

    The token is burned ONLY on a matching, successful consumption (done while
    holding the lock, so it is single-use even under concurrent requests). A
    MISMATCHED presentation is a refused attempt and must NOT burn the
    operator's legitimately-issued token - otherwise a misdirected or replayed
    request could deny the real confirmation."""
    if not isinstance(token, str) or not token:
        raise bridge.BridgeError(
            "Generation refused: no confirmation token. Confirm the costed action first "
            "(the server issues a one-time token); a blind request spends nothing."
        )
    now = time.time()
    # Recompute the current estimate OUTSIDE the lock (it loads settings + the
    # job from disk); the binding/expiry/burn decision happens under the lock.
    current_total = estimate(job_dir_rel, quality, max_scenes)["estimate"].get("total")
    with _confirm_lock:
        _purge_expired_tokens(now)
        entry = _confirm_tokens.get(token)
        if entry is None:
            # _purge_expired_tokens above already dropped any expired token, so
            # "absent" covers unknown, already-used, AND expired.
            raise bridge.BridgeError(
                "Generation refused: confirmation token is unknown, already used, or expired. "
                "Confirm the costed action again to mint a fresh token."
            )
        # Match against the token's recorded binding (job+quality+cap+estimate).
        expected = _confirm_binding(job_dir_rel, quality, max_scenes, entry["estimate_total"])
        if expected != entry["binding"]:
            # Wrong job/quality/cap: refuse WITHOUT burning the real token.
            raise bridge.BridgeError(
                "Generation refused: confirmation token does not match this job, quality, or spend cap."
            )
        if current_total != entry["estimate_total"]:
            # The costed action changed since confirmation; refuse and burn the
            # now-stale token so the operator must review the new estimate.
            _confirm_tokens.pop(token, None)
            raise bridge.BridgeError(
                "Generation refused: the cost estimate changed since you confirmed. "
                "Review the new estimate and confirm again."
            )
        # Matched + current: burn it now (single-use) and proceed.
        _confirm_tokens.pop(token, None)


def generate(job_dir_rel: str, quality: str, confirm_token: str, max_scenes=None) -> dict:
    """Run one paid generation. A valid server-issued confirmation token (bound
    to this exact job+quality+max_scenes+estimate) replaces the typed phrase for
    simple mode; it is consumed single-use here. The token is NOT an
    authorization - the underlying gates are unchanged: a fresh dry-run of the
    written packet must pass and start_live_run still requires allow_live_run
    plus the adapter's own --run + packet-flag gates. `quality` may be a legacy
    quality ("draft"/"hq") or a VIDEO render-tier key
    ("standard"/"quality"/"ultra4k")."""
    settings = bridge.load_settings()
    selection = _resolve_video_selection(quality, settings)  # validates the tier

    job = load_job(job_dir_rel)
    job_dir_rel = job["job_dir"]  # canonical repo-relative form
    resolved_max = _normalize_max_scenes(job, max_scenes)
    job["max_scenes"] = resolved_max

    # Validate + burn the one-time token BEFORE writing any packet or spending.
    # A blind/accidental POST with no valid token is refused right here.
    _consume_confirmation(confirm_token, job_dir_rel, quality, resolved_max)

    packet = _packet_for(job, quality, settings, authorized=True)
    job_dir = bridge.safe_path(job["job_dir"])
    packet_path = job_dir / f"packet_{bridge.slugify(selection['key'])}.json"
    with packet_path.open("w", encoding="utf-8") as handle:
        json.dump(packet, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    packet_rel = bridge.rel_path(packet_path)

    dry = bridge.dry_run(packet_rel)
    if not dry["ok"]:
        raise bridge.BridgeError(
            "Validation failed - nothing was spent:\n" + (dry["stderr"] or dry["stdout"] or "unknown error")
        )

    # The single-use token already stood in for the human's deliberate
    # confirmation (validated + burned above). Satisfy start_live_run's
    # confirm-phrase gate internally - that gate is replaced by the token for
    # simple mode, NOT removed: start_live_run still independently re-checks
    # allow_live_run + a fresh dry-run, and the adapter re-checks its own gates.
    result = bridge.start_live_run(packet_rel, bridge.CONFIRM_PHRASE)
    job.setdefault("runs", {})[selection["key"]] = {
        "ui_run_id": result["ui_run_id"],
        "tier": selection["key"],
        "model": packet["model"],
        "resolution": packet["resolution"],
        "max_scenes": packet["max_scenes"],
        "started_at": bridge.utc_now(),
    }
    _write_job(job)
    bridge.audit("simple_generate", job_dir=job["job_dir"], quality=selection["key"],
                 model=packet["model"], max_scenes=packet["max_scenes"])
    return {
        "ui_run_id": result["ui_run_id"],
        "quality": quality,
        "tier": selection["key"],
        "packet_path": packet_rel,
        "model": packet["model"],
        "resolution": packet["resolution"],
        "max_scenes": packet["max_scenes"],
        "job": job,
    }


# --------------------------------------------------------------------------- #
# Scene concept images (one cached image per scene, served via /api/media)     #
# --------------------------------------------------------------------------- #
def _job_scene_prompts(job: dict) -> list:
    """Read the scene prompts from the job's on-disk scenes.json (the engine's
    own artifact), in order. Returns a list of prompt strings."""
    scenes_data = bridge.read_json_file(bridge.safe_path(job["scenes_path"]), "Scenes")
    scenes = scenes_data.get("scenes") if isinstance(scenes_data, dict) else scenes_data
    if not isinstance(scenes, list):
        return []
    return [str(s.get("prompt", "")) for s in scenes if isinstance(s, dict)]


def scene_image(job_dir_rel: str, scene_index: int) -> dict:
    """Return a concept image for scene `scene_index` (1-based), generating it
    once and reusing it thereafter. The image lives inside the job directory so
    the existing path-safe media endpoint can serve it.

    PAID only on the first render of a given scene (one image, no batching) -
    cached on every later request, so the preview grid never re-spends. The key
    is read from the environment/.env and is never logged or returned."""
    job = load_job(job_dir_rel)
    job_dir = bridge.safe_path(job["job_dir"])

    try:
        index = int(scene_index)
    except (TypeError, ValueError):
        raise bridge.BridgeError("scene_index must be a positive integer (scenes are 1-based).")
    prompts = _job_scene_prompts(job)
    if not prompts:
        raise bridge.BridgeError("This job has no usable scene prompts to render.")
    if not 1 <= index <= len(prompts):
        raise bridge.BridgeError(f"scene_index must be between 1 and {len(prompts)}.")
    prompt = prompts[index - 1].strip()
    if not prompt:
        raise bridge.BridgeError(f"Scene {index} has an empty prompt; nothing to render.")

    target = scene_images.cached_scene_image_path(job_dir, index)
    # Keep the rendered image inside the repo so the media endpoint can serve it.
    media_path = bridge.rel_path(target)

    try:
        if target.is_file() and target.stat().st_size > 0:
            cached = True
        else:
            api_key = scene_images.scene_image_api_key()  # raises if no usable key
            result = scene_images.generate_scene_image_cached(job_dir, index, prompt, api_key)
            cached = result["cached"]
    except scene_images.SceneImageError as exc:
        raise bridge.BridgeError(str(exc))

    bridge.audit("simple_scene_image", job_dir=job["job_dir"], scene_index=index, cached=cached)
    return {
        "job_dir": job["job_dir"],
        "scene_index": index,
        "path": media_path,
        "cached": cached,
    }


# --------------------------------------------------------------------------- #
# Tiered storyboard images (Basic = FREE/ungated; Standard/Premium = GATED)    #
# --------------------------------------------------------------------------- #
# The Basic (Imagen) image tier is intentionally UNGATED per product decision
# (the business absorbs its cost). It is NOT tokenless-and-unbounded, though: the
# MAX_STORYBOARD_IMAGES runaway guard caps how many images a single storyboard
# render may produce, so a bug cannot loop the free path into surprise spend.
# The paid Standard/Premium tiers are GATED by the same single-use confirm-token
# mechanism as video (bound here to job + image_tier + image_count + estimate).
def _storyboard_image_count(job: dict, images_per_scene) -> tuple:
    """Resolve (scene_count, images_per_scene, total_images) for a storyboard
    render, clamping images_per_scene to the engineering cap. total_images is
    what the runaway guard and the cost estimate are computed against."""
    prompts = _job_scene_prompts(job)
    scene_count = len(prompts)
    if scene_count < 1:
        raise bridge.BridgeError("This job has no usable scene prompts to storyboard.")
    per_scene = storyboard_mod.clamp_image_count(images_per_scene)  # raises on junk/<1
    total = scene_count * per_scene
    if total > video_tiers.MAX_STORYBOARD_IMAGES:
        raise bridge.BridgeError(
            f"Storyboard would generate {total} images "
            f"({scene_count} scenes x {per_scene}/scene), over the safety cap of "
            f"{video_tiers.MAX_STORYBOARD_IMAGES}. Lower images-per-scene."
        )
    return scene_count, per_scene, total


def estimate_storyboard(job_dir_rel: str, image_tier=None, images_per_scene=1) -> dict:
    """A rough, operator-facing spend estimate for a storyboard render. NEVER
    spends and NEVER gates - it only labels a number a human can check.

    With NO image_tier (the default user path), the estimate reflects the ONE
    admin-configured image model (settings.image_model): it is free to the user
    (the cost is a business cost), and billed_to is "business". Passing an
    explicit image_tier estimates that tier's model (the gated tiers carry the
    free/paid distinction in free_to_user)."""
    settings = bridge.load_settings()
    job = load_job(job_dir_rel)
    job_dir_rel = job["job_dir"]
    scene_count, per_scene, total_images = _storyboard_image_count(job, images_per_scene)
    pricing = settings.get("pricing") or cost_estimator.DEFAULT_PRICING

    if image_tier is None or (isinstance(image_tier, str) and not image_tier.strip()):
        # Default user path: the admin-configured model, free to the user.
        tier_key = None
        model = settings["image_model"]
        resolution = _image_model_resolution(model)
        gated = False
        free_to_user = True
    else:
        try:
            tier = video_tiers.resolve_image_tier(image_tier)
        except video_tiers.UnknownTierError:
            raise bridge.BridgeError(
                f"image_tier must be one of {tuple(video_tiers.image_tier_keys())}, got: {image_tier!r}."
            )
        tier_key = tier["key"]
        model = tier["model"]
        resolution = tier.get("resolution")
        gated = tier["gated"]
        free_to_user = tier.get("free_to_user", False)

    breakdown = cost_estimator.estimate_storyboard_cost(
        total_images, model, resolution,
        pricing=pricing, free_to_user=free_to_user,
    )
    return {
        "job_dir": job_dir_rel,
        "image_tier": tier_key,
        "model": model,
        "resolution": resolution,
        "gated": gated,
        "free_to_user": free_to_user,
        "scene_count": scene_count,
        "images_per_scene": per_scene,
        "total_images": total_images,
        "estimate": breakdown,
    }


def _image_model_resolution(model: str):
    """The IMAGE_TIERS resolution for `model` (so the estimate is resolution-
    aware), or None if the model is not in the tier list."""
    for tier in video_tiers.IMAGE_TIERS:
        if tier["model"] == model:
            return tier.get("resolution")
    return None


def _image_confirm_binding(job_dir_rel: str, image_tier: str, total_images: int, estimate_total) -> str:
    """A stable fingerprint of a costed STORYBOARD action. The kind discriminator
    keeps an image token from ever satisfying a video binding (and vice versa)."""
    payload = json.dumps(
        {"kind": "image", "job_dir": job_dir_rel, "image_tier": image_tier,
         "total_images": int(total_images), "estimate_total": estimate_total},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def issue_storyboard_confirmation(job_dir_rel: str, image_tier: str, images_per_scene=1) -> dict:
    """Mint a single-use confirmation token for a PAID storyboard tier, bound to
    exactly this job + image_tier + image_count + current estimate. Reuses the
    same token registry/TTL as video. The Basic (ungated) tier never needs a
    token; minting one for it is refused so the UI does not gate the free tier."""
    tier = None
    try:
        tier = video_tiers.resolve_image_tier(image_tier)
    except video_tiers.UnknownTierError:
        raise bridge.BridgeError(
            f"image_tier must be one of {tuple(video_tiers.image_tier_keys())}, got: {image_tier!r}."
        )
    if not tier["gated"]:
        raise bridge.BridgeError(
            f"The {tier['label']} image tier is free to the user and ungated; no confirmation token is needed."
        )
    detail = estimate_storyboard(job_dir_rel, tier["key"], images_per_scene)
    job_dir_rel = detail["job_dir"]
    total_images = detail["total_images"]
    estimate_total = detail["estimate"].get("total")
    binding = _image_confirm_binding(job_dir_rel, tier["key"], total_images, estimate_total)

    token = secrets.token_urlsafe(24)
    now = time.time()
    with _confirm_lock:
        _purge_expired_tokens(now)
        _confirm_tokens[token] = {
            "binding": binding,
            "kind": "image",
            "job_dir": job_dir_rel,
            "image_tier": tier["key"],
            "total_images": total_images,
            "estimate_total": estimate_total,
            "at": bridge.utc_now(),
            "expires_at": now + CONFIRM_TOKEN_TTL_SECONDS,
        }
    bridge.audit("simple_storyboard_token_issued", job_dir=job_dir_rel,
                 image_tier=tier["key"], total_images=total_images, estimate_total=estimate_total)
    return {
        "confirm_token": token,
        "expires_in_seconds": CONFIRM_TOKEN_TTL_SECONDS,
        "job_dir": job_dir_rel,
        "image_tier": tier["key"],
        "images_per_scene": detail["images_per_scene"],
        "total_images": total_images,
        "estimate": detail["estimate"],
    }


def _consume_storyboard_confirmation(token: str, job_dir_rel: str, image_tier: str, total_images: int) -> None:
    """Validate + atomically burn a storyboard confirmation token. Refuses
    (raising BridgeError, so nothing is spent) when the token is absent, already
    used, expired, the wrong kind, or does not match this exact
    job + image_tier + image_count + estimate. A MISMATCHED presentation is a
    refused attempt and must NOT burn the operator's legitimate token; a stale
    estimate burns the now-invalid token so the operator re-confirms."""
    if not isinstance(token, str) or not token:
        raise bridge.BridgeError(
            "Storyboard generation refused: no confirmation token. Confirm the costed "
            "action first (the server issues a one-time token); a blind request spends nothing."
        )
    now = time.time()
    # Recompute the current cost from the SAME inputs the estimate uses
    # (tier + total image count + operator pricing), so a pricing change since
    # the token was minted is caught. Done outside the lock (it loads settings).
    try:
        tier = video_tiers.resolve_image_tier(image_tier)
    except video_tiers.UnknownTierError:
        raise bridge.BridgeError(
            f"image_tier must be one of {tuple(video_tiers.image_tier_keys())}, got: {image_tier!r}."
        )
    pricing = bridge.load_settings().get("pricing") or cost_estimator.DEFAULT_PRICING
    current_total = cost_estimator.estimate_storyboard_cost(
        total_images, tier["model"], tier.get("resolution"),
        pricing=pricing, free_to_user=tier.get("free_to_user", False),
    ).get("total")
    with _confirm_lock:
        _purge_expired_tokens(now)
        entry = _confirm_tokens.get(token)
        if entry is None or entry.get("kind") != "image":
            raise bridge.BridgeError(
                "Storyboard generation refused: confirmation token is unknown, already used, "
                "expired, or not a storyboard token. Confirm the costed action again."
            )
        expected = _image_confirm_binding(job_dir_rel, image_tier, total_images, entry["estimate_total"])
        if expected != entry["binding"]:
            raise bridge.BridgeError(
                "Storyboard generation refused: confirmation token does not match this job, "
                "image tier, or image count."
            )
        if current_total != entry["estimate_total"]:
            _confirm_tokens.pop(token, None)
            raise bridge.BridgeError(
                "Storyboard generation refused: the cost estimate changed since you confirmed. "
                "Review the new estimate and confirm again."
            )
        _confirm_tokens.pop(token, None)


def storyboard_generate(job_dir_rel: str, image_tier=None, images_per_scene=1, confirm_token=None) -> dict:
    """Generate a time-progression storyboard (several images per scene) and
    return repo-relative image paths the existing media endpoint can serve.

    The DEFAULT user path takes no image_tier and no token: the storyboard
    always renders with the ONE admin-configured image model
    (settings.image_model, defaulting to gemini-2.5-flash-image). This is FREE
    TO THE USER and UNGATED per product decision - the user no longer picks an
    image tier. It is still bounded by the MAX_STORYBOARD_IMAGES runaway guard
    (engineering safety, not a gate), so the free path can never loop into
    runaway spend.

    The legacy GATED tier path is preserved for admin/future use: passing an
    explicit image_tier resolves a video_tiers.IMAGE_TIERS entry, and a PAID
    (gated) tier still REQUIRES a valid single-use confirm-token bound to this
    exact job + image_tier + image_count + estimate (burned here, exactly like
    the video confirm-token). A blind request with no valid token is refused
    and spends nothing.

    Returns {"job_dir", "image_tier", "model", "gated", "scene_count",
    "images_per_scene", "total_images", "rendered", "reused", "scenes": [
    {"scene_index", "summary", "method", "warning", "moments": [
    {"moment_index", "prompt", "path": <media-rel>, "cached": bool}]}]}.
    For the default user path "image_tier" is None and "gated" is False.
    """
    job = load_job(job_dir_rel)
    job_dir_rel = job["job_dir"]
    scene_count, per_scene, total_images = _storyboard_image_count(job, images_per_scene)

    if image_tier is None or (isinstance(image_tier, str) and not image_tier.strip()):
        # Default user path: the admin-configured image model. FREE + UNGATED,
        # no token; only the runaway cap (enforced above) bounds it.
        tier_key = None
        model = bridge.load_settings()["image_model"]
        gated = False
        free_to_user = True
    else:
        # Legacy/admin gated-tier path (kept intact for future use).
        try:
            tier = video_tiers.resolve_image_tier(image_tier)
        except video_tiers.UnknownTierError:
            raise bridge.BridgeError(
                f"image_tier must be one of {tuple(video_tiers.image_tier_keys())}, got: {image_tier!r}."
            )
        tier_key = tier["key"]
        model = tier["model"]
        gated = tier["gated"]
        free_to_user = tier.get("free_to_user", False)
        # The PAID tiers are gated by the confirm-token; an ungated tier is not.
        if gated:
            _consume_storyboard_confirmation(confirm_token, job_dir_rel, tier_key, total_images)

    try:
        api_key = scene_images.scene_image_api_key()  # raises if no usable key
    except scene_images.SceneImageError as exc:
        raise bridge.BridgeError(str(exc))
    job_dir = bridge.safe_path(job["job_dir"])
    prompts = _job_scene_prompts(job)
    summaries = job.get("scene_summaries") or []

    scenes_out = []
    rendered = reused = 0
    for scene_index, prompt in enumerate(prompts, start=1):
        try:
            board = storyboard_mod.generate_storyboard(
                job_dir, scene_index, prompt, per_scene, api_key, model=model,
            )
        except storyboard_mod.StoryboardError as exc:
            raise bridge.BridgeError(str(exc))
        rendered += board["rendered"]
        reused += board["reused"]
        scenes_out.append({
            "scene_index": scene_index,
            "summary": summaries[scene_index - 1] if scene_index - 1 < len(summaries) else None,
            "method": board["method"],
            "warning": board.get("warning"),
            "moments": [
                {
                    "moment_index": m["moment_index"],
                    "prompt": m["prompt"],
                    # Serve via the existing path-safe media endpoint.
                    "path": bridge.rel_path(m["path"]),
                    "cached": m["cached"],
                }
                for m in board["moments"]
            ],
        })

    bridge.audit("simple_storyboard", job_dir=job_dir_rel, image_tier=tier_key,
                 model=model, images_per_scene=per_scene, total_images=total_images,
                 rendered=rendered, reused=reused)
    return {
        "job_dir": job_dir_rel,
        "image_tier": tier_key,
        "model": model,
        "gated": gated,
        "free_to_user": free_to_user,
        "scene_count": scene_count,
        "images_per_scene": per_scene,
        "total_images": total_images,
        "rendered": rendered,
        "reused": reused,
        "scenes": scenes_out,
    }


# --------------------------------------------------------------------------- #
# Edit prompt(s) + regenerate the affected storyboard images                   #
# --------------------------------------------------------------------------- #
def _resolve_edit_scope(scope, scene_count: int) -> list:
    """Resolve `scope` to the 1-based scene indices it targets. "all" (any case)
    targets every scene; a 1-based integer (or numeric string) targets just that
    scene. Raises BridgeError on anything else or an out-of-range index."""
    if isinstance(scope, str) and scope.strip().lower() == "all":
        return list(range(1, scene_count + 1))
    if isinstance(scope, bool):  # bool is an int subclass; reject it explicitly
        raise bridge.BridgeError('scope must be "all" or a 1-based scene index.')
    try:
        index = int(str(scope).strip())
    except (TypeError, ValueError):
        raise bridge.BridgeError('scope must be "all" or a 1-based scene index.')
    if not 1 <= index <= scene_count:
        raise bridge.BridgeError(f"scene index must be between 1 and {scene_count}.")
    return [index]


def _delete_cached_scene_images(job_dir: Path, scene_index: int) -> int:
    """Delete the cached concept + moment images for one scene so the next
    render is fresh. Returns the number of files removed. Pure-ish (only deletes
    inside the job's scene_images dir); never raises on a missing file."""
    images_dir = scene_images.cached_scene_image_path(job_dir, scene_index).parent
    removed = 0
    if not images_dir.is_dir():
        return 0
    for stale in images_dir.glob(f"scene_{scene_index:02d}*.png"):
        try:
            stale.unlink()
            removed += 1
        except OSError:
            pass
    return removed


# Per-job lock so two concurrent edit_scenes calls on the SAME job can't
# interleave their read-modify-write of scenes.json (and image regen).
_job_edit_locks: dict = {}
_job_edit_locks_guard = threading.Lock()


def _job_edit_lock(job_dir_rel: str) -> threading.Lock:
    with _job_edit_locks_guard:
        lock = _job_edit_locks.get(job_dir_rel)
        if lock is None:
            lock = threading.Lock()
            _job_edit_locks[job_dir_rel] = lock
        return lock


def edit_scenes(job_dir_rel: str, scope, instruction: str) -> dict:
    """Apply a plain-language edit to one scene's prompt (scope = a 1-based scene
    index) or every scene's prompt (scope = "all"), then regenerate the affected
    storyboard images.

    Exactly ONE Gemini text call (gemini-3.1-flash-lite, same client style as
    gemini_author) rewrites the affected prompt(s), preserving each scene's core
    structure. The rewrite is applied to scenes.json on disk (the SAME artifact
    that feeds the video stage), the affected human-readable summaries are
    refreshed, and the affected scenes' storyboard images are regenerated: the
    stale cached images for those scenes are deleted, then re-rendered with the
    admin-configured image model (settings.image_model), bounded by the
    MAX_STORYBOARD_IMAGES runaway guard.

    This NEVER triggers video generation and NEVER touches the video
    confirm-token gates. On ANY LLM failure it raises BridgeError and changes
    nothing (scenes.json, summaries, and cached images are only mutated AFTER a
    successful rewrite).

    Returns {"job_dir", "scope", "edited_indices", "model", "rendered",
    "reused", "scenes": [{"scene_index", "prompt", "summary", "method",
    "warning", "moments": [{"moment_index", "prompt", "path", "cached"}]}]}.
    """
    if not isinstance(instruction, str) or not instruction.strip():
        raise bridge.BridgeError("An edit instruction is required.")

    settings = bridge.load_settings()
    job = load_job(job_dir_rel)
    job_dir_rel = job["job_dir"]
    job_dir = bridge.safe_path(job["job_dir"])

    # One edit at a time per job: the read -> rewrite -> regenerate -> write
    # sequence below must be atomic so concurrent edits can't corrupt
    # scenes.json (the artifact that feeds the paid video stage).
    with _job_edit_lock(job_dir_rel):
        scenes_path = bridge.safe_path(job["scenes_path"])
        scenes_data = bridge.read_json_file(scenes_path, "Scenes")
        scenes = scenes_data.get("scenes") if isinstance(scenes_data, dict) else scenes_data
        if not isinstance(scenes, list) or not scenes:
            raise bridge.BridgeError("This job has no scenes to edit.")

        edited_indices = _resolve_edit_scope(scope, len(scenes))
        character_doc = characters.load_characters(job_dir_rel)
        full_cast = character_doc["characters"]
        resolved_characters = (
            characters.resolve_assignments(character_doc, len(scenes))
            if full_cast else {index: [] for index in range(1, len(scenes) + 1)}
        )

        # Runaway guard FIRST: refuse an oversized edit BEFORE any LLM call,
        # disk write, or paid render (one image per affected scene).
        if len(edited_indices) > video_tiers.MAX_STORYBOARD_IMAGES:
            raise bridge.BridgeError(
                f"Editing {len(edited_indices)} scenes would re-render more than the "
                f"safety cap of {video_tiers.MAX_STORYBOARD_IMAGES} images."
            )

        # The image model the user storyboard renders with (admin-configured).
        model = settings["image_model"]

        # Re-rendering is a paid image call per affected scene; require a usable
        # key up front so a missing key fails BEFORE any LLM call / disk write.
        try:
            api_key = scene_images.scene_image_api_key()
        except scene_images.SceneImageError as exc:
            raise bridge.BridgeError(str(exc))

        # The text-rewrite key: AI extraction must be on AND a key configured.
        # The rewrite is LLM-only (no deterministic fallback) - on any failure
        # we fail loud and change nothing.
        text_key = _gemini_key_for_text() if settings.get("ai_extraction") else None
        if not text_key:
            raise bridge.BridgeError(
                "Editing scene prompts needs a Gemini key with AI extraction enabled "
                "(Admin > Settings). Nothing was changed."
            )

        # --- ONE LLM call: rewrite ONLY the affected scenes, IN MEMORY. ----- #
        targeted = []
        for index in edited_indices:
            scene = dict(scenes[index - 1])
            scene["prompt"] = characters.strip_injected_blocks(scene["prompt"], full_cast)
            targeted.append(scene)
        try:
            rewritten = _rewrite_scene_prompts(targeted, instruction, text_key)
        except AuthorError as exc:
            raise bridge.BridgeError(f"Prompt rewrite failed - nothing was changed: {exc}")

        # Apply the rewrite in memory only (preserve every other field:
        # seed_image, mode, duration_seconds, etc.). Nothing is written to disk
        # yet - scenes.json (which feeds the video stage) stays the old,
        # consistent version until the regeneration below succeeds.
        for index, new in zip(edited_indices, rewritten):
            scene = scenes[index - 1]
            scene["prompt"] = new["prompt"]
            if new.get("negative_prompt"):
                scene["negative_prompt"] = new["negative_prompt"]
        if 1 in edited_indices:
            _normalize_scene1(scenes[0])

        # Refresh affected summaries in memory (the helper never raises).
        summaries = list(job.get("scene_summaries") or [])
        while len(summaries) < len(scenes):
            summaries.append("")
        for index in edited_indices:
            try:
                summary_result = storyboard_mod.human_readable_summary(
                    scenes[index - 1]["prompt"], text_key)
                summaries[index - 1] = summary_result["summary"]
            except storyboard_mod.StoryboardError:
                summaries[index - 1] = str(scenes[index - 1]["prompt"]).strip()[:240]

        # Regenerate the affected images BEFORE committing any on-disk source of
        # truth. If a render fails we raise here, leaving scenes.json and the
        # summaries untouched (and consistent) - the edit is all-or-nothing for
        # the artifacts that matter.
        scenes_out = []
        rendered = reused = 0
        for index in edited_indices:
            _delete_cached_scene_images(job_dir, index)
            prompt = str(scenes[index - 1]["prompt"]).strip()
            try:
                board = storyboard_mod.generate_storyboard(
                    job_dir, index, prompt, 1, api_key, model=model,
                )
            except storyboard_mod.StoryboardError as exc:
                raise bridge.BridgeError(str(exc))
            rendered += board["rendered"]
            reused += board["reused"]
            scenes_out.append({
                "scene_index": index,
                "prompt": prompt,
                "summary": summaries[index - 1],
                "method": board["method"],
                "warning": board.get("warning"),
                "moments": [
                    {
                        "moment_index": m["moment_index"],
                        "prompt": m["prompt"],
                        "path": bridge.rel_path(m["path"]),
                        "cached": m["cached"],
                    }
                    for m in board["moments"]
                ],
            })

        for index in edited_indices:
            scene = scenes[index - 1]
            scene["prompt"] = characters.inject_blocks(
                characters.strip_injected_blocks(scene["prompt"], full_cast),
                resolved_characters[index],
            )
        for scene_out, index in zip(scenes_out, edited_indices):
            scene_out["prompt"] = scenes[index - 1]["prompt"]

        # All rewrites + renders succeeded: commit scenes.json (feeds the video
        # stage) and the job summaries now, last.
        if isinstance(scenes_data, dict):
            scenes_data["scenes"] = scenes
            to_write = scenes_data
        else:
            to_write = {"scenes": scenes}
        scenes_path.write_text(
            json.dumps(to_write, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        job["scene_summaries"] = summaries
        _write_job(job)

        scope_out = "all" if (isinstance(scope, str) and scope.strip().lower() == "all") else edited_indices[0]
        bridge.audit("simple_edit_scenes", job_dir=job_dir_rel, scope=scope_out,
                     edited_indices=edited_indices, model=model,
                     rendered=rendered, reused=reused)
        return {
            "job_dir": job_dir_rel,
            "scope": scope_out,
            "edited_indices": edited_indices,
            "model": model,
            "rendered": rendered,
            "reused": reused,
            "scenes": scenes_out,
        }
