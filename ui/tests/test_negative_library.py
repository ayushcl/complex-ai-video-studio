# IMPORTANT: match how the existing ui/tests files import ui modules
# (look at test_simple.py's import of docparse/simple_flow).
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

import negative_library as nl  # noqa: E402
import simple_flow  # noqa: E402

ORIGINAL_DEFAULT = (
    "readable text, captions, subtitles, watermarks, logos, "
    "brand marks, identifiable faces, distortion, low quality, camera shake"
)
# F3's exact merged drift terms (from run_veo_extension_chain._merge_negative_prompt)
F3_NUDGE = "different subject, subject missing from frame, empty frame, abrupt scene change, inconsistent lighting"

# packet_04 forbidden classes (anatomy / age-adjacent / NSFW / security) + model names
FORBIDDEN = [
    "skin", "nude", "naked", "anatomy", "body part", "breast", "genital", "thigh",
    "child", "kid", "minor", "teen", "young", "underage", "baby", "toddler",
    "nsfw", "sexual", "sexy", "erotic", "explicit", "porn", "lingerie",
    "weapon", "gun", "bomb", "explosive", "knife",
    "veo", "gemini", "lyria", "google", "sora", "openai", "runway",
]

# Negation phrasing that must NOT appear in the positive reframe.
NEGATION_TOKENS = {
    "no", "not", "never", "avoid", "without", "exclude", "excluding", "remove", "removing",
}


def _f3_merge(existing):
    """Mirror of run_veo_extension_chain._merge_negative_prompt (whole-substring dedup)."""
    existing = (existing or "").strip()
    if not existing:
        return F3_NUDGE
    if F3_NUDGE in existing:
        return existing
    return existing + ", " + F3_NUDGE


class ComposeNegativeTests(unittest.TestCase):
    def setUp(self):
        nl._CACHE = None

    def test_default_is_byte_identical(self):
        self.assertEqual(nl.compose_negative(nl.DEFAULT_GROUPS), ORIGINAL_DEFAULT)

    def test_json_base_matches_fallback(self):
        self.assertEqual(nl.load_library()["groups"]["base"], list(nl._FALLBACK_BASE))

    def test_dedupe_across_repeated_groups(self):
        self.assertEqual(nl.compose_negative(("base", "base")), ORIGINAL_DEFAULT)

    def test_order_stable(self):
        self.assertEqual(nl.compose_negative(nl.DEFAULT_GROUPS).split(", "), list(nl._FALLBACK_BASE))

    def test_extra_appended_and_deduped(self):
        out = nl.compose_negative(("base",), extra=["watermarks", "film grain"])
        frags = out.split(", ")
        self.assertEqual(frags.count("watermarks"), 1)
        self.assertEqual(frags[-1], "film grain")
        self.assertEqual(len(frags), len(set(frags)))

    def test_never_empty_on_unknown_group(self):
        self.assertTrue(nl.compose_negative(("does-not-exist",)).strip())

    def test_string_group_arg(self):
        self.assertEqual(nl.compose_negative("base"), ORIGINAL_DEFAULT)


class PositiveReframeTests(unittest.TestCase):
    def setUp(self):
        nl._CACHE = None

    def test_returns_nonempty(self):
        self.assertTrue(nl.positive_reframe().strip())

    def test_matches_json(self):
        self.assertEqual(nl.positive_reframe(), nl.load_library()["positive_reframe"])

    def test_reframe_is_actually_positive(self):
        # scene 1 reframe must NOT smuggle negative phrasing into the positive prompt
        words = set(re.findall(r"[a-z]+", nl.positive_reframe().lower()))
        offending = words & NEGATION_TOKENS
        self.assertEqual(offending, set(), "reframe contains negation phrasing: %r" % offending)


class Packet04ComplianceTests(unittest.TestCase):
    def setUp(self):
        nl._CACHE = None

    def _assert_clean(self, text):
        low = text.lower()
        for term in FORBIDDEN:
            self.assertNotIn(term, low, "forbidden term present: %r" % term)

    def test_default_negative_clean(self):
        self._assert_clean(nl.compose_negative(nl.DEFAULT_GROUPS))

    def test_positive_reframe_clean(self):
        self._assert_clean(nl.positive_reframe())


class LibraryContentGuardTests(unittest.TestCase):
    """Restraint enforced as a LOUD test-time data invariant: every fragment in
    every group must be packet_04-clean AND disjoint from F3's engine nudge, so
    a bad fragment added to the JSON fails here instead of reaching the engine."""
    def setUp(self):
        nl._CACHE = None

    def test_all_group_fragments_clean_and_f3_disjoint(self):
        f3 = set(F3_NUDGE.split(", "))
        groups = nl.load_library()["groups"]
        self.assertTrue(groups, "library must define at least one group")
        for name, frags in groups.items():
            self.assertTrue(frags, "group %r must be non-empty" % name)
            for frag in frags:
                low = frag.lower()
                for term in FORBIDDEN:
                    self.assertNotIn(term, low,
                        "forbidden term %r in group %r fragment %r" % (term, name, frag))
                self.assertNotIn(frag, f3,
                    "F3 drift term %r must not live in the library (group %r)" % (frag, name))


