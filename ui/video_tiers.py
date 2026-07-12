"""Phase-A render tiers: pure data + lookups for the operator UI.

This module is the single source of truth for the operator-facing render
tiers - the three VIDEO final-render tiers and the three IMAGE storyboard
tiers - mapping each friendly tier key onto the concrete model, resolution,
and per-unit rate it bills at. The orchestrator wires these into the UI and
the spend gates later; this file itself is pure:

  * Pure: no network, no disk, no environment reads, no imports of the rest of
    the UI. It is just constant data and dictionary lookups.
  * Authoritative pricing: unlike cost_estimator.DEFAULT_PRICING (which carries
    obvious PLACEHOLDER stand-ins for the human sanity-check estimate), the
    rates here are the REAL Gemini Developer API prices from the official
    pricing page dated 2026-06-09 (USD). They map a tier to what it actually
    bills so a credit mapping can be layered on later.

Spend-safety note (data only - the gates live elsewhere):
  * Video tiers are ALWAYS gated by the existing confirm-token + spend gates;
    there is no ungated video path.
  * Image tiers carry an explicit ``gated`` flag. The FREE Basic (Imagen) tier
    is intentionally UNGATED per product decision (the business absorbs its
    cost); the PAID Standard/Premium image tiers are GATED by the same
    cost-confirm + token mechanism as video. ``gated`` here is the declarative
    contract the wiring layer reads - this module does not itself enforce it.
  * MAX_STORYBOARD_IMAGES is an engineering runaway guard (a sane internal cap
    on images per storyboard/job) so a bug in the ungated Basic path cannot
    loop into surprise spend. It is NOT a user-facing gate.

Per the Gemini Developer API pricing page (2026-06-09, USD):
  Veo per SECOND of output (audio included):
    veo-3.1-fast-generate-preview @ 1080p = 0.12
    veo-3.1-generate-preview      @ 1080p = 0.40
    veo-3.1-generate-preview      @ 4k    = 0.60
  Image per IMAGE:
    imagen-4.0-fast-generate-001 (flat) = 0.02
    gemini-3.1-flash-image   @ 1024px = 0.067
    gemini-3-pro-image       @ 1024px = 0.134
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Runaway guard for the FREE (ungated) Basic image tier.                       #
# --------------------------------------------------------------------------- #
# Engineering safety, NOT a user gate: the Basic (Imagen) image tier is
# intentionally ungated per product decision, so this caps how many images a
# single storyboard/job may generate. It exists so a bug cannot loop the free
# path into runaway spend - it is not a deliberate operator-facing limit.
MAX_STORYBOARD_IMAGES = 40


# --------------------------------------------------------------------------- #
# Video final-render tiers (ordered: cheapest -> most expensive).             #
# Each maps to model + resolution + the REAL per-second rate it bills at.     #
# Designed so a credit mapping can be layered on later.                       #
# --------------------------------------------------------------------------- #
VIDEO_TIERS = [
    {
        "key": "standard",
        "label": "Standard",
        "model": "veo-3.1-fast-generate-preview",
        "resolution": "1080p",
        "per_second_rate": 0.12,
        # Standard is the fast model and is the only video tier that supports
        # the Veo extension chain (scene 1 + extensions).
        "supports_extension": True,
    },
    {
        "key": "quality",
        "label": "Quality",
        "model": "veo-3.1-generate-preview",
        "resolution": "1080p",
        "per_second_rate": 0.40,
        "supports_extension": True,
    },
    {
        "key": "ultra4k",
        "label": "Ultra 4K",
        "model": "veo-3.1-generate-preview",
        "resolution": "4k",
        "per_second_rate": 0.60,
        "supports_extension": True,
    },
]


# --------------------------------------------------------------------------- #
# Image storyboard tiers (ordered: free -> most expensive).                   #
# Several images per scene (a time-progression storyboard). Each maps to a    #
# model + resolution + REAL per-image rate, plus the gated contract.          #
# --------------------------------------------------------------------------- #
IMAGE_TIERS = [
    {
        "key": "basic",
        "label": "Basic",
        # gemini-2.5-flash-image ("Nano Banana"): cheap AND faithful. Imagen 4
        # Fast was cheaper ($0.02) but adhered poorly to scene prompts (produced
        # unrelated images), which defeats the free-storyboard hook; this model
        # renders the actual scene reliably for $0.039 and supports 16:9.
        "model": "gemini-2.5-flash-image",
        "resolution": "1024px",
        "per_image_rate": 0.039,
        # FREE TO THE USER: ungated per product decision (business absorbs the
        # cost). The runaway guard (MAX_STORYBOARD_IMAGES) still applies.
        "gated": False,
        "free_to_user": True,
    },
    {
        "key": "standard",
        "label": "Standard",
        "model": "gemini-3.1-flash-image",
        "resolution": "1024px",
        "per_image_rate": 0.067,
        # PAID: gated by the cost-confirm + token mechanism.
        "gated": True,
        "free_to_user": False,
    },
    {
        "key": "premium",
        "label": "Premium",
        "model": "gemini-3-pro-image",
        "resolution": "1024px",
        "per_image_rate": 0.134,
        "gated": True,
        "free_to_user": False,
    },
]


# --------------------------------------------------------------------------- #
# Lookups (raise on an unknown key - callers must handle a bad tier loudly,   #
# never silently fall back to a different price).                             #
# --------------------------------------------------------------------------- #
class UnknownTierError(KeyError):
    """Raised when a tier key does not match any defined tier. Subclasses
    KeyError so existing ``except KeyError`` handlers still catch it, while the
    distinct type lets callers single it out."""


def _resolve(tiers: list, key, kind: str) -> dict:
    """Return the tier dict whose 'key' matches `key`. Raise UnknownTierError
    (listing the valid keys) on no match. Returns the stored dict by reference;
    callers must not mutate it - this is read-only reference data."""
    for tier in tiers:
        if tier["key"] == key:
            return tier
    valid = ", ".join(repr(t["key"]) for t in tiers)
    raise UnknownTierError(f"Unknown {kind} tier {key!r}. Valid keys: {valid}.")


def resolve_video_tier(key) -> dict:
    """Look up a VIDEO render tier by key (e.g. 'standard', 'quality',
    'ultra4k'). Raises UnknownTierError on an unknown key."""
    return _resolve(VIDEO_TIERS, key, "video")


def resolve_image_tier(key) -> dict:
    """Look up an IMAGE storyboard tier by key (e.g. 'basic', 'standard',
    'premium'). Raises UnknownTierError on an unknown key."""
    return _resolve(IMAGE_TIERS, key, "image")


def video_tier_keys() -> list:
    """Ordered list of valid video tier keys (cheapest first)."""
    return [tier["key"] for tier in VIDEO_TIERS]


def image_tier_keys() -> list:
    """Ordered list of valid image tier keys (free first)."""
    return [tier["key"] for tier in IMAGE_TIERS]
