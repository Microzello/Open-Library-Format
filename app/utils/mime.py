"""MIME type detection and validation."""
import magic
from pathlib import Path


# Allowed MIME types by library type
ALLOWED_MIMES = {
    "photo_video": {
        # Images
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
        "image/tiff",
        # Videos
        "video/mp4",
        "video/quicktime",  # .mov
        "video/x-matroska",  # .mkv
        "video/webm",
    },
    "music": {
        "audio/mpeg",  # mp3
        "audio/flac",
        "audio/wav",
        "audio/x-wav",
        "audio/mp4",  # m4a
        "audio/x-m4a",
        "audio/ogg",
        "audio/vorbis",
    },
    "documents": None,  # Allow all
}


def sniff_mime(filepath: Path) -> str:
    """Sniff MIME type using libmagic."""
    mime = magic.Magic(mime=True)
    return mime.from_file(str(filepath))


def is_mime_allowed(mime: str, library_type: str) -> bool:
    """Check if MIME type is allowed for library type."""
    allowed = ALLOWED_MIMES.get(library_type)
    if allowed is None:
        return True  # documents allow all
    return mime in allowed


def is_image(mime: str) -> bool:
    """Check if MIME type is an image."""
    return mime.startswith("image/")


def is_video(mime: str) -> bool:
    """Check if MIME type is a video."""
    return mime.startswith("video/")


def is_audio(mime: str) -> bool:
    """Check if MIME type is audio."""
    return mime.startswith("audio/")

