from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import time
import uuid
from pathlib import Path
import logging
from typing import Optional

from fastapi import UploadFile

from .db import get_connection
from .libraries import ensure_library_dirs, library_db_path

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - optional
    Image = None  # type: ignore

try:
    import exifread  # type: ignore
except Exception:  # pragma: no cover - optional
    exifread = None  # type: ignore


def _uuid_hex() -> str:
    return uuid.uuid4().hex


def _shard(uuid_hex: str) -> str:
    return uuid_hex[:2]


def _safe_ext(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext


def _mime_from_ext(ext: str) -> Optional[str]:
    if not ext:
        return None
    return mimetypes.types_map.get('.' + ext)


def _exif_datetime_epoch(tags: dict) -> Optional[int]:
    # Common EXIF tags
    for key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
        if key in tags:
            value = str(tags[key])
            # Expected format: YYYY:MM:DD HH:MM:SS
            try:
                parts = value.replace(':', '-').replace(' ', '-')
                y, m, d, hh, mm, ss = [int(x) for x in parts.split('-')]
                import datetime as dt

                return int(dt.datetime(y, m, d, hh, mm, ss, tzinfo=dt.timezone.utc).timestamp())
            except Exception:
                continue
    return None


def _probe_image_meta(path: Path) -> tuple[Optional[int], Optional[int], Optional[int], Optional[str], Optional[str]]:
    width = height = None
    taken = None
    camera_make = camera_model = None
    if Image is None:
        return width, height, taken, camera_make, camera_model
    try:
        with Image.open(path) as im:
            width, height = im.size
        if exifread is not None:
            with path.open('rb') as fh:
                tags = exifread.process_file(fh, details=False)
            taken = _exif_datetime_epoch(tags)
            camera_make = str(tags.get('Image Make') or '') or None
            camera_model = str(tags.get('Image Model') or '') or None
    except Exception:
        pass
    return width, height, taken, camera_make, camera_model


def _run_ffprobe(ffprobe_path: str, path: Path) -> Optional[dict]:
    try:
        cmd = [ffprobe_path, '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', str(path)]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return json.loads(out.decode('utf-8'))
    except Exception:
        return None


def _probe_video_meta(ffprobe_path: str, path: Path) -> tuple[Optional[int], Optional[int], Optional[int]]:
    width = height = None
    duration_ms = None
    data = _run_ffprobe(ffprobe_path, path)
    if not data:
        return width, height, duration_ms
    try:
        vstreams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
        if vstreams:
            vs = vstreams[0]
            width = int(vs.get('width')) if vs.get('width') else None
            height = int(vs.get('height')) if vs.get('height') else None
        fmt = data.get('format') or {}
        if fmt.get('duration'):
            duration_ms = int(float(fmt['duration']) * 1000)
    except Exception:
        pass
    return width, height, duration_ms


def ingest_files(library_root: Path, ffprobe_path: str, files: list[UploadFile]) -> list[str]:
    ensure_library_dirs(library_root)
    db_path = library_db_path(library_root)
    conn = get_connection(db_path)
    now = int(time.time())
    inserted_ids: list[str] = []

    for uf in files:
        original_name = uf.filename or 'unknown'
        ext = _safe_ext(original_name)
        uid = _uuid_hex()
        shard = _shard(uid)
        stored_filename = f"{uid}.{ext}" if ext else uid
        raw_dir = library_root / 'media' / 'raw' / shard
        raw_dir.mkdir(parents=True, exist_ok=True)
        target_path = raw_dir / stored_filename

        # Save file
        with target_path.open('wb') as out:
            while True:
                chunk = uf.file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        mime = _mime_from_ext(ext) or uf.content_type or 'application/octet-stream'
        mtype = 'video' if (mime.startswith('video/') or ext in {'mp4','mov','mkv','webm','avi'}) else 'photo'

        width = height = duration_ms = None
        camera_make = camera_model = None
        taken_at = None

        if mtype == 'photo':
            width, height, taken_at, camera_make, camera_model = _probe_image_meta(target_path)
        else:
            width, height, duration_ms = _probe_video_meta(ffprobe_path, target_path)

        filesize = target_path.stat().st_size

        logging.info("ingest: id=%s name=%s size=%s", uid, original_name, filesize)
        conn.execute(
            """
            INSERT INTO media (
                id, type, original_filename, stored_filename, ext, shard, mime_type, filesize,
                width, height, duration_ms, camera_make, camera_model, gps_lat, gps_lon,
                taken_at_epoch, created_at_epoch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                uid, mtype, original_name, stored_filename, ext, shard, mime, filesize,
                width, height, duration_ms, camera_make, camera_model, taken_at, now,
            ),
        )
        inserted_ids.append(uid)

    conn.commit()
    return inserted_ids


