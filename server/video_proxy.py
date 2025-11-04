from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
import logging
from typing import Optional

from .config import get_config
from .db import get_connection
from .libraries import library_db_path
from .media_service import raw_media_path


def _ffprobe(path: Path) -> Optional[dict]:
    try:
        out = subprocess.check_output([
            get_config().ffprobe_path, '-v', 'error', '-print_format', 'json',
            '-show_streams', '-show_format', str(path)
        ], stderr=subprocess.STDOUT)
        return json.loads(out.decode('utf-8'))
    except Exception:
        return None


def is_playable_original(path: Path) -> bool:
    data = _ffprobe(path)
    if not data:
        return False
    fmt = data.get('format') or {}
    format_name = (fmt.get('format_name') or '')
    container_ok = ('mp4' in format_name)
    vcodec = acodec = None
    vlevel = None
    for s in data.get('streams', []):
        if s.get('codec_type') == 'video' and not vcodec:
            vcodec = s.get('codec_name')
            try:
                vlevel = int(s.get('level')) if s.get('level') is not None else None
            except Exception:
                vlevel = None
        if s.get('codec_type') == 'audio' and not acodec:
            acodec = s.get('codec_name')
    if container_ok and vcodec == 'h264' and (vlevel is None or vlevel <= 41) and (acodec in (None, 'aac')):
        return True
    return False


def proxy_mp4_path(library_root: Path, media_id: str) -> Path:
    return library_root / 'media' / 'proxies' / 'mp4' / f'{media_id}.mp4'


def ensure_proxy_mp4(library_root: Path, media: dict) -> Path:
    out = proxy_mp4_path(library_root, media['id'])
    if out.exists():
        return out
    src = raw_media_path(library_root, media)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Baseline proxy with faststart and reasonable bitrate
    cmd = [
        get_config().ffmpeg_path,
        '-y', '-i', str(src),
        '-c:v', 'libx264', '-preset', 'veryfast', '-profile:v', 'high', '-level', '4.1', '-movflags', '+faststart',
        '-c:a', 'aac', '-b:a', '128k',
        str(out)
    ]
    logging.info("ffmpeg proxy: %s", ' '.join(cmd))
    subprocess.check_call(cmd)
    # record in DB
    conn = get_connection(library_db_path(library_root))
    conn.execute(
        "INSERT OR REPLACE INTO proxies (media_id, kind, path, width, height, bitrate_kbps, created_at_epoch) VALUES (?,?,?,?,?,?,?)",
        (media['id'], 'mp4', str(out), None, None, None, int(time.time())),
    )
    conn.commit()
    return out


