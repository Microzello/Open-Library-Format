"""EXIF parsing and timezone handling."""
import subprocess
import json
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import dateutil.parser
from zoneinfo import ZoneInfo

from .features import detect_exiftool


def parse_exif_datetime(
    filepath: Path, library_tz: str = "UTC"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse EXIF DateTimeOriginal from an image file.
    
    Returns:
        (utc_timestamp, raw_exif_string)
        utc_timestamp is ISO format UTC, raw_exif_string is the original EXIF value.
    """
    if not detect_exiftool():
        return None, None

    try:
        result = subprocess.run(
            ["exiftool", "-DateTimeOriginal", "-json", str(filepath)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode != 0:
            return None, None
        
        data = json.loads(result.stdout)
        if not data or len(data) == 0:
            return None, None
        
        exif_date = data[0].get("DateTimeOriginal")
        if not exif_date:
            return None, None
        
        # Parse as naive datetime and localize to library TZ
        try:
            # EXIF format: "2023:01:15 14:30:00"
            dt_naive = datetime.strptime(exif_date, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            # Try ISO format fallback
            try:
                dt_naive = dateutil.parser.parse(exif_date, ignoretz=True)
            except:
                return None, exif_date
        
        # Localize to library timezone
        tz = ZoneInfo(library_tz)
        dt_local = dt_naive.replace(tzinfo=tz)
        
        # Convert to UTC
        dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
        
        return dt_utc.isoformat(), exif_date
        
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None, None


def get_file_mtime_utc(filepath: Path) -> str:
    """Get file modification time as UTC ISO string."""
    mtime = filepath.stat().st_mtime
    dt_utc = datetime.fromtimestamp(mtime, tz=ZoneInfo("UTC"))
    return dt_utc.isoformat()

