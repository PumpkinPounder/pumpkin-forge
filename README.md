# Pumpkin Forge

> **Early beta:** Pumpkin Forge is still in very early development and is not yet 100% ready for production use. Test carefully, review every release manually, and keep backups of your local data.

Pumpkin Forge is a local, review-first release builder for preparing media releases, generating release images, building UNIT3D-compatible descriptions, creating torrents, and submitting approved uploads to configured trackers.

It is designed to keep the sensitive part of the workflow on the user's own computer. Tracker credentials, provider tokens, release history, job state, and local paths are stored in the local application database and are never part of the public source repository.

## Quick navigation

| Go to | What it covers |
| --- | --- |
| [What Pumpkin Forge does](#what-pumpkin-forge-does) | Application purpose and design |
| [Requirements](#requirements) | Windows and software requirements |
| [Start the application](#start-the-application) | Launching the app and opening the dashboard |
| [First-time setup](#first-time-setup) | Settings to complete before processing releases |
| [Release workflow](#release-workflow) | The complete review-first process |
| [Folder monitoring](#folder-monitoring) | Automatic detection of release folders and media files |
| [Thumb It and generated images](#thumb-it-and-generated-images) | Image generation, layouts, and troubleshooting |
| [Metadata matching](#metadata-matching) | Optional ThePornDB and StashDB matching |
| [Descriptions and BBCode Lab](#descriptions-and-bbcode-lab) | Editing and previewing descriptions |
| [Tracker profiles](#tracker-profiles) | BitPorn and external UNIT3D configuration |
| [Review and upload safety](#review-and-upload-safety) | Final checks before anything is submitted |
| [Files and local storage](#files-and-local-storage) | What is stored locally and where |
| [GitHub updates](#github-updates) | Version checking with `version.txt` |
| [Troubleshooting](#troubleshooting) | Common problems and solutions |
| [Development and testing](#development-and-testing) | Running tests and contributing changes |
| [Privacy and credentials](#privacy-and-credentials) | Keeping tokens and private data out of GitHub |
| [Reporting an issue](#reporting-an-issue) | How to request help or report a bug |

## What Pumpkin Forge does

Pumpkin Forge separates release preparation into visible stages rather than silently uploading files in the background:

1. Detect or select a local release folder.
2. Wait until files are stable before scanning them.
3. Read media information from the release files.
4. Generate or import the configured release images.
5. Check optional metadata providers for possible matches.
6. Create a private torrent using the selected tracker announce identity.
7. Build a description from the release information and generated images.
8. Pause at **Awaiting Description** for manual editing.
9. Send the release to **Final Review**.
10. Run the final safety checks and upload only after approval.

The application is local-first: the web interface listens on the local computer, while the worker performs the processing in the same application.

## Requirements

- Windows 10 or newer is recommended.
- Python 3.11 or newer.
- `ffmpeg` and `ffprobe` available on the system `PATH`, or configured with their full paths in Settings.
- Network access for tracker uploads, optional metadata lookups, GitHub version checks, and any configured image service.
- A tracker account and API credentials for live uploads.

Pumpkin Forge does not include or distribute tracker credentials. Each user supplies their own credentials through the local Settings page.

## Start the application

### Using the launcher

Double-click **Start Pumpkin Forge.bat**. The launcher starts the local server, waits for it to become reachable, and opens the dashboard in the default browser. Keep the launcher window open while using the application.

### Using Python directly

From the Pumpkin Forge folder:

```powershell
python main.py
```

The default port is `8766`. Existing installations may have a saved port such as `8877` in their local database. Open the address shown in the launcher window, or check the **Web UI port** field in Settings.

The default local-only address is:

```text
http://127.0.0.1:8766
```

If another local application is using that port, change the port in **Settings → Application** and restart Pumpkin Forge. Keeping the bind address as `127.0.0.1` limits access to the same computer.

## First-time setup

Open **Settings** and work through the sections from top to bottom. Each group can be opened or collapsed, and the top navigation tabs jump directly to the relevant settings.

### Application

Configure the local processing locations and network settings:

- **Web UI port**: local TCP port used by the browser interface.
- **Bind address**: normally `127.0.0.1` for local-only access.
- **Working directory**: temporary files used while a job is processed.
- **Generated directory**: generated images and other derived files.
- **Torrent directory**: newly created torrent files.

Relative paths are portable. They are resolved beneath the Pumpkin Forge folder, so the project can be moved to another drive without creating a second embedded drive path.

### Thumb It

Configure the bundled Pumpkin's Thumb It integration:

- Enable or disable automatic thumbnail generation.
- Set the Thumb It script path if using a different copy.
- Set the logo or release image used in generated output.
- Set the optional overlay image, or leave it blank to disable the overlay.
- Set the number of centre images and still images to prepare.
- Set the timeout and retry count.
- Optionally provide a custom headless command using `{folder}`, `{output}`, `{logo}`, and `{overlay}` substitutions.

The bundled headless runner is used when no custom command is supplied and Thumb It is enabled.

### Upload and workflow

These settings control upload timing and review behaviour:

- Image and upload request timeouts.
- Retry count for failed network operations.
- BBCode image width defaults.
- Whether jobs must pass through Final Review.
- Whether processing starts automatically after detection.

### Updates

To check for a newer release, enter the raw URL for the repository's `version.txt` file:

```text
https://raw.githubusercontent.com/PumpkinPounder/pumpkin-forge/main/version.txt
```

Enable GitHub update checks and use **Check for updates**. Pumpkin Forge compares the installed version with the remote version and reports the result. It does not download or install updates automatically.

### Metadata

Metadata matching is optional. Configure provider URLs and tokens locally, then enable the providers you want to use. Tokens are stored in the local database and are masked from the browser state returned by the application.

## Release workflow

### 1. Add a release

There are two ways to add work:

- Use **Add local release** to select one folder for one-time processing.
- Configure **Folder Monitoring** to watch a parent folder whose child release folders become jobs.

The folder browser selects the folder on the local machine and writes the selected path into the form before it is saved.

### 2. Wait for file stability

Pumpkin Forge waits for a release to stop changing before it scans it. This prevents a partially copied file from being treated as a complete release.

When a monitored folder contains supported media files directly rather than child folders, Pumpkin Forge can create a folder from the filename without its extension and move the matching file into it. Multiple loose files are handled gradually, with a dashboard notice showing the current progress so the drive is not hammered by repeated scans.

### 3. Scan the release

The media scanner records file count, total size, video count, duration, resolution, codecs, frame rate, pixel format, audio channels, and language where available.

### 4. Generate release images

Pumpkin Forge runs the configured Thumb It stage or imports existing output from the release `scr` folder. Generated assets are shown in the job and can be regenerated from the description screen.

### 5. Match metadata

If enabled, the application searches the configured metadata providers using cleaned release information. Site prefixes and tracker labels are removed from the search query when appropriate, improving matches for titles such as:

```text
[Studio.com OtherStudio.com] Example Release Title
```

The search query becomes the useful title portion rather than the entire tracker-style folder name. Matches are suggestions only: the user chooses whether to apply one.

### 6. Create the torrent

The torrent is created locally with the selected tracker announce URL. Pumpkin Forge reads the actual torrent name and info hash instead of guessing them from the folder name.

### 7. Build the description

The job pauses at **Awaiting Description**. Select **Build Description** to edit the title, category, type, resolution, tags, flags, and BBCode description.

### 8. Review and approve

Save the description and continue to **Final Review**. Check the title, tracker, torrent details, image set, BBCode, and upload fields. The upload is not sent until the final action is approved.

## Folder monitoring

Folder monitoring is intended for a parent directory containing release folders. Each child release folder can become one job.

For each monitor, configure:

- **Folder name**: friendly label shown in the application.
- **Path**: parent folder to monitor.

The monitor checks at a controlled interval and waits for file stability. Avoid pointing it at a large, constantly changing download directory unless that is intentional.

## Thumb It and generated images

Pumpkin Forge includes a copy of the Thumb It integration under `tools/`. The original reference application is not modified.

The standard generated set may include:

- A centre preview image.
- A `centerlongest_<release>.webp` cover image. This is the preferred cover for the live description preview.
- Still screenshots sampled through the video.
- One or more screenshot sheets or thumbnail collages.

The number of centre and still images can be changed in Settings. Existing images can be imported from the release `scr` folder, and the **Regenerate thumbnails** action forces a fresh generation attempt.

If a job reports **No generated images found**, check the following:

1. The release contains a supported video file.
2. Thumb It is enabled in Settings.
3. The Thumb It script path is correct.
4. `ffmpeg` and `ffprobe` are installed and available.
5. The release `scr` folder is writable, or the generated output directory is writable.
6. A custom command contains the correct substitutions and produces files in its configured output directory.

## Metadata matching

Pumpkin Forge can use optional providers to suggest titles, studios, performers, dates, tags, and scene information. Provider errors do not stop the local media scan.

### ThePornDB

ThePornDB is intended for general adult scene, performer, studio, and related metadata. Add the API URL and token in **Settings → Metadata**. Leave it disabled or blank if it is not needed.

### StashDB

StashDB is intended for scene matching through its GraphQL endpoint. Add the GraphQL URL and token in **Settings → Metadata**. It is also optional.

### Matching tips

- Search with the meaningful release title rather than tracker prefixes.
- Remove unnecessary resolution, codec, and release-group text when a provider does not return results.
- Use **Refresh metadata** after changing provider settings.
- Treat results as suggestions and confirm the chosen match manually.

## Descriptions and BBCode Lab

The description editor provides a UNIT3D-compatible BBCode input with formatting tools and insertion buttons for generated assets.

### Live website view

The right-hand **Live Website View — BBCode** panel renders the description as visitors would see it. It updates while the BBCode is edited and is separate from the raw BBCode editor.

Use the preview to check:

- Heading sizes and alignment.
- Colour separators and section headings.
- Cover or release image placement.
- The `centerlongest` cover position.
- Still-image rows and thumbnail sheets.
- Release information spacing.
- Whether unsupported or malformed tags are visible.

### BBCode Lab

**BBCode Lab** is a blank UNIT3D-compatible sandbox for testing descriptions. It does not use the current job description as its starting content. Use the top navigation or sidebar link to open it, paste test BBCode, and view the rendered result.

The layout selector is reserved for reusable description layouts. Layouts can insert a configured logo or release image, release information, the preferred cover, still images, and thumbnail sheets while preserving the intended BBCode structure.

### Image insertion

Insert generated files only where they are needed. The normal description pattern is:

1. One `centerlongest_<release>.webp` image as the main cover.
2. The still screenshots centred beneath the Screenshots heading.
3. The thumbnail sheet or sheets beneath the still screenshots.

The live preview is designed to preserve the grouping created by `[center]...[/center]` blocks. If several images appear in one line, check that the source description contains the same centred groups expected by the target tracker.

## Tracker profiles

### BitPorn

The BitPorn profile uses its native UNIT3D upload fields and BitPorn's supported image handling. Configure the site URL, API URL, upload endpoint, announce URL, API key, source, and the default category, type, and resolution IDs.

The Build Description dropdowns use the saved category, type, and resolution mappings. The selected defaults are applied when a new description is created.

### External UNIT3D trackers

External UNIT3D profiles are configured separately. The user must provide the complete tracker details, including:

- Tracker name and site URL.
- API URL and upload endpoint.
- Announce URL.
- API key or token.
- Source value.
- Category, type, and resolution mappings.
- Any additional UNIT3D-specific fields required by that tracker.

External profiles are not assumed to have BitPorn's image-host behaviour. Supply image-host URLs accepted by the destination tracker and verify the resulting description in Final Review.

## Review and upload safety

Pumpkin Forge uses backend checks in addition to the browser interface. This matters because browser controls alone can be bypassed by editing a page or sending a direct request.

> **🚫 BitPorn image host restriction**
>
> BitPorn's image host is configured for **BitPorn uploads only**. It must not be used for external trackers. If an external UNIT3D upload contains BitPorn-hosted image URLs, Pumpkin Forge **blocks the upload before anything is sent**. Replace those URLs with images hosted by the destination tracker, then return to Final Review.

Before an upload, the application checks the selected tracker profile, announce identity, required credentials, torrent file, description, and image fields.

BitPorn-hosted image usage is restricted to the BitPorn workflow. If a release is configured for another tracker while the description contains BitPorn-hosted image URLs, the upload is blocked with a clear message asking the user to replace the image host.

The application does not silently change a release and does not upload a job that fails final validation. Correct the issue, regenerate or replace the affected assets, and return to Final Review.

## Files and local storage

The important source files are:

| Path | Purpose |
| --- | --- |
| `main.py` | Starts the worker and local web server |
| `app/database.py` | Local SQLite schema, defaults, and persistence |
| `app/services.py` | Media, metadata, torrent, image, and tracker services |
| `app/workflow.py` | Job processing and review workflow |
| `app/web.py` | Local HTTP API and page serving |
| `app/static/` | Browser interface, styles, and BBCode tools |
| `tools/ThumbIt.py` | Bundled Thumb It application copy |
| `tools/thumbit_headless.py` | Headless image-generation runner |
| `tools/assets/` | Bundled Thumb It assets |
| `data/app.db` | Local settings, jobs, logs, tokens, and history |
| `storage/working` | Temporary processing files |
| `storage/generated` | Generated release assets |
| `storage/torrents` | Locally created torrent files |
| `version.txt` | Installed application version |

`data/` and `storage/` are intentionally ignored by Git. They are created automatically when the application starts.

## Backups and moving the application

For a full local backup, stop Pumpkin Forge and copy the complete application folder, including `data/app.db`, if you want to preserve settings, jobs, logs, and credentials. Keep that backup private.

To create a clean code copy for GitHub, copy only the source-controlled files or use Git with the included `.gitignore`. Do not copy `data/app.db` into a public repository.

Relative storage paths are resolved from the folder containing `main.py`. This allows the application to be moved between folders or drives without retaining stale paths from an older build.

## GitHub updates

The installed version is read from `version.txt`. The Settings page can compare it with a remote raw GitHub `version.txt` file.

For this repository, the raw URL is:

```text
https://raw.githubusercontent.com/PumpkinPounder/pumpkin-forge/main/version.txt
```

Update checking only reports whether a newer version exists. It does not install files, replace the application, or change local settings.

## Troubleshooting

### The browser says connection refused

Check that the launcher window is still open and that the displayed port matches the browser address. If the port is occupied, change **Web UI port** in Settings and restart the application.

### The browser opens before the app is ready

The launcher waits for the local server socket before opening the dashboard. If a stale browser tab is open, close it and use the address printed by the launcher.

### A folder browser does not fill the path

Refresh the page, use the Browse button again, select the actual folder rather than a file, and confirm that the selected path appears in the field before clicking **Add monitored folder**.

### A job stays at Awaiting Description

That is an intentional review stage. Open **Awaiting Description**, select the job, build or edit the description, save it, and continue to Final Review.

### Metadata says no confident match

Confirm that the provider token is configured, refresh metadata, and search with the meaningful title without tracker prefixes. A provider returning no match does not mean the local release scan failed.

### Thumb It fails

Check the video format, `ffmpeg`/`ffprobe`, Thumb It path, output permissions, and the generated-image settings. Use **Regenerate thumbnails** after correcting the configuration.

### The live preview does not match the BBCode grouping

Make sure each intended row is inside its own `[center]...[/center]` block and that the image tags are valid for the destination tracker. The raw editor shows exactly what will be sent; the live panel shows the rendered interpretation.

### An upload is blocked for image-host reasons

Confirm the selected tracker profile and replace any image URL belonging to a different tracker or image host. The block is intentional and is enforced by the backend.

## Development and testing

Install the tool requirements when needed:

```powershell
python -m pip install -r tools/requirements.txt
```

Run the test suite from the application folder:

```powershell
python -m unittest discover -s tests -v
```

Keep generated output, local databases, torrents, and test media outside commits. Changes to the browser interface are primarily in `app/static/`; workflow and validation changes are primarily in `app/workflow.py` and `app/services.py`.

## Privacy and credentials

Never commit:

- `data/app.db` or database sidecar files.
- API keys, bearer tokens, passkeys, passwords, or cookies.
- Local release paths that reveal private storage locations.
- Generated media, torrents, logs, or personal backups.
- `.env` files containing credentials.

The repository `.gitignore` excludes these categories. Before publishing a change, inspect the staged file list and confirm that only source files, documentation, tests, and safe example assets are included.

If a credential is ever committed or shared accidentally, revoke it at the provider and create a replacement. Removing it from the latest file is not enough if it remains in Git history.

## Reporting an issue

Please report bugs and feature requests through the [Pumpkin Forge GitHub issue tracker](https://github.com/PumpkinPounder/pumpkin-forge/issues/new).

When reporting a problem, include:

- What you were trying to do.
- The page and action involved.
- The visible warning or error text.
- Whether the issue is repeatable.
- The relevant application log message with credentials and private paths removed.
- Your Windows and Python versions when relevant.

Do not include API keys, tokens, cookies, passwords, private tracker URLs, or release media in an issue report.
