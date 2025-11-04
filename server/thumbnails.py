from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from .config import get_config
from .db import get_connection
from .libraries import library_db_path
from .media_service import raw_media_path

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - optional
    Image = None  # type: ignore


def _thumb_path(library_root: Path, media_id: str) -> Path:
    return library_root / 'media' / 'thumbs' / f'{media_id}.jpg'


def _generate_image_thumb(src: Path, dst: Path, max_side: int) -> None:
    if Image is None:
        raise RuntimeError('Pillow not available')
    with Image.open(src) as im:
        im.thumbnail((max_side, max_side))
        im = im.convert('RGB')
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, format='JPEG', quality=82, optimize=True)


def _generate_video_thumb(ffmpeg_path: str, src: Path, dst: Path, max_side: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Extract frame at 1s and scale preserving aspect ratio
    cmd = [
        ffmpeg_path,
        '-y',
        '-ss', '1',
        '-i', str(src),
        '-frames:v', '1',
        '-vf', f"scale='if(gt(a,1),{max_side},-2)':'if(gt(a,1),-2,{max_side})'",
        str(dst),
    ]
    subprocess.check_call(cmd)


def ensure_thumbnail(library_root: Path, media: dict) -> Path:
    cfg = get_config()
    thumb = _thumb_path(library_root, media['id'])
    if thumb.exists():
        return thumb
    src = raw_media_path(library_root, media)
    try:
        if media['type'] == 'photo':
            _generate_image_thumb(src, thumb, cfg.thumb_size)
        else:
            _generate_video_thumb(get_config().ffmpeg_path, src, thumb, cfg.thumb_size)
    except Exception:
        # Fallback placeholder thumbnail
        if Image is not None:
            from PIL import Image as PILImage  # type: ignore
            im = PILImage.new('RGB', (cfg.thumb_size, cfg.thumb_size), color=(32, 36, 50))
            thumb.parent.mkdir(parents=True, exist_ok=True)
            im.save(thumb, format='JPEG', quality=70)
        else:
            # Last resort: create empty file to avoid repeated attempts
            thumb.parent.mkdir(parents=True, exist_ok=True)
            thumb.write_bytes(b"")

    # record in DB (best-effort)
    try:
        conn = get_connection(library_db_path(library_root))
        conn.execute(
            "INSERT OR REPLACE INTO thumbnails (media_id, path, width, height, created_at_epoch) VALUES (?,?,?,?,?)",
            (media['id'], str(thumb), None, None, int(time.time())),
        )
        conn.commit()
    except Exception:
        pass

    return thumb


