"""Thumbnail generation service."""
import subprocess
from pathlib import Path
from PIL import Image

from app.storage import get_file_path, get_thumb_path
from app.utils.mime import is_image, is_video
from app.utils.features import detect_ffmpeg


class ThumbnailService:
    """Generates thumbnails for images and videos."""

    THUMB_SIZE = 512

    def __init__(self, library_path: Path):
        self.library_path = library_path

    def generate_image_thumbnail(self, sha256: str) -> bool:
        """Generate thumbnail for an image."""
        src = get_file_path(self.library_path, sha256)
        dest = get_thumb_path(self.library_path, sha256, kind="img").with_suffix(".jpg")

        # Skip if already exists
        if dest.exists():
            return True

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            with Image.open(src) as img:
                # Convert to RGB if needed (for PNG with alpha, HEIC, etc.)
                if img.mode in ("RGBA", "LA", "P"):
                    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                    img = rgb_img
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                
                # Thumbnail
                img.thumbnail((self.THUMB_SIZE, self.THUMB_SIZE), Image.Resampling.LANCZOS)
                img.save(dest, "JPEG", quality=85, optimize=True)
            
            return True
        except Exception as e:
            print(f"Failed to generate thumbnail for {sha256}: {e}")
            return False

    def generate_video_poster(self, sha256: str) -> bool:
        """Generate poster frame for a video using ffmpeg."""
        if not detect_ffmpeg():
            return False

        src = get_file_path(self.library_path, sha256)
        dest = get_thumb_path(self.library_path, sha256, kind="vid").with_suffix(".jpg")

        # Skip if already exists
        if dest.exists():
            return True

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Extract frame at 1 second
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", str(src),
                    "-ss", "00:00:01",
                    "-vframes", "1",
                    "-vf", f"scale={self.THUMB_SIZE}:{self.THUMB_SIZE}:force_original_aspect_ratio=decrease",
                    "-y",
                    str(dest),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
            
            return True
        except Exception as e:
            print(f"Failed to generate video poster for {sha256}: {e}")
            return False

    def generate_thumbnail(self, sha256: str, mime: str) -> bool:
        """Generate appropriate thumbnail based on MIME type."""
        if is_image(mime):
            return self.generate_image_thumbnail(sha256)
        elif is_video(mime):
            return self.generate_video_poster(sha256)
        return False

