from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .database import Database, clean_release_name, utc_now


VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".mts", ".3gp", ".ogv", ".divx", ".asf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
TEMP_SUFFIXES = {".part", ".tmp", ".partial", ".crdownload", ".download", ".!qb"}


def safe_json(value: Any) -> Any:
    try:
        return json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return {}


def redact(value: str, secrets: Iterable[str] = ()) -> str:
    result = str(value)
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[REDACTED]")
    result = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+", r"\1[REDACTED]", result)
    result = re.sub(r"(?i)(api[_-]?key|token|passkey|password)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", result)
    result = re.sub(r"(?i)(/announce/)[^\s/?#]+", r"\1[REDACTED]", result)
    return result


class UpdateChecker:
    """Compare the installed version.txt with a configured GitHub raw file."""

    def __init__(self, root: str | Path, settings: dict[str, Any]):
        self.root = Path(root)
        self.settings = settings

    def local_version(self) -> str:
        version_file = self.root / "version.txt"
        try:
            value = version_file.read_text(encoding="utf-8").strip()
        except OSError:
            value = "0.0.0"
        return value.lstrip("vV") or "0.0.0"

    def cached(self) -> dict[str, Any]:
        """Return the last saved GitHub comparison without making a network request."""
        local = self.local_version()
        remote = str(self.settings.get("last_remote_version", "") or "").strip().lstrip("vV")
        checked_at = str(self.settings.get("last_update_check_at", "") or "").strip()
        error = str(self.settings.get("last_update_error", "") or "").strip()

        if self.settings.get("update_check_enabled", True) is False:
            return {
                "enabled": False,
                "status": "Disabled",
                "local_version": local,
                "remote_version": remote,
                "checked_at": checked_at,
                "error": "",
            }

        url = str(self.settings.get("github_version_url", "") or "").strip()
        if not url:
            return {
                "enabled": False,
                "status": "Not configured",
                "local_version": local,
                "remote_version": "",
                "checked_at": "",
                "error": "",
            }

        if error:
            return {
                "enabled": True,
                "status": "Error",
                "local_version": local,
                "remote_version": remote,
                "checked_at": checked_at,
                "error": error,
            }

        if not remote:
            return {
                "enabled": True,
                "status": "Not checked",
                "local_version": local,
                "remote_version": "",
                "checked_at": checked_at,
                "error": "",
            }

        local_key = self._version_key(local)
        remote_key = self._version_key(remote)
        if remote_key > local_key:
            status = "Update available"
        elif remote_key == local_key:
            status = "Up to date"
        else:
            status = "Local version is newer"

        return {
            "enabled": True,
            "status": status,
            "local_version": local,
            "remote_version": remote,
            "checked_at": checked_at,
            "error": "",
        }

    def check(self) -> dict[str, Any]:
        local = self.local_version()
        url = str(self.settings.get("github_version_url", "") or "").strip()
        checked_at = utc_now()
        if self.settings.get("update_check_enabled", True) is False:
            return {"enabled": False, "status": "Disabled", "local_version": local, "remote_version": "", "checked_at": "", "error": "GitHub update checks are disabled in Settings."}
        if not url:
            return {"enabled": False, "status": "Not configured", "local_version": local, "remote_version": "", "checked_at": "", "error": "Configure the raw GitHub version.txt URL in Settings."}
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() != "https" or parsed.hostname not in {"raw.githubusercontent.com", "github.com"}:
            return {"enabled": True, "status": "Error", "local_version": local, "remote_version": "", "checked_at": checked_at, "error": "Version URL must use HTTPS and point to GitHub or raw.githubusercontent.com."}
        request = urllib.request.Request(url, headers={"Accept": "text/plain", "User-Agent": "Pumpkin-Forge-Update-Checker/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=int(self.settings.get("update_check_timeout_seconds", 10))) as response:
                raw = response.read(4096)
                remote = raw.decode("utf-8", "replace").strip().splitlines()[0].strip() if raw else ""
        except (urllib.error.URLError, TimeoutError, OSError, IndexError) as exc:
            return {"enabled": True, "status": "Error", "local_version": local, "remote_version": "", "checked_at": checked_at, "error": redact(str(exc))}
        remote = remote.lstrip("vV")
        if not remote:
            return {"enabled": True, "status": "Error", "local_version": local, "remote_version": "", "checked_at": checked_at, "error": "GitHub version.txt was empty."}
        local_key = self._version_key(local)
        remote_key = self._version_key(remote)
        if remote_key > local_key:
            status = "Update available"
        elif remote_key == local_key:
            status = "Up to date"
        else:
            status = "Local version is newer"
        return {"enabled": True, "status": status, "local_version": local, "remote_version": remote, "checked_at": checked_at, "error": ""}

    @staticmethod
    def _version_key(value: str) -> tuple[int, ...]:
        # Keep comparison useful for display versions such as "1.0 Beta".
        match = re.match(r"^(\d+(?:\.\d+)*)", value.strip().lstrip("vV"))
        if not match:
            return (0,)
        return tuple(int(part) for part in match.group(1).split("."))


@dataclass(frozen=True)
class BitPornValidation:
    valid: bool
    reason: str
    host: str = ""
    path: str = ""


class BitPornTrackerValidator:
    """The mandatory backend-only BitPorn compatibility rule."""

    @staticmethod
    def validate(announce_url: str) -> BitPornValidation:
        raw = str(announce_url or "").strip()
        try:
            parts = urllib.parse.urlsplit(raw)
        except ValueError:
            return BitPornValidation(False, "Announce URL could not be parsed")
        host = (parts.hostname or "").lower().rstrip(".")
        path = parts.path.rstrip("/") or "/"
        if parts.scheme.lower() != "https":
            return BitPornValidation(False, "BitPorn announce URL must use HTTPS", host, path)
        if host not in {"bitporn.eu", "www.bitporn.eu"}:
            return BitPornValidation(False, "Unsupported tracker announce host", host, path)
        if path != "/announce" and not path.startswith("/announce/"):
            return BitPornValidation(False, "Unsupported BitPorn announce path", host, path)
        if parts.fragment:
            return BitPornValidation(False, "Announce URL must not contain a fragment", host, path)
        return BitPornValidation(True, "Compatible BitPorn announce identity", host, path)


def tracker_type(tracker: dict[str, Any]) -> str:
    """Return the configured upload platform without guessing from its hostname."""
    value = str(tracker.get("tracker_type") or "bitporn").strip().lower()
    return value if value in {"bitporn", "external_unit3d"} else "bitporn"


def is_bitporn_tracker(tracker: dict[str, Any]) -> bool:
    return tracker_type(tracker) == "bitporn"


BITPORN_IMAGE_HOST_BLOCK_MESSAGE = "Upload blocked: BitPorn-hosted images cannot be used with this tracker. Replace the image Host before continuing."


def contains_bitporn_image_url(description: str) -> bool:
    """Detect explicit BitPorn image-host URLs in a tracker description."""
    pattern = re.compile(r"\[img(?:=[^\]]+)?\]\s*(https?://[^\s\[\]]+)\s*\[/img\]", re.IGNORECASE)
    for value in pattern.findall(str(description or "")):
        try:
            host = (urllib.parse.urlsplit(value).hostname or "").lower().rstrip(".")
        except ValueError:
            continue
        if host == "bitporn.eu" or host.endswith(".bitporn.eu"):
            return True
    return False


class Bencode:
    @staticmethod
    def encode(value: Any) -> bytes:
        if isinstance(value, bool):
            value = int(value)
        if isinstance(value, int):
            return b"i" + str(value).encode("ascii") + b"e"
        if isinstance(value, bytes):
            return str(len(value)).encode("ascii") + b":" + value
        if isinstance(value, str):
            return Bencode.encode(value.encode("utf-8"))
        if isinstance(value, list):
            return b"l" + b"".join(Bencode.encode(item) for item in value) + b"e"
        if isinstance(value, dict):
            items = []
            for key in sorted(value, key=lambda item: item.encode("utf-8") if isinstance(item, str) else item):
                key_bytes = key if isinstance(key, bytes) else str(key).encode("utf-8")
                items.append(Bencode.encode(key_bytes))
                items.append(Bencode.encode(value[key]))
            return b"d" + b"".join(items) + b"e"
        raise TypeError(f"Unsupported bencode value: {type(value).__name__}")

    @staticmethod
    def decode(data: bytes) -> Any:
        def parse(index: int) -> tuple[Any, int]:
            if index >= len(data):
                raise ValueError("Unexpected end of bencoded data")
            marker = data[index:index + 1]
            if marker == b"i":
                end = data.index(b"e", index)
                return int(data[index + 1:end]), end + 1
            if marker == b"l":
                items, index = [], index + 1
                while data[index:index + 1] != b"e":
                    item, index = parse(index)
                    items.append(item)
                return items, index + 1
            if marker == b"d":
                result, index = {}, index + 1
                while data[index:index + 1] != b"e":
                    key, index = parse(index)
                    value, index = parse(index)
                    if isinstance(key, bytes):
                        key = key.decode("utf-8", "replace")
                    result[str(key)] = value
                return result, index + 1
            if marker.isdigit():
                colon = data.index(b":", index)
                length = int(data[index:colon])
                start = colon + 1
                return data[start:start + length], start + length
            raise ValueError(f"Invalid bencode marker at {index}")

        result, end = parse(0)
        if end != len(data):
            raise ValueError("Trailing data after bencoded value")
        return result


class MediaScanner:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    def scan(self, folder: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        root = Path(folder).resolve()
        if not root.exists() or not root.is_dir():
            raise RuntimeError(f"Release folder does not exist: {folder}")
        files: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*") if self.settings.get("include_subfolders", False) else root.glob("*")):
            if not path.is_file() or path.suffix.lower() in TEMP_SUFFIXES or path.suffix.lower() == ".torrent":
                continue
            stat = path.stat()
            rel = str(path.relative_to(root)).replace("\\", "/")
            is_video = path.suffix.lower() in VIDEO_EXTENSIONS
            files.append({
                "path": str(path),
                "relative_path": rel,
                "file_name": path.name,
                "extension": path.suffix.lower(),
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
                "is_video": is_video,
                "media": self._probe(path) if is_video else {},
            })
        if not files:
            raise RuntimeError("No usable files were found in the release folder")
        total_size = sum(file["size"] for file in files)
        videos = [file for file in files if file["is_video"]]
        media = {
            "folder_name": clean_release_name(root.name),
            "file_count": len(files),
            "total_size": total_size,
            "video_count": len(videos),
            "videos": [{"file": file["relative_path"], **file["media"]} for file in videos],
        }
        return files, media

    def _probe(self, path: Path) -> dict[str, Any]:
        executable = str(self.settings.get("ffprobe_path", "") or "ffprobe")
        try:
            completed = subprocess.run([executable, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(path)], capture_output=True, text=True, timeout=30)
            if completed.returncode != 0:
                return {}
            payload = json.loads(completed.stdout or "{}")
            streams = payload.get("streams") or []
            video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
            audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
            return {
                "duration": (payload.get("format") or {}).get("duration", ""),
                "video_codec": video.get("codec_name", ""),
                "audio_codec": audio.get("codec_name", ""),
                "width": video.get("width", ""),
                "height": video.get("height", ""),
                "frame_rate": video.get("r_frame_rate", ""),
                "pixel_format": video.get("pix_fmt", ""),
                "audio_channels": audio.get("channels", ""),
                "language": (audio.get("tags") or {}).get("language", ""),
            }
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return {}


class MetadataService:
    """Find release metadata without making provider availability a workflow blocker.

    Provider credentials stay server-side.  The service deliberately uses the local
    folder name and already-probed media first; fingerprints can be added later as
    an optional second pass without changing the review workflow.
    """

    PROVIDERS = ("theporndb", "stashdb")

    def __init__(self, settings: dict[str, Any], db: Database | None = None):
        self.settings = settings
        self.db = db

    def identify(self, folder: str, files: list[dict[str, Any]], media: dict[str, Any]) -> dict[str, Any]:
        root = Path(folder)
        video_names = [str(file.get("file_name") or file.get("relative_path") or "") for file in files if file.get("is_video")]
        query, jav_code = self._build_query(root.name, video_names)
        result: dict[str, Any] = {
            "query": query,
            "jav_code": jav_code,
            "checked_at": utc_now(),
            "status": "Not configured",
            "matches": [],
            "providers": {},
        }
        if not self.settings.get("metadata_auto_identify", True):
            result["status"] = "Disabled"
            return result

        candidates: list[dict[str, Any]] = []
        for provider in self.PROVIDERS:
            try:
                matches, provider_status = self._search_provider(provider, query, jav_code)
                result["providers"][provider] = provider_status
                candidates.extend(matches)
            except Exception as exc:
                result["providers"][provider] = {"status": "Error", "error": redact(str(exc))}

        unique: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            candidate["confidence"] = self._confidence(candidate, query, jav_code)
            key = f"{candidate.get('provider')}:{candidate.get('provider_id') or candidate.get('title')}"
            if key not in unique or candidate["confidence"] > unique[key]["confidence"]:
                unique[key] = candidate
        minimum = max(0, min(100, int(self.settings.get("metadata_min_confidence", 0) or 0)))
        ordered = sorted(unique.values(), key=lambda item: (item.get("confidence", 0), item.get("title", "")), reverse=True)
        result["matches"] = ordered[:max(1, min(20, int(self.settings.get("metadata_search_results", 5) or 5)))]
        result["status"] = "Matches found" if any(item.get("confidence", 0) >= minimum for item in result["matches"]) else "No confident match"
        result["minimum_confidence"] = minimum
        return result

    def _search_provider(self, provider: str, query: str, jav_code: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        enabled_key = f"metadata_{provider}_enabled"
        token_key = f"{provider}_api_token"
        if not self.settings.get(enabled_key, True):
            return [], {"status": "Disabled"}
        token = str(self.settings.get(token_key, "") or "").strip()
        if not token:
            return [], {"status": "Not configured", "message": "Add an API token in Settings to enable this provider."}
        base = str(self.settings.get(f"{provider}_api_url", "") or "").strip().rstrip("/")
        if not base:
            return [], {"status": "Not configured", "message": "Provider API URL is empty."}
        if provider == "stashdb":
            payload = self._graphql(base, token, query, jav_code)
            records = self._records(payload, ("scenes", "results", "data"))
        else:
            path = "/jav" if provider == "theporndb" and jav_code else "/scenes"
            params = {"q": query, "per_page": str(self.settings.get("metadata_search_results", 5) or 5), "page": "1"}
            payload = self._rest(base + path, token, params)
            records = self._records(payload, ("scenes", "movies", "jav", "results", "data"))
        matches = [self._normalise_candidate(provider, record) for record in records]
        matches = [match for match in matches if match.get("title") or match.get("provider_id")]
        return matches, {"status": "Checked", "count": len(matches)}

    def _rest(self, url: str, token: str, params: dict[str, str]) -> Any:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value})
        request = urllib.request.Request(f"{url}?{query}" if query else url, headers=self._headers(token))
        with urllib.request.urlopen(request, timeout=self._timeout()) as response:
            return json.loads(response.read(2 * 1024 * 1024).decode("utf-8", "replace") or "{}")

    def _graphql(self, url: str, token: str, title: str, jav_code: str = "") -> Any:
        query = """query SearchScenes($input: SceneQueryInput!) {
            queryScenes(input: $input) {
                count scenes { id title details release_date date code duration urls { url }
                studio { name } performers { performer { name } } tags { name } }
            }
        }"""
        input_value: dict[str, Any] = {"title": title, "page": 1, "per_page": int(self.settings.get("metadata_search_results", 5) or 5)}
        if jav_code:
            input_value["code"] = {"value": jav_code, "modifier": "EQUALS"}
        body = json.dumps({"query": query, "variables": {"input": input_value}}).encode("utf-8")
        headers = self._headers(token)
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self._timeout()) as response:
            payload = json.loads(response.read(2 * 1024 * 1024).decode("utf-8", "replace") or "{}")
        if payload.get("errors"):
            raise RuntimeError("; ".join(str(error.get("message", "GraphQL error")) for error in payload["errors"][:2]))
        return payload.get("data") or {}

    def _headers(self, token: str) -> dict[str, str]:
        auth = token if token.lower().startswith(("bearer ", "apikey ")) else f"Bearer {token}"
        return {"Accept": "application/json", "Authorization": auth, "APIKey": token, "User-Agent": "Pumpkin-Forge-Metadata/1.0"}

    def _timeout(self) -> int:
        return max(3, min(60, int(self.settings.get("metadata_timeout_seconds", 15) or 15)))

    @staticmethod
    def _records(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = MetadataService._records(value, keys)
                if nested:
                    return nested
        for value in payload.values():
            nested = MetadataService._records(value, keys)
            if nested:
                return nested
        return [payload] if any(key in payload for key in ("title", "name", "id", "uuid")) else []

    @staticmethod
    def _value(record: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = record.get(key)
            if value not in (None, "", [], {}):
                return value
        return ""

    @classmethod
    def _normalise_candidate(cls, provider: str, record: dict[str, Any]) -> dict[str, Any]:
        studio = cls._value(record, "studio", "site", "maker", "producer")
        if isinstance(studio, dict):
            studio = cls._value(studio, "name", "title")
        urls = cls._value(record, "urls", "url", "link", "permalink")
        if isinstance(urls, list):
            urls = cls._value(urls[0], "url") if urls and isinstance(urls[0], dict) else (urls[0] if urls else "")
        performers = cls._value(record, "performers", "actors", "cast")
        if isinstance(performers, list):
            performers = [cls._value(item.get("performer", item), "name", "stage_name") if isinstance(item, dict) else str(item) for item in performers]
        tags = cls._value(record, "tags", "genres", "categories")
        if isinstance(tags, list):
            tags = [cls._value(item, "name", "title") if isinstance(item, dict) else str(item) for item in tags]
        return {"provider": provider, "provider_id": str(cls._value(record, "id", "uuid", "scene_id", "movie_id")), "title": str(cls._value(record, "title", "name", "scene_name", "movie_title")), "studio": str(studio), "site": str(cls._value(record, "site", "site_name", "website")), "date": str(cls._value(record, "date", "release_date", "released_at", "air_date")), "duration": str(cls._value(record, "duration", "runtime")), "performers": performers if isinstance(performers, list) else ([str(performers)] if performers else []), "tags": tags if isinstance(tags, list) else ([str(tags)] if tags else []), "url": str(urls), "description": str(cls._value(record, "description", "details", "synopsis")), "confidence": 0}

    @staticmethod
    def _build_query(folder_name: str, video_names: list[str]) -> tuple[str, str]:
        stem = Path(video_names[0]).stem if video_names else ""
        folder_name = clean_release_name(folder_name)
        stem = clean_release_name(stem)
        jav_match = re.search(r"\b([A-Za-z]{2,10}[-_ ]?\d{3,6})\b", f"{folder_name} {stem}")
        jav_code = jav_match.group(1).replace(" ", "-").replace("_", "-").upper() if jav_match else ""
        cleaned = folder_name or stem
        cleaned = re.sub(r"\[[^\]]+\]|\([^)]*\)", " ", cleaned)
        cleaned = re.sub(r"[._]+", " ", cleaned)
        cleaned = re.sub(r"\b(?:480p|576p|720p|1080p|2160p|4k|x264|x265|h264|h265|web[- ]?dl|remux)\b", " ", cleaned, flags=re.I)
        query = re.sub(r"\s+", " ", cleaned).strip()
        if not query and stem:
            query = re.sub(r"\s+", " ", re.sub(r"\[[^\]]+\]|\([^)]*\)", " ", stem)).strip()
        query = query or folder_name
        return query[:240], jav_code

    @staticmethod
    def _confidence(candidate: dict[str, Any], query: str, jav_code: str) -> int:
        from difflib import SequenceMatcher
        title = str(candidate.get("title", ""))
        if not title:
            return 0
        left = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
        right = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        score = SequenceMatcher(None, left, right).ratio() * 75
        query_words = set(left.split())
        title_words = set(right.split())
        if query_words and title_words:
            score += (len(query_words & title_words) / len(query_words)) * 25
        if jav_code and jav_code.lower() in right:
            score = max(score, 96)
        return max(0, min(100, round(score)))


class TorrentService:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    def create(self, source_folder: str, announce_url: str, requested_name: str = "") -> dict[str, Any]:
        root = Path(source_folder).resolve()
        if not root.is_dir():
            raise RuntimeError(f"Torrent source folder is missing: {source_folder}")
        files = self._files(root)
        if not files:
            raise RuntimeError("Cannot create torrent: source folder contains no usable files")
        total_size = sum(size for _, _, size in files)
        piece_length = int(self.settings.get("piece_size") or 0) or self._piece_length(total_size)
        pieces = b""
        buffer = b""
        for path, _, _ in files:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(max(piece_length, 4 * 1024 * 1024))
                    if not chunk:
                        break
                    buffer += chunk
                    while len(buffer) >= piece_length:
                        pieces += hashlib.sha1(buffer[:piece_length]).digest()
                        buffer = buffer[piece_length:]
        if buffer:
            pieces += hashlib.sha1(buffer).digest()
        name = self._safe_name(requested_name.strip() or root.name)
        info: dict[str, Any] = {
            "name": name,
            "piece length": piece_length,
            "pieces": pieces,
            "private": 1 if self.settings.get("private_torrent", True) else 0,
            "files": [{"length": size, "path": relative.split("/")} for _, relative, size in files],
        }
        announce = str(announce_url or "").strip()
        if not BitPornTrackerValidator.validate(announce).valid:
            raise RuntimeError("Torrent announce URL is not a valid BitPorn tracker identity")
        torrent = {
            "announce": announce,
            "creation date": int(time.time()),
            "created by": str(self.settings.get("torrent_created_by") or "Pumpkin Forge"),
            "comment": str(self.settings.get("torrent_comment") or ""),
            "info": info,
        }
        output = Path(self.settings.get("torrent_directory") or "storage/torrents").resolve()
        output.mkdir(parents=True, exist_ok=True)
        output_path = output / f"{name}_{int(time.time())}_{uuid.uuid4().hex[:6]}.torrent"
        output_path.write_bytes(Bencode.encode(torrent))
        info_hash = hashlib.sha1(Bencode.encode(info)).hexdigest()
        return {"path": str(output_path), "internal_name": name, "info_hash": info_hash, "piece_length": piece_length, "file_count": len(files), "total_size": total_size}

    def read_metadata(self, torrent_path: str) -> dict[str, Any]:
        data = Bencode.decode(Path(torrent_path).read_bytes())
        info = data.get("info") or {}
        return {"announce": data.get("announce", ""), "internal_name": info.get("name", b"").decode("utf-8", "replace") if isinstance(info.get("name"), bytes) else str(info.get("name", "")), "private": bool(info.get("private", 0)), "info_hash": hashlib.sha1(Bencode.encode(info)).hexdigest(), "file_count": len(info.get("files") or [])}

    def _files(self, root: Path) -> list[tuple[Path, str, int]]:
        result = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() in TEMP_SUFFIXES or path.suffix.lower() == ".torrent":
                continue
            result.append((path, str(path.relative_to(root)).replace("\\", "/"), path.stat().st_size))
        return result

    @staticmethod
    def _piece_length(total: int) -> int:
        if total < 512 * 1024 * 1024:
            return 256 * 1024
        if total < 2 * 1024 * 1024 * 1024:
            return 512 * 1024
        if total < 8 * 1024 * 1024 * 1024:
            return 1024 * 1024
        return 2 * 1024 * 1024

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = re.sub(r'[\\/:"*?<>|]+', "_", value).strip(" .")
        return cleaned[:180] or "release"


class ThumbItService:
    def __init__(self, settings: dict[str, Any], db: Database):
        self.settings = settings
        self.db = db

    def generate_or_import(self, job_id: int, folder: str, force: bool = False) -> list[dict[str, Any]]:
        root = Path(folder).resolve()
        output = Path(self.settings.get("thumbit_output_directory") or (root / "scr")).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
            probe = output / ".pumpkin_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            fallback_root = Path(self.settings.get("generated_directory") or "storage/generated").expanduser()
            output = fallback_root / "thumbit" / str(job_id)
            output.mkdir(parents=True, exist_ok=True)
            self.db.log(job_id, f"Thumb It release scr folder is not writable; using generated output folder: {output}")
        if force:
            # Only remove image files previously recorded for this job. This
            # keeps unrelated files in a user's release/scr folder intact.
            previous_job = self.db.job(job_id) or {}
            for image in previous_job.get("images", []):
                image_path = Path(str(image.get("path", "")))
                try:
                    if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                        image_path.unlink()
                except OSError:
                    pass
            self.db.replace_images(job_id, [])
        existing = [] if force else self._collect_images(root, output)
        command_template = str(self.settings.get("thumbit_command", "")).strip()
        logo = str(self.settings.get("thumbit_logo_url") or self.settings.get("thumbit_header_logo") or "").strip()
        if not command_template and self.settings.get("thumbit_enabled", True):
            runner = Path(__file__).resolve().parent.parent / "tools" / "thumbit_headless.py"
            if runner.is_file():
                command_template = (
                    f'"{sys.executable}" "{runner}" --folder "{{folder}}" --output "{{output}}" '
                    f'--center-images "{int(self.settings.get("thumbit_center_images", 5) or 5)}" '
                    f'--still-images "{int(self.settings.get("thumbit_still_images", 5) or 5)}" '
                    f'--overlay "{{overlay}}" --logo "{logo}"'
                )
        if not existing and self.settings.get("thumbit_enabled", True) and command_template:
            overlay = str(self.settings.get("thumbit_overlay_image", "") or "")
            command = command_template.format(folder=str(root), output=str(output), logo=logo, overlay=overlay)
            args = [part.strip('"') for part in shlex.split(command, posix=False)]
            env = os.environ.copy()
            env["PUMPKIN_THUMBIT_OVERLAY_PATH"] = overlay
            completed = subprocess.run(args, capture_output=True, text=True, timeout=int(self.settings.get("thumbit_timeout_seconds", 900)), env=env)
            if completed.returncode != 0:
                details = "\n".join(part for part in [completed.stderr, completed.stdout] if part).strip()
                raise RuntimeError(f"Pumpkin's Thumb It command failed: {redact(details[-1500:] or 'No diagnostic output was returned.')}")
            existing = self._collect_images(root, output)
        if not existing:
            raise RuntimeError("No generated images found. Configure a headless Thumb It command or place generated images in the release scr folder.")
        images = []
        for path, image_type in existing:
            digest = self._hash(path)
            images.append({"path": str(path), "file_name": path.name, "file_hash": digest, "image_type": image_type, "status": "Pending", "bbcode": f"[upimg]"})
        self.db.replace_images(job_id, images)
        self.db.log(job_id, f"Prepared {len(images)} generated image(s) for BitPorn native multipart upload")
        return images

    def _collect_images(self, root: Path, output: Path) -> list[tuple[Path, str]]:
        paths = []
        for candidate_root in [output, root / "scr"]:
            if not candidate_root.exists():
                continue
            for path in sorted(candidate_root.iterdir()):
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                    lower = path.stem.lower()
                    if lower.startswith("centerlongest"):
                        image_type = "cover"
                    elif lower.startswith("center"):
                        image_type = "preview"
                    elif lower.startswith("banner"):
                        image_type = "banner"
                    else:
                        image_type = "still"
                    if str(path) not in {str(item[0]) for item in paths}:
                        paths.append((path, image_type))
        image_order = {"cover": 0, "banner": 1, "preview": 2, "still": 3}
        paths.sort(key=lambda item: (image_order.get(item[1], 9), item[0].name.casefold()))
        return paths

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


class BitPornImageHostService:
    """BitPorn's proven image path: native multipart image slots on upload.

    Pumpkin Auto does not expose a separate image-host endpoint. It attaches
    the cover, banner and description images to the BitPorn upload request.
    This service therefore prepares and caches those exact local assets; the
    tracker client attaches them once during the final upload.
    """

    def __init__(self, db: Database):
        self.db = db

    def assert_allowed(self, announce_url: str) -> BitPornValidation:
        result = BitPornTrackerValidator.validate(announce_url)
        if not result.valid:
            raise RuntimeError("BitPorn image hosting is only available for BitPorn tracker uploads. " + result.reason)
        return result


class DuplicateService:
    def __init__(self, db: Database, settings: dict[str, Any]):
        self.db = db
        self.settings = settings

    def check(self, job: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.get("duplicate_local_enabled", True):
            return {"result": "Skipped", "reason": "Local duplicate detection disabled"}
        matches = []
        for other in self.db.job_rows():
            if int(other["id"]) == int(job["id"]):
                continue
            if self.settings.get("duplicate_match_info_hash", True) and job.get("info_hash") and job.get("info_hash") == other.get("info_hash"):
                matches.append({"job_id": other["id"], "match": "info_hash"})
            elif self.settings.get("duplicate_match_title", True) and job.get("upload_title", "").strip().casefold() == str(other.get("upload_title", "")).strip().casefold() and str(other.get("status")) in {"Completed", "Uploading", "Awaiting Description", "Final Review"}:
                matches.append({"job_id": other["id"], "match": "upload_title"})
        if matches:
            return {"result": "Possible Duplicate", "reason": "A previous job has the same configured identity", "matches": matches}
        return {"result": "Clear", "reason": "No local duplicate matched", "matches": []}


class BitPornTrackerClient:
    def __init__(self, db: Database, settings: dict[str, Any]):
        self.db = db
        self.settings = settings

    def upload(self, job: dict[str, Any], tracker: dict[str, Any]) -> dict[str, Any]:
        selected_type = tracker_type(tracker)
        validation = BitPornTrackerValidator.validate(tracker.get("announce_url", ""))
        if selected_type == "bitporn" and not validation.valid:
            raise RuntimeError("Final BitPorn tracker validation failed: " + validation.reason)
        if selected_type not in {"bitporn", "external_unit3d"}:
            raise RuntimeError("Unsupported tracker profile")
        endpoint = str(tracker.get("upload_endpoint", "")).strip()
        endpoint_parts = urllib.parse.urlsplit(endpoint)
        endpoint_host = (endpoint_parts.hostname or "").lower().rstrip(".")
        if endpoint_parts.scheme.lower() != "https" or not endpoint_host:
            raise RuntimeError("Tracker upload endpoint must use HTTPS")
        if selected_type == "bitporn" and endpoint_host not in {"bitporn.eu", "www.bitporn.eu"}:
            raise RuntimeError("Refused to send BitPorn credentials to an untrusted upload endpoint")
        token = str(tracker.get("api_key", "")).strip()
        if not token:
            raise RuntimeError(f"{tracker.get('name') or 'Tracker'} API key/token is not configured")
        fields: dict[str, str] = {
            "name": job.get("upload_title") or job.get("torrent_internal_name") or job.get("folder_name", "release"),
            "description": job.get("description", ""),
            "category_id": str(job.get("category", "")),
            "type_id": str(job.get("type", "")),
            "resolution_id": str(job.get("resolution", "")),
            "keywords": ", ".join(safe_json(job.get("tags_json", "[]")) or []),
            "anonymous": "1" if job.get("anonymous") else "0",
            "mod_queue_opt_in": "1" if job.get("moderation_queue") else "0",
            "personal_release": "1" if job.get("personal_release") else "0",
            "internal": "1" if job.get("internal_release") else "0",
        }
        if tracker.get("source"):
            fields["source"] = str(tracker["source"])
        extra_fields = safe_json(tracker.get("custom_fields_json", "{}"))
        if isinstance(extra_fields, dict):
            for key, value in extra_fields.items():
                field_name = str(key).strip()
                if field_name and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", field_name) and field_name not in fields:
                    fields[field_name] = str(value)
        files = [("torrent", job.get("torrent_path", ""))]
        images = self.db.conn.execute("SELECT * FROM job_images WHERE job_id=? ORDER BY id", (job["id"],)).fetchall()
        # BitPorn accepts local multipart image slots. External trackers need
        # their own image host URLs in the description/custom fields instead.
        if selected_type == "bitporn":
            cover = next((row["path"] for row in images if row["image_type"] == "cover"), "")
            banner = next((row["path"] for row in images if row["image_type"] == "banner" and row["path"] != cover), "")
            if cover:
                files.append(("cover", cover))
            if banner:
                files.append(("banner", banner))
            for index, row in enumerate(row for row in images if row["image_type"] in {"preview", "still"}):
                files.append((f"description_images[{index}]", row["path"]))
        body, content_type = self._multipart(fields, files)
        request = urllib.request.Request(endpoint, data=body, method="POST", headers={"Content-Type": content_type, "Authorization": f"Bearer {token}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=int(self.settings.get("bitporn_upload_timeout_seconds", 180))) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read(1024 * 1024)
            raise RuntimeError(f"BitPorn upload failed: HTTP {exc.code} {redact(raw.decode('utf-8', 'replace'), [token])}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"BitPorn upload request failed: {redact(str(exc), [token])}") from exc
        if len(raw) > 4 * 1024 * 1024:
            raise RuntimeError("BitPorn upload response exceeded the 4 MB safety limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("BitPorn upload returned invalid JSON") from exc
        if status >= 400 or payload.get("success") is False:
            raise RuntimeError("BitPorn upload rejected: " + redact(json.dumps(payload, ensure_ascii=False), [token]))
        for row in images:
            self.db.conn.execute("UPDATE job_images SET status='Uploaded',uploaded_at=? WHERE id=?", (utc_now(), row["id"]))
        self.db.conn.commit()
        return {"status": status, "response": payload, "uploaded_at": utc_now()}

    @staticmethod
    def _multipart(fields: dict[str, str], files: list[tuple[str, str]]) -> tuple[bytes, str]:
        boundary = "----PumpkinForge" + uuid.uuid4().hex
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), str(value).encode("utf-8"), b"\r\n"])
        for name, path in files:
            if not path or not Path(path).is_file():
                continue
            filename = Path(path).name
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            chunks.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(), f"Content-Type: {mime}\r\n\r\n".encode(), Path(path).read_bytes(), b"\r\n"])
        chunks.append(f"--{boundary}--\r\n".encode())
        return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
