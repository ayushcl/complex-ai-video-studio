"""Bridge between the operator UI and video_generation_agency/run_from_packet.py.

This module is the ONLY place the UI touches the pipeline. Rules it enforces:

  * Every pipeline invocation goes through run_from_packet.py (the packet
    adapter). The UI never builds or calls run_full_chain.py / generation
    scripts directly. Structured validation reuses the adapter's own
    functions in-process, so there is a single source of truth.
  * Dry-run is the default and is free: the adapter is invoked WITHOUT --run.
  * Live runs are gated three ways server-side, on top of the adapter's own
    two gates:
      1. the packet file must carry spend_controls.allow_live_run = true
         (flipped only by the explicit "authorize spend" action),
      2. the request must carry the typed confirmation phrase, and
      3. a successful dry-run of the byte-identical packet must exist in this
         server session (sha256 match) - no live run without a fresh preview.
  * All operator-supplied paths are resolved against the repo root and
    rejected if they escape it.
  * Voice selection is never automated: list order is alphabetical, nothing
    is preselected or ranked, and a selection is only written when the
    request asserts the human listened to that sample.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

import cost_estimator  # pure sibling module: REAL pricing for cost estimates
import video_tiers  # pure sibling module: render-tier data (video + image tiers)

REPO_ROOT = Path(__file__).resolve().parent.parent
ADAPTER_REL = Path("video_generation_agency") / "run_from_packet.py"
ADAPTER_PATH = REPO_ROOT / ADAPTER_REL

DATA_DIR = REPO_ROOT / "ui" / "data"
PACKETS_DIR = DATA_DIR / "packets"
VOICES_DIR = DATA_DIR / "voices"
RUNS_LEDGER_PATH = DATA_DIR / "runs.json"
AUDIT_LOG_PATH = DATA_DIR / "audit.jsonl"

STAGES = ("video", "extract", "sts", "music", "assemble")
CONFIRM_PHRASE = "SPEND"
DRYRUN_TIMEOUT_SECONDS = 300
DEFAULT_ASPECT_RATIO = "9:16"
VALID_ASPECT_RATIOS = ("9:16", "16:9")

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | {".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".gif", ".json"}

# Directories never shown by the file browser.
HIDDEN_DIR_NAMES = {".git", "venv", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}


class BridgeError(Exception):
    """Operator-facing error. The message is safe to show in the UI."""


# --------------------------------------------------------------------------- #
# Adapter module (lazy import, bypasses the package __init__)                  #
# --------------------------------------------------------------------------- #
_adapter_module = None
_adapter_lock = threading.Lock()


def adapter():
    """Load run_from_packet.py as a module so structured validation reuses the
    adapter's own code instead of reimplementing it."""
    global _adapter_module
    with _adapter_lock:
        if _adapter_module is None:
            spec = importlib.util.spec_from_file_location("run_from_packet_ui", ADAPTER_PATH)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _adapter_module = module
    return _adapter_module


