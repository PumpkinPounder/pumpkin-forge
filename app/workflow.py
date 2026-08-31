from __future__ import annotations

import json
import fnmatch
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from .database import Database, utc_now
from .services import (
    BITPORN_IMAGE_HOST_BLOCK_MESSAGE,
    BitPornUploadAmbiguous,
    BitPornImageHostService,
    BitPornTrackerClient,
    BitPornTrackerValidator,
    contains_bitporn_image_url,
    is_bitporn_tracker,
    IMAGE_EXTENSIONS,
    DuplicateService,
    MediaScanner,
    MetadataService,
    ThumbItService,
    TorrentService,
    VIDEO_EXTENSIONS,
)


LOOSE_MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
LOOSE_MEDIA_TEMP_SUFFIXES = {".part", ".tmp", ".partial", ".crdownload", ".download", ".!qb"}


class Workflow:
    def __init__(self, db: Database):
        self.db = db
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._worker_loop, name="pumpkin-worker", daemon=True)
        self.monitor = threading.Thread(target=self._monitor_loop, name="pumpkin-monitor", daemon=True)
        self._monitor_status_lock = threading.Lock()
        self._loose_batches: dict[int, dict[str, Any]] = {}
        self._loose_file_states: dict[tuple[int, str], tuple[int, int, int]] = {}
        self._monitor_status: dict[str, Any] = {"active": False, "processed": 0, "total": 0, "remaining": 0}

    def start(self) -> None:
        if not self.worker.is_alive():
            self.worker.start()
        if not self.monitor.is_alive():
            self.monitor.start()

    def stop(self) -> None:
        self.stop_event.set()

    def monitor_status_snapshot(self) -> dict[str, Any]:
        with self._monitor_status_lock:
            return dict(self._monitor_status)

    def enqueue(self, source_path: str, tracker_id: int | None = None, defaults: dict[str, Any] | None = None) -> int:
        settings = self.db.settings()
        tracker_id = tracker_id or self.db.ensure_default_tracker()
        tracker = self.db.tracker(tracker_id)
        if not tracker:
            raise RuntimeError("Selected tracker does not exist")
        job_id = self.db.create_job(source_path, tracker_id, tracker["announce_url"], defaults)
        return job_id

    def process_now(self, job_id: int) -> None:
        thread = threading.Thread(target=self._process_job_safe, args=(job_id,), daemon=True)
        thread.start()

    def regenerate_thumbnails(self, job_id: int) -> None:
        job = self.db.job(job_id)
        if not job:
            raise RuntimeError("Job not found")
        if job["status"] in {"Uploading", "Completed"}:
            raise RuntimeError("Thumbnails cannot be regenerated in the current state")
        self.db.update_job(job_id, status="Generating Images", stage="Regenerating Images", progress=30, error="")
        self.db.log(job_id, "Thumbnail regeneration requested")
        thread = threading.Thread(target=self._regenerate_thumbnails_safe, args=(job_id,), daemon=True)
        thread.start()

    def refresh_metadata(self, job_id: int) -> None:
        job = self.db.job(job_id)
        if not job:
            raise RuntimeError("Job not found")
        thread = threading.Thread(target=self._refresh_metadata_safe, args=(job_id,), daemon=True)
        thread.start()

    def _refresh_metadata_safe(self, job_id: int) -> None:
        try:
            job = self.db.job(job_id)
            if not job:
                return
            settings = self.db.settings()
            files = [{"file_name": item.get("file_name"), "relative_path": item.get("relative_path"), "is_video": bool(item.get("is_video"))} for item in job.get("files", [])]
            metadata = MetadataService(settings, self.db).identify(job["source_path"], files, job.get("media", {}))
            self.db.update_job(job_id, metadata_json=metadata)
            self.db.log(job_id, f"Metadata refresh complete: {len(metadata.get('matches', []))} candidate(s)")
        except Exception as exc:
            self.db.log(job_id, f"Metadata refresh failed: {exc}", "warning")

    def select_metadata_match(self, job_id: int, values: dict[str, Any]) -> None:
        job = self.db.job(job_id)
        if not job:
            raise RuntimeError("Job not found")
        metadata = job.get("metadata") or {}
        matches = metadata.get("matches") or []
        provider = str(values.get("provider", ""))
        try:
            index = int(values.get("index"))
        except (TypeError, ValueError):
            raise ValueError("Metadata match selection is invalid")
        selected = matches[index] if 0 <= index < len(matches) else None
        if not selected or selected.get("provider") != provider:
            raise ValueError("Metadata match is no longer available")
        metadata["selected"] = selected
        tags = selected.get("tags") or []
        updates: dict[str, Any] = {"metadata_json": metadata}
        if selected.get("title"):
            updates["upload_title"] = str(selected["title"])
        if tags:
            updates["tags_json"] = [str(tag) for tag in tags if str(tag).strip()]
        self.db.update_job(job_id, **updates)
        self.db.log(job_id, f"Selected {provider} metadata match: {selected.get('title') or selected.get('provider_id')}")

    def _regenerate_thumbnails_safe(self, job_id: int) -> None:
        try:
            job = self.db.job(job_id)
            if not job:
                return
            settings = self.db.settings()
            ThumbItService(settings, self.db).generate_or_import(job_id, job["source_path"], force=True)
            self.db.update_job(job_id, status="Awaiting Description", stage="Awaiting Description", progress=78, error="")
            self.db.log(job_id, "Thumbnail regeneration completed")
        except Exception as exc:
            self.db.update_job(job_id, status="Failed", stage="Thumbnail Regeneration Failed", error=str(exc))
            self.db.log(job_id, str(exc), "error")

    def approve_and_upload(self, job_id: int) -> None:
        self.db.update_job(job_id, status="Uploading", stage="Uploading", progress=95, error="")
        thread = threading.Thread(target=self._upload_job_safe, args=(job_id,), daemon=True)
        thread.start()

    def retry(self, job_id: int) -> None:
        job = self.db.job(job_id)
        if not job:
            raise RuntimeError("Job not found")
        if job["status"] in {"Completed", "Uploading"}:
            raise RuntimeError("This job cannot be retried in its current state")
        self.db.update_job(job_id, status="Detected", stage="Detected", progress=0, error="")
        self.db.log(job_id, "Job queued for retry")
        self.process_now(job_id)

    def save_description(self, job_id: int, values: dict[str, Any]) -> None:
        job = self.db.job(job_id)
        if not job:
            raise RuntimeError("Job not found")
        description = str(values.get("description", ""))
        tags = values.get("tags", [])
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        def flag(name: str) -> Any:
            return values[name] if name in values else job.get(name)
        self.db.update_job(job_id, upload_title=str(values.get("upload_title", job["upload_title"])), category=str(values.get("category", job.get("category", ""))), type=str(values.get("type", job.get("type", ""))), resolution=str(values.get("resolution", job.get("resolution", ""))), tags_json=tags, description=description, description_saved_at=utc_now(), anonymous=flag("anonymous"), moderation_queue=flag("moderation_queue"), personal_release=flag("personal_release"), internal_release=flag("internal"), status="Final Review", stage="Description Draft Saved", progress=85)
        self.db.log(job_id, "Description draft saved")

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                if self.db.settings().get("auto_start_processing", True):
                    jobs = [job for job in self.db.job_rows() if job["status"] in {"Detected", "Waiting For Files"}]
                    for job in jobs[:2]:
                        self._process_job_safe(int(job["id"]))
            except Exception:
                pass
            self.stop_event.wait(2)

    def _monitor_loop(self) -> None:
        last_scan: dict[int, float] = {}
        while not self.stop_event.is_set():
            try:
                now = time.time()
                for folder in self.db.folder_rows():
                    if not folder["enabled"] or now - last_scan.get(int(folder["id"]), 0) < int(folder["scan_interval_seconds"] or 20):
                        continue
                    last_scan[int(folder["id"])] = now
                    root = Path(folder["path"])
                    if not root.is_dir():
                        continue
                    entries = list(root.rglob("*") if folder["include_subfolders"] else root.iterdir())
                    self._organize_loose_media(folder, root, entries, now)
                    for entry in entries:
                        if not entry.is_dir() or entry.name.startswith("."):
                            continue
                        if now - entry.stat().st_mtime < int(folder["minimum_folder_age_seconds"] or 0):
                            continue
                        tracker_id = int(folder["default_tracker_id"] or self.db.ensure_default_tracker())
                        defaults = {"category": folder["default_category"], "type": folder["default_type"], "resolution": folder["default_resolution"], "anonymous": folder["default_anonymous"], "moderation_queue": folder["default_moderation_queue"], "personal_release": folder["default_personal_release"], "internal": folder["default_internal"], "auto_upload": folder["auto_upload"]}
                        job_id = self.enqueue(str(entry), tracker_id, defaults)
                        self.db.log(job_id, f"Detected by monitored folder: {folder['name']}")
                self._refresh_monitor_status()
            except Exception:
                pass
            self.stop_event.wait(2)

    def _organize_loose_media(self, folder: dict[str, Any], root: Path, entries: list[Path], now: float) -> None:
        folder_id = int(folder["id"])
        patterns = self._folder_patterns(folder.get("ignore_patterns_json", "[]"))
        minimum_age = int(folder.get("minimum_folder_age_seconds") or 0)
        stable_checks = max(1, min(int(folder.get("stable_checks") or 2), 10))
        loose: list[Path] = []
        for entry in entries:
            if not entry.is_file() or entry.name.startswith("."):
                continue
            if entry.parent != root:
                continue
            if entry.suffix.lower() not in LOOSE_MEDIA_EXTENSIONS or entry.suffix.lower() in LOOSE_MEDIA_TEMP_SUFFIXES:
                continue
            if any(fnmatch.fnmatch(entry.name, pattern) for pattern in patterns):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            key = (folder_id, str(entry))
            previous = self._loose_file_states.get(key)
            signature = (int(stat.st_size), int(stat.st_mtime_ns))
            stable_count = previous[2] + 1 if previous and previous[:2] == signature else 1
            self._loose_file_states[key] = (signature[0], signature[1], stable_count)
            if now - stat.st_mtime >= minimum_age and stable_count >= stable_checks:
                loose.append(entry)

        batch = self._loose_batches.get(folder_id)
        if not loose:
            if batch:
                self._loose_batches.pop(folder_id, None)
            return
        if not batch:
            batch = {"name": folder["name"], "total": len(loose), "processed": 0, "remaining": len(loose)}
            self._loose_batches[folder_id] = batch
        else:
            batch["total"] = max(int(batch["total"]), int(batch["processed"]) + len(loose))
            batch["remaining"] = len(loose)

        groups: dict[Path, list[Path]] = {}
        for path in loose:
            groups.setdefault(path.with_suffix(""), []).append(path)
        destination, group = sorted(groups.items(), key=lambda item: str(item[0]).lower())[0]
        moved = 0
        try:
            destination.mkdir(parents=False, exist_ok=True)
            for source in sorted(group, key=lambda item: item.name.lower()):
                target = destination / source.name
                if target.exists():
                    raise RuntimeError(f"Cannot organize {source.name}: destination file already exists")
                shutil.move(str(source), str(target))
                self._loose_file_states.pop((folder_id, str(source)), None)
                moved += 1
        except (OSError, RuntimeError) as exc:
            self.db.log(None, f"Could not organize loose media in {folder['name']}: {exc}", "warning")
            batch["remaining"] = len(loose)
            return
        if moved:
            batch["processed"] = int(batch["processed"]) + moved
            batch["remaining"] = max(0, len(loose) - moved)
            tracker_id = int(folder["default_tracker_id"] or self.db.ensure_default_tracker())
            defaults = {"category": folder["default_category"], "type": folder["default_type"], "resolution": folder["default_resolution"], "anonymous": folder["default_anonymous"], "moderation_queue": folder["default_moderation_queue"], "personal_release": folder["default_personal_release"], "internal": folder["default_internal"], "auto_upload": folder["auto_upload"]}
            job_id = self.enqueue(str(destination), tracker_id, defaults)
            self.db.log(job_id, f"Organized {moved} loose media file(s) into release folder: {destination}")

    @staticmethod
    def _folder_patterns(raw: Any) -> list[str]:
        try:
            parsed = json.loads(raw or "[]") if isinstance(raw, str) else raw
            return [str(item) for item in parsed if str(item).strip()]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def _refresh_monitor_status(self) -> None:
        batches = list(self._loose_batches.values())
        processed = sum(int(batch.get("processed", 0)) for batch in batches)
        total = sum(int(batch.get("total", 0)) for batch in batches)
        remaining = sum(int(batch.get("remaining", 0)) for batch in batches)
        with self._monitor_status_lock:
            self._monitor_status = {"active": remaining > 0, "processed": processed, "total": total, "remaining": remaining}

    def _process_job_safe(self, job_id: int) -> None:
        try:
            self._process_job(job_id)
        except Exception as exc:
            self.db.update_job(job_id, status="Failed", stage="Failed", error=str(exc))
            self.db.log(job_id, str(exc), "error")

    def _process_job(self, job_id: int) -> None:
        job = self.db.job(job_id)
        if not job:
            return
        settings = self.db.settings()
        tracker = self.db.tracker(int(job["tracker_id"]))
        if not tracker:
            raise RuntimeError("Tracker configuration is missing")
        source = job["source_path"]
        self.db.update_job(job_id, status="Waiting For Files", stage="Waiting For Files", progress=5, error="")
        self.db.log(job_id, "Waiting for folder stability")
        self._wait_until_stable(Path(source), int(settings.get("stability_interval_seconds", 10)), int(settings.get("stable_checks", 2)))
        scanner = MediaScanner(settings)
        self.db.update_job(job_id, status="Scanning", stage="Scanning Media", progress=15, error="")
        self.db.log(job_id, "Scanning files")
        files, media = scanner.scan(source)
        self.db.replace_files(job_id, files)
        self.db.update_job(job_id, file_count=len(files), total_size=media["total_size"], video_count=media["video_count"], media_json=media)
        self.db.log(job_id, f"Media scan complete: {len(files)} file(s), {media['video_count']} video file(s)")
        self.db.update_job(job_id, status="Identifying Metadata", stage="Identifying Metadata", progress=22, error="")
        self.db.log(job_id, "Checking configured metadata providers")
        try:
            metadata = MetadataService(settings, self.db).identify(source, files, media)
            self.db.update_job(job_id, metadata_json=metadata)
            self.db.log(job_id, f"Metadata check complete: {len(metadata.get('matches', []))} candidate(s)")
        except Exception as exc:
            self.db.update_job(job_id, metadata_json={"status": "Error", "matches": [], "error": str(exc), "checked_at": utc_now()})
            self.db.log(job_id, f"Metadata check skipped: {exc}", "warning")
        self.db.update_job(job_id, status="Generating Images", stage="Generating Images", progress=30, error="")
        self.db.log(job_id, "Running Pumpkin's Thumb It image stage")
        ThumbItService(settings, self.db).generate_or_import(job_id, source)
        self.db.update_job(job_id, status="Creating Torrent", stage="Creating Private Torrent", progress=45, error="")
        self.db.log(job_id, "Creating private torrent")
        torrent = TorrentService(settings).create(source, tracker["announce_url"], job.get("upload_title") or job["folder_name"])
        self.db.update_job(job_id, torrent_path=torrent["path"], torrent_internal_name=torrent["internal_name"], upload_title=torrent["internal_name"], info_hash=torrent["info_hash"], progress=60)
        self.db.log(job_id, f"Torrent created; internal name: {torrent['internal_name']}; info hash: {torrent['info_hash']}")
        self.db.update_job(job_id, status="Validating Tracker", stage="Validating Tracker Settings", progress=65, error="")
        if is_bitporn_tracker(tracker):
            validation = BitPornTrackerValidator.validate(tracker["announce_url"])
            if not validation.valid:
                raise RuntimeError("BitPorn image hosting blocked: " + validation.reason)
            self.db.log(job_id, "BitPorn tracker validation successful")
            BitPornImageHostService(self.db).assert_allowed(tracker["announce_url"])
        else:
            self.db.log(job_id, "External UNIT3D tracker selected; using user-supplied upload settings")
        self.db.update_job(job_id, status="Uploading Images", stage="Preparing Upload Assets", progress=72, error="")
        self.db.log(job_id, "BitPorn native image slots prepared" if is_bitporn_tracker(tracker) else "External UNIT3D profile will use user-supplied image-host URLs")
        duplicate = DuplicateService(self.db, settings).check(self.db.job(job_id) or job)
        self.db.add_duplicate(job_id, duplicate["result"], duplicate["reason"], duplicate)
        self.db.update_job(job_id, duplicate_result_json=duplicate)
        if duplicate["result"] == "Possible Duplicate":
            self.db.update_job(job_id, status="Duplicate", stage="Duplicate Check", progress=75, error="")
            self.db.log(job_id, "Possible duplicate detected; upload blocked")
            return
        self.db.update_job(job_id, status="Awaiting Description", stage="Awaiting Description", progress=78, error="")
        self.db.log(job_id, "Awaiting user description and tags")
        if job.get("auto_upload") and not settings.get("require_final_review", True) and job.get("description"):
            self.approve_and_upload(job_id)

    def _upload_job_safe(self, job_id: int) -> None:
        try:
            self._upload_job(job_id)
        except BitPornUploadAmbiguous as exc:
            self.db.update_job(job_id, status="Upload Unconfirmed", stage="Upload Unconfirmed", error=str(exc))
            self.db.log(job_id, str(exc), "warning")
        except Exception as exc:
            self.db.update_job(job_id, status="Failed", stage="Upload Failed", error=str(exc))
            self.db.log(job_id, str(exc), "error")

    def _upload_job(self, job_id: int) -> None:
        job = self.db.job(job_id)
        if not job:
            raise RuntimeError("Job not found")
        tracker = self.db.tracker(int(job["tracker_id"]))
        if not tracker:
            raise RuntimeError("Tracker configuration is missing")
        if not job.get("description", "").strip():
            raise RuntimeError("Upload blocked: description is empty")
        if not is_bitporn_tracker(tracker) and contains_bitporn_image_url(job.get("description", "")):
            raise RuntimeError(BITPORN_IMAGE_HOST_BLOCK_MESSAGE)
        if is_bitporn_tracker(tracker):
            validation = BitPornTrackerValidator.validate(tracker["announce_url"])
            if not validation.valid:
                raise RuntimeError("Final BitPorn tracker validation failed: " + validation.reason)
        self.db.log(job_id, "Final tracker validation successful")
        result = BitPornTrackerClient(self.db, self.db.settings()).upload(job, tracker)
        self.db.update_job(job_id, status="Completed", stage="Completed", progress=100, upload_result_json=result, completed_at=utc_now(), error="")
        self.db.log(job_id, "Torrent uploaded successfully")

    @staticmethod
    def _wait_until_stable(path: Path, interval: int, checks: int) -> None:
        if not path.is_dir():
            raise RuntimeError("Release folder does not exist")
        checks = max(1, min(checks, 10))
        previous = None
        for index in range(checks):
            current = []
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    stat = child.stat()
                    current.append((str(child), stat.st_size, stat.st_mtime_ns))
            snapshot = tuple(current)
            if previous is not None and snapshot != previous:
                previous = snapshot
                time.sleep(max(1, interval))
                continue
            previous = snapshot
            if index < checks - 1:
                time.sleep(max(1, interval))
