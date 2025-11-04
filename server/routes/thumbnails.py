from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..media_service import get_media_by_id
from ..thumbnails import ensure_thumbnail
from ..config import get_config


router = APIRouter(prefix="/api/libraries/{lib_id}", tags=["thumbnails"])


@router.get("/media/{media_id}/thumb")
def get_thumb(lib_id: str, media_id: str):
    cfg = get_config()
    lib_root = cfg.libraries_root / lib_id
    if not lib_root.exists():
        raise HTTPException(status_code=404, detail="library not found")
    media = get_media_by_id(lib_root, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="media not found")
    thumb = ensure_thumbnail(lib_root, media)
    return FileResponse(str(thumb), media_type="image/jpeg")


