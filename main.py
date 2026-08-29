from __future__ import annotations

import os
import re
import signal
import socket
import threading
import time
import webbrowser
from pathlib import Path

from app.database import Database
from app.web import AppServer
from app.workflow import Workflow


ROOT = Path(__file__).resolve().parent
DEFAULT_URL = "http://127.0.0.1:8877"
STORAGE_DEFAULTS = {
    "working_directory": "storage/working",
    "generated_directory": "storage/generated",
    "torrent_directory": "storage/torrents",
}


def open_browser_when_ready(url: str) -> None:
    """Open the local dashboard after the HTTP socket has been bound."""

    def launch() -> None:
        time.sleep(0.75)
        try:
            webbrowser.open_new_tab(url)
        except Exception as exc:
            print(f"Could not open the browser automatically: {exc}")

    threading.Thread(target=launch, name="pumpkin-open-browser", daemon=True).start()


def wait_for_socket(host: str, port: int, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.15)
    raise RuntimeError(f"The web server did not become reachable at {host}:{port}: {last_error}")


def is_stale_build_path(value: object) -> bool:
    """Return True for paths accidentally persisted by a different build machine.

    Older UI-refresh builds could save a container path such as
    /mnt/data/.../J:/Pumpkin Local Upload/storage/working. On Windows that
    becomes an invalid path containing a second drive letter. These values are
    safe to replace with the application's normal portable storage defaults.
    """

    raw = str(value or "").strip()
    if not raw:
        return False

    normalised = raw.replace("\\", "/").lower()
    if "/mnt/data/" in normalised or "pumpkin_ui_work" in normalised:
        return True

    # Detect an embedded Windows drive letter, e.g. C:/some/path/J:/other/path.
    # A normal path beginning with J:/ is deliberately not matched.
    if re.search(r".+/[a-z]:/", normalised, flags=re.IGNORECASE):
        return True

    return False


def prepare_storage_directories(database: Database, settings: dict[str, object]) -> dict[str, object]:
    """Repair stale storage settings and make the required directories.

    Relative settings stay relative in the database so the whole Pumpkin Forge
    folder remains portable if it is moved to another drive or directory.
    Runtime path resolution is anchored to ROOT by changing the process working
    directory at startup.
    """

    repaired: dict[str, object] = {}

    for key, default in STORAGE_DEFAULTS.items():
        raw_value = settings.get(key) or default

        if is_stale_build_path(raw_value):
            print(f"Repairing stale {key} path from an older build.")
            raw_value = default
            settings[key] = default
            repaired[key] = default

        value = Path(str(raw_value)).expanduser()
        if not value.is_absolute():
            value = ROOT / value

        try:
            value.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Could not create {key}: {value}") from exc

    if repaired:
        database.save_settings(repaired)

    return settings


def main() -> None:
    # Make every relative application path resolve from the folder containing
    # main.py, even when Python was launched from another working directory.
    os.chdir(ROOT)

    database = Database(ROOT / "data" / "app.db")
    settings = database.settings()
    settings = prepare_storage_directories(database, settings)

    database.ensure_default_tracker()
    workflow = Workflow(database)
    workflow.start()
    host = str(settings.get("bind_address") or "127.0.0.1")
    port = int(settings.get("web_port") or 8766)

    try:
        server = AppServer(database, workflow, ROOT / "app", host, port)
    except OSError as exc:
        workflow.stop()
        database.close()
        raise RuntimeError(
            f"Could not start Pumpkin Forge on {host}:{port}. Is another app using this port?"
        ) from exc

    signal.signal(signal.SIGINT, lambda *_: server.shutdown())
    signal.signal(signal.SIGTERM, lambda *_: server.shutdown())
    url = f"http://{host}:{port}"
    server_thread = threading.Thread(target=server.serve_forever, name="pumpkin-web-server", daemon=True)
    server_thread.start()

    try:
        wait_for_socket(host, port)
    except Exception:
        server.shutdown()
        workflow.stop()
        database.close()
        raise

    print(f"Pumpkin Forge running at {url}")
    print("Web server is reachable. Opening the dashboard in your default browser...")
    open_browser_when_ready(url)

    try:
        server_thread.join()
    finally:
        workflow.stop()
        database.close()


if __name__ == "__main__":
    main()
