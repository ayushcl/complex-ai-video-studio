"""Pure, self-contained cost estimator for a VEO ad-pipeline generation.

This module computes a rough, operator-facing spend ESTIMATE for a job before
anything is generated. It is intentionally:

  * Pure: no network, no disk, no environment reads, no imports of the rest of
    the UI. Everything it needs comes in through its arguments.
  * Approximate: it does NOT replace the real spend gates. Nothing here can
    trigger, authorize, or influence a paid run - it only labels a number a
    human can sanity-check. Every result is marked approximate and carries the
    list of assumptions that produced it.

PRICING IS REAL. The DEFAULT_PRICING rates below are the REAL Gemini Developer
API prices from the official pricing page dated 2026-06-09 (USD). They are the
same authoritative numbers carried in video_tiers.py (which maps a tier ->
model/resolution/rate); this module keeps its own copy so it stays a pure,
dependency-free estimator. An operator may still override any rate in Admin
Settings; an operator-supplied override is labelled as such in the estimate.

Veo is billed PER SECOND OF OUTPUT and the rate depends on BOTH the model AND
the resolution - a flat per-tier number would be wrong (4k standard is 6x lite
720p). So ``veo_per_second`` is keyed model -> resolution -> rate.

Image generation is billed PER IMAGE and the rate depends on the model (and,
for the multi-resolution models, the resolution). The FREE "Basic" image tier
(Imagen 4 Fast) still has a REAL business cost of 0.02/img even though it is
free to the USER - the estimate labels that distinction (``billed_to`` is
"business" for the free tier, "user" for the gated paid tiers).

Duration model mirrors the rest of the UI (see engine_bridge.inspect_scenes and
docparse.heuristic_author): scene 1 is generated from a seed image and runs
about its own duration_seconds (default 6s); each later scene EXTENDS the prior
shot by about 7s. So a job that generates N scenes is roughly
``seed_seconds + 7 * (N - 1)`` seconds of video.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Duration constants (match engine_bridge.inspect_scenes / docparse)           #
# --------------------------------------------------------------------------- #
DEFAULT_SEED_SECONDS = 6      # scene 1 default length when not specified
EXTENSION_SECONDS = 7         # each scene after the first extends ~7s
DEFAULT_CURRENCY = "USD"

# Presenter reference (Veo asset-reference likeness) FORCES a fixed scene-1
# seed: veo-3.1-fast-generate-preview @ 720p for 8s, regardless of the tier the
# operator picked or the scenes file's own duration. Mirrors
# run_veo_extension_chain.PRESENTER_REFERENCE_* (kept here so this estimator
# stays pure and dependency-free, exactly as it keeps its own copy of pricing).
# A job carrying a truthy ``presenter_reference_image_path`` is costed at these
# forced values so the estimate matches what reference mode actually bills.
PRESENTER_REFERENCE_MODEL = "veo-3.1-fast-generate-preview"
PRESENTER_REFERENCE_RESOLUTION = "720p"
PRESENTER_REFERENCE_SEED_SECONDS = 8


# --------------------------------------------------------------------------- #
# REAL pricing (Gemini Developer API, official page dated 2026-06-09, USD).    #
# An operator may still override any of these in Admin Settings.               #
# --------------------------------------------------------------------------- #
# Veo per SECOND of output (audio included), keyed model -> resolution -> rate.
DEFAULT_VEO_PER_SECOND = {
    "veo-3.1-generate-preview": {"720p": 0.40, "1080p": 0.40, "4k": 0.60},
    "veo-3.1-fast-generate-preview": {"720p": 0.10, "1080p": 0.12, "4k": 0.30},
    "veo-3.1-lite-generate-preview": {"720p": 0.05, "1080p": 0.08},  # no 4k
}

# Lyria music per SONG (flat, not per second).
DEFAULT_MUSIC_PER_SONG = {
    "lyria-3-pro-preview": 0.08,
    "lyria-3-clip-preview": 0.04,
}

# Image per IMAGE, keyed model -> resolution -> rate. Imagen bills a flat rate
# (use the "flat" pseudo-resolution key).
DEFAULT_IMAGE_PER_IMAGE = {
    "gemini-2.5-flash-image": {"512px": 0.039, "1024px": 0.039},  # Basic tier (faithful, cheap)
    "imagen-4.0-fast-generate-001": {"flat": 0.02},
    "gemini-3.1-flash-image": {"512px": 0.045, "1024px": 0.067, "2048px": 0.101, "4096px": 0.151},
    "gemini-3-pro-image": {"1024px": 0.134, "2048px": 0.134, "4096px": 0.24},
}

# Default model/resolution behind each VIDEO quality tier the simple flow uses
# (draft = the cheap/fast tier, hq = the high-quality tier). These let
# estimate_cost(job, quality, pricing) resolve a resolution-aware Veo rate when
# the caller does not pass an explicit model/resolution on the job. They mirror
# engine_bridge.DEFAULT_SETTINGS and video_tiers.VIDEO_TIERS.
DEFAULT_TIER_MODELS = {
    "draft": {"model": "veo-3.1-fast-generate-preview", "resolution": "720p"},
    "hq": {"model": "veo-3.1-generate-preview", "resolution": "1080p"},
}

# Default music model the silent-brand simple flow bills (one flat song).
DEFAULT_MUSIC_MODEL = "lyria-3-pro-preview"

# Default seed/placeholder-image model + resolution. A generated placeholder
# seed image counts as one image-preview generation at this rate.
DEFAULT_IMAGE_PREVIEW_MODEL = "imagen-4.0-fast-generate-001"
DEFAULT_IMAGE_PREVIEW_RESOLUTION = "flat"


DEFAULT_PRICING = {
    # Veo per-SECOND rate, keyed model -> resolution. Resolution-aware on
    # purpose: a flat per-tier rate is wrong (4k is 6x lite 720p).
    "veo_per_second": DEFAULT_VEO_PER_SECOND,
    # Map each simple-mode quality tier to the model+resolution it bills at, so
    # estimate_cost can resolve a resolution-aware rate from a "draft"/"hq" tier.
    "tier_models": DEFAULT_TIER_MODELS,
    # Lyria music per SONG (flat), keyed by model.
    "music_per_song": DEFAULT_MUSIC_PER_SONG,
    "music_model": DEFAULT_MUSIC_MODEL,
    # Image per IMAGE, keyed model -> resolution.
    "image_per_image": DEFAULT_IMAGE_PER_IMAGE,
    # Which model+resolution a generated placeholder seed image is billed at.
    "image_preview_model": DEFAULT_IMAGE_PREVIEW_MODEL,
    "image_preview_resolution": DEFAULT_IMAGE_PREVIEW_RESOLUTION,
    "currency": DEFAULT_CURRENCY,
}


# --------------------------------------------------------------------------- #
# Internal helpers (pure)                                                      #
# --------------------------------------------------------------------------- #
def _coerce_int(value, default):
    """Best-effort int coercion that tolerates None / "6" / "6s"; falls back to
    the default for anything unusable. Pure and exception-free."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(str(value).strip().rstrip("s"))
        except (TypeError, ValueError):
            return default


