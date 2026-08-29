from __future__ import annotations

import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .database import Database
from .services import BitPornTrackerValidator, UpdateChecker
from .workflow import Workflow


def choose_local_folder(initial_path: str = "") -> str:
    """Open the local machine's native folder picker and return the chosen path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError("The native folder picker is unavailable on this Python installation") from exc

    root = tk.Tk()
    try:
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        options = {"title": "Select a folder"}
        candidate = Path(initial_path).expanduser()
        if candidate.is_dir():
            options["initialdir"] = str(candidate)
        return str(filedialog.askdirectory(**options) or "")
    finally:
        root.destroy()


class AppServer:
    def __init__(self, db: Database, workflow: Workflow, root: Path, host: str, port: int):
        self.db = db
        self.workflow = workflow
        self.root = root
        self.httpd = ThreadingHTTPServer((host, port), self._handler())

    def _handler(self):
        db, workflow, root = self.db, self.workflow, self.root

        class Handler(BaseHTTPRequestHandler):
            server_version = "PumpkinForge/1.0"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def send_json(self, value: Any, status: int = 200) -> None:
                payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 5 * 1024 * 1024:
                    raise ValueError("Request body too large")
                raw = self.rfile.read(length) if length else b"{}"
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("JSON body must be an object")
                return value

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                try:
                    if parsed.path == "/api/state":
                        settings = db.settings()
                        public_settings = dict(settings)
                        for secret in ["theporndb_api_token", "stashdb_api_token"]:
                            public_settings[f"{secret}_configured"] = bool(settings.get(secret))
                            public_settings[secret] = ""
                        update_checker = UpdateChecker(root.parent, settings)
                        return self.send_json({"settings": public_settings, "app_version": update_checker.local_version(), "update": update_checker.cached(), "trackers": public_trackers(), "folders": db.folder_rows(), "jobs": db.job_rows(), "monitor_status": workflow.monitor_status_snapshot()})
                    if parsed.path == "/api/trackers":
                        return self.send_json(public_trackers())
                    if parsed.path == "/api/folders":
                        return self.send_json(db.folder_rows())
                    if parsed.path == "/api/browse-folder":
                        selected = choose_local_folder()
                        return self.send_json({"ok": True, "path": selected, "cancelled": not bool(selected)})
                    if parsed.path.startswith("/api/jobs/"):
                        parts = parsed.path.split("/")
                        if len(parts) == 4 and parts[3].isdigit():
                            job = db.job(int(parts[3]))
                            return self.send_json(job or {"error": "Job not found"}, 200 if job else 404)
                        if len(parts) == 6 and parts[3].isdigit() and parts[4] == "image" and parts[5].isdigit():
                            return self.send_image(int(parts[3]), int(parts[5]))
                    return self.serve_static(parsed.path)
                except Exception as exc:
                    self.send_json({"error": str(exc)}, 500)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                try:
                    body = self.read_json()
                    if parsed.path == "/api/browse-folder":
                        selected = choose_local_folder(str(body.get("initial_path", "")))
                        return self.send_json({"ok": True, "path": selected, "cancelled": not bool(selected)})
                    if parsed.path == "/api/settings":
                        current = db.settings()
                        for secret in ["theporndb_api_token", "stashdb_api_token"]:
                            if not str(body.get(secret, "") or "").strip() and current.get(secret):
                                body[secret] = current[secret]
                        for key in ["metadata_auto_identify", "metadata_theporndb_enabled", "metadata_stashdb_enabled"]:
                            if key in body:
                                body[key] = str(body[key]).strip().lower() in {"1", "true", "yes", "on"}
                        for key in ["metadata_search_results", "metadata_min_confidence", "metadata_timeout_seconds"]:
                            if key in body:
                                body[key] = int(body[key])
                        # Pumpkin Forge branding is fixed and is not user-configurable.
                        body["application_name"] = "Pumpkin Forge"
                        db.save_settings(body)
                        settings = db.settings()
                        public_settings = dict(settings)
                        for secret in ["theporndb_api_token", "stashdb_api_token"]:
                            public_settings[f"{secret}_configured"] = bool(settings.get(secret))
                            public_settings[secret] = ""
                        return self.send_json({"ok": True, "settings": public_settings})
                    if parsed.path == "/api/update-check":
                        settings = db.settings()
                        result = UpdateChecker(root.parent, settings).check()
                        db.save_settings({"last_update_check_at": result.get("checked_at", ""), "last_remote_version": result.get("remote_version", ""), "last_update_error": result.get("error", "")})
                        return self.send_json({"ok": not result.get("error"), "update": result})
                    if parsed.path == "/api/trackers":
                        tracker_id = int(body.pop("id", 0) or 0) or None
                        if not tracker_id and not body.get("name"):
                            raise ValueError("Tracker name is required")
                        if tracker_id:
                            existing = db.tracker(tracker_id) or {}
                            if not body.get("api_key"):
                                body["api_key"] = existing.get("api_key", "")
                        saved = db.save_tracker(normalize_tracker(body), tracker_id)
                        return self.send_json({"ok": True, "id": saved, "trackers": public_trackers()})
                    if parsed.path == "/api/folders":
                        folder_id = int(body.pop("id", 0) or 0) or None
                        if not body.get("path"):
                            raise ValueError("Folder path is required")
                        saved = db.save_folder(normalize_folder(body), folder_id)
                        return self.send_json({"ok": True, "id": saved, "folders": db.folder_rows()})
                    if parsed.path == "/api/jobs":
                        job_id = workflow.enqueue(str(body.get("source_path", "")), int(body.get("tracker_id") or 0) or None, body.get("defaults") or {})
                        workflow.process_now(job_id)
                        return self.send_json({"ok": True, "id": job_id}, 201)
                    parts = parsed.path.split("/")
                    if len(parts) == 5 and parts[2] == "jobs" and parts[3].isdigit():
                        job_id = int(parts[3])
                        action = unquote(parts[4]).strip().lower()
                        if action == "process":
                            workflow.process_now(job_id)
                        elif action == "retry":
                            workflow.retry(job_id)
                        elif action == "clear":
                            if not db.delete_job(job_id):
                                raise ValueError("Job not found")
                            return self.send_json({"ok": True, "cleared": job_id})
                        elif action == "description":
                            workflow.save_description(job_id, body)
                        elif action == "regenerate-thumbnails":
                            workflow.regenerate_thumbnails(job_id)
                        elif action == "refresh-metadata":
                            workflow.refresh_metadata(job_id)
                        elif action == "select-metadata":
                            workflow.select_metadata_match(job_id, body)
                        elif action == "approve":
                            workflow.approve_and_upload(job_id)
                        else:
                            raise ValueError("Unknown job action")
                        return self.send_json({"ok": True, "job": db.job(job_id)})
                    self.send_json({"error": "Not found"}, 404)
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 400)
                except Exception as exc:
                    self.send_json({"error": str(exc)}, 500)

            def send_image(self, job_id: int, image_id: int) -> None:
                row = db.conn.execute("SELECT path FROM job_images WHERE id=? AND job_id=?", (image_id, job_id)).fetchone()
                if not row or not Path(row["path"]).is_file():
                    return self.send_json({"error": "Image not found"}, 404)
                path = Path(row["path"]).resolve()
                data = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def serve_static(self, path: str) -> None:
                relative = "index.html" if path in {"", "/"} else path.removeprefix("/static/").lstrip("/")
                candidate = (root / "static" / relative).resolve()
                static_root = (root / "static").resolve()
                if static_root not in candidate.parents and candidate != static_root or not candidate.is_file():
                    return self.send_json({"error": "Not found"}, 404)
                data = candidate.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        def public_trackers() -> list[dict[str, Any]]:
            result = []
            for tracker in db.tracker_rows():
                check = BitPornTrackerValidator.validate(tracker.get("announce_url", ""))
                item = dict(tracker)
                item["api_key"] = ""
                item["api_key_configured"] = bool(tracker.get("api_key"))
                item["bitporn_compatible"] = check.valid
                item["bitporn_validation_reason"] = check.reason
                result.append(item)
            return result

        def normalize_tracker(value: dict[str, Any]) -> dict[str, Any]:
            value = dict(value)
            for field in ["category_map_json", "type_map_json", "resolution_map_json", "tag_map_json", "default_tags_json", "custom_fields_json"]:
                if field in value and not isinstance(value[field], str):
                    value[field] = json.dumps(value[field])
            return value

        def normalize_folder(value: dict[str, Any]) -> dict[str, Any]:
            value = dict(value)
            for field in ["ignore_patterns_json", "include_patterns_json"]:
                if field in value and not isinstance(value[field], str):
                    value[field] = json.dumps(value[field])
            return value

        return Handler

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()
