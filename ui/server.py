"""Operator UI server for the VEO ad pipeline.

Stdlib-only on purpose: `python ui/server.py` works with no pip installs.
Serves the static operator console and a JSON API that wraps
video_generation_agency/run_from_packet.py via ui/engine_bridge.py.

Binds to 127.0.0.1 by default - this is an internal operator tool.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine_bridge as bridge  # noqa: E402
import characters  # noqa: E402
import simple_flow  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 8765

JSON_CT = "application/json; charset=utf-8"
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "VeoAdPipelineUI/1.0"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------ #
    # Plumbing                                                            #
    # ------------------------------------------------------------------ #
    def log_message(self, fmt, *args):  # quieter default log line
        sys.stderr.write("[ui] %s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", JSON_CT)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"error": str(message)}, status=status)

    def read_body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise bridge.BridgeError(f"Request body is not valid JSON: {exc}")
        if not isinstance(data, dict):
            raise bridge.BridgeError("Request body must be a JSON object.")
        return data

    def query(self):
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    # ------------------------------------------------------------------ #
    # Routing                                                             #
    # ------------------------------------------------------------------ #
    def do_GET(self):
        route = urlparse(self.path).path
        try:
            if route == "/api/health":
                return self.send_json(bridge.health())
            if route == "/api/packets":
                return self.send_json({
                    "saved": bridge.list_saved_packets(),
                    "examples": bridge.list_example_packets(),
                })
            if route == "/api/packet":
                return self.send_json(bridge.load_packet_file(self.query().get("path", "")))
            if route == "/api/dryrun/state":
                return self.send_json(bridge.dryrun_state(self.query().get("path", "")))
            if route == "/api/runs":
                return self.send_json({"runs": bridge.list_runs()})
            if route.startswith("/api/runs/"):
                ui_run_id = route.rsplit("/", 1)[-1]
                return self.send_json(bridge.run_status(ui_run_id))
            if route == "/api/auditions":
                return self.send_json(bridge.list_auditions(self.query().get("dir", "")))
            if route == "/api/fs":
                return self.send_json(bridge.fs_list(self.query().get("path") or None))
            if route == "/api/media":
                return self.serve_media(self.query().get("path", ""))
            if route == "/api/settings":
                return self.send_json({
                    "settings": bridge.load_settings(),
                    "tiers": bridge.tiers_config(),
                    # The allow-list the admin image-model dropdown renders from
                    # (the IMAGE_TIERS models). load_settings() carries the
                    # currently-configured image_model.
                    "image_model_options": bridge.image_model_options(),
                    "keys": {name: bridge._key_is_set(name) for name in bridge.MANAGED_ENV_KEYS},
                    "python_deps": bridge.python_deps(),
                    **bridge.capabilities(),
                })
            if route == "/api/simple/tiers":
                # The Phase-A render tiers (video + image) with their REAL rates,
                # plus the runaway-guard cap. Pure data; gates live elsewhere.
                return self.send_json(bridge.tiers_config())
            if route == "/api/simple/jobs":
                return self.send_json({"jobs": simple_flow.list_jobs()})
            if route == "/api/simple/job":
                return self.send_json(simple_flow.open_job(self.query().get("dir", "")))
            if route == "/api/simple/characters":
                job_dir = self.query().get("dir", "")
                if not str(job_dir).strip():
                    raise bridge.BridgeError("dir is required.")
                doc = characters.load_characters(job_dir)
                return self.send_json({
                    "ok": True,
                    "characters": doc["characters"],
                    "assignments": doc["assignments"],
                })
            if route == "/api/simple/estimate":
                q = self.query()
                return self.send_json(simple_flow.estimate(
                    q.get("dir", ""), q.get("quality", ""),
                    q.get("max_scenes") or None,  # _normalize_max_scenes validates
                ))
            if route == "/api/simple/storyboard/estimate":
                q = self.query()
                # No image_tier -> the admin-configured user model (free to user).
                return self.send_json(simple_flow.estimate_storyboard(
                    q.get("dir", ""), q.get("image_tier"),
                    q.get("images_per_scene") or 1,
                ))
            return self.serve_static(route)
        except bridge.BridgeError as exc:
            return self.send_error_json(exc, status=400)
        except BrokenPipeError:
            pass
        except ConnectionAbortedError:
            pass
        except Exception as exc:  # surface, never hide
            return self.send_error_json(f"Internal error: {exc}", status=500)

    def do_POST(self):
        route = urlparse(self.path).path
        try:
            if route == "/api/upload/image":
                return self.handle_image_upload()
            if route == "/api/simple/upload":
                return self.handle_upload()
            body = self.read_body_json()
            if route == "/api/packet/build":
                packet = bridge.build_packet_from_form(body.get("form") or {})
                return self.send_json({
                    "packet": packet,
                    "structured": bridge.structured_review(packet),
                })
            if route == "/api/packet/review":
                packet = body.get("packet")
                if not isinstance(packet, dict):
                    raise bridge.BridgeError("Body must include a 'packet' object.")
                return self.send_json({"structured": bridge.structured_review(packet)})
            if route == "/api/packet/save":
                packet = body.get("packet")
                if isinstance(body.get("packet_text"), str):
                    try:
                        packet = json.loads(body["packet_text"])
                    except json.JSONDecodeError as exc:
                        raise bridge.BridgeError(f"Pasted packet is not valid JSON: {exc}")
                if not isinstance(packet, dict):
                    raise bridge.BridgeError("Body must include 'packet' (object) or 'packet_text' (JSON string).")
                saved = bridge.save_packet(packet, body.get("name"))
                return self.send_json({**saved, "packet": packet})
            if route == "/api/packet/authorize":
                if "allow" not in body:
                    raise bridge.BridgeError("Body must include 'allow' (true/false).")
                return self.send_json(
                    bridge.set_spend_authorization(body.get("path", ""), bool(body["allow"]))
                )
            if route == "/api/dryrun":
                return self.send_json(bridge.dry_run(body.get("path", "")))
            if route == "/api/engineplan":
                return self.send_json(bridge.engine_plan(body.get("path", "")))
            if route == "/api/run/live":
                result = bridge.start_live_run(body.get("path", ""), body.get("confirm", ""))
                return self.send_json(result)
            if route == "/api/voice/select":
                return self.send_json(bridge.select_voice(body))
            if route == "/api/scenes/inspect":
                return self.send_json(
                    bridge.inspect_scenes(body.get("path", ""), body.get("max_scenes"))
                )
            if route == "/api/simple/author":
                return self.send_json(simple_flow.author_job(body))
            if route == "/api/simple/estimate":
                return self.send_json(simple_flow.estimate(
                    body.get("job_dir", ""), body.get("quality", ""), body.get("max_scenes"),
                ))
            if route == "/api/simple/confirm-token":
                # Mints a single-use token bound to this exact job+quality+cap+
                # estimate; /api/simple/generate consumes it instead of a typed
                # phrase. The token authorizes nothing on its own. `quality` may
                # be a legacy quality (draft/hq) or a video render-tier key.
                return self.send_json(simple_flow.issue_confirmation(
                    body.get("job_dir", ""), body.get("quality", ""), body.get("max_scenes"),
                ))
            if route == "/api/simple/storyboard/estimate":
                # No image_tier -> the admin-configured user model (free to user).
                return self.send_json(simple_flow.estimate_storyboard(
                    body.get("job_dir", ""), body.get("image_tier"),
                    body.get("images_per_scene", 1),
                ))
            if route == "/api/simple/storyboard/confirm-token":
                # Mints a single-use token for a PAID image tier bound to this
                # exact job+image_tier+image_count+estimate. The FREE Basic tier
                # is ungated and rejects token minting (no gate for the free tier).
                return self.send_json(simple_flow.issue_storyboard_confirmation(
                    body.get("job_dir", ""), body.get("image_tier", ""),
                    body.get("images_per_scene", 1),
                ))
            if route == "/api/simple/storyboard":
                # Storyboard images. The DEFAULT user path takes NO image_tier:
                # it renders with the admin-configured image model (free, ungated,
                # bounded by the runaway cap). Passing an explicit image_tier uses
                # the legacy/admin gated-tier path (paid tiers REQUIRE a valid
                # storyboard confirm-token). Images are served via /api/media.
                return self.send_json(simple_flow.storyboard_generate(
                    body.get("job_dir", ""), body.get("image_tier"),
                    body.get("images_per_scene", 1), body.get("confirm_token"),
                ))
            if route == "/api/simple/scene-image":
                # Generate (once) + cache a concept image for one scene, returned
                # as a repo-relative path the path-safe media endpoint can serve.
                return self.send_json(simple_flow.scene_image(
                    body.get("job_dir", ""), body.get("scene_index"),
                ))
            if route == "/api/simple/edit-scenes":
                # Rewrite one scene's prompt (scope = 1-based index) or all
                # prompts (scope = "all") via one Gemini text call, update
                # scenes.json + the affected summaries, and regenerate the
                # affected storyboard images. NEVER triggers video generation
                # and NEVER touches the video confirm-token gates.
                return self.send_json(simple_flow.edit_scenes(
                    body.get("job_dir", ""), body.get("scope"),
                    body.get("instruction", ""),
                ))
            if route == "/api/simple/characters":
                job_dir = body.get("job_dir", "")
                if not str(job_dir).strip():
                    raise bridge.BridgeError("job_dir is required.")
                result = characters.save_characters(
                    job_dir,
                    body.get("characters"),
                    body.get("assignments"),
                )
                applied = characters.apply_characters_to_job(job_dir)
                return self.send_json({
                    "ok": True,
                    "characters": result["characters"],
                    "assignments": result["assignments"],
                    "changed": applied["changed"],
                    "prompts": applied["prompts"],
                })
            if route == "/api/simple/generate":
                # Simple mode: a server-issued one-time confirm_token replaces the
                # typed SPEND phrase. A blind POST with no valid token is refused.
                return self.send_json(simple_flow.generate(
                    body.get("job_dir", ""), body.get("quality", ""),
                    body.get("confirm_token", ""), body.get("max_scenes"),
                ))
            if route == "/api/settings/models":
                return self.send_json({"settings": bridge.save_settings(body)})
            if route == "/api/settings/key":
                # Accepts a key VALUE for storage; the response (and every other
                # endpoint) only ever reports presence booleans.
                return self.send_json(bridge.set_env_key(
                    body.get("name", ""), body.get("value"), clear=bool(body.get("clear")),
                ))
            return self.send_error_json("Unknown API route.", status=404)
        except bridge.BridgeError as exc:
            return self.send_error_json(exc, status=400)
        except BrokenPipeError:
            pass
        except ConnectionAbortedError:
            pass
        except Exception as exc:
            return self.send_error_json(f"Internal error: {exc}", status=500)

    def handle_upload(self):
        """Raw-body document upload: POST /api/simple/upload?name=<filename>
        with the file bytes as the request body (no multipart parsing needed)."""
        name = self.query().get("name", "")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise bridge.BridgeError("Empty upload.")
        if length > 22 * 1024 * 1024:
            raise bridge.BridgeError("Document is too large (20 MB cap).")
        data = self.rfile.read(length)
        return self.send_json(simple_flow.save_upload(name, data))

    def handle_image_upload(self):
        """Raw-body image upload: POST /api/upload/image?name=<filename>."""
        name = self.query().get("name", "")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise bridge.BridgeError("Empty image upload.")
        if length > simple_flow.IMAGE_UPLOAD_MAX_BYTES:
            raise bridge.BridgeError("Image is too large (10 MB cap).")
        data = self.rfile.read(length)
        return self.send_json(simple_flow.save_image_upload(name, data))

    # ------------------------------------------------------------------ #
    # Static + media                                                      #
    # ------------------------------------------------------------------ #
    def serve_static(self, route: str):
        if route in ("/", "/index.html"):
            route = "/index.html"
        target = (STATIC_DIR / route.lstrip("/")).resolve()
        try:
            target.relative_to(STATIC_DIR)
        except ValueError:
            return self.send_error_json("Not found.", status=404)
        if not target.is_file():
            return self.send_error_json("Not found.", status=404)
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def serve_media(self, raw_path: str):
        """Serve a repo-internal media/report file with basic Range support so
        <audio>/<video> seeking works."""
        path = bridge.safe_path(raw_path)
        if not path.is_file():
            return self.send_error_json(f"File not found: {raw_path}", status=404)
        if path.suffix.lower() not in bridge.MEDIA_EXTENSIONS:
            return self.send_error_json(
                f"Refusing to serve {path.suffix!r} files over the media endpoint.", status=400
            )
        size = path.stat().st_size
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        range_header = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        if range_header:
            match = RANGE_RE.match(range_header.strip())
            if match:
                if match.group(1):
                    start = int(match.group(1))
                    if match.group(2):
                        end = min(int(match.group(2)), size - 1)
                elif match.group(2):  # suffix range: last N bytes
                    suffix = int(match.group(2))
                    start = max(0, size - suffix)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    return
                remaining -= len(chunk)


def main():
    parser = argparse.ArgumentParser(description="VEO ad pipeline operator UI server.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1, internal tool).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (default {DEFAULT_PORT}).")
    args = parser.parse_args()

    # The adapter and all packet paths are repo-relative; run from the root.
    os.chdir(bridge.REPO_ROOT)
    bridge.ensure_data_dirs()

    server = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    print(f"VEO Ad Pipeline operator UI -> http://{args.host}:{args.port}")
    print(f"Repo root: {bridge.REPO_ROOT}")
    print("Dry-run is free and the default. Live runs require explicit double confirmation.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