def _coerce_float(value, default):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _scenes_to_generate(job):
    """How many scenes a live run would actually pay for, honouring the spend
    cap. Reads the same fields the rest of the UI uses on a simple-mode job /
    packet, without ever touching disk."""
    if not isinstance(job, dict):
        return 1, []
    notes = []
    scene_count = job.get("scene_count")
    if scene_count is None:
        scene_count = job.get("scenes_total")
    scene_count = _coerce_int(scene_count, None)
    max_scenes = _coerce_int(job.get("max_scenes"), None)

    if scene_count is None and max_scenes is None:
        notes.append(
            "Job carried no scene_count or max_scenes; assumed 1 scene generated."
        )
        return 1, notes
    if scene_count is None:
        notes.append(
            f"Job carried no scene_count; used the spend cap (max_scenes={max_scenes}) as the scene count."
        )
        return max(1, max_scenes), notes
    if max_scenes is None:
        notes.append(
            f"Job carried no spend cap (max_scenes); assumed all {scene_count} scene(s) would be generated."
        )
        return max(1, scene_count), notes

    effective = min(scene_count, max_scenes)
    if max_scenes < scene_count:
        notes.append(
            f"Spend cap limits generation to {effective} of {scene_count} scene(s)."
        )
    return max(1, effective), notes