class F3NoDuplicationTests(unittest.TestCase):
    def setUp(self):
        nl._CACHE = None

    def test_base_disjoint_from_f3_nudge(self):
        base = set(nl.compose_negative(nl.DEFAULT_GROUPS).split(", "))
        f3 = set(F3_NUDGE.split(", "))
        self.assertEqual(base & f3, set())

    def test_merged_scene2_has_no_duplicate_fragments(self):
        merged = _f3_merge(nl.compose_negative(nl.DEFAULT_GROUPS))
        frags = [f.strip() for f in merged.split(",")]
        self.assertEqual(len(frags), len(set(frags)))


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self._orig_path = nl._JSON_PATH
        nl._CACHE = None

    def tearDown(self):
        nl._JSON_PATH = self._orig_path
        nl._CACHE = None

    def test_missing_json_falls_back(self):
        nl._JSON_PATH = Path("/nonexistent/negative_library.json")
        nl._CACHE = None
        self.assertEqual(nl.compose_negative(nl.DEFAULT_GROUPS), ORIGINAL_DEFAULT)
        self.assertTrue(nl.positive_reframe().strip())

    def test_corrupt_json_falls_back(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write("{ this is not valid json ")
            nl._JSON_PATH = Path(path)
            nl._CACHE = None
            self.assertEqual(nl.compose_negative(nl.DEFAULT_GROUPS), ORIGINAL_DEFAULT)
        finally:
            os.unlink(path)


class ApplyNegativeLibraryTests(unittest.TestCase):
    def setUp(self):
        nl._CACHE = None
        self._orig_nl = simple_flow.negative_library

    def tearDown(self):
        simple_flow.negative_library = self._orig_nl
        nl._CACHE = None

    def test_scene1_drops_negative_and_folds_positive(self):
        scenes = [
            {"prompt": "A dog runs across a field.", "negative_prompt": "whatever"},
            {"prompt": "Wide shot.", "negative_prompt": ""},
        ]
        simple_flow._apply_negative_library(scenes)
        self.assertNotIn("negative_prompt", scenes[0])
        self.assertTrue(scenes[0]["prompt"].startswith("A dog runs across a field."))
        self.assertIn(nl.positive_reframe(), scenes[0]["prompt"])

    def test_scene2_plus_get_composed_when_absent(self):
        scenes = [{"prompt": "one"}, {"prompt": "two"}, {"prompt": "three", "negative_prompt": ""}]
        simple_flow._apply_negative_library(scenes)
        self.assertEqual(scenes[1]["negative_prompt"], ORIGINAL_DEFAULT)
        self.assertEqual(scenes[2]["negative_prompt"], ORIGINAL_DEFAULT)

    def test_operator_negative_on_scene2_is_preserved(self):
        scenes = [{"prompt": "one"}, {"prompt": "two", "negative_prompt": "custom operator negative"}]
        simple_flow._apply_negative_library(scenes)
        self.assertEqual(scenes[1]["negative_prompt"], "custom operator negative")

    def test_scene2_composed_no_dup_after_simulated_f3_append(self):
        scenes = [{"prompt": "one"}, {"prompt": "two"}]
        simple_flow._apply_negative_library(scenes)
        merged = _f3_merge(scenes[1]["negative_prompt"])
        frags = [f.strip() for f in merged.split(",")]
        self.assertEqual(len(frags), len(set(frags)))

    def test_reframe_not_double_folded(self):
        scenes = [{"prompt": "seed. " + nl.positive_reframe()}]
        before = scenes[0]["prompt"]
        simple_flow._apply_negative_library(scenes)
        self.assertEqual(scenes[0]["prompt"].count(nl.positive_reframe()), 1)
        self.assertEqual(scenes[0]["prompt"], before)

    def test_single_scene_job(self):
        scenes = [{"prompt": "only scene", "negative_prompt": "x"}]
        summary = simple_flow._apply_negative_library(scenes)
        self.assertNotIn("negative_prompt", scenes[0])
        self.assertIn(nl.positive_reframe(), scenes[0]["prompt"])
        self.assertEqual(summary[0]["mode"], "positive")

    def test_library_absent_is_noop(self):
        simple_flow.negative_library = None
        scenes = [
            {"prompt": "one", "negative_prompt": "keep me"},
            {"prompt": "two"},
        ]
        out = simple_flow._apply_negative_library(scenes)
        self.assertEqual(out, [])
        self.assertEqual(scenes[0]["negative_prompt"], "keep me")   # untouched
        self.assertNotIn(nl.positive_reframe(), scenes[0]["prompt"])
        self.assertNotIn("negative_prompt", scenes[1])              # not filled

    def test_non_dict_scene_skipped(self):
        scenes = [{"prompt": "one"}, "not a dict"]
        simple_flow._apply_negative_library(scenes)  # must not raise


if __name__ == "__main__":
    unittest.main()