# --------------------------------------------------------------------------- #
# Small helpers                                                                #
# --------------------------------------------------------------------------- #
def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_data_dirs() -> None:
    for directory in (DATA_DIR, PACKETS_DIR, VOICES_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def safe_path(raw: str) -> Path:
    """Resolve an operator-supplied path against the repo root. Reject empty
    paths and anything that escapes the repo."""
    if not raw or not str(raw).strip():
        raise BridgeError("Path is empty.")
    raw_text = str(raw).strip()
    if os.name != "nt" and PureWindowsPath(raw_text).is_absolute():
        raise BridgeError(f"Path is outside the repository root and was refused: {raw}")
    candidate = Path(raw_text)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        raise BridgeError(f"Path is outside the repository root and was refused: {raw}")
    return resolved


def rel_path(path: Path) -> str:
    """Repo-relative path with forward slashes (packets are repo-relative)."""
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(event: str, **fields) -> None:
    ensure_data_dirs()
    record = {"at": utc_now(), "event": event, **fields}
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_json_file(path: Path, label: str) -> dict:
    if not path.is_file():
        raise BridgeError(f"{label} not found: {rel_path(path)}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except UnicodeDecodeError:
        raise BridgeError(
            f"{label} is not a text file ({rel_path(path)}). "
            "This field needs a JSON file, not a media/binary file."
        )
    except json.JSONDecodeError as exc:
        raise BridgeError(f"{label} is not valid JSON: {exc}")


# --------------------------------------------------------------------------- #
# Packet building (form -> packet JSON)                                       #
# --------------------------------------------------------------------------- #
def build_packet_from_form(form: dict) -> dict:
    """Map the conditional job form onto the packet contract. Never sets
    start_stage (the adapter derives it) and always starts with
    allow_live_run=false (spend authorization is a separate explicit action)."""
    content_path = form.get("content_path")
    video_source = form.get("video_source")
    if content_path not in ("silent_brand", "presenter"):
        raise BridgeError("content_path must be 'silent_brand' or 'presenter'.")
    if video_source not in ("existing", "generate"):
        raise BridgeError("video_source must be 'existing' or 'generate'.")

    def text(key):
        value = form.get(key)
        return str(value).strip() if value is not None and str(value).strip() else None

    presenter_reference_image_path = (
        text("presenter_reference_image_path")
        or text("presenter_reference_image")  # compatibility with early UI payloads
    )
    aspect_ratio = None
    if video_source == "generate":
        aspect_ratio = text("aspect_ratio") or DEFAULT_ASPECT_RATIO
        if aspect_ratio not in VALID_ASPECT_RATIOS:
            raise BridgeError("aspect_ratio must be one of: 9:16, 16:9")

    packet = {
        "job_id": text("job_id") or f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "content_path": content_path,
        "video_source": video_source,
        "video_path": text("video_path") if video_source == "existing" else None,
        "scenes_path": text("scenes_path") if video_source == "generate" else None,
        "presenter_reference_image_path": (
            presenter_reference_image_path
            if video_source == "generate"
            else None
        ),
        "storyboard_path": text("storyboard_path"),
        "model": (text("model") or "veo-3.1-fast-generate-preview") if video_source == "generate" else None,
        "resolution": (text("resolution") or "720p") if video_source == "generate" else None,
        **({"aspect_ratio": aspect_ratio} if video_source == "generate" else {}),
        "max_scenes": None,
        "voice": {
            "prepared_voice_path": text("prepared_voice_path") if content_path == "presenter" else None,
        },
        "accent_dialect": None,
        "output_settings": {
            "output_dir": text("output_dir") or "runs",
            "final_video_name": "final_video.mp4",
        },
        "spend_controls": {
            "allow_live_run": False,
            "notes": text("spend_notes") or "",
        },
        "metadata": {
            "client": text("client") or "",
            "campaign": text("campaign") or "",
            "notes": text("notes") or "",
        },
    }

    if video_source == "generate":
        raw_max = form.get("max_scenes")
        if raw_max in (None, ""):
            packet["max_scenes"] = 1  # default the spend cap LOW
        else:
            try:
                packet["max_scenes"] = int(raw_max)
            except (TypeError, ValueError):
                raise BridgeError(f"max_scenes must be a positive integer, got: {raw_max!r}")
            if packet["max_scenes"] < 1:
                raise BridgeError("max_scenes must be at least 1.")

    return packet


# --------------------------------------------------------------------------- #
# Structured review (adapter functions in-process)                            #
# --------------------------------------------------------------------------- #
def planned_stage_chips(packet: dict, start_stage: str) -> list:
    """Presentational stage summary for the preview screen. Mirrors the
    routing rules documented in project_packet_schema.md; authoritative
    statuses always come from the engine's own output/manifest at run time."""
    silent = packet.get("content_path") == "silent_brand"
    generate = packet.get("video_source") == "generate"
    chips = []
    for stage in STAGES:
        skipped_by_start = STAGES.index(stage) < STAGES.index(start_stage)
        if stage == "video":
            if skipped_by_start:
                chips.append({"stage": stage, "planned": "skipped", "note": "existing video supplied"})
            elif generate:
                chips.append({"stage": stage, "planned": "active", "note": "Veo generation (paid on live run)"})
            else:
                chips.append({"stage": stage, "planned": "active", "note": "copy existing video into run"})
        elif stage == "extract":
            note = "silent path needs no speech extraction" if silent else "STS self-extracts source audio"
            chips.append({"stage": stage, "planned": "skipped", "note": note})
        elif stage == "sts":
            if silent:
                chips.append({"stage": stage, "planned": "skipped", "note": "silent_brand never runs STS"})
            else:
                chips.append({"stage": stage, "planned": "active", "note": "ElevenLabs STS (paid on live run)"})
        elif stage == "music":
            mode = "music bed only" if silent else "music under voice"
            chips.append({"stage": stage, "planned": "active", "note": f"{mode} (paid on live run)"})
        else:  # assemble
            chips.append({"stage": stage, "planned": "active", "note": "ffmpeg mux (local, free)"})
    return chips


def structured_review(packet: dict) -> dict:
    """Validate + derive using the adapter's own functions. Returns a dict the
    UI can render; never raises for packet problems (they come back as fields)."""
    mod = adapter()
    try:
        warnings = mod.validate_packet(packet)
        argv, start_stage = mod.build_command(packet)
    except mod.PacketError as exc:
        return {"valid": False, "error": str(exc)}
    except Exception as exc:  # malformed packet shapes (e.g. voice as string)
        return {"valid": False, "error": f"Packet could not be processed: {exc}"}

    spend = packet.get("spend_controls") or {}
    return {
        "valid": True,
        "warnings": warnings,
        "derived_command": " ".join(argv),
        "derived_argv": argv,
        "start_stage": start_stage,
        "stages": planned_stage_chips(packet, start_stage),
        "job_id": packet.get("job_id"),
        "content_path": packet.get("content_path"),
        "video_source": packet.get("video_source"),
        "model": (
            mod.PRESENTER_REFERENCE_MODEL
            if packet.get("presenter_reference_image_path")
            else packet.get("model")
        ),
        "resolution": (
            mod.PRESENTER_REFERENCE_RESOLUTION
            if packet.get("presenter_reference_image_path")
            else packet.get("resolution")
        ),
        "aspect_ratio": (
            (packet.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
            if packet.get("video_source") == "generate"
            else None
        ),
        "max_scenes": packet.get("max_scenes"),
        "storyboard_path": packet.get("storyboard_path"),
        "video_path": packet.get("video_path"),
        "scenes_path": packet.get("scenes_path"),
        "presenter_reference_image_path": packet.get("presenter_reference_image_path"),
        "prepared_voice_path": (packet.get("voice") or {}).get("prepared_voice_path"),
        "output_dir": (packet.get("output_settings") or {}).get("output_dir") or "runs",
        "allow_live_run": bool(spend.get("allow_live_run", False)),
        "experimental": packet.get("content_path") == "presenter" and packet.get("video_source") == "generate",
    }


# --------------------------------------------------------------------------- #
# Packet files                                                                 #
# --------------------------------------------------------------------------- #
def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "")).strip("-").lower()
    return slug or "packet"


def save_packet(packet: dict, name_hint: str | None = None) -> dict:
    ensure_data_dirs()
    slug = slugify(name_hint or packet.get("job_id") or "packet")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = PACKETS_DIR / f"{slug}_{stamp}.json"
    counter = 1
    while path.exists():
        counter += 1
        path = PACKETS_DIR / f"{slug}_{stamp}_{counter}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(packet, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    audit("packet_saved", path=rel_path(path), job_id=packet.get("job_id"))
    return {"path": rel_path(path), "sha256": file_sha256(path)}


def load_packet_file(raw_path: str) -> dict:
    path = safe_path(raw_path)
    packet = read_json_file(path, "Packet")
    return {"path": rel_path(path), "packet": packet, "sha256": file_sha256(path)}


def list_saved_packets() -> list:
    ensure_data_dirs()
    entries = []
    candidates = sorted(PACKETS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates[:100]:
        try:
            packet = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        entries.append({
            "path": rel_path(path),
            "job_id": packet.get("job_id"),
            "content_path": packet.get("content_path"),
            "video_source": packet.get("video_source"),
            "allow_live_run": bool((packet.get("spend_controls") or {}).get("allow_live_run", False)),
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return entries


def list_example_packets() -> list:
    examples_dir = REPO_ROOT / "video_generation_agency" / "packets"
    entries = []
    for path in sorted(examples_dir.glob("*.json")):
        try:
            packet = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        entries.append({
            "path": rel_path(path),
            "job_id": packet.get("job_id"),
            "content_path": packet.get("content_path"),
            "video_source": packet.get("video_source"),
        })
    return entries


def set_spend_authorization(raw_path: str, allow: bool) -> dict:
    """Flip spend_controls.allow_live_run in the packet file. This is gate 1
    and is always a deliberate, audited operator action."""
    path = safe_path(raw_path)
    packet = read_json_file(path, "Packet")
    spend = packet.get("spend_controls")
    if not isinstance(spend, dict):
        spend = {}
        packet["spend_controls"] = spend
    spend["allow_live_run"] = bool(allow)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(packet, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    audit("spend_authorization", path=rel_path(path), allow_live_run=bool(allow))
    return {"path": rel_path(path), "packet": packet, "sha256": file_sha256(path)}


# --------------------------------------------------------------------------- #
# Dry-run (free)                                                               #
# --------------------------------------------------------------------------- #
# packet rel path -> {"sha256": ..., "ok": bool, "at": ...}; in-memory on
# purpose: a server restart should force a fresh dry-run before any live run.
_dryrun_registry: dict = {}
_dryrun_lock = threading.Lock()


def dry_run(raw_packet_path: str) -> dict:
    """Invoke run_from_packet.py WITHOUT --run. Free by design."""
    path = safe_path(raw_packet_path)
    if not path.is_file():
        raise BridgeError(f"Packet file not found: {raw_packet_path}")
    packet_rel = rel_path(path)
    sha = file_sha256(path)

    try:
        packet = read_json_file(path, "Packet")
        structured = structured_review(packet)
    except BridgeError as exc:
        structured = {"valid": False, "error": str(exc)}

    completed = subprocess.run(
        [sys.executable, str(ADAPTER_REL), "--packet", packet_rel],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=DRYRUN_TIMEOUT_SECONDS,
    )
    ok = completed.returncode == 0

    with _dryrun_lock:
        _dryrun_registry[packet_rel] = {"sha256": sha, "ok": ok, "at": utc_now()}

    audit("dry_run", path=packet_rel, ok=ok, returncode=completed.returncode)
    return {
        "ok": ok,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "structured": structured,
        "packet_path": packet_rel,
        "packet_sha256": sha,
        "command": f"{Path(sys.executable).name} {ADAPTER_REL.as_posix()} --packet {packet_rel}",
    }


def dryrun_state(raw_packet_path: str) -> dict:
    """Whether the current bytes of this packet have a passing dry-run."""
    path = safe_path(raw_packet_path)
    packet_rel = rel_path(path)
    with _dryrun_lock:
        entry = _dryrun_registry.get(packet_rel)
    if not path.is_file():
        return {"fresh": False, "reason": "packet file not found"}
    if entry is None:
        return {"fresh": False, "reason": "no dry-run yet in this server session"}
    if not entry["ok"]:
        return {"fresh": False, "reason": "last dry-run failed validation"}
    if entry["sha256"] != file_sha256(path):
        return {"fresh": False, "reason": "packet changed since last dry-run"}
    return {"fresh": True, "at": entry["at"]}


# --------------------------------------------------------------------------- #
# Engine plan (free full plan through the derived command, no --run)          #
# --------------------------------------------------------------------------- #
def engine_plan(raw_packet_path: str) -> dict:
    """Execute the adapter-derived run_full_chain.py command WITHOUT --run.
    run_full_chain.py dry-runs by default: it creates a run folder + manifest
    and prints the full ordered plan without invoking any sub-script."""
    path = safe_path(raw_packet_path)
    packet = read_json_file(path, "Packet")
    mod = adapter()
    try:
        mod.validate_packet(packet)
        argv, _start_stage = mod.build_command(packet)
    except mod.PacketError as exc:
        raise BridgeError(f"Packet rejected: {exc}")

    if "--run" in argv:
        # Defensive: build_command never appends --run, but never execute if it did.
        raise BridgeError("Derived command unexpectedly contained --run; refusing.")

    completed = subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=DRYRUN_TIMEOUT_SECONDS,
    )
    parsed = parse_engine_output(completed.stdout)
    manifest = None
    if parsed.get("manifest_path"):
        try:
            manifest = read_json_file(safe_path(parsed["manifest_path"]), "Manifest")
        except BridgeError:
            manifest = None
    audit("engine_plan", path=rel_path(path), returncode=completed.returncode)
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "command": " ".join(argv),
        "parsed": parsed,
        "manifest": manifest,
    }


# --------------------------------------------------------------------------- #
# Engine output parsing                                                        #
# --------------------------------------------------------------------------- #
RUN_ID_RE = re.compile(r"^Run ID: (\S+)", re.MULTILINE)
RUN_DIR_RE = re.compile(r"^Run directory: (.+)$", re.MULTILINE)
MANIFEST_RE = re.compile(r"^Manifest: (.+)$", re.MULTILINE)
EXEC_STAGE_RE = re.compile(r"^Executing stage (\w+): (\S+)", re.MULTILINE)
STAGE_RC_RE = re.compile(r"^\[(\w+)\] return code: (-?\d+)", re.MULTILINE)
LIVE_EXEC_RE = re.compile(r"^live_execution: (\S+)", re.MULTILINE)


def parse_engine_output(stdout: str) -> dict:
    parsed = {
        "engine_run_id": None,
        "run_dir": None,
        "manifest_path": None,
        "live_execution": None,
        "stage_events": [],
    }
    if not stdout:
        return parsed
    match = RUN_ID_RE.search(stdout)
    if match:
        parsed["engine_run_id"] = match.group(1)
    match = RUN_DIR_RE.search(stdout)
    if match:
        parsed["run_dir"] = match.group(1).strip()
    manifests = MANIFEST_RE.findall(stdout)
    if manifests:
        parsed["manifest_path"] = manifests[-1].strip()
    match = LIVE_EXEC_RE.findall(stdout)
    if match:
        parsed["live_execution"] = match[-1]
    for stage, status in EXEC_STAGE_RE.findall(stdout):
        parsed["stage_events"].append({"stage": stage, "event": "started", "status": status})
    for stage, rc in STAGE_RC_RE.findall(stdout):
        parsed["stage_events"].append({"stage": stage, "event": "command_done", "returncode": int(rc)})
    return parsed


def live_stage_view(stdout: str, manifest: dict | None, process_running: bool) -> list:
    """Truthful per-stage status. The manifest (written by the engine at the
    end) wins; while running, statuses come from the engine's own progress
    lines; everything else is 'pending'."""
    states = {stage: {"stage": stage, "status": "pending", "detail": ""} for stage in STAGES}

    if manifest and isinstance(manifest.get("ordered_stage_plan"), list):
        for entry in manifest["ordered_stage_plan"]:
            stage = entry.get("stage")
            if stage not in states:
                continue
            final = entry.get("final_status", "PENDING")
            if final.startswith("SKIPPED"):
                status = "skipped"
            elif final == "EXECUTED":
                status = "ok"
            elif final in ("FAILED", "FAILED_NOT_WIRED"):
                status = "failed"
            elif final.startswith("NOT_RUN"):
                status = "not_run"
            else:
                status = "pending"
            states[stage] = {"stage": stage, "status": status, "detail": final}
        return [states[s] for s in STAGES]

    parsed = parse_engine_output(stdout or "")
    started: list = []
    for event in parsed["stage_events"]:
        stage = event["stage"]
        if stage not in states:
            continue
        if event["event"] == "started":
            states[stage] = {"stage": stage, "status": "running", "detail": event.get("status", "")}
            started.append(stage)
        elif event["event"] == "command_done":
            if event["returncode"] != 0:
                states[stage] = {"stage": stage, "status": "failed", "detail": f"command exited {event['returncode']}"}
    # A stage that started and was followed by another started stage finished ok.
    for index, stage in enumerate(started[:-1] if process_running else started):
        if index < len(started) - 1 or not process_running:
            if states[stage]["status"] == "running":
                states[stage] = {"stage": stage, "status": "ok", "detail": "completed"}
    return [states[s] for s in STAGES]


# --------------------------------------------------------------------------- #
# Live runs                                                                    #
# --------------------------------------------------------------------------- #
_runs: dict = {}
_runs_lock = threading.Lock()
# Held across the whole gate-check -> run-registration sequence so two
# concurrent live requests can never both pass the "one live run at a time"
# check (check-then-act must be atomic when real money is behind it).
_live_start_lock = threading.Lock()


def _persist_ledger() -> None:
    ensure_data_dirs()
    with _runs_lock:
        snapshot = [summarize_run(record) for record in _runs.values()]
    snapshot.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    with RUNS_LEDGER_PATH.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2)
        handle.write("\n")


def load_ledger() -> list:
    if not RUNS_LEDGER_PATH.is_file():
        return []
    try:
        return json.loads(RUNS_LEDGER_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def summarize_run(record: dict) -> dict:
    return {
        "ui_run_id": record["ui_run_id"],
        "mode": record.get("mode", "live"),
        "packet_path": record["packet_path"],
        "job_id": record.get("job_id"),
        "status": record["status"],
        "returncode": record.get("returncode"),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
        "engine_run_id": record.get("engine_run_id"),
        "run_dir": record.get("run_dir"),
    }


def start_live_run(raw_packet_path: str, confirm: str) -> dict:
    """Start a live (paid) run. Refuses unless every gate passes. The spawned
    process is the adapter with --run; the adapter re-checks its own gates."""
    if confirm != CONFIRM_PHRASE:
        raise BridgeError(
            f"Live run refused: confirmation phrase mismatch. Type {CONFIRM_PHRASE!r} to confirm paid execution."
        )

    path = safe_path(raw_packet_path)
    if not path.is_file():
        raise BridgeError(f"Packet file not found: {raw_packet_path}")
    packet_rel = rel_path(path)

    with _live_start_lock:
        packet = read_json_file(path, "Packet")
        spend = packet.get("spend_controls") or {}
        if spend.get("allow_live_run") is not True:
            raise BridgeError(
                "Live run refused: the packet has spend_controls.allow_live_run = false. "
                "Authorize live spend on the dry-run screen first."
            )

        freshness = dryrun_state(packet_rel)
        if not freshness.get("fresh"):
            raise BridgeError(
                f"Live run refused: {freshness.get('reason')}. Run a passing dry-run of this exact packet first."
            )

        ui_run_id = f"ui_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        record = {
            "ui_run_id": ui_run_id,
            "mode": "live",
            "packet_path": packet_rel,
            "packet_sha256": file_sha256(path),
            "job_id": packet.get("job_id"),
            "status": "running",
            "returncode": None,
            "started_at": utc_now(),
            "finished_at": None,
            "stdout_lines": [],
            "stderr_lines": [],
            "engine_run_id": None,
            "run_dir": None,
            "manifest_path": None,
        }
        with _runs_lock:
            for existing in _runs.values():
                if existing["status"] == "running":
                    raise BridgeError(
                        f"Live run refused: run {existing['ui_run_id']} is still in progress. "
                        "One live run at a time."
                    )
            _runs[ui_run_id] = record

    argv = [sys.executable, str(ADAPTER_REL), "--packet", packet_rel, "--run"]
    audit("live_run_started", ui_run_id=ui_run_id, path=packet_rel, command=" ".join(argv))

    def reader(stream, sink_key):
        try:
            for line in iter(stream.readline, ""):
                with _runs_lock:
                    record[sink_key].append(line.rstrip("\n"))
                if sink_key == "stdout_lines":
                    _harvest_progress(record, line)
        finally:
            stream.close()

    def waiter(process):
        process.wait()
        for thread in io_threads:
            thread.join(timeout=10)
        with _runs_lock:
            record["returncode"] = process.returncode
            record["finished_at"] = utc_now()
            if process.returncode == 0:
                record["status"] = "succeeded"
            elif process.returncode == 3:
                record["status"] = "refused"
            else:
                record["status"] = "failed"
        audit(
            "live_run_finished",
            ui_run_id=ui_run_id,
            status=record["status"],
            returncode=process.returncode,
        )
        _persist_ledger()

    process = subprocess.Popen(
        argv,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        # Unbuffered (live progress arrives promptly) + .env keys injected so
        # credentials saved via the admin panel reach the engine.
        env=engine_subprocess_env(),
    )
    io_threads = [
        threading.Thread(target=reader, args=(process.stdout, "stdout_lines"), daemon=True),
        threading.Thread(target=reader, args=(process.stderr, "stderr_lines"), daemon=True),
    ]
    for thread in io_threads:
        thread.start()
    threading.Thread(target=waiter, args=(process,), daemon=True).start()

    _persist_ledger()
    return {"ui_run_id": ui_run_id, "status": "running", "command": " ".join(argv)}


def _harvest_progress(record: dict, line: str) -> None:
    match = RUN_ID_RE.match(line)
    if match:
        record["engine_run_id"] = match.group(1)
    match = RUN_DIR_RE.match(line)
    if match:
        record["run_dir"] = match.group(1).strip()
    match = MANIFEST_RE.match(line)
    if match:
        record["manifest_path"] = match.group(1).strip()


def _report_entry(run_dir: Path, relative: str, label: str) -> dict:
    path = run_dir / relative
    return {"label": label, "path": rel_path(path) if _inside_repo(path) else str(path), "exists": path.is_file()}


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def run_status(ui_run_id: str, tail: int = 400) -> dict:
    with _runs_lock:
        record = _runs.get(ui_run_id)
        if record is None:
            raise BridgeError(f"Unknown run: {ui_run_id}")
        snapshot = dict(record)
        stdout_lines = list(record["stdout_lines"])
        stderr_lines = list(record["stderr_lines"])

    stdout_text = "\n".join(stdout_lines)
    running = snapshot["status"] == "running"

    manifest = None
    music_report = None
    failure = None
    reports = []
    final_video = None
    run_dir = Path(snapshot["run_dir"]) if snapshot.get("run_dir") else None
    if run_dir is not None and not run_dir.is_absolute():
        run_dir = REPO_ROOT / run_dir

    if run_dir is not None and run_dir.is_dir():
        manifest_path = run_dir / "manifest.json"
        if not running and manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                failure = manifest.get("failure")
            except (json.JSONDecodeError, OSError):
                manifest = None
        music_report_path = run_dir / "music" / "music_report.json"
        if music_report_path.is_file():
            try:
                music_report = json.loads(music_report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                music_report = None
        reports = [
            _report_entry(run_dir, "manifest.json", "Run manifest"),
            _report_entry(run_dir, "music/music_report.json", "Music report"),
            _report_entry(run_dir, "music/music_brief.json", "Music brief"),
            _report_entry(run_dir, "music/mix_report.json", "Mix report"),
            _report_entry(run_dir, "video/chain_report.json", "Veo chain report"),
        ]
        final_path = run_dir / "final" / "final_video.mp4"
        final_video = {
            "path": rel_path(final_path) if _inside_repo(final_path) else str(final_path),
            "exists": final_path.is_file(),
        }

    music_warning = None
    if isinstance(music_report, dict):
        if music_report.get("used_safe_prompt"):
            music_warning = (
                "Music used the SAFE FALLBACK prompt (primary prompt was rejected). "
                "Review the music for brand fit before delivery."
            )
        elif music_report.get("status") == "failed":
            music_warning = "Music generation FAILED - see the music report."

    return {
        **summarize_run(snapshot),
        "stdout_tail": "\n".join(stdout_lines[-tail:]),
        "stderr": "\n".join(stderr_lines),
        "stages": live_stage_view(stdout_text, manifest, running),
        "manifest_path": snapshot.get("manifest_path"),
        "manifest_failure": failure,
        "music_report": music_report if isinstance(music_report, dict) else None,
        "music_warning": music_warning,
        "reports": reports,
        "final_video": final_video,
        "output_dirs": {
            "run_dir": snapshot.get("run_dir"),
        },
    }


def list_runs() -> list:
    with _runs_lock:
        active = [summarize_run(r) for r in _runs.values()]
    active_ids = {r["ui_run_id"] for r in active}
    historic = [r for r in load_ledger() if r.get("ui_run_id") not in active_ids]
    combined = active + historic
    combined.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return combined


# --------------------------------------------------------------------------- #
# Voice auditions                                                              #
# --------------------------------------------------------------------------- #
def _load_audition_manifest(directory: Path) -> dict:
    """Optional metadata: auditions_manifest.json or manifest.json in the
    directory, mapping sample file -> workspace_voice_id/label."""
    mapping = {}
    for name in ("auditions_manifest.json", "manifest.json"):
        manifest_path = directory / name
        if not manifest_path.is_file():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        entries = data.get("auditions") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("file"):
                mapping[str(entry["file"])] = entry
        break
    return mapping


def list_auditions(raw_dir: str) -> dict:
    directory = safe_path(raw_dir)
    if not directory.is_dir():
        raise BridgeError(f"Audition directory not found: {raw_dir}")
    manifest_map = _load_audition_manifest(directory)
    samples = []
    # Alphabetical order on purpose: neutral, never ranked, never preselected.
    for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file() or entry.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        meta = manifest_map.get(entry.name, {})
        sidecar = entry.with_suffix(entry.suffix + ".json")
        if not meta and not sidecar.is_file():
            sidecar = entry.with_suffix(".json")
        if not meta and sidecar.is_file():
            try:
                sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
                if isinstance(sidecar_data, dict):
                    meta = sidecar_data
            except (json.JSONDecodeError, OSError):
                meta = {}
        samples.append({
            "file": entry.name,
            "path": rel_path(entry),
            "size_bytes": entry.stat().st_size,
            "workspace_voice_id": meta.get("workspace_voice_id") or meta.get("voice_id"),
            "label": meta.get("label") or meta.get("name"),
            "notes": meta.get("notes"),
        })
    return {"dir": rel_path(directory), "samples": samples}


def select_voice(payload: dict) -> dict:
    """Write prepared_voice.json for a HUMAN-selected audition sample. Refuses
    unless the request asserts the operator listened to that sample."""
    if payload.get("listened") is not True:
        raise BridgeError("Voice selection refused: the operator must listen to the sample before selecting it.")
    voice_id = str(payload.get("workspace_voice_id") or "").strip()
    if not voice_id:
        raise BridgeError(
            "Voice selection refused: workspace_voice_id is required "
            "(from the audition manifest/sidecar, or entered by the operator)."
        )
    sample_rel = None
    if payload.get("sample_path"):
        sample = safe_path(payload["sample_path"])
        if not sample.is_file():
            raise BridgeError(f"Audition sample not found: {payload['sample_path']}")
        sample_rel = rel_path(sample)

    ensure_data_dirs()
    slug = slugify(payload.get("label") or (Path(sample_rel).stem if sample_rel else "voice"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = VOICES_DIR / f"prepared_voice_{slug}_{stamp}.json"
    prepared = {
        "workspace_voice_id": voice_id,
        "label": payload.get("label") or None,
        "source_sample": sample_rel,
        "selected_at": utc_now(),
        "selected_via": "operator_ui_human_pick",
        "listened_confirmed": True,
        "notes": payload.get("notes") or None,
    }
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(prepared, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    audit("voice_selected", path=rel_path(out_path), sample=sample_rel, label=payload.get("label"))
    return {"prepared_voice_path": rel_path(out_path), "prepared_voice": prepared}


# --------------------------------------------------------------------------- #
# Filesystem browsing + scenes inspection                                      #
# --------------------------------------------------------------------------- #
def fs_list(raw_path: str | None) -> dict:
    directory = safe_path(raw_path) if raw_path else REPO_ROOT
    if not directory.is_dir():
        raise BridgeError(f"Not a directory: {raw_path}")
    entries = []
    try:
        children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        raise BridgeError(f"Could not list directory: {exc}")
    for child in children[:500]:
        if child.name in HIDDEN_DIR_NAMES or child.name.startswith("."):
            continue
        entries.append({
            "name": child.name,
            "path": rel_path(child),
            "type": "dir" if child.is_dir() else "file",
            "size_bytes": child.stat().st_size if child.is_file() else None,
        })
    parent = None
    if directory != REPO_ROOT:
        parent = rel_path(directory.parent) if directory.parent != REPO_ROOT else ""
    return {"path": rel_path(directory) if directory != REPO_ROOT else "", "parent": parent, "entries": entries}


def inspect_scenes(raw_path: str, max_scenes=None) -> dict:
    """Light, read-only hints about a scenes.json for the form. The engine's
    own load_scenes() remains the authoritative validator."""
    path = safe_path(raw_path)
    if path.suffix.lower() in MEDIA_EXTENSIONS - {".json"}:
        raise BridgeError(
            f"{path.name} looks like a media file. The scenes field needs the scenes JSON; "
            "the seed image is referenced from INSIDE that file (scene 1's seed_image), "
            "not entered here."
        )
    data = read_json_file(path, "Scenes file")
    scenes = data.get("scenes") if isinstance(data, dict) else data
    issues = []
    if not isinstance(scenes, list) or not scenes:
        return {"path": rel_path(path), "issues": ["Scenes file must be a JSON array of scenes or an object with a 'scenes' array."]}

    first = scenes[0] if isinstance(scenes[0], dict) else {}
    seed_image = first.get("seed_image")
    seed_exists = False
    if not isinstance(seed_image, str) or not seed_image.strip():
        issues.append("Scene 1 is the image seed and must include a non-empty seed_image path - the engine rejects this at plan time.")
    else:
        try:
            seed_exists = safe_path(seed_image).is_file()
        except BridgeError:
            seed_exists = Path(seed_image).is_file()
        if not seed_exists:
            issues.append(f"Scene 1 seed_image not found on disk: {seed_image}")

    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            issues.append(f"Scene {index} is not a JSON object.")
            continue
        prompt = scene.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            issues.append(f"Scene {index} is missing a non-empty prompt.")
        elif prompt.strip() == "FILL_FROM_PROOF_SCRIPT":
            issues.append(f"Scene {index} prompt is the FILL_FROM_PROOF_SCRIPT placeholder.")

    effective = len(scenes)
    if isinstance(max_scenes, int) and max_scenes >= 1:
        effective = min(effective, max_scenes)
    seed_duration = first.get("duration_seconds", first.get("duration", 6))
    try:
        seed_seconds = int(str(seed_duration).rstrip("s"))
    except (ValueError, TypeError):
        seed_seconds = 6
    est_seconds = seed_seconds + 7 * max(0, effective - 1)

    return {
        "path": rel_path(path),
        "scene_count": len(scenes),
        "effective_scenes": effective,
        "seed_image": seed_image if isinstance(seed_image, str) else None,
        "seed_image_exists": seed_exists,
        "estimated_duration_seconds": est_seconds,
        "issues": issues,
    }


# --------------------------------------------------------------------------- #
# Settings (model config for draft/high-quality, AI extraction toggle,        #
# operator-editable cost-estimate pricing).                                    #
# --------------------------------------------------------------------------- #
# The image model the user storyboard always renders with: one admin-configured
# model (the user never picks an image tier). Defaults to the cheap+faithful
# Basic model. Valid options are the IMAGE_TIERS models (the allow-list), so the
# admin dropdown and the validation share the single source of truth.
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"
DEFAULT_SETTINGS = {
    "draft": {"model": "veo-3.1-fast-generate-preview", "resolution": "720p"},
    "hq": {"model": "veo-3.1-generate-preview", "resolution": "1080p"},
    "ai_extraction": True,
    # The single image model the user storyboard renders with (admin-configured;
    # the user no longer picks an image tier). Validated against IMAGE_TIERS.
    "image_model": DEFAULT_IMAGE_MODEL,
    # REAL rates (see cost_estimator.DEFAULT_PRICING). The estimate is a human
    # sanity-check only - it never gates, authorizes, or influences spend.
    "pricing": cost_estimator.DEFAULT_PRICING,
}
VALID_RESOLUTIONS = ("720p", "1080p", "4k")


def image_model_options() -> list:
    """The allow-list of image models the admin may configure for the user
    storyboard: the IMAGE_TIERS models (single source of truth in video_tiers)."""
    return [tier["model"] for tier in video_tiers.IMAGE_TIERS]


def tiers_config() -> dict:
    """The Phase-A render tiers (video + image) the UI offers, with their REAL
    per-unit rates, sourced from video_tiers (the single source of truth). Pure
    data the settings/tiers endpoints surface; the spend gates live elsewhere."""
    return {
        "video": [dict(t) for t in video_tiers.VIDEO_TIERS],
        "image": [dict(t) for t in video_tiers.IMAGE_TIERS],
        "max_storyboard_images": video_tiers.MAX_STORYBOARD_IMAGES,
    }


def _settings_path() -> Path:
    return DATA_DIR / "settings.json"


def _coerce_rate(value, label: str) -> float:
    """Validate an operator-supplied price as a finite, non-negative number."""
    try:
        rate = float(value)
    except (TypeError, ValueError):
        raise BridgeError(f"{label} must be a number, got: {value!r}")
    if rate != rate or rate in (float("inf"), float("-inf")):  # NaN/inf guard
        raise BridgeError(f"{label} must be a finite number, got: {value!r}")
    if rate < 0:
        raise BridgeError(f"{label} must not be negative, got: {value!r}")
    return rate


def _default_pricing() -> dict:
    return json.loads(json.dumps(cost_estimator.DEFAULT_PRICING))  # deep copy


# Two-level rate tables in the pricing dict: model -> resolution -> rate.
_NESTED_RATE_TABLES = ("veo_per_second", "image_per_image")
# One-level flat rate tables: model -> rate.
_FLAT_RATE_TABLES = ("music_per_song",)


def _merge_pricing(pricing: dict, incoming) -> None:
    """Merge an operator-supplied pricing override into `pricing` (a deep copy of
    the defaults), in place. Every rate is validated (finite, non-negative); a
    bad rate raises BridgeError so nothing silently corrupts the estimate.

    The pricing shape is resolution-aware:
      * veo_per_second / image_per_image: model -> resolution -> rate (2 levels)
      * music_per_song: model -> rate (1 level)
      * tier_models: quality -> {model, resolution} (string passthrough)
      * music_model / image_preview_model / image_preview_resolution / currency:
        plain strings."""
    if not isinstance(incoming, dict):
        return

    for table_name in _NESTED_RATE_TABLES:
        table = incoming.get(table_name)
        if not isinstance(table, dict):
            continue
        target = pricing.setdefault(table_name, {})
        for model, resolutions in table.items():
            if not isinstance(resolutions, dict):
                raise BridgeError(
                    f"pricing.{table_name}.{model} must be a {{resolution: rate}} object."
                )
            model_target = target.setdefault(str(model), {})
            for resolution, rate in resolutions.items():
                if rate is None:
                    continue
                model_target[str(resolution)] = _coerce_rate(
                    rate, f"pricing.{table_name}.{model}.{resolution}")

    for table_name in _FLAT_RATE_TABLES:
        table = incoming.get(table_name)
        if not isinstance(table, dict):
            continue
        target = pricing.setdefault(table_name, {})
        for model, rate in table.items():
            if rate is None:
                continue
            target[str(model)] = _coerce_rate(rate, f"pricing.{table_name}.{model}")

    tier_models = incoming.get("tier_models")
    if isinstance(tier_models, dict):
        target = pricing.setdefault("tier_models", {})
        for quality, entry in tier_models.items():
            if not isinstance(entry, dict):
                continue
            merged = dict(target.get(quality) or {})
            for field in ("model", "resolution"):
                value = entry.get(field)
                if isinstance(value, str) and value.strip():
                    merged[field] = value.strip()
            target[str(quality)] = merged

    for str_field in ("music_model", "image_preview_model",
                      "image_preview_resolution", "currency"):
        value = incoming.get(str_field)
        if isinstance(value, str) and value.strip():
            pricing[str_field] = value.strip()


def load_settings() -> dict:
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
    settings["pricing"] = _default_pricing()
    path = _settings_path()
    if path.is_file():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            stored = {}
        for quality in ("draft", "hq"):
            if isinstance(stored.get(quality), dict):
                settings[quality].update({
                    k: v for k, v in stored[quality].items()
                    if k in ("model", "resolution") and isinstance(v, str) and v.strip()
                })
        if isinstance(stored.get("ai_extraction"), bool):
            settings["ai_extraction"] = stored["ai_extraction"]
        stored_image_model = stored.get("image_model")
        if (isinstance(stored_image_model, str) and stored_image_model.strip()
                and stored_image_model.strip() in image_model_options()):
            settings["image_model"] = stored_image_model.strip()
        _merge_pricing(settings["pricing"], stored.get("pricing"))
    return settings


def save_settings(update: dict) -> dict:
    settings = load_settings()
    for quality in ("draft", "hq"):
        incoming = update.get(quality)
        if isinstance(incoming, dict):
            model = str(incoming.get("model", "")).strip()
            resolution = str(incoming.get("resolution", "")).strip()
            if model:
                settings[quality]["model"] = model
            if resolution:
                if resolution not in VALID_RESOLUTIONS:
                    raise BridgeError(f"resolution must be one of {VALID_RESOLUTIONS}, got: {resolution!r}")
                settings[quality]["resolution"] = resolution
    if "ai_extraction" in update:
        settings["ai_extraction"] = bool(update["ai_extraction"])
    if "image_model" in update:
        image_model = str(update.get("image_model") or "").strip()
        if not image_model:
            raise BridgeError("image_model must not be empty.")
        allowed = image_model_options()
        if image_model not in allowed:
            raise BridgeError(
                f"image_model must be one of {tuple(allowed)}, got: {image_model!r}"
            )
        settings["image_model"] = image_model
    _merge_pricing(settings["pricing"], update.get("pricing"))
    ensure_data_dirs()
    with _settings_path().open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")
    audit("settings_saved", draft=settings["draft"], hq=settings["hq"],
          ai_extraction=settings["ai_extraction"], image_model=settings["image_model"],
          pricing=settings["pricing"])
    return settings


# --------------------------------------------------------------------------- #
# API keys (.env management). Key VALUES never leave the server: the API      #
# accepts them for storage and only ever reports presence booleans back.      #
# --------------------------------------------------------------------------- #
ENV_PATH = REPO_ROOT / ".env"
MANAGED_ENV_KEYS = ("GEMINI_API_KEY", "ELEVENLABS_API_KEY")
_PLACEHOLDER_MARKERS = ("your-", "changeme", "xxxx")


def _env_file_values() -> dict:
    """Parse .env into {NAME: value}. Internal only - values are injected into
    engine subprocess environments and never serialized to any API response."""
    values = {}
    if ENV_PATH.is_file():
        try:
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, value = stripped.partition("=")
                    values[key.strip()] = value.strip().strip('"').strip("'")
        except OSError:
            pass
    return values


def _key_is_set(name: str) -> bool:
    value = _env_file_values().get(name) or os.environ.get(name) or ""
    return bool(value) and not any(marker in value.lower() for marker in _PLACEHOLDER_MARKERS)


def set_env_key(name: str, value: str | None = None, clear: bool = False) -> dict:
    if name not in MANAGED_ENV_KEYS:
        raise BridgeError(f"Unknown key {name!r}. Managed keys: {', '.join(MANAGED_ENV_KEYS)}.")
    lines = []
    if ENV_PATH.is_file():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    if clear:
        lines = [l for l in lines if not l.strip().startswith(f"{name}=")]
        os.environ.pop(name, None)
    else:
        value = str(value or "").strip()
        if not value:
            raise BridgeError("Key value is empty.")
        if "\n" in value or "\r" in value or len(value) > 400:
            raise BridgeError("Key value looks malformed (newlines or too long).")
        replaced = False
        for index, line in enumerate(lines):
            if line.strip().startswith(f"{name}="):
                lines[index] = f"{name}={value}"
                replaced = True
                break
        if not replaced:
            lines.append(f"{name}={value}")
        os.environ[name] = value

    ENV_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    audit("env_key_" + ("cleared" if clear else "set"), key=name)  # never the value
    return {"key": name, "configured": _key_is_set(name)}


def engine_subprocess_env() -> dict:
    """Environment for engine subprocesses: current env + .env values (so keys
    saved via the admin panel reach the engine) + unbuffered output."""
    env = {**os.environ}
    for key, value in _env_file_values().items():
        if value and not any(marker in value.lower() for marker in _PLACEHOLDER_MARKERS):
            env.setdefault(key, value)
    env["PYTHONUNBUFFERED"] = "1"
    return env


# --------------------------------------------------------------------------- #
# Health & capabilities                                                        #
# --------------------------------------------------------------------------- #
def python_deps() -> dict:
    """Which engine python dependencies are importable. The UI itself needs
    none of them; live stages do."""
    deps = {}
    for label, spec_name in (("requests", "requests"), ("dotenv", "dotenv"), ("google_genai", "google.genai")):
        try:
            deps[label] = importlib.util.find_spec(spec_name) is not None
        except (ImportError, ValueError, ModuleNotFoundError):
            deps[label] = False
    return deps


def capabilities() -> dict:
    """What can actually run right now. The app always runs; these gate which
    PAID stages would succeed, so the UI can say so instead of failing late."""
    import shutil as _shutil
    deps = python_deps()
    gemini = _key_is_set("GEMINI_API_KEY")
    elevenlabs = _key_is_set("ELEVENLABS_API_KEY")
    ffmpeg = _shutil.which("ffmpeg") is not None
    caps = {
        "dry_run": ADAPTER_PATH.is_file(),
        "veo_generation": gemini and deps["google_genai"],
        "music": gemini and deps["requests"] and deps["dotenv"],
        "voice_sts": elevenlabs and deps["requests"] and deps["dotenv"],
        "assemble": ffmpeg,
        "ai_extraction": gemini,  # stdlib HTTP; only the key is needed
    }
    missing = {
        "veo_generation": [] if caps["veo_generation"] else
            (["Gemini API key"] if not gemini else []) + ([] if deps["google_genai"] else ["google-genai package"]),
        "music": [] if caps["music"] else
            (["Gemini API key"] if not gemini else []) + [f"{d} package" for d in ("requests", "dotenv") if not deps[d]],
        "voice_sts": [] if caps["voice_sts"] else
            (["ElevenLabs API key"] if not elevenlabs else []) + [f"{d} package" for d in ("requests", "dotenv") if not deps[d]],
        "assemble": [] if ffmpeg else ["ffmpeg on PATH"],
    }
    return {"capabilities": caps, "missing": missing}


def health() -> dict:
    import shutil as _shutil
    return {
        "ok": ADAPTER_PATH.is_file(),
        "repo_root": str(REPO_ROOT),
        "adapter": ADAPTER_REL.as_posix(),
        "adapter_exists": ADAPTER_PATH.is_file(),
        "python": sys.version.split()[0],
        "ffmpeg": _shutil.which("ffmpeg") is not None,
        "ffprobe": _shutil.which("ffprobe") is not None,
        # Booleans only - the UI never sees key material.
        "gemini_key_configured": _key_is_set("GEMINI_API_KEY"),
        "elevenlabs_key_configured": _key_is_set("ELEVENLABS_API_KEY"),
        "python_deps": python_deps(),
        **capabilities(),
        "confirm_phrase": CONFIRM_PHRASE,
        "time": utc_now(),
    }