def _seed_seconds(job):
    """Length of scene 1. Presenter reference mode forces 8s; otherwise reads
    the first scene's duration if the job carries inline scenes, falling back to
    the documented default (6s)."""
    if isinstance(job, dict):
        if job.get("presenter_reference_image_path"):
            # Reference mode forces an 8s scene-1 seed regardless of the scenes
            # file (see run_veo_extension_chain.PRESENTER_REFERENCE_DURATION_SECONDS),
            # so cost it at 8s rather than the 6s default.
            return PRESENTER_REFERENCE_SEED_SECONDS
        scenes = job.get("scenes")
        if isinstance(scenes, list) and scenes and isinstance(scenes[0], dict):
            first = scenes[0]
            raw = first.get("duration_seconds", first.get("duration"))
            return max(1, _coerce_int(raw, DEFAULT_SEED_SECONDS))
        raw = job.get("seed_duration_seconds")
        if raw is not None:
            return max(1, _coerce_int(raw, DEFAULT_SEED_SECONDS))
    return DEFAULT_SEED_SECONDS


def _resolve_tier_model(job, quality, pricing, assumptions):
    """Resolve the (model, resolution) a "draft"/"hq" generation bills at.

    Order of precedence: an explicit model/resolution on the job (wins), then
    the pricing's tier_models map for this quality, then DEFAULT_TIER_MODELS.
    Returns (model_or_None, resolution_or_None); a None model means the caller
    must fall back to a tier-keyed/zero rate (and the assumption list says so)."""
    if isinstance(job, dict) and job.get("presenter_reference_image_path"):
        # Reference-image presenter mode forces a fixed model + resolution; it
        # overrides any operator tier pick or explicit job model/resolution.
        assumptions.append(
            "Presenter reference image set: video billed at the forced "
            f"{PRESENTER_REFERENCE_MODEL} @ {PRESENTER_REFERENCE_RESOLUTION} "
            "(reference mode overrides the selected tier/model/resolution)."
        )
        return PRESENTER_REFERENCE_MODEL, PRESENTER_REFERENCE_RESOLUTION
    if isinstance(job, dict) and job.get("model"):
        model = str(job.get("model"))
        resolution = str(job.get("resolution") or "").strip() or None
        return model, resolution
    tier_models = pricing.get("tier_models")
    if not isinstance(tier_models, dict):
        tier_models = {}
    entry = tier_models.get(quality)
    if not isinstance(entry, dict):
        entry = DEFAULT_TIER_MODELS.get(quality)
        if isinstance(entry, dict):
            assumptions.append(
                f"Quality tier {quality!r} not mapped to a model in pricing; "
                "used the documented default model/resolution for it."
            )
    if isinstance(entry, dict) and entry.get("model"):
        return str(entry["model"]), str(entry.get("resolution") or "").strip() or None
    return None, None


def _veo_rate(model, resolution, pricing, assumptions):
    """Look up the per-second Veo rate for model+resolution. Falls back across
    resolutions for the same model, then to 0.0, recording assumptions."""
    table = pricing.get("veo_per_second")
    if not isinstance(table, dict):
        table = {}
    model_rates = table.get(model) if model else None
    if not isinstance(model_rates, dict) or not model_rates:
        assumptions.append(
            f"No per-second Veo rate found for model {model!r}; treated video as 0 "
            "(set the rate in Admin Settings)."
        )
        return 0.0
    if resolution and resolution in model_rates:
        return _coerce_float(model_rates[resolution], 0.0)
    # Resolution missing/unknown for this model: use any one rate as a stand-in.
    fallback_res, fallback_rate = next(iter(model_rates.items()))
    assumptions.append(
        f"Resolution {resolution!r} not priced for model {model!r}; used the "
        f"{fallback_res!r} rate as a stand-in."
    )
    return _coerce_float(fallback_rate, 0.0)


def _music_rate(pricing, assumptions, currency):
    """The flat per-song Lyria rate for the configured music model."""
    model = pricing.get("music_model") or DEFAULT_MUSIC_MODEL
    table = pricing.get("music_per_song")
    if not isinstance(table, dict):
        table = {}
    if model in table:
        rate = _coerce_float(table[model], 0.0)
    else:
        rate = 0.0
        assumptions.append(
            f"No per-song music rate found for model {model!r}; treated music as 0."
        )
    return rate, model


