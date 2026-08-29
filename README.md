# Pumpkin Forge

Pumpkin Forge is a local, review-first torrent preparation and upload application for BitPorn-compatible UNIT3D workflows.

## Start

From this folder:

```powershell
python main.py
```

Or double-click `Start Pumpkin Forge.bat`. The launcher starts the server on port `8766` and opens the dashboard automatically in the default browser. Keep the launcher window open while using the app.

Open `http://127.0.0.1:8877` in a browser. The port and bind address are stored in SQLite Settings and can be changed from the Settings page. `8877` avoids the ReelOps service on port `8765`.

The application creates `data/app.db`, `storage/working`, `storage/generated`, and `storage/torrents` on first start.

The sidebar uses `app/static/pumpkin-logo.png`. The installed application version is stored in `version.txt`. In Settings, enter the raw GitHub URL for the repository's `version.txt`, for example `https://raw.githubusercontent.com/OWNER/REPO/main/version.txt`, then use **Check for updates**. The backend compares semantic versions and reports whether an update is available; it does not download or install anything automatically.

Pumpkin's Thumb It is copied into `tools/ThumbIt.py` with its bundled overlay asset and requirements file. The reference application remains unchanged.

## Current workflow

1. Add a release folder from the dashboard or configure a monitored folder.
2. The worker waits for stability and scans the release.
3. It imports existing Pumpkin's Thumb It output, or runs the bundled headless Thumb It runner automatically. A custom `thumbit_command` can still override it using `{folder}`, `{output}`, `{logo}`, and `{overlay}` substitutions.
4. It creates a private torrent and reads the actual internal torrent name and info hash.
5. It enforces the BitPorn announce identity on the backend.
6. It prepares the proven Pumpkin Auto-compatible native BitPorn image slots.
7. It performs local duplicate detection.
8. It pauses at **Awaiting Description**.
9. Build and save a BBCode description, select tags and upload flags, then inspect the torrent on **Final Review**.
10. Approval performs the final BitPorn validation and submits the real multipart UNIT3D request.

## BitPorn image behavior

The reference Pumpkin Auto implementation does not expose a separate generic image-host API. It attaches the cover, banner, and description images to the BitPorn torrent upload request using native multipart fields. This project keeps that proven behavior in `app/services.py` and does not invent a custom image-host protocol.

The validator accepts only HTTPS URLs whose host is `bitporn.eu` or `www.bitporn.eu` and whose path is `/announce` or `/announce/<tracker credential>`. It rejects lookalike hosts, query-string tricks, HTTP, and unrelated UNIT3D sites. The check is performed before image preparation and again before final upload.

## Configuration

Normal operational values are stored in SQLite and exposed in the web UI. Tracker API keys are masked in the UI and are not returned by the API state endpoint. Logs redact bearer tokens, API keys, passkeys, and password-like values.

The reference folder is read-only by convention and is not modified by the new application.

## Windows path portability fix

This build repairs stale `/mnt/data/...` storage paths left by an earlier UI-refresh package. The working, generated, and torrent folders default to portable paths under the application folder, so moving Pumpkin Forge between Windows folders or drives does not create an invalid double-drive path.
