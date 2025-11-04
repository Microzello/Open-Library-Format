from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from ..config import get_config
from ..media_service import get_media_by_id, raw_media_path
from ..video_proxy import is_playable_original, ensure_proxy_mp4, proxy_mp4_path


router = APIRouter(prefix="/api/libraries/{lib_id}", tags=["stream"])


def _lib_root_or_404(lib_id: str):
    root = get_config().libraries_root / lib_id
    if not root.exists():
        raise HTTPException(status_code=404, detail="library not found")
    return root


@router.get("/media/{media_id}/play")
def resolve_play(lib_id: str, media_id: str):
    root = _lib_root_or_404(lib_id)
    media = get_media_by_id(root, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="media not found")
    src = raw_media_path(root, media)
    if media['type'] == 'photo':
        return JSONResponse({"kind": "image", "url": f"/api/libraries/{lib_id}/stream/raw/{media_id}"})

    # video path
    if is_playable_original(src):
        return JSONResponse({"kind": "video", "url": f"/api/libraries/{lib_id}/stream/raw/{media_id}"})

    # generate proxy (blocking for now; on failure ask client to retry later)
    try:
        ensure_proxy_mp4(root, media)
        return JSONResponse({"kind": "video", "url": f"/api/libraries/{lib_id}/stream/mp4/{media_id}.mp4"})
    except Exception:
        return JSONResponse({"kind": "video", "status": "preparing"}, status_code=202)


@router.get("/stream/raw/{media_id}")
def stream_raw(lib_id: str, media_id: str):
    root = _lib_root_or_404(lib_id)
    media = get_media_by_id(root, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="media not found")
    path = raw_media_path(root, media)
    return FileResponse(str(path))


@router.get("/stream/mp4/{media_id}.mp4")
def stream_proxy_mp4(lib_id: str, media_id: str):
    root = _lib_root_or_404(lib_id)
    path = proxy_mp4_path(root, media_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="proxy not found")
    return FileResponse(str(path), media_type="video/mp4")


