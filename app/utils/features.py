"""Runtime feature detection."""
import shutil
import os
from typing import Dict


def detect_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    env_override = os.getenv("ENABLE_FFMPEG", "auto").lower()
    if env_override == "false":
        return False
    if env_override == "true":
        return True
    return shutil.which("ffmpeg") is not None


def detect_exiftool() -> bool:
    """Check if exiftool is available."""
    env_override = os.getenv("ENABLE_EXIFTOOL", "auto").lower()
    if env_override == "false":
        return False
    if env_override == "true":
        return True
    return shutil.which("exiftool") is not None


def detect_poppler() -> bool:
    """Check if pdftotext (poppler-utils) is available."""
    return shutil.which("pdftotext") is not None


def get_features() -> Dict[str, bool]:
    """Get all feature flags."""
    return {
        "ffmpeg": detect_ffmpeg(),
        "exiftool": detect_exiftool(),
        "poppler": detect_poppler(),
        "fts": True,  # SQLite FTS5 always available in Python 3.11+
    }