def image_rate(pricing, model, resolution, assumptions=None):
    """Resolve the per-image rate for an image model+resolution from a pricing
    dict. Falls back across resolutions for the same model, then to 0.0. Pure;
    appends to `assumptions` only when given a list."""
    table = pricing.get("image_per_image") if isinstance(pricing, dict) else None
    if not isinstance(table, dict):
        table = {}
    model_rates = table.get(model) if model else None
    if not isinstance(model_rates, dict) or not model_rates:
        if isinstance(assumptions, list):
            assumptions.append(
                f"No per-image rate found for model {model!r}; treated images as 0 "
                "(set the rate in Admin Settings)."
            )
        return 0.0
    if resolution and resolution in model_rates:
        return _coerce_float(model_rates[resolution], 0.0)
    fallback_res, fallback_rate = next(iter(model_rates.items()))
    if resolution and isinstance(assumptions, list):
        assumptions.append(
            f"Resolution {resolution!r} not priced for image model {model!r}; "
            f"used the {fallback_res!r} rate as a stand-in."
        )
    return _coerce_float(fallback_rate, 0.0)


def _is_default_pricing(pricing) -> bool:
    """Whether the supplied pricing is (identical to) the real DEFAULT_PRICING -
    used only to label the estimate, never to gate."""
    return pricing is DEFAULT_PRICING


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def estimate_cost(job, quality, pricing=None):
    """Estimate the spend for one VIDEO generation, as a per-stage breakdown.

    Arguments
    ---------
    job : dict
        A simple-mode job / packet-shaped dict. Read (never mutated) for:
          * ``scene_count`` (or ``scenes_total``) - scenes available,
          * ``max_scenes`` - the spend cap,
          * ``scenes`` (optional) - inline scenes; scene 1's
            ``duration_seconds`` sets the seed length,
          * ``model`` / ``resolution`` (optional) - the exact Veo model +
            resolution this generation bills at; when present they win over the
            quality-tier mapping (so the estimate is resolution-aware),
          * ``seed_is_placeholder`` (optional) - whether scene 1's seed image
            is an auto-generated placeholder (counts as an image preview).
    quality : str
        ``"draft"`` or ``"hq"``; selects the model/resolution (and thus the
        per-second Veo rate) via the pricing's ``tier_models`` map when the job
        does not carry an explicit model/resolution.
    pricing : dict, optional
        Overrides DEFAULT_PRICING (the operator's Admin-Settings rates). Falls
        back to the REAL defaults, and the result labels which was used.

    Returns
    -------
    dict with keys: ``video``, ``music``, ``image``, ``total`` (floats),
    ``currency``, ``approximate`` (always True), ``assumptions`` (list of str),
    plus ``breakdown`` detail. This is an ESTIMATE only - it never spends and
    never gates a run.
    """
    pricing = pricing if isinstance(pricing, dict) else DEFAULT_PRICING
    assumptions = []

    using_defaults = _is_default_pricing(pricing)
    assumptions.append(
        "Rates are the REAL Gemini Developer API prices (2026-06-09); verify "
        "they are current before relying on the estimate."
        if using_defaults
        else "Using operator-supplied rates from Admin Settings (verify they are current)."
    )

    currency = pricing.get("currency") or DEFAULT_CURRENCY

    # --- Veo video (resolution-aware) --------------------------------------- #
    model, resolution = _resolve_tier_model(job, quality, pricing, assumptions)
    veo_rate = _veo_rate(model, resolution, pricing, assumptions)

    scenes_to_generate, scene_notes = _scenes_to_generate(job)
    assumptions.extend(scene_notes)

    seed_seconds = _seed_seconds(job)
    # scene 1 ~ its own duration; each later scene extends ~7s.
    seconds_total = seed_seconds + EXTENSION_SECONDS * max(0, scenes_to_generate - 1)
    assumptions.append(
        f"Video length approximated as scene 1 (~{seed_seconds}s) + "
        f"{max(0, scenes_to_generate - 1)} extension(s) x ~{EXTENSION_SECONDS}s "
        f"= ~{seconds_total}s across {scenes_to_generate} scene(s)."
    )
    seconds_per_scene = (seconds_total / scenes_to_generate) if scenes_to_generate else 0.0
    video_cost = scenes_to_generate * seconds_per_scene * veo_rate
    # (scenes * (total/scenes) * rate) == total_seconds * rate; expressed this
    # way to match the documented scenes_to_generate * seconds_per_scene formula.

    # --- Lyria music (flat per song) ---------------------------------------- #
    music_rate, music_model = _music_rate(pricing, assumptions, currency)
    music_cost = music_rate
    assumptions.append(
        f"Music is one flat Lyria song per video ({music_model}, ~{music_rate} {currency})."
    )

    # --- Image / seed preview (optional) ------------------------------------ #
    preview_model = pricing.get("image_preview_model") or DEFAULT_IMAGE_PREVIEW_MODEL
    preview_resolution = pricing.get("image_preview_resolution") or DEFAULT_IMAGE_PREVIEW_RESOLUTION
    image_preview_rate = image_rate(pricing, preview_model, preview_resolution, assumptions)
    image_count = 0
    if isinstance(job, dict) and job.get("seed_is_placeholder"):
        # A generated placeholder seed counts as one image-preview generation.
        image_count = 1
        assumptions.append(
            f"Scene 1 uses a generated placeholder seed image, counted as one "
            f"image preview ({preview_model}, ~{image_preview_rate} {currency})."
        )
    image_cost = image_count * image_preview_rate

    total = video_cost + music_cost + image_cost

    return {
        "video": round(video_cost, 4),
        "music": round(music_cost, 4),
        "image": round(image_cost, 4),
        "total": round(total, 4),
        "currency": currency,
        "approximate": True,
        "assumptions": assumptions,
        "breakdown": {
            "quality": quality,
            "veo_model": model,
            "veo_resolution": resolution,
            "veo_rate_per_second": veo_rate,
            "scenes_to_generate": scenes_to_generate,
            "seed_seconds": seed_seconds,
            "seconds_per_scene": round(seconds_per_scene, 4),
            "seconds_total": seconds_total,
            "music_model": music_model,
            "music_flat_rate": music_rate,
            "image_preview_model": preview_model,
            "image_preview_rate": image_preview_rate,
            "image_count": image_count,
            "using_default_pricing": using_defaults,
        },
    }


