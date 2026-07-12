"""Negative-prompt fragment library (F5).

Stdlib-only. Does NOT import docparse (docparse imports THIS module) and does
NOT import engine_bridge, so it stays zero-dependency and safe to import from
the parser. Every public function falls back to a built-in literal if the JSON
data file is missing or corrupt, so authoring never breaks.
"""

import json
from pathlib import Path

__all__ = [
    "NegativeLibraryError",
    "DEFAULT_GROUPS",
    "load_library",
    "compose_negative",
    "positive_reframe",
]


class NegativeLibraryError(Exception):
    """Raised for invalid programmatic use of the library API."""


# Byte-identical fallback: the historical docparse._DEFAULT_NEGATIVE split into
# its 10 comma-separated fragments. compose_negative(DEFAULT_GROUPS) MUST equal
# the original literal so day-one behaviour is unchanged.
_FALLBACK_BASE = [
    "readable text",
    "captions",
    "subtitles",
    "watermarks",
    "logos",
    "brand marks",
    "identifiable faces",
    "distortion",
    "low quality",
    "camera shake",
]

# Positive clause folded into scene 1's prompt in place of a negative_prompt.
# Positively phrased ON PURPOSE: scene 1's reference path drops negative_prompt,
# and negation inside a positive prompt is unreliable, so this describes what we
# WANT, not what to avoid. packet_04-clean: no anatomy/age-adjacent/NSFW/
# security terms, no model names, no negation phrasing.
_FALLBACK_POSITIVE = (
    "clean, well-composed frame with a single clear subject, "
    "sharp focus, steady camera, polished commercial framing, "
    "and uncluttered visual presentation"
)

DEFAULT_GROUPS = ("base",)

_JSON_PATH = Path(__file__).with_name("negative_library.json")
_CACHE = None


def load_library():
    """Return {'groups': {...}, 'positive_reframe': str}. Cached, lenient."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    lib = {
        "groups": {"base": list(_FALLBACK_BASE)},
        "positive_reframe": _FALLBACK_POSITIVE,
    }
    try:
        with open(_JSON_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        groups = data.get("groups")
        if isinstance(groups, dict):
            clean = {}
            for name, frags in groups.items():
                if isinstance(frags, list):
                    clean[name] = [str(f).strip() for f in frags if str(f).strip()]
            if clean.get("base"):
                lib["groups"] = clean
        pr = data.get("positive_reframe")
        if isinstance(pr, str) and pr.strip():
            lib["positive_reframe"] = pr.strip()
    except (OSError, ValueError, TypeError):
        pass  # keep built-in fallback; authoring must never break
    _CACHE = lib
    return lib


def _dedupe(fragments):
    seen = {}
    for frag in fragments:
        f = str(frag).strip()
        if f and f not in seen:
            seen[f] = None
    return list(seen.keys())


def compose_negative(groups=DEFAULT_GROUPS, extra=None):
    """Flat, comma-joined, de-duplicated, order-stable negative string.

    Pure composition (dedupe + join), same shape the engine consumes (a plain
    ', '-joined string). Never empty. Restraint is enforced by keeping the
    library CONTENT clean and F3-disjoint (guarded by tests), not by silently
    scrubbing fragments here.
    """
    if isinstance(groups, str):
        groups = (groups,)
    lib_groups = load_library().get("groups", {})
    fragments = []
    for name in groups:
        fragments.extend(lib_groups.get(name, []))
    if extra:
        fragments.extend(extra)
    if not fragments:
        fragments = list(_FALLBACK_BASE)  # safety: never return empty
    return ", ".join(_dedupe(fragments))


def positive_reframe(groups=None):
    """Return the scene-1 positive clause (JSON-overridable, safe fallback)."""
    return load_library().get("positive_reframe", _FALLBACK_POSITIVE)
