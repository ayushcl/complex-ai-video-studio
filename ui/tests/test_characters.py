"""Tests for Simple character identity block helpers.

Run from the repo root with:
    python3 -m unittest ui.tests.test_characters -v

Free by construction: these helpers only read/write local character metadata and
never call generation, LLM, or pipeline code.
"""

from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_DIR))

import characters  # noqa: E402
import engine_bridge as bridge  # noqa: E402


class CharacterHelperTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = bridge.REPO_ROOT / "ui" / "data" / f"test_characters_{uuid.uuid4().hex[:8]}"
        self._bridge_paths = {
            "DATA_DIR": bridge.DATA_DIR,
            "PACKETS_DIR": bridge.PACKETS_DIR,
            "VOICES_DIR": bridge.VOICES_DIR,
            "RUNS_LEDGER_PATH": bridge.RUNS_LEDGER_PATH,
            "AUDIT_LOG_PATH": bridge.AUDIT_LOG_PATH,
        }
        bridge.DATA_DIR = self.data_dir
        bridge.PACKETS_DIR = self.data_dir / "packets"
        bridge.VOICES_DIR = self.data_dir / "voices"
        bridge.RUNS_LEDGER_PATH = self.data_dir / "runs.json"
        bridge.AUDIT_LOG_PATH = self.data_dir / "audit.jsonl"
        self.job_dir = self.data_dir / "simple" / "job"
        self.job_rel = bridge.rel_path(self.job_dir)
        self.job_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for name, value in self._bridge_paths.items():
            setattr(bridge, name, value)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def write_scenes(self, scenes, wrapped=True):
        data = {"scenes": scenes} if wrapped else scenes
        (self.job_dir / "scenes.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def read_scenes(self):
        return json.loads((self.job_dir / "scenes.json").read_text(encoding="utf-8"))["scenes"]

    def scenes_bytes(self):
        return (self.job_dir / "scenes.json").read_bytes()

    def test_inject_blocks_byte_identical(self):
        prompt = "A calm opening shot."
        blocks = [
            {"name": "Ava", "block": "Figure. Exact commas, spacing, and case stay locked."},
            {"name": "Bo", "block": "Wardrobe. Black jacket.\nHair. Neat side part."},
        ]

        injected = characters.inject_blocks(prompt, blocks)
        expected = (
            "A calm opening shot."
            "\n\n[character: Ava]\n"
            "Figure. Exact commas, spacing, and case stay locked."
            "\n\n[character: Bo]\n"
            "Wardrobe. Black jacket.\nHair. Neat side part."
        )

        self.assertEqual(injected.encode("utf-8"), expected.encode("utf-8"))

    def test_strip_then_inject_is_idempotent_across_repeated_edits(self):
        prompt = "Base prompt."
        edited_prompt = "EDITED: Base prompt."
        blocks = [{"name": "Ava", "block": "Face. Locked description."}]

        once = characters.inject_blocks(prompt, blocks)
        twice = characters.inject_blocks(characters.strip_injected_blocks(once, blocks), blocks)
        edited_once = characters.inject_blocks(
            characters.strip_injected_blocks(twice, blocks).replace(prompt, edited_prompt),
            blocks,
        )
        edited_twice = characters.inject_blocks(
            characters.strip_injected_blocks(edited_once, blocks),
            blocks,
        )

        self.assertEqual(twice.encode("utf-8"), once.encode("utf-8"))
        self.assertEqual(edited_twice.encode("utf-8"), edited_once.encode("utf-8"))
        self.assertEqual(edited_once.count("[character: Ava]\n"), 1)

    def test_strip_full_cast_then_inject_subset_matches_subset_only(self):
        prompt = "Base prompt."
        full_cast = [
            {"name": "Ava", "block": "Figure. Ava."},
            {"name": "Bo", "block": "Figure. Bo."},
            {"name": "Cy", "block": "Figure. Cy."},
        ]
        subset = full_cast[:2]
        previous = characters.inject_blocks(prompt, full_cast)

        reinjected_subset = characters.inject_blocks(
            characters.strip_injected_blocks(previous, full_cast),
            subset,
        )
        subset_only = characters.inject_blocks(prompt, subset)

        self.assertEqual(reinjected_subset.encode("utf-8"), subset_only.encode("utf-8"))

    def test_strip_full_cast_with_now_unassigned_character_noops_cleanly(self):
        prompt = "Base prompt."
        full_cast = [
            {"name": "Ava", "block": "Figure. Ava."},
            {"name": "Bo", "block": "Figure. Bo."},
            {"name": "Cy", "block": "Figure. Cy."},
        ]
        subset = full_cast[:2]

        reinjected_subset = characters.inject_blocks(
            characters.strip_injected_blocks(prompt, full_cast),
            subset,
        )
        subset_only = characters.inject_blocks(prompt, subset)

        self.assertEqual(reinjected_subset.encode("utf-8"), subset_only.encode("utf-8"))

    def test_strip_reversed_cast_order_removes_all_injected_blocks(self):
        prompt = "Base prompt."
        blocks = [
            {"name": "Ava", "block": "Figure. Ava."},
            {"name": "Bo", "block": "Figure. Bo."},
            {"name": "Cy", "block": "Figure. Cy."},
        ]

        injected = characters.inject_blocks(prompt, blocks)
        stripped = characters.strip_injected_blocks(injected, list(reversed(blocks)))

        self.assertEqual(stripped.encode("utf-8"), prompt.encode("utf-8"))

    def test_identical_block_text_different_names_strip_by_sentinel(self):
        prompt = "Base prompt."
        blocks = [
            {"name": "Ava", "block": "Figure. Same locked block."},
            {"name": "Bo", "block": "Figure. Same locked block."},
        ]

        injected = characters.inject_blocks(prompt, blocks)
        stripped = characters.strip_injected_blocks(injected, blocks)

        self.assertIn("[character: Ava]\n", injected)
        self.assertIn("[character: Bo]\n", injected)
        self.assertEqual(stripped.encode("utf-8"), prompt.encode("utf-8"))

    def test_resolve_assignments_expands_all_in_cast_order(self):
        doc = {
            "characters": [
                {"name": "Ava", "block": "Figure. Ava."},
                {"name": "Bo", "block": "Figure. Bo."},
            ],
            "assignments": {"Ava": "all", "Bo": [2]},
        }

        resolved = characters.resolve_assignments(doc, 3)

        self.assertEqual([item["name"] for item in resolved[1]], ["Ava"])
        self.assertEqual([item["name"] for item in resolved[2]], ["Ava", "Bo"])
        self.assertEqual([item["name"] for item in resolved[3]], ["Ava"])

    def test_resolve_assignments_rejects_out_of_range(self):
        doc = {
            "characters": [{"name": "Ava", "block": "Figure. Ava."}],
            "assignments": {"Ava": [3]},
        }

        with self.assertRaisesRegex(bridge.BridgeError, "between 1 and 2"):
            characters.resolve_assignments(doc, 2)

    def test_resolve_assignments_rejects_bool(self):
        doc = {
            "characters": [{"name": "Ava", "block": "Figure. Ava."}],
            "assignments": {"Ava": [True]},
        }

        with self.assertRaisesRegex(bridge.BridgeError, "list of scene indices"):
            characters.resolve_assignments(doc, 2)

    def test_load_characters_absent_file_returns_empty_default(self):
        self.assertEqual(
            characters.load_characters(self.job_rel),
            {"characters": [], "assignments": {}},
        )

    def test_save_characters_rejects_duplicate_names(self):
        with self.assertRaisesRegex(bridge.BridgeError, "duplicate character name"):
            characters.save_characters(
                self.job_rel,
                [
                    {"name": "Ava", "block": "Figure. One."},
                    {"name": "Ava", "block": "Figure. Two."},
                ],
                {},
            )

    def test_save_characters_rejects_duplicate_names_after_strip(self):
        with self.assertRaisesRegex(bridge.BridgeError, "duplicate character name"):
            characters.save_characters(
                self.job_rel,
                [
                    {"name": "Ava", "block": "Figure. One."},
                    {"name": " Ava ", "block": "Figure. Two."},
                ],
                {},
            )

    def test_save_characters_rejects_name_longer_than_eighty_chars(self):
        with self.assertRaisesRegex(bridge.BridgeError, "80"):
            characters.save_characters(
                self.job_rel,
                [{"name": "A" * 81, "block": "Figure. Ava."}],
                {},
            )

    def test_save_characters_rejects_empty_block(self):
        with self.assertRaisesRegex(bridge.BridgeError, "non-empty block"):
            characters.save_characters(
                self.job_rel,
                [{"name": "Ava", "block": ""}],
                {},
            )

    def test_save_characters_rejects_more_than_eight_characters(self):
        too_many = [
            {"name": f"Character {index}", "block": f"Figure. Character {index}."}
            for index in range(9)
        ]

        with self.assertRaisesRegex(bridge.BridgeError, "more than 8"):
            characters.save_characters(self.job_rel, too_many, {})

    def test_save_characters_rejects_bad_assignment_values(self):
        for value in (0, -1, "2"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(bridge.BridgeError, "list of scene indices"):
                    characters.save_characters(
                        self.job_rel,
                        [{"name": "Ava", "block": "Figure. Ava."}],
                        {"Ava": [value]},
                    )

    def test_save_characters_stores_stripped_canonical_name(self):
        characters.save_characters(
            self.job_rel,
            [{"name": " Ava ", "block": "Figure. Ava."}],
            {"Ava": "all"},
        )

        saved = json.loads((self.job_dir / "characters.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["characters"][0]["name"], "Ava")

    def test_apply_no_characters_file_leaves_scenes_bytes_unchanged(self):
        scenes = [
            {"prompt": "Scene one.", "negative_prompt": "no text"},
            {"prompt": "Scene two.", "duration_seconds": 7},
        ]
        self.write_scenes(scenes)
        before = self.scenes_bytes()

        result = characters.apply_characters_to_job(self.job_rel)

        self.assertFalse(result["changed"])
        self.assertEqual(self.scenes_bytes(), before)
        self.assertEqual(
            result["prompts"],
            [
                {"scene_index": 1, "prompt": "Scene one."},
                {"scene_index": 2, "prompt": "Scene two."},
            ],
        )

    def test_apply_empty_characters_list_leaves_scenes_bytes_unchanged(self):
        scenes = [
            {"prompt": "Scene one.", "negative_prompt": "no text"},
            {"prompt": "Scene two.", "duration_seconds": 7},
        ]
        self.write_scenes(scenes)
        characters.save_characters(self.job_rel, [], {})
        before = self.scenes_bytes()

        result = characters.apply_characters_to_job(self.job_rel)

        self.assertFalse(result["changed"])
        self.assertEqual(self.scenes_bytes(), before)
        self.assertEqual(
            result["prompts"],
            [
                {"scene_index": 1, "prompt": "Scene one."},
                {"scene_index": 2, "prompt": "Scene two."},
            ],
        )

    def test_apply_writes_assigned_verbatim_blocks_and_preserves_fields(self):
        scenes = [
            {
                "prompt": "Scene one.",
                "negative_prompt": "no text",
                "seed_image": "ui/data/seed.png",
                "mode": "image",
                "duration_seconds": 6,
            },
            {
                "prompt": "Scene two.",
                "negative_prompt": "no logos",
                "duration_seconds": 7,
            },
        ]
        self.write_scenes(scenes)
        before = self.read_scenes()
        before_scene_one_fields = json.dumps(
            {
                "seed_image": before[0]["seed_image"],
                "duration_seconds": before[0]["duration_seconds"],
            },
            sort_keys=True,
        ).encode("utf-8")
        ava_block = "Figure. Ava exact commas, spacing, and case."
        bo_block = "Wardrobe. Bo exact commas, spacing, and case."
        characters.save_characters(
            self.job_rel,
            [
                {"name": "Ava", "block": ava_block},
                {"name": "Bo", "block": bo_block},
            ],
            {"Ava": "all", "Bo": [2]},
        )

        result = characters.apply_characters_to_job(self.job_rel)
        after = self.read_scenes()
        after_scene_one_fields = json.dumps(
            {
                "seed_image": after[0]["seed_image"],
                "duration_seconds": after[0]["duration_seconds"],
            },
            sort_keys=True,
        ).encode("utf-8")

        self.assertTrue(result["changed"])
        self.assertIn(ava_block.encode("utf-8"), after[0]["prompt"].encode("utf-8"))
        self.assertIn(ava_block.encode("utf-8"), after[1]["prompt"].encode("utf-8"))
        self.assertNotIn(bo_block.encode("utf-8"), after[0]["prompt"].encode("utf-8"))
        self.assertIn(bo_block.encode("utf-8"), after[1]["prompt"].encode("utf-8"))
        self.assertEqual(before_scene_one_fields, after_scene_one_fields)
        self.assertEqual(after[0]["negative_prompt"], "no text")
        self.assertEqual(after[0]["mode"], "image")
        self.assertEqual(
            result["prompts"],
            [
                {"scene_index": 1, "prompt": after[0]["prompt"]},
                {"scene_index": 2, "prompt": after[1]["prompt"]},
            ],
        )

    def test_apply_is_idempotent_on_disk(self):
        self.write_scenes([
            {"prompt": "Scene one."},
            {"prompt": "Scene two."},
        ])
        characters.save_characters(
            self.job_rel,
            [{"name": "Ava", "block": "Figure. Ava."}],
            {"Ava": "all"},
        )

        first = characters.apply_characters_to_job(self.job_rel)
        first_bytes = self.scenes_bytes()
        second = characters.apply_characters_to_job(self.job_rel)

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(self.scenes_bytes(), first_bytes)

    def test_apply_reassignment_removes_now_unassigned_block(self):
        self.write_scenes([
            {"prompt": "Scene one."},
            {"prompt": "Scene two."},
        ])
        block = "Figure. Ava stays byte identical."
        characters.save_characters(
            self.job_rel,
            [{"name": "Ava", "block": block}],
            {"Ava": "all"},
        )
        characters.apply_characters_to_job(self.job_rel)
        self.assertIn(block, self.read_scenes()[1]["prompt"])

        characters.save_characters(
            self.job_rel,
            [{"name": "Ava", "block": block}],
            {"Ava": [1]},
        )
        result = characters.apply_characters_to_job(self.job_rel)
        after = self.read_scenes()

        self.assertTrue(result["changed"])
        self.assertIn(block, after[0]["prompt"])
        self.assertNotIn(block, after[1]["prompt"])


if __name__ == "__main__":
    unittest.main()