def estimate_storyboard_cost(images_count, image_model, image_resolution=None,
                             pricing=None, free_to_user=False):
    """Estimate the spend for a storyboard image generation.

    Storyboard cost = ``images_count * per_image_rate`` for the given image
    model+resolution. This is a separate estimate from estimate_cost (video);
    nothing here spends or gates.

    free_to_user distinguishes the FREE "Basic" tier from the paid tiers: the
    Basic tier (Imagen 4 Fast) still has a REAL business cost per image, so the
    estimate reports both the cost and WHO it is billed to (``billed_to`` is
    "business" when free_to_user, "user" otherwise).

    Returns a dict: ``images_count``, ``per_image_rate``, ``image_model``,
    ``image_resolution``, ``total`` (float), ``billed_to`` (str), ``free_to_user``
    (bool), ``currency``, ``approximate`` (True), ``assumptions`` (list).
    """
    pricing = pricing if isinstance(pricing, dict) else DEFAULT_PRICING
    assumptions = []
    using_defaults = _is_default_pricing(pricing)
    assumptions.append(
        "Rates are the REAL Gemini Developer API prices (2026-06-09); verify "
        "they are current before relying on the estimate."
        if using_defaults
        else "Using operator-supplied rates from Admin Settings (verify they are current)."
    )
    currency = pricing.get("currency") or DEFAULT_CURRENCY

    count = max(0, _coerce_int(images_count, 0))
    per_image = image_rate(pricing, image_model, image_resolution, assumptions)
    total = count * per_image
    billed_to = "business" if free_to_user else "user"
    if free_to_user:
        assumptions.append(
            f"This image tier is FREE TO THE USER; the {currency} {per_image}/image "
            "is a business cost the company absorbs (not billed to the operator)."
        )
    assumptions.append(
        f"Storyboard cost = {count} image(s) x {per_image} {currency}/image "
        f"({image_model}{(' @ ' + image_resolution) if image_resolution else ''})."
    )

    return {
        "images_count": count,
        "per_image_rate": per_image,
        "image_model": image_model,
        "image_resolution": image_resolution,
        "total": round(total, 4),
        "billed_to": billed_to,
        "free_to_user": bool(free_to_user),
        "currency": currency,
        "approximate": True,
        "assumptions": assumptions,
    }
