"""
Snapchat Memories Downloader
Usage: python downloader.py [path/to/mydata~*.zip]
If no argument is given, searches for mydata~*.zip in the current directory.
"""

import os
import re
import sys
import json
import time
import shutil
import hashlib
import zipfile
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image, ImageOps
from tqdm import tqdm
import piexif
from mutagen.mp4 import MP4

import config
import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".gif"}


def detect_type(header: bytes) -> tuple[str, str] | None:
    """Return (extension, media_type) from first 16 bytes, or None if HTML/unknown."""
    if len(header) < 4:
        return None
    if header[:5].lower() in (b"<!doc", b"<html"):
        return None
    if header[:3] == b"\xff\xd8\xff":
        return ".jpg", "image"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png", "image"
    if header[4:8] in (b"ftyp", b"mdat", b"moov", b"wide"):
        return ".mp4", "video"
    if header[:4] == b"PK\x03\x04":
        return ".zip", "zip"
    return None


def parse_location(raw: str) -> tuple[float, float] | None:
    m = re.search(r"([-\d.]+),\s*([-\d.]+)\s*$", raw)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def extract_uuid(text: str) -> str | None:
    m = re.search(
        r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}",
        text,
    )
    return m.group(0).upper() if m else None


def make_entry_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def make_filename(date_str: str, entry_id: str, ext: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
    return f"{dt.strftime('%Y%m%d_%H%M%S')}_{entry_id[:8]}{ext}"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path, session: requests.Session) -> tuple[bool, tuple | None]:
    """Download URL to dest. Returns (success, (ext, media_type))."""
    tmp = dest.with_suffix(".tmp")
    for attempt, delay in enumerate([0] + config.RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            resp = session.get(url, timeout=60, stream=True)
            if resp.status_code >= 400:
                raise ValueError(f"HTTP {resp.status_code}")

            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(65536):
                    f.write(chunk)

            if tmp.stat().st_size < 100:
                raise ValueError("File too small")

            with open(tmp, "rb") as f:
                header = f.read(16)

            type_info = detect_type(header)
            if type_info is None:
                raise ValueError("HTML or unknown content")

            tmp.rename(dest)
            return True, type_info

        except Exception as e:
            if tmp.exists():
                tmp.unlink()
            if attempt == len(config.RETRY_DELAYS):
                return False, None
            # Will retry

    return False, None


# ---------------------------------------------------------------------------
# Metadata writing
# ---------------------------------------------------------------------------

def _to_dms_rational(value: float):
    d = int(abs(value))
    m = int((abs(value) - d) * 60)
    s = round(((abs(value) - d) * 60 - m) * 60 * 10000)
    return (d, 1), (m, 1), (s, 10000)


def write_image_exif(path: Path, date_str: str, lat: float | None, lon: float | None):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
        exif_date = dt.strftime("%Y:%m:%d %H:%M:%S").encode()

        try:
            exif_dict = piexif.load(str(path))
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

        exif_dict.setdefault("Exif", {})[piexif.ExifIFD.DateTimeOriginal]  = exif_date
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized]                = exif_date
        exif_dict.setdefault("0th",  {})[piexif.ImageIFD.DateTime]         = exif_date

        if lat is not None and lon is not None:
            exif_dict["GPS"] = {
                piexif.GPSIFD.GPSLatitudeRef:  b"N" if lat >= 0 else b"S",
                piexif.GPSIFD.GPSLatitude:     _to_dms_rational(lat),
                piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
                piexif.GPSIFD.GPSLongitude:    _to_dms_rational(lon),
            }

        piexif.insert(piexif.dump(exif_dict), str(path))
    except Exception:
        pass  # Metadata is best-effort


