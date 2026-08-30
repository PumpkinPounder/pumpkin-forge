from __future__ import annotations

import json
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_release_name(value: object) -> str:
    """Make filename-style release names readable without changing source files."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("_", " ")
    text = re.sub(r"\.{2,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ._-–—")
    return text


DEFAULT_SETTINGS: dict[str, Any] = {
    "application_name": "Pumpkin Forge",
    "github_version_url": "",
    "update_check_enabled": True,
    "update_check_timeout_seconds": 10,
    "last_update_check_at": "",
    "last_remote_version": "",
    "last_update_error": "",
    "database_path": "data/app.db",
    "working_directory": "storage/working",
    "generated_directory": "storage/generated",
    "torrent_directory": "storage/torrents",
    "auto_start_processing": True,
    "bind_address": "127.0.0.1",
    "web_port": 8877,
    "dashboard_refresh_seconds": 5,
    "folder_scan_interval_seconds": 20,
    "minimum_folder_age_seconds": 60,
    "stability_interval_seconds": 10,
    "stable_checks": 2,
    "include_subfolders": False,
    "ignore_patterns": ["*.torrent", "*.part", "*.tmp", "*.crdownload", "*.!qb"],
    "thumbit_enabled": True,
    "thumbit_script_path": "tools/ThumbIt.py",
    "thumbit_command": "",
    "thumbit_output_directory": "",
    "thumbit_header_logo": "",
    "thumbit_logo_url": "https://imghost.dev/images/2026/07/05/6da6ca143482.png",
    "description_release_image": "",
    "thumbit_overlay_image": "tools/assets/centerlongest_overlay.png",
    "thumbit_center_images": 5,
    "thumbit_still_images": 5,
    "thumbit_timeout_seconds": 900,
    "thumbit_retry_count": 1,
    "bbcode_image_width": 450,
    "bitporn_automatic_image_upload": True,
    "bitporn_upload_timeout_seconds": 180,
    "bitporn_retry_count": 2,
    "bitporn_retry_delay_seconds": 10,
    "private_torrent": True,
    "torrent_source": "",
    "torrent_comment": "Created by Pumpkin Forge",
    "torrent_created_by": "Pumpkin Forge",
    "piece_size": 0,
    "hashing_workers": 1,
    "duplicate_local_enabled": True,
    "duplicate_remote_enabled": False,
    "duplicate_match_title": True,
    "duplicate_match_info_hash": True,
    "duplicate_match_file_list": True,
    "duplicate_size_tolerance": 0,
    "anonymous_default": False,
    "moderation_queue_default": False,
    "personal_release_default": False,
    "internal_release_default": False,
    "auto_upload": False,
    "require_final_review": True,
    "description_autosave_seconds": 10,
    "log_level": "info",
    "redact_credentials": True,
    "metadata_auto_identify": True,
    "metadata_search_results": 5,
    "metadata_min_confidence": 55,
    "metadata_timeout_seconds": 15,
    "metadata_theporndb_enabled": True,
    "theporndb_api_url": "https://api.theporndb.net",
    "theporndb_api_token": "",
    "metadata_stashdb_enabled": True,
    "stashdb_api_url": "https://stashdb.org/graphql",
    "stashdb_api_token": "",
}


# Seeded from PumpkinAuto's BitPorn category and resolution definitions.
# These are stored as label-to-ID maps so the Build Description form can show
# readable choices while submitting the tracker IDs.
DEFAULT_TRACKER_CATEGORY_MAP: dict[str, int] = {
    "Uncategorized": 52,
    "Amateur": 4,
    "Anal": 5,
    "Asian": 6,
    "BBW": 7,
    "BDSM": 8,
    "Big Ass": 9,
    "Big Tits": 10,
    "Black": 11,
    "Cartoon": 12,
    "Casting": 13,
    "Classic": 14,
    "Collection": 15,
    "Creampie": 16,
    "Cumshot": 17,
    "Deepthroat": 18,
    "Extreme": 19,
    "Fansite": 20,
    "Family": 21,
    "Feature": 22,
    "Fetish": 23,
    "Fisting": 24,
    "Gangbang": 25,
    "Game": 26,
    "Gay/Bi": 27,
    "Hair": 28,
    "Hardcore": 29,
    "Hidden Cam": 30,
    "Homemade": 31,
    "Interracial": 32,
    "Lesbian": 33,
    "Magyar": 34,
    "Masturbation": 35,
    "Mature": 36,
    "MILF": 37,
    "Old and Young": 38,
    "Parody": 39,
    "Pictures": 40,
    "Pissing": 41,
    "POV": 42,
    "Pregnant": 43,
    "Public": 44,
    "Shemale": 45,
    "Softcore": 46,
    "Squirt": 47,
    "Scat": 48,
    "Teen": 49,
    "Threesome": 50,
    "VR": 51,
    "AI Generated": 54,
}
DEFAULT_TRACKER_TYPE_MAP: dict[str, int] = {"Default": 1}
DEFAULT_TRACKER_RESOLUTION_MAP: dict[str, int] = {
    "Other": 11,
    "SD": 12,
    "720p": 17,
    "1080p": 13,
    "2K/2048p": 14,
    "4K/2160p": 18,
    "6K/3160p": 15,
    "8K/4320p": 16,
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trackers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tracker_type TEXT NOT NULL DEFAULT 'bitporn',
    site_url TEXT NOT NULL,
    api_url TEXT NOT NULL,
    upload_endpoint TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    announce_url TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    private_flag INTEGER NOT NULL DEFAULT 1,
    category_map_json TEXT NOT NULL DEFAULT '{}',
    type_map_json TEXT NOT NULL DEFAULT '{}',
    resolution_map_json TEXT NOT NULL DEFAULT '{}',
    tag_map_json TEXT NOT NULL DEFAULT '{}',
    default_category TEXT NOT NULL DEFAULT '',
    default_type TEXT NOT NULL DEFAULT '',
    default_resolution TEXT NOT NULL DEFAULT '',
    default_tags_json TEXT NOT NULL DEFAULT '[]',
    anonymous_default INTEGER,
    moderation_queue_default INTEGER,
    personal_release_default INTEGER,
    internal_default INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    custom_fields_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS monitored_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    include_subfolders INTEGER NOT NULL DEFAULT 0,
    scan_interval_seconds INTEGER NOT NULL DEFAULT 20,
    minimum_folder_age_seconds INTEGER NOT NULL DEFAULT 60,
    stability_interval_seconds INTEGER NOT NULL DEFAULT 10,
    stable_checks INTEGER NOT NULL DEFAULT 2,
    default_tracker_id INTEGER,
    default_category TEXT NOT NULL DEFAULT '',
    default_type TEXT NOT NULL DEFAULT '',
    default_resolution TEXT NOT NULL DEFAULT '',
    default_anonymous INTEGER,
    default_moderation_queue INTEGER,
    default_personal_release INTEGER,
    default_internal INTEGER,
    auto_upload INTEGER,
    ignore_patterns_json TEXT NOT NULL DEFAULT '[]',
    include_patterns_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(default_tracker_id) REFERENCES trackers(id)
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL UNIQUE,
    folder_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Detected',
    stage TEXT NOT NULL DEFAULT 'Detected',
    progress REAL NOT NULL DEFAULT 0,
    tracker_id INTEGER NOT NULL,
    announce_url TEXT NOT NULL,
    torrent_path TEXT NOT NULL DEFAULT '',
    torrent_internal_name TEXT NOT NULL DEFAULT '',
    upload_title TEXT NOT NULL DEFAULT '',
    info_hash TEXT NOT NULL DEFAULT '',
    file_count INTEGER NOT NULL DEFAULT 0,
    total_size INTEGER NOT NULL DEFAULT 0,
    video_count INTEGER NOT NULL DEFAULT 0,
    media_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    category TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    resolution TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    description TEXT NOT NULL DEFAULT '',
    description_saved_at TEXT,
    anonymous INTEGER,
    moderation_queue INTEGER,
    personal_release INTEGER,
    internal_release INTEGER,
    duplicate_result_json TEXT NOT NULL DEFAULT '{}',
    upload_result_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    auto_upload INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(tracker_id) REFERENCES trackers(id)
);
CREATE TABLE IF NOT EXISTS job_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    extension TEXT NOT NULL,
    size INTEGER NOT NULL,
    modified_at REAL NOT NULL,
    is_video INTEGER NOT NULL DEFAULT 0,
    media_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS job_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    image_type TEXT NOT NULL,
    hosted_url TEXT NOT NULL DEFAULT '',
    bbcode TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Pending',
    error TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT,
    UNIQUE(job_id, path, file_hash),
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS duplicate_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    result TEXT NOT NULL,
    reason TEXT NOT NULL,
    match_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS upload_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    state TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL DEFAULT '',
    response_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_logs_job ON logs(job_id, created_at);
CREATE INDEX IF NOT EXISTS idx_files_job ON job_files(job_id);
CREATE INDEX IF NOT EXISTS idx_images_job ON job_images(job_id);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.migrate()

    def migrate(self) -> None:
        with self._lock, self.conn:
            self.conn.executescript(SCHEMA)
            version = self.conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
            if version < 1:
                now = utc_now()
                for key, value in DEFAULT_SETTINGS.items():
                    self.conn.execute(
                        "INSERT OR IGNORE INTO settings(key,value_json,updated_at) VALUES(?,?,?)",
                        (key, json.dumps(value), now),
                    )
                self.conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES(1,?)", (now,))
                version = 1
            if version < 2:
                now = utc_now()
                legacy_values = {
                    "application_name": "Pumpkin Local Upload",
                    "torrent_comment": "Created by Pumpkin Local Upload",
                    "torrent_created_by": "Pumpkin Local Upload",
                }
                replacement_values = {
                    "application_name": "Pumpkin Forge",
                    "torrent_comment": "Created by Pumpkin Forge",
                    "torrent_created_by": "Pumpkin Forge",
                }
                for key, legacy in legacy_values.items():
                    row = self.conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
                    if row and json.loads(row["value_json"]) == legacy:
                        self.conn.execute(
                            "UPDATE settings SET value_json=?, updated_at=? WHERE key=?",
                            (json.dumps(replacement_values[key]), now, key),
                        )
                self.conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES(2,?)", (now,))
                version = 2
            if version < 3:
                now = utc_now()
                columns = {row[1] for row in self.conn.execute("PRAGMA table_info(jobs)").fetchall()}
                if "metadata_json" not in columns:
                    self.conn.execute("ALTER TABLE jobs ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'" )
                self.conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES(3,?)", (now,))
                version = 3
            if version < 4:
                now = utc_now()
                columns = {row[1] for row in self.conn.execute("PRAGMA table_info(trackers)").fetchall()}
                if "tracker_type" not in columns:
                    self.conn.execute("ALTER TABLE trackers ADD COLUMN tracker_type TEXT NOT NULL DEFAULT 'bitporn'")
                self.conn.execute("UPDATE trackers SET tracker_type='bitporn' WHERE tracker_type IS NULL OR tracker_type=''")
                self.conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES(4,?)", (now,))

    def _json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def settings(self) -> dict[str, Any]:
        rows = self.conn.execute("SELECT key,value_json FROM settings").fetchall()
        result = dict(DEFAULT_SETTINGS)
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value_json"])
            except json.JSONDecodeError:
                result[row["key"]] = row["value_json"]
        return result

    def save_settings(self, values: dict[str, Any]) -> None:
        now = utc_now()
        with self._lock, self.conn:
            for key, value in values.items():
                if key not in DEFAULT_SETTINGS:
                    continue
                self.conn.execute(
                    "INSERT INTO settings(key,value_json,updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                    (key, self._json(value), now),
                )

    def tracker_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM trackers ORDER BY name").fetchall()]

    def tracker(self, tracker_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM trackers WHERE id=?", (tracker_id,)).fetchone()
        return dict(row) if row else None

    def save_tracker(self, values: dict[str, Any], tracker_id: int | None = None) -> int:
        now = utc_now()
        fields = [
            "name", "tracker_type", "site_url", "api_url", "upload_endpoint", "api_key", "announce_url", "source",
            "private_flag", "category_map_json", "type_map_json", "resolution_map_json", "tag_map_json",
            "default_category", "default_type", "default_resolution", "default_tags_json",
            "anonymous_default", "moderation_queue_default", "personal_release_default", "internal_default",
            "enabled", "custom_fields_json",
        ]
        payload = {field: values.get(field, "bitporn" if field == "tracker_type" else "") for field in fields}
        for field in ["private_flag", "enabled"]:
            payload[field] = int(bool(payload[field]))
        if tracker_id:
            assignments = ",".join(f"{field}=?" for field in fields) + ",updated_at=?"
            with self._lock, self.conn:
                self.conn.execute(f"UPDATE trackers SET {assignments} WHERE id=?", [payload[f] for f in fields] + [now, tracker_id])
            return tracker_id
        with self._lock, self.conn:
            cur = self.conn.execute(
                f"INSERT INTO trackers({','.join(fields)},created_at,updated_at) VALUES({','.join('?' for _ in fields)},?,?)",
                [payload[f] for f in fields] + [now, now],
            )
            return int(cur.lastrowid)

    def ensure_default_tracker(self) -> int:
        row = self.conn.execute("SELECT id FROM trackers ORDER BY id LIMIT 1").fetchone()
        if row:
            return int(row[0])
        return self.save_tracker({
            "name": "BitPorn",
            "tracker_type": "bitporn",
            "site_url": "https://bitporn.eu",
            "api_url": "https://bitporn.eu/api",
            "upload_endpoint": "https://bitporn.eu/api/torrents/upload",
            "announce_url": "https://bitporn.eu/announce",
            "source": "",
            "private_flag": True,
            "enabled": True,
            "default_tags_json": "[]",
            "category_map_json": json.dumps(DEFAULT_TRACKER_CATEGORY_MAP),
            "type_map_json": json.dumps(DEFAULT_TRACKER_TYPE_MAP),
            "resolution_map_json": json.dumps(DEFAULT_TRACKER_RESOLUTION_MAP),
            "tag_map_json": "{}",
            "default_category": "52",
            "default_type": "1",
            "default_resolution": "11",
            "custom_fields_json": "{}",
        })

    def folder_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM monitored_folders ORDER BY name").fetchall()]

    def save_folder(self, values: dict[str, Any], folder_id: int | None = None) -> int:
        now = utc_now()
        fields = ["name", "path", "enabled", "include_subfolders", "scan_interval_seconds", "minimum_folder_age_seconds", "stability_interval_seconds", "stable_checks", "default_tracker_id", "default_category", "default_type", "default_resolution", "default_anonymous", "default_moderation_queue", "default_personal_release", "default_internal", "auto_upload", "ignore_patterns_json", "include_patterns_json"]
        payload = {field: values.get(field, "") for field in fields}
        payload["path"] = str(Path(payload["path"]).expanduser())
        if folder_id:
            assignments = ",".join(f"{field}=?" for field in fields) + ",updated_at=?"
            with self._lock, self.conn:
                self.conn.execute(f"UPDATE monitored_folders SET {assignments} WHERE id=?", [payload[f] for f in fields] + [now, folder_id])
            return folder_id
        with self._lock, self.conn:
            cur = self.conn.execute(f"INSERT INTO monitored_folders({','.join(fields)},created_at,updated_at) VALUES({','.join('?' for _ in fields)},?,?)", [payload[f] for f in fields] + [now, now])
            return int(cur.lastrowid)

    def job_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()]

    def job(self, job_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        for key in ["media_json", "metadata_json", "tags_json", "duplicate_result_json", "upload_result_json"]:
            try:
                result[key[:-5] if key.endswith("_json") else key] = json.loads(result[key])
            except (TypeError, json.JSONDecodeError):
                result[key[:-5] if key.endswith("_json") else key] = {}
        result["files"] = [dict(r) for r in self.conn.execute("SELECT * FROM job_files WHERE job_id=? ORDER BY relative_path", (job_id,)).fetchall()]
        result["images"] = [dict(r) for r in self.conn.execute("SELECT * FROM job_images WHERE job_id=? ORDER BY id", (job_id,)).fetchall()]
        result["logs"] = [dict(r) for r in self.conn.execute("SELECT * FROM logs WHERE job_id=? ORDER BY id DESC LIMIT 200", (job_id,)).fetchall()]
        return result

    def delete_job(self, job_id: int) -> bool:
        """Remove one job and its database records, leaving the source release untouched."""
        with self._lock, self.conn:
            cursor = self.conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            return cursor.rowcount > 0

    def create_job(self, source_path: str, tracker_id: int, announce_url: str, defaults: dict[str, Any] | None = None) -> int:
        source = str(Path(source_path).expanduser())
        folder = clean_release_name(Path(source).name or source)
        defaults = defaults or {}
        now = utc_now()
        with self._lock, self.conn:
            existing = self.conn.execute("SELECT id FROM jobs WHERE source_path=?", (source,)).fetchone()
            if existing:
                return int(existing[0])
            cur = self.conn.execute("""INSERT INTO jobs(source_path,folder_name,tracker_id,announce_url,upload_title,category,type,resolution,anonymous,moderation_queue,personal_release,internal_release,auto_upload,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (source, folder, tracker_id, announce_url, folder, defaults.get("category", ""), defaults.get("type", ""), defaults.get("resolution", ""), defaults.get("anonymous"), defaults.get("moderation_queue"), defaults.get("personal_release"), defaults.get("internal"), defaults.get("auto_upload"), now, now))
            job_id = int(cur.lastrowid)
            self.conn.execute("INSERT INTO logs(job_id,level,message,created_at) VALUES(?,?,?,?)", (job_id, "info", "Folder detected", now))
            return job_id

    def update_job(self, job_id: int, **values: Any) -> None:
        values["updated_at"] = utc_now()
        json_fields = {"media_json", "metadata_json", "tags_json", "duplicate_result_json", "upload_result_json"}
        for field in list(values):
            if field in json_fields and not isinstance(values[field], str):
                values[field] = self._json(values[field])
        assignments = ",".join(f"{key}=?" for key in values)
        with self._lock, self.conn:
            self.conn.execute(f"UPDATE jobs SET {assignments} WHERE id=?", list(values.values()) + [job_id])

    def log(self, job_id: int | None, message: str, level: str = "info") -> None:
        with self._lock, self.conn:
            self.conn.execute("INSERT INTO logs(job_id,level,message,created_at) VALUES(?,?,?,?)", (job_id, level, message, utc_now()))

    def replace_files(self, job_id: int, files: list[dict[str, Any]]) -> None:
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM job_files WHERE job_id=?", (job_id,))
            for file in files:
                self.conn.execute("INSERT INTO job_files(job_id,path,relative_path,file_name,extension,size,modified_at,is_video,media_json) VALUES(?,?,?,?,?,?,?,?,?)", (job_id, file["path"], file["relative_path"], file["file_name"], file["extension"], file["size"], file["modified_at"], int(file.get("is_video", False)), self._json(file.get("media", {}))))

    def replace_images(self, job_id: int, images: list[dict[str, Any]]) -> None:
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM job_images WHERE job_id=?", (job_id,))
            for image in images:
                self.conn.execute("INSERT OR REPLACE INTO job_images(job_id,path,file_name,file_hash,image_type,hosted_url,bbcode,status,error,uploaded_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (job_id, image["path"], image["file_name"], image["file_hash"], image["image_type"], image.get("hosted_url", ""), image.get("bbcode", ""), image.get("status", "Pending"), image.get("error", ""), image.get("uploaded_at")))

    def add_duplicate(self, job_id: int, result: str, reason: str, match: dict[str, Any]) -> None:
        with self._lock, self.conn:
            self.conn.execute("INSERT INTO duplicate_checks(job_id,result,reason,match_json,created_at) VALUES(?,?,?,?,?)", (job_id, result, reason, self._json(match), utc_now()))

    def close(self) -> None:
        self.conn.close()
