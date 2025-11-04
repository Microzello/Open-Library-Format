from __future__ import annotations

import mimetypes
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

from fastapi import UploadFile
from PIL import Image, ExifTags

from .config import settings
from .library_manager import Library


def ingest_upload(library: Library, upload: UploadFile) -> Dict[str, object]:
    if not upload.filename:
        raise ValueError("Uploaded file must have a filename")

    original_name = Path(upload.filename).name
    extension = Path(original_name).suffix.lower()
    stored_name = uuid.uuid4().hex
    stored_filename = stored_name + extension

    raw_dir = library.media_root / "raw" / stored_name[:2]
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest_path = raw_dir / stored_filename

    with dest_path.open("wb") as destination:
        shutil.copyfileobj(upload.file, destination)
    upload.file.close()

    size_bytes = dest_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(original_name)
    mime_type = mime_type or "application/octet-stream"

    media_type = "document"
    if mime_type.startswith("image/"):
        media_type = "photo"
    elif mime_type.startswith("video/"):
        media_type = "video"

    metadata = {
        "width": None,
        "height": None,
        "duration": None,
        "camera_make": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lon": None,
        "taken_at": None,
    }

    if media_type == "photo":
        metadata.update(_extract_image_metadata(dest_path))
        _generate_thumbnail(dest_path, library, stored_name)

    if metadata.get("taken_at") is None:
        metadata["taken_at"] = int(dest_path.stat().st_mtime)

    imported_at = int(time.time())

    record = {
        "id": str(uuid.uuid4()),
        "original_filename": original_name,
        "stored_filename": stored_filename,
        "extension": extension,
        "media_type": media_type,
        "mime_type": mime_type,
        "taken_at": metadata.get("taken_at"),
        "imported_at": imported_at,
        "size_bytes": size_bytes,
        "width": metadata.get("width"),
        "height": metadata.get("height"),
        "duration": metadata.get("duration"),
        "camera_make": metadata.get("camera_make"),
        "camera_model": metadata.get("camera_model"),
        "gps_lat": metadata.get("gps_lat"),
        "gps_lon": metadata.get("gps_lon"),
        "description": None,
    }

    return {
        "record": record,
        "path": dest_path,
    }


def _extract_image_metadata(path: Path) -> Dict[str, object]:
    result: Dict[str, object] = {}
    with Image.open(path) as image:
        result["width"], result["height"] = image.size
        exif_data = image._getexif() or {}
        mapped = {ExifTags.TAGS.get(tag, tag): value for tag, value in exif_data.items()}

        if "Make" in mapped:
            result["camera_make"] = _normalize_string(mapped.get("Make"))
        if "Model" in mapped:
            result["camera_model"] = _normalize_string(mapped.get("Model"))
        if "DateTimeOriginal" in mapped:
            taken = _parse_exif_datetime(mapped["DateTimeOriginal"])
            if taken is not None:
                result["taken_at"] = taken

        gps_info = mapped.get("GPSInfo")
        if isinstance(gps_info, dict) and gps_info:
            lat, lon = _parse_gps(gps_info)
            result["gps_lat"] = lat
            result["gps_lon"] = lon

    return result


def _normalize_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore").strip() or None
        except Exception:
            return None
    text = str(value).strip()
    return text or None


def _parse_exif_datetime(value: object) -> int | None:
    try:
        text = str(value)
        dt = datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return None


def _parse_gps(data: Dict[int, object]) -> Tuple[float | None, float | None]:
    lat = None
    lon = None

    gps_tags = {ExifTags.GPSTAGS.get(key, key): value for key, value in data.items()}

    if all(k in gps_tags for k in ("GPSLatitude", "GPSLatitudeRef")):
        lat = _convert_to_degrees(gps_tags["GPSLatitude"])
        if gps_tags.get("GPSLatitudeRef") in {"S", "s"}:
            lat = -lat if lat is not None else None

    if all(k in gps_tags for k in ("GPSLongitude", "GPSLongitudeRef")):
        lon = _convert_to_degrees(gps_tags["GPSLongitude"])
        if gps_tags.get("GPSLongitudeRef") in {"W", "w"}:
            lon = -lon if lon is not None else None

    return lat, lon


def _convert_to_degrees(value: object) -> float | None:
    try:
        d, m, s = value
        degrees = _ratio_to_float(d)
        minutes = _ratio_to_float(m)
        seconds = _ratio_to_float(s)
        if None in (degrees, minutes, seconds):
            return None
        return degrees + (minutes / 60.0) + (seconds / 3600.0)
    except Exception:
        return None


def _ratio_to_float(value: object) -> float | None:
    try:
        if isinstance(value, tuple):
            numerator, denominator = value
            if denominator == 0:
                return None
            return float(numerator) / float(denominator)
        return float(value)
    except Exception:
        return None


def _generate_thumbnail(source: Path, library: Library, stored_name: str) -> None:
    thumb_dir = library.media_root / "thumbnails" / stored_name[:2]
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / f"{stored_name}.jpg"

    with Image.open(source) as image:
        image_copy = image.copy()
        image_copy.thumbnail((settings.thumbnail_size, settings.thumbnail_size))
        image_copy.save(thumb_path, "JPEG", quality=85)
