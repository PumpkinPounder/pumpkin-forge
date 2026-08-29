"""Headless Pumpkin's Thumb It runner used by the Pumpkin Forge workflow."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".mts", ".3gp", ".ogv", ".divx", ".asf"}


def load_thumbit():
    module_path = Path(__file__).with_name("ThumbIt.py")
    spec = importlib.util.spec_from_file_location("pumpkin_thumbit", module_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load Pumpkin's Thumb It from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Pumpkin's Thumb It images without opening its GUI")
    parser.add_argument("--folder", required=True, help="Release folder to scan")
    parser.add_argument("--output", default="", help="Optional folder to collect generated images")
    parser.add_argument("--overlay", default="", help="Overlay image path; blank disables the overlay")
    parser.add_argument("--logo", default=None, help="Remote URL or local header/logo image; an empty value disables it")
    parser.add_argument(
        "--center-images",
        type=int,
        default=5,
        help="Maximum number of video files to prepare (1-5)",
    )
    parser.add_argument(
        "--still-images",
        type=int,
        default=5,
        help="Compatibility setting; still sheets follow the selected video-file count",
    )
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        raise RuntimeError(f"Release folder does not exist: {folder}")

    collection = Path(args.output).expanduser().resolve() if args.output else folder / "scr"
    collection.mkdir(parents=True, exist_ok=True)

    os.environ["PUMPKIN_THUMBIT_HEADLESS"] = "1"
    os.environ["PUMPKIN_THUMBIT_OVERLAY_PATH"] = str(Path(args.overlay).expanduser().resolve()) if args.overlay else ""
    os.environ["PUMPKIN_THUMBIT_OUTPUT_DIR"] = str(collection)
    if args.logo is not None:
        logo = args.logo.strip()
        if logo.lower().startswith(("http://", "https://")):
            os.environ["PUMPKIN_THUMBIT_LOGO_URL"] = logo
        else:
            os.environ["PUMPKIN_THUMBIT_LOGO_URL"] = str(Path(logo).expanduser().resolve()) if logo else ""

    thumbit = load_thumbit()
    thumbit._resolve_ff_tools()
    cfg = dict(thumbit.SPEED_PROFILES.get("Fast", thumbit.SPEED_PROFILES["Normal"]))
    videos = [path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]
    if not videos:
        raise RuntimeError("No supported video files found in the release folder")

    # Remove only names owned by the automated layout generator. This clears
    # stale center2..center5/sheet files when a release is regenerated with
    # fewer source videos, without touching unrelated images in scr.
    generated_names = {
        *(f"center{index}.webp" for index in range(1, 6)),
        *(f"sheet{index}.png" for index in range(1, 6)),
    }
    for cleanup_root in {collection, folder / "scr"}:
        if not cleanup_root.is_dir():
            continue
        for name in generated_names:
            candidate = cleanup_root / name
            if candidate.is_file():
                candidate.unlink()
        for candidate in cleanup_root.glob("sheet_*.png"):
            if candidate.is_file():
                candidate.unlink()

    generated: list[Path] = []
    file_count = max(1, min(5, int(args.center_images or 5)))
    selected_videos = sorted(videos, key=lambda path: str(path).casefold())[:file_count]
    longest = thumbit.find_longest_video([str(path) for path in videos]) or str(selected_videos[0])
    folder_tag = thumbit._safe_tag(folder.name or "release")

    # Keep the focused centre preview used by existing descriptions and
    # create the full Thumb It contact-sheet layouts beside it.  The sheet
    # generator writes PNGs to the video's native scr folder, while WebPs
    # honour the configured output directory.
    longest_output = thumbit.create_middle_animated_webp(
        longest,
        cfg,
        f"centerlongest_{folder_tag}.webp",
        clip_seconds=thumbit.CENTERLONGEST_SECONDS,
        out_fps=thumbit.CENTERLONGEST_FPS,
        skip_existing=False,
    )
    if longest_output:
        generated.append(Path(longest_output))

    # generate_thumbnail_sheet uses the fixed name center1.webp internally.
    # Give each source video its own temporary output directory, then copy it
    # to the public center1..center5 name so numbering maps to video files.
    work_output = collection / ".pumpkin_thumbit_work"
    work_output.mkdir(parents=True, exist_ok=True)
    previous_output = os.environ.get("PUMPKIN_THUMBIT_OUTPUT_DIR", "")
    os.environ["PUMPKIN_THUMBIT_OUTPUT_DIR"] = str(work_output)
    try:
        for file_index, video_path in enumerate(selected_videos, start=1):
            sheet_png, _ = thumbit.generate_thumbnail_sheet(
                str(video_path),
                cfg,
                anim_index=None,
                skip_existing=False,
            )
            if sheet_png:
                sheet_destination = collection / f"sheet{file_index}.png"
                shutil.copy2(sheet_png, sheet_destination)
                generated.append(sheet_destination)
                # Do not let the descriptive native name create a duplicate
                # image in Pumpkin Forge's image collection.
                native_sheet = Path(sheet_png)
                if native_sheet.resolve() != sheet_destination.resolve():
                    native_sheet.unlink(missing_ok=True)

            _sheet_png, center_output = thumbit.generate_thumbnail_sheet(
                str(video_path),
                cfg,
                anim_index=1,
                skip_existing=False,
            )
            if center_output:
                center_destination = collection / f"center{file_index}.webp"
                shutil.copy2(center_output, center_destination)
                generated.append(center_destination)
    finally:
        if previous_output:
            os.environ["PUMPKIN_THUMBIT_OUTPUT_DIR"] = previous_output
        else:
            os.environ.pop("PUMPKIN_THUMBIT_OUTPUT_DIR", None)
        shutil.rmtree(work_output, ignore_errors=True)

    if not generated:
        raise RuntimeError("Thumb It did not produce any images")

    for path in generated:
        destination = collection / path.name
        if path.resolve() != destination.resolve():
            shutil.copy2(path, destination)
        print(destination)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Thumb It headless runner failed: {exc}")
        raise SystemExit(1)
