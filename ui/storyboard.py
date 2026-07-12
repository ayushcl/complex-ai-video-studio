"""Storyboard orchestration: one scene prompt -> N time-ordered MOMENT images.

Built on top of ui/scene_images.py (the single, deliberately-minimal paid image
primitive). What this module adds:

  * moment_prompts(scene_prompt, n, api_key) - split ONE scene prompt into N
    time-ordered "still frame" prompts via a single cheap Gemini text call
    (gemini-3.1-flash-lite), in the same stdlib-urllib client style as
    simple_flow.gemini_author / the brief call in generate_music.py. On ANY
    failure it falls back to N copies of the base prompt, so the storyboard
    still renders without an LLM (just with plainer moments).
  * generate_storyboard(...) - for each moment, generate ONE image through
    scene_images.generate_scene_image_cached, keyed per (job, scene, moment) so
    a concept image is rendered once and reused thereafter. Concurrency-safe via
    scene_images' per-target lock, so simultaneous requests never double-spend.
  * human_readable_summary(scene_prompt, api_key) - one cheap Gemini text call
    returning a short, friendly, NON-technical sentence or two describing the
    scene (fallback: a trimmed plain-text version of the prompt).

SPEND SAFETY: the per-moment images are generated through the same minimal,
one-image-per-call primitive scene_images already exposes, behind its cache and
per-target lock. The MOMENT COUNT is hard-capped (MAX_STORYBOARD_IMAGES) so a
bad N can never fan a scene out into runaway spend. The image MODEL is supplied
by the caller (the chosen IMAGE tier) - this module never hardcodes a paid tier;
it defaults to scene_images.DEFAULT_IMAGE_MODEL only when none is given.

Stdlib + (lazily, via scene_images) google-genai only. No new pip dependencies:
the text calls use urllib exactly like simple_flow.gemini_author; the image
calls reuse scene_images, which lazily imports google-genai.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

import scene_images

# The cheap text model used for the moment-split and the friendly summary. Same
# family simple_flow's authoring and generate_music.py's brief use.
GEMINI_TEXT_MODEL = "gemini-3.1-flash-lite"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_TIMEOUT_SECONDS = 60

# Internal engineering cap on images per storyboard render. This is NOT a user
# spend gate - it is the safety rail that keeps a bug (e.g. a wild N) from
# looping the paid image API. Prefer video_tiers.MAX_STORYBOARD_IMAGES when that
# module exists; otherwise this sane default. The FREE Basic image tier is
# ungated to the user by product decision, so this cap is what stops a runaway.
_DEFAULT_MAX_STORYBOARD_IMAGES = 40
try:  # pragma: no cover - import shape varies by environment
    from video_tiers import MAX_STORYBOARD_IMAGES  # type: ignore
except Exception:  # noqa: BLE001 - any import failure -> documented default
    MAX_STORYBOARD_IMAGES = _DEFAULT_MAX_STORYBOARD_IMAGES

# Human-summary length guard for the fallback (trimmed plain text).
_SUMMARY_FALLBACK_CHARS = 240


class StoryboardError(Exception):
    """Operator-facing storyboard failure. Safe to show in the UI; never
    contains key material."""


# --------------------------------------------------------------------------- #
# Moment-count clamping (engineering safety rail, not a user gate)             #
# --------------------------------------------------------------------------- #
def clamp_image_count(n) -> int:
    """Coerce the requested images-per-scene to a sane, capped integer.

    Refuses non-numbers and counts < 1 (raising StoryboardError - nothing is
    spent). Silently clamps anything above MAX_STORYBOARD_IMAGES down to the
    cap: that ceiling is the engineering safety rail (see module docstring), so
    even a buggy caller can never loop the paid image API."""
    if isinstance(n, bool) or not isinstance(n, int):
        # Tolerate a clean numeric string ("3") but reject junk / floats / bools.
        try:
            n = int(str(n).strip())
        except (TypeError, ValueError):
            raise StoryboardError("images_per_scene must be a whole number >= 1.")
    if n < 1:
        raise StoryboardError("images_per_scene must be at least 1.")
    return min(n, MAX_STORYBOARD_IMAGES)


# --------------------------------------------------------------------------- #
# Cheap Gemini text call (stdlib urllib; mirrors simple_flow.gemini_author)    #
# --------------------------------------------------------------------------- #
def _gemini_text(system_prompt: str, user_text: str, api_key: str,
                 *, json_mode: bool, temperature: float) -> str:
    """One Gemini generateContent text call over stdlib urllib (no new deps).
    Returns the concatenated text of the first candidate. Raises StoryboardError
    on any transport/decode failure so callers can fall back cleanly. The key is
    sent as the x-goog-api-key header and is NEVER placed in an error message."""
    if not api_key or not str(api_key).strip():
        raise StoryboardError("A Gemini API key is required for this text call.")
    generation_config = {"temperature": temperature}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": generation_config,
    }
    request = urllib.request.Request(
        GEMINI_URL.format(model=GEMINI_TEXT_MODEL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError, ValueError) as exc:
        # Never interpolate api_key; only the exception, which carries the URL
        # and status, not the header value.
        raise StoryboardError(f"Gemini text request failed: {exc}")
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts).strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise StoryboardError(f"Gemini returned an unusable response: {exc}")
    if not text:
        raise StoryboardError("Gemini returned an empty response.")
    return text


# --------------------------------------------------------------------------- #
# (1) Scene prompt -> N time-ordered MOMENT prompts                            #
# --------------------------------------------------------------------------- #
_MOMENT_SYSTEM_PROMPT = (
    "You are a storyboard artist. You are given ONE video scene description and "
    "a number N. Describe the scene as N still frames captured across its "
    "duration, moment by moment, in chronological order from the start of the "
    "scene to the end. Each frame is a vivid, self-contained image-generation "
    "prompt that keeps the same subject, setting, palette, lighting, and style "
    "as the scene, but advances the moment (camera, action, or time of day) so "
    "the N frames read as a clear time progression. Do not add readable text, "
    "captions, watermarks, or logos. Output ONLY a valid JSON object of the "
    'exact shape {"moments": ["frame 1 prompt", "frame 2 prompt", ...]} with '
    "EXACTLY N strings in chronological order, no prose and no code fences."
)


def _coerce_moment_list(raw: str, n: int) -> list:
    """Parse the model's JSON into exactly n non-empty moment strings, or raise.
    Tolerates either {"moments": [...]} or a bare JSON array."""
    data = json.loads(raw)
    moments = data.get("moments") if isinstance(data, dict) else data
    if not isinstance(moments, list):
        raise StoryboardError("Moment split response was not a list of moments.")
    cleaned = [str(m).strip() for m in moments if isinstance(m, (str, int, float)) and str(m).strip()]
    if not cleaned:
        raise StoryboardError("Moment split produced no usable moment prompts.")
    # Normalize length to exactly n: truncate extras, pad by repeating the last
    # usable moment so the count the caller asked for is always honoured.
    if len(cleaned) >= n:
        return cleaned[:n]
    while len(cleaned) < n:
        cleaned.append(cleaned[-1])
    return cleaned


def moment_prompts(scene_prompt: str, n: int, api_key: str | None) -> dict:
    """Split a single scene prompt into N time-ordered MOMENT prompts.

    Makes ONE cheap Gemini text call (gemini-3.1-flash-lite). On ANY failure -
    no/blank key, transport error, unusable JSON, or a missing google/network -
    falls back to N copies of the trimmed base prompt, so the storyboard still
    renders. N is clamped to [1, MAX_STORYBOARD_IMAGES] first (engineering
    safety rail, not a user gate).

    Returns {"moments": [str, ...], "method": "ai"|"fallback", "warning": str|None}.
    """
    if not isinstance(scene_prompt, str) or not scene_prompt.strip():
        raise StoryboardError("Scene prompt is empty; nothing to split into moments.")
    count = clamp_image_count(n)
    base = scene_prompt.strip()

    def _fallback(reason: str | None) -> dict:
        return {
            "moments": [base for _ in range(count)],
            "method": "fallback",
            "warning": reason,
        }

    if count == 1:
        # One moment is just the scene itself; no LLM call needed (no spend, no
        # failure surface) - the single frame is the base prompt.
        return {"moments": [base], "method": "single", "warning": None}
    if not api_key or not str(api_key).strip():
        return _fallback("No Gemini key configured; used the base prompt for every moment.")

    user_text = (
        f"N = {count}\n\nScene description:\n{base[:8000]}\n\n"
        f"Return exactly {count} still-frame prompts in chronological order."
    )
    try:
        raw = _gemini_text(
            _MOMENT_SYSTEM_PROMPT, user_text, str(api_key),
            json_mode=True, temperature=0.4,
        )
        moments = _coerce_moment_list(raw, count)
    except (StoryboardError, json.JSONDecodeError) as exc:
        return _fallback(f"Moment split unavailable ({exc}); used the base prompt for every moment.")
    return {"moments": moments, "method": "ai", "warning": None}


# --------------------------------------------------------------------------- #
# (2) Per-moment image generation (cached per job/scene/moment)                #
# --------------------------------------------------------------------------- #
def cached_moment_image_path(job_dir, scene_index: int, moment_index: int):
    """Deterministic on-disk path for one (scene, moment) frame, inside job_dir.
    Pure path logic - no I/O, no spend: the same job_dir + scene + moment always
    maps to the same file, so a frame is generated once and reused thereafter.
    Both indices are 1-based, matching scene_images' scene numbering."""
    for label, value in (("scene_index", scene_index), ("moment_index", moment_index)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise StoryboardError(f"{label} must be a positive integer (1-based).")
    parent = scene_images.cached_scene_image_path(job_dir, scene_index).parent
    return parent / f"scene_{scene_index:02d}_moment_{moment_index:02d}.png"


def generate_moment_image_cached(
    job_dir,
    scene_index: int,
    moment_index: int,
    prompt: str,
    api_key: str,
    model: str,
) -> dict:
    """Render (PAID) or reuse (FREE) ONE moment frame, keyed per (job, scene,
    moment). Delegates to scene_images.generate_scene_image under its existing
    per-target lock so concurrent requests for the SAME frame collapse to a
    single paid call. Returns {"path": Path, "cached": bool, "scene_index": int,
    "moment_index": int}."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise StoryboardError(f"Moment {moment_index} of scene {scene_index} has an empty prompt.")
    target = cached_moment_image_path(job_dir, scene_index, moment_index)

    # Fast path (no lock): a non-empty existing frame is reused with no spend.
    if target.is_file() and target.stat().st_size > 0:
        return {"path": target, "cached": True,
                "scene_index": scene_index, "moment_index": moment_index}

    # Reuse scene_images' per-target lock + paid primitive so the check-then-
    # generate is atomic and a frame is never double-spent under concurrency.
    lock = scene_images._lock_for(target)
    with lock:
        if target.is_file() and target.stat().st_size > 0:
            return {"path": target, "cached": True,
                    "scene_index": scene_index, "moment_index": moment_index}
        scene_images.generate_scene_image(prompt.strip(), target, api_key, model=model)
        return {"path": target, "cached": False,
                "scene_index": scene_index, "moment_index": moment_index}


def generate_storyboard(
    job_dir,
    scene_index: int,
    scene_prompt: str,
    images_per_scene: int,
    api_key: str,
    model: str = scene_images.DEFAULT_IMAGE_MODEL,
) -> dict:
    """Build a time-ordered storyboard for ONE scene: split the scene prompt
    into N moments (one cheap Gemini text call, with a base-prompt fallback),
    then generate/cache one image per moment via scene_images.

    PAID per never-before-rendered moment frame (one image, no batching, behind
    the cache + per-target lock); FREE on every later request for a frame that
    already exists. N is clamped to [1, MAX_STORYBOARD_IMAGES] - the engineering
    safety rail that bounds spend even on the ungated free image tier. The image
    MODEL is the caller's chosen IMAGE tier (never hardcoded to a paid tier).

    Returns {"scene_index", "model", "method", "warning", "moments": [
    {"moment_index", "prompt", "path": Path, "cached": bool}, ...],
    "rendered": int, "reused": int}. Raises StoryboardError on bad input or a
    failed paid render (so the caller fails loud rather than showing a gap)."""
    if not api_key or not str(api_key).strip():
        # Guard, but never surface the (absent) value.
        raise StoryboardError("A Gemini API key is required to generate storyboard images.")

    # Clamp the count HERE too, not only inside moment_prompts: this is the
    # orchestration boundary that actually issues paid image calls, so the
    # runaway-spend safety rail must hold regardless of how the moments are
    # produced (a custom/mocked splitter must not be able to fan out past cap).
    count = clamp_image_count(images_per_scene)
    split = moment_prompts(scene_prompt, count, api_key)
    # Belt and braces: never render more frames than the cap even if a splitter
    # returns extras.
    moments = split["moments"][:count]
    moments_out = []
    rendered = reused = 0
    try:
        for offset, prompt in enumerate(moments, start=1):
            result = generate_moment_image_cached(
                job_dir, scene_index, offset, prompt, api_key, model=model,
            )
            if result["cached"]:
                reused += 1
            else:
                rendered += 1
            moments_out.append({
                "moment_index": offset,
                "prompt": prompt,
                "path": result["path"],
                "cached": result["cached"],
            })
    except scene_images.SceneImageError as exc:
        # Surface the paid-layer failure as a storyboard failure; never leak keys
        # (scene_images already keeps key material out of its messages).
        raise StoryboardError(str(exc))

    return {
        "scene_index": scene_index,
        "model": model,
        "method": split["method"],
        "warning": split.get("warning"),
        "moments": moments_out,
        "rendered": rendered,
        "reused": reused,
    }


# --------------------------------------------------------------------------- #
# (3) Friendly, non-technical scene summary                                    #
# --------------------------------------------------------------------------- #
_SUMMARY_SYSTEM_PROMPT = (
    "You explain a video scene to a non-technical client in one or two short, "
    "friendly, plain-English sentences. Describe what they would SEE and the "
    "feeling of it. Do NOT use jargon, camera or lens terminology, generation "
    "settings, negative-prompt language, or lists. Output only the sentence(s), "
    "no labels, no quotes, no markdown."
)


def _summary_fallback(scene_prompt: str) -> str:
    """A trimmed, plain-text version of the prompt: collapse whitespace, drop a
    leading 'Scene N:' marker, and cut to a sentence-ish length. Pure, no spend."""
    text = re.sub(r"\s+", " ", str(scene_prompt or "")).strip()
    text = re.sub(r"^(?:scene|shot)\s*[#:\-]?\s*\d+\s*[:\-.]?\s*", "", text, flags=re.IGNORECASE).strip()
    if len(text) <= _SUMMARY_FALLBACK_CHARS:
        return text
    clipped = text[:_SUMMARY_FALLBACK_CHARS].rsplit(" ", 1)[0].rstrip(",;:- ")
    return f"{clipped}..."


def human_readable_summary(scene_prompt: str, api_key: str | None) -> dict:
    """Return a short, friendly, NON-technical summary of a scene.

    Makes ONE cheap Gemini text call (gemini-3.1-flash-lite). On ANY failure -
    no/blank key, transport error, empty/unusable response - falls back to a
    trimmed plain-text version of the prompt. Returns {"summary": str,
    "method": "ai"|"fallback", "warning": str|None}."""
    if not isinstance(scene_prompt, str) or not scene_prompt.strip():
        raise StoryboardError("Scene prompt is empty; nothing to summarize.")
    base = scene_prompt.strip()

    if not api_key or not str(api_key).strip():
        return {"summary": _summary_fallback(base), "method": "fallback",
                "warning": "No Gemini key configured; summarized the prompt locally."}
    try:
        summary = _gemini_text(
            _SUMMARY_SYSTEM_PROMPT,
            f"Scene:\n{base[:8000]}",
            str(api_key),
            json_mode=False,
            temperature=0.3,
        )
    except StoryboardError as exc:
        return {"summary": _summary_fallback(base), "method": "fallback",
                "warning": f"Friendly summary unavailable ({exc}); summarized the prompt locally."}
    # The model may wrap a stray quote/newline; tidy without altering wording.
    summary = re.sub(r"\s+", " ", summary).strip().strip('"').strip()
    if not summary:
        return {"summary": _summary_fallback(base), "method": "fallback",
                "warning": "Friendly summary was empty; summarized the prompt locally."}
    return {"summary": summary, "method": "ai", "warning": None}