def write_video_metadata(path: Path, date_str: str, lat: float | None, lon: float | None):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
        tags = MP4(str(path))
        tags["\xa9day"] = [dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")]
        if lat is not None and lon is not None:
            tags["\xa9xyz"] = [f"{lat:+.4f}{lon:+.4f}/"]
        tags.save()
    except Exception:
        pass


def _ffmpeg_binary() -> str:
    """Returns path to ffmpeg, including when it is not in PATH (via imageio-ffmpeg)."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return "ffmpeg"
    except FileNotFoundError:
        pass
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"  # fallback, will fail if not installed


def generate_poster(video_path: Path, poster_path: Path) -> bool:
    try:
        result = subprocess.run(
            [_ffmpeg_binary(), "-y", "-i", str(video_path),
             "-ss", "00:00:01", "-vframes", "1", str(poster_path)],
            capture_output=True, timeout=30,
        )
        return result.returncode == 0 and poster_path.exists() and poster_path.stat().st_size > 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Overlay compositing
# ---------------------------------------------------------------------------

def composite_image_overlay(main: Path, overlay: Path, out: Path):
    base = ImageOps.exif_transpose(Image.open(main).convert("RGBA"))
    ovl  = ImageOps.exif_transpose(Image.open(overlay).convert("RGBA"))
    if ovl.size != base.size:
        ovl = ovl.resize(base.size, Image.LANCZOS)
    Image.alpha_composite(base, ovl).convert("RGB").save(out, "JPEG", quality=95)


def composite_video_overlay(main: Path, overlay: Path, out: Path) -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-y",
             "-i", str(main),
             "-loop", "1", "-i", str(overlay),
             "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1",
             "-c:a", "copy", str(out)],
            capture_output=True, timeout=120,
        )
        return result.returncode == 0 and out.exists()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Per-entry processing
# ---------------------------------------------------------------------------

def process_entry(
    entry: dict,
    raw_groups: dict[str, list[dict]],
    session: requests.Session,
    used_lock,
    used_set: set,
) -> dict | None:
    url        = entry.get("Media Download Url", "")
    date_str   = entry["Date"]
    media_type = entry["Media Type"].lower()

    entry_id = make_entry_id(url or date_str)
    loc  = parse_location(entry["Location"]) if entry.get("Location") else None
    lat, lon = loc if loc else (None, None)

    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")

    # Decide extension
    ext = ".mp4" if media_type == "video" else ".jpg"
    out_filename = make_filename(date_str, entry_id, ext)
    out_path     = config.MEDIA_DIR / out_filename

    if out_path.exists():
        return _build_record(entry_id, dt, media_type, out_filename, lat, lon)

    # --- Match raw group from zip by date prefix ---
    date_prefix = date_str[:10]   # "YYYY-MM-DD"
    main_raw = overlay_raw = None

    with used_lock:
        candidates = [
            grp for grp in raw_groups.get(date_prefix, [])
            if id(grp) not in used_set and grp["main"] is not None
        ]
        if candidates:
            grp = candidates[0]
            used_set.add(id(grp))
            main_raw    = grp["main"]
            overlay_raw = grp.get("overlay")

    # --- Acquire the main file ---
    staging_main = config.MEDIA_DIR / f"_stg_{entry_id}_main{ext}"

    if main_raw and main_raw.exists():
        shutil.copy2(main_raw, staging_main)
    elif url:
        success, type_info = download_file(url, staging_main, session)
        if not success:
            return None
        if type_info:
            ext          = type_info[0]
            out_filename = make_filename(date_str, entry_id, ext)
            out_path     = config.MEDIA_DIR / out_filename
    else:
        return None  # Nothing to work with

    # --- Re-detect actual file type (Snapchat soms wrong media_type in JSON) ---
    if staging_main.exists():
        with open(staging_main, "rb") as fh:
            actual_header = fh.read(16)
        actual_type = detect_type(actual_header)
        if actual_type and actual_type[1] != media_type:
            media_type   = actual_type[1]
            ext          = actual_type[0]
            out_filename = make_filename(date_str, entry_id, ext)
            out_path     = config.MEDIA_DIR / out_filename
            if out_path.exists():
                staging_main.unlink(missing_ok=True)
                return _build_record(entry_id, dt, media_type, out_filename, lat, lon)

    # --- Composite overlay if available ---
    if overlay_raw and overlay_raw.exists():
        staging_comp = config.MEDIA_DIR / f"_stg_{entry_id}_comp{ext}"
        try:
            if media_type == "image":
                composite_image_overlay(staging_main, overlay_raw, staging_comp)
                staging_main.unlink(missing_ok=True)
                staging_main = staging_comp
            elif media_type == "video":
                if composite_video_overlay(staging_main, overlay_raw, staging_comp):
                    staging_main.unlink(missing_ok=True)
                    staging_main = staging_comp
        except Exception:
            if staging_comp.exists():
                staging_comp.unlink()

    # --- Move to final location ---
    shutil.move(str(staging_main), str(out_path))

    # --- Write metadata ---
    if media_type == "image" and ext == ".jpg":
        write_image_exif(out_path, date_str, lat, lon)
    elif media_type == "video":
        write_video_metadata(out_path, date_str, lat, lon)

    # Set file timestamp to memory creation date
    ts = dt.timestamp()
    os.utime(out_path, (ts, ts))

    # --- Generate video poster ---
    poster_filename = None
    if media_type == "video":
        poster_path = config.MEDIA_DIR / f"{out_path.stem}_poster.jpg"
        if generate_poster(out_path, poster_path):
            poster_filename = poster_path.name

    record = _build_record(entry_id, dt, media_type, out_filename, lat, lon)
    record["poster"] = poster_filename
    return record


def _build_record(entry_id, dt, media_type, filename, lat, lon):
    return {
        "id":         entry_id,
        "date_utc":   dt.isoformat(),
        "media_type": media_type,
        "filename":   filename,
        "poster":     None,
        "latitude":   lat,
        "longitude":  lon,
        "year":       dt.year,
        "month":      dt.month,
        "day":        dt.day,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Find zip
    if len(sys.argv) > 1:
        zip_path = Path(sys.argv[1])
    else:
        candidates = list(config.BASE_DIR.glob("mydata~*.zip"))
        if not candidates:
            print("Error: no mydata~*.zip found. Pass the path as an argument.")
            sys.exit(1)
        zip_path = candidates[0]
        print(f"Found zip: {zip_path.name}")

    if not zip_path.exists():
        print(f"Error: {zip_path} does not exist.")
        sys.exit(1)

    config.MEDIA_DIR.mkdir(exist_ok=True)
    db.init_db()

    # --- Phase 1: Extract zip ---
    print("Extracting zip...")
    raw_dir = config.MEDIA_DIR / "_raw"
    raw_dir.mkdir(exist_ok=True)

    entries: list[dict] = []
    # raw_groups: date_prefix (YYYY-MM-DD) -> list of {main: Path, overlay: Path|None}
    raw_groups: dict[str, list[dict]] = {}

    with zipfile.ZipFile(zip_path) as zf:
        # Read the JSON (in json/ subfolder)
        try:
            json_bytes = zf.read("json/memories_history.json")
        except KeyError:
            candidates = [n for n in zf.namelist() if n.endswith("memories_history.json")]
            if not candidates:
                print("Error: memories_history.json not found in zip.")
                sys.exit(1)
            json_bytes = zf.read(candidates[0])

        entries = json.loads(json_bytes).get("Saved Media", [])
        print(f"{len(entries)} memories found in JSON")

        # Extract media files; group by UUID found in filename
        skip_prefixes = ("html/", "json/", "._")
        skip_names    = {"index.html", "memories.html"}
        # uuid -> {main: Path|None, overlay: Path|None, date_prefix: str}
        uuid_groups: dict[str, dict] = {}

        for name in zf.namelist():
            if name.endswith("/"):
                continue
            basename = Path(name).name
            if (any(name.startswith(p) for p in skip_prefixes)
                    or basename in skip_names
                    or basename.startswith("._")):
                continue
            if Path(basename).suffix.lower() not in MEDIA_EXTENSIONS:
                continue

            out = raw_dir / basename
            if not out.exists():
                with zf.open(name) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)

            # Extract UUID and date prefix from filename like:
            # 2026-03-09_EDC3A815-C689-40E9-B6AF-F482A2C00B3F-main.mp4
            file_uuid = extract_uuid(basename)
            date_prefix = basename[:10]  # "YYYY-MM-DD"
            if not file_uuid:
                continue

            if file_uuid not in uuid_groups:
                uuid_groups[file_uuid] = {"main": None, "overlay": None, "date_prefix": date_prefix}
            if "-overlay" in basename.lower():
                uuid_groups[file_uuid]["overlay"] = out
            else:
                uuid_groups[file_uuid]["main"] = out

        # Index groups by date prefix (sorted by UUID for deterministic ordering)
        for file_uuid, grp in sorted(uuid_groups.items()):
            dp = grp["date_prefix"]
            raw_groups.setdefault(dp, []).append(grp)

    total_raw = sum(len(v) for v in raw_groups.values())
    print(f"{total_raw} media groups extracted from zip")

    # --- Check what's already imported ---
    conn_check = db.get_connection()
    existing = {
        row[0] for row in conn_check.execute("SELECT id FROM memories").fetchall()
    }
    conn_check.close()

    to_process = [
        e for e in entries
        if make_entry_id(e.get("Media Download Url", "") or e["Date"]) not in existing
    ]

    print(f"{len(existing)} already imported, {len(to_process)} to process")

    if not to_process:
        print("Nothing to do — all memories already imported.")
        return

    # --- Phase 2: Process entries in parallel ---
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"

    success_count = 0
    failed_count  = 0

    import threading
    used_lock = threading.Lock()
    used_set: set = set()

    with tqdm(total=len(to_process), unit="memory") as pbar:
        with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
            futures = {
                pool.submit(process_entry, e, raw_groups, session, used_lock, used_set): e
                for e in to_process
            }
            for future in as_completed(futures):
                try:
                    record = future.result()
                    if record:
                        conn = db.get_connection()
                        db.upsert_memory(conn, record)
                        conn.close()
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as exc:
                    failed_count += 1
                    tqdm.write(f"  Error: {exc}")
                finally:
                    pbar.update(1)

    print(f"\nDone: {success_count} imported, {failed_count} failed")

    stats = db.get_stats()
    print(f"Database: {stats['total']} total "
          f"({stats['images']} photos, {stats['videos']} videos, "
          f"{stats['with_gps']} with location)")


if __name__ == "__main__":
    main()
