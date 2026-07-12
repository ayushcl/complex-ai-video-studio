"""Character identity block helpers for Simple jobs.

Packet-02 placement (block after scene-opener) deferred by Matt; blocks are appended at end to guarantee byte-identical propagation. Revisit placement as a later pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import engine_bridge as bridge

SEP = "\n\n"
MAX_CHARACTERS = 8
MAX_BLOCK_CHARS = 4000
CHARACTERS_FILENAME = "characters.json"


def _sentinel(name: str) -> str:
    return f"[character: {name}]\n"


def _characters_path(job_dir_rel) -> Path:
    return bridge.safe_path(job_dir_rel) / CHARACTERS_FILENAME


def _empty_doc() -> dict:
    return {"characters": [], "assignments": {}}


def _validate_characters(characters) -> list[dict]:
    if characters is None:
        characters = []
    if not isinstance(characters, list):
        raise bridge.BridgeError("characters must be a list.")
    if len(characters) > MAX_CHARACTERS:
        raise bridge.BridgeError(f"characters cannot contain more than {MAX_CHARACTERS} entries.")

    seen = set()
    cleaned = []
    for index, item in enumerate(characters, start=1):
        if not isinstance(item, dict):
            raise bridge.BridgeError(f"character {index} must be an object.")
        raw_name = item.get("name")
        block = item.get("block")
        if not isinstance(raw_name, str):
            raise bridge.BridgeError(f"character {index} needs a non-empty name.")
        name = raw_name.strip()
        if not name:
            raise bridge.BridgeError(f"character {index} needs a non-empty name.")
        if len(name) > 80:
            raise bridge.BridgeError(f"character {name} name cannot exceed 80 characters.")
        if name in seen:
            raise bridge.BridgeError(f"duplicate character name: {name}")
        if not isinstance(block, str) or not block:
            raise bridge.BridgeError(f"character {name} needs a non-empty block.")
        if len(block) > MAX_BLOCK_CHARS:
            raise bridge.BridgeError(
                f"character {name} block cannot exceed {MAX_BLOCK_CHARS} characters."
            )
        seen.add(name)
        cleaned.append({"name": name, "block": block})
    return cleaned


def _validate_assignments(assignments, character_names: set[str]) -> dict:
    if assignments is None:
        assignments = {}
    if not isinstance(assignments, dict):
        raise bridge.BridgeError("assignments must be an object.")

    cleaned = {}
    for name, value in assignments.items():
        if not isinstance(name, str) or name not in character_names:
            raise bridge.BridgeError(f"assignment references unknown character: {name}")
        if value == "all":
            cleaned[name] = "all"
        elif isinstance(value, list):
            for scene_index in value:
                if (
                    isinstance(scene_index, bool)
                    or not isinstance(scene_index, int)
                    or scene_index < 1
                ):
                    raise bridge.BridgeError(
                        'assignments values must be "all" or a list of scene indices.'
                    )
            cleaned[name] = value
        else:
            raise bridge.BridgeError('assignments values must be "all" or a list of scene indices.')
    return cleaned


def _validate_doc(doc: dict) -> dict:
    if not isinstance(doc, dict):
        raise bridge.BridgeError("characters.json must contain an object.")
    characters = _validate_characters(doc.get("characters", []))
    assignments = _validate_assignments(
        doc.get("assignments", {}),
        {item["name"] for item in characters},
    )
    return {"characters": characters, "assignments": assignments}


def load_characters(job_dir_rel) -> dict:
    path = _characters_path(job_dir_rel)
    if not path.exists():
        return _empty_doc()
    return _validate_doc(bridge.read_json_file(path, "Characters"))


def save_characters(job_dir_rel, characters, assignments) -> dict:
    doc = _validate_doc({"characters": characters, "assignments": assignments})
    path = _characters_path(job_dir_rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bridge.audit(
        "simple_characters_saved",
        job_dir=bridge.rel_path(path.parent),
        characters=len(doc["characters"]),
    )
    return doc


def inject_blocks(prompt: str, blocks: list[dict]) -> str:
    out = prompt
    for item in blocks:
        out += SEP + _sentinel(item["name"]) + item["block"]
    return out


def strip_injected_blocks(prompt: str, blocks: list[dict]) -> str:
    out = prompt
    for item in blocks:
        out = out.replace(SEP + _sentinel(item["name"]) + item["block"], "")
    return out


def _resolve_scene_index(value, scene_count: int) -> int:
    if isinstance(value, bool):
        raise bridge.BridgeError('scene index must be a 1-based integer.')
    try:
        index = int(str(value).strip())
    except (TypeError, ValueError):
        raise bridge.BridgeError('scene index must be a 1-based integer.')
    if not 1 <= index <= scene_count:
        raise bridge.BridgeError(f"scene index must be between 1 and {scene_count}.")
    return index


def resolve_assignments(characters_doc, scene_count) -> dict:
    try:
        scene_total = int(str(scene_count).strip())
    except (TypeError, ValueError):
        raise bridge.BridgeError("scene_count must be a positive integer.")
    if isinstance(scene_count, bool) or scene_total < 1:
        raise bridge.BridgeError("scene_count must be a positive integer.")

    doc = _validate_doc(characters_doc)
    resolved = {index: [] for index in range(1, scene_total + 1)}
    assignments = doc["assignments"]
    for item in doc["characters"]:
        target = assignments.get(item["name"])
        if target is None:
            continue
        if target == "all":
            indices = list(range(1, scene_total + 1))
        else:
            indices = [_resolve_scene_index(value, scene_total) for value in target]
        for index in indices:
            resolved[index].append(item)
    return resolved


def _load_scenes(job_dir_rel) -> tuple[Path, list, bool]:
    path = bridge.safe_path(job_dir_rel) / "scenes.json"
    data = bridge.read_json_file(path, "Scenes")
    if isinstance(data, dict):
        scenes = data.get("scenes")
        wrapped = True
    else:
        scenes = data
        wrapped = False
    if not isinstance(scenes, list):
        raise bridge.BridgeError("Scenes must contain a list of scene objects.")
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            raise bridge.BridgeError(f"Scene {index} must be an object.")
        if "prompt" not in scene:
            raise bridge.BridgeError(f"Scene {index} is missing a prompt.")
    return path, scenes, wrapped


def _prompt_rows(scenes: list) -> list[dict]:
    return [
        {"scene_index": index, "prompt": scene["prompt"]}
        for index, scene in enumerate(scenes, start=1)
    ]


def apply_characters_to_job(job_dir_rel) -> dict:
    doc = load_characters(job_dir_rel)
    scenes_path, scenes, wrapped = _load_scenes(job_dir_rel)
    if not doc["characters"]:
        return {"changed": False, "prompts": _prompt_rows(scenes)}

    resolved = resolve_assignments(doc, len(scenes))
    full_cast = doc["characters"]
    changed_count = 0
    out_scenes = []
    for index, scene in enumerate(scenes, start=1):
        new_scene = dict(scene)
        prompt = scene["prompt"]
        new_prompt = inject_blocks(
            strip_injected_blocks(prompt, full_cast),
            resolved[index],
        )
        if new_prompt != prompt:
            changed_count += 1
        new_scene["prompt"] = new_prompt
        out_scenes.append(new_scene)

    if not changed_count:
        return {"changed": False, "prompts": _prompt_rows(scenes)}

    to_write = {"scenes": out_scenes} if wrapped else out_scenes
    scenes_path.write_text(
        json.dumps(to_write, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    bridge.audit(
        "simple_characters_injected",
        job_dir=bridge.rel_path(scenes_path.parent),
        scenes=changed_count,
    )
    return {"changed": True, "prompts": _prompt_rows(out_scenes)}
