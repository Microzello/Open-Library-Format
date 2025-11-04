from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
import logging
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import io
import zipfile

from ..config import get_config
from ..libraries import bootstrap_library_db
from ..ingest import ingest_files
from ..media_service import list_media, delete_media, delete_media_batch, get_media_by_id, raw_media_path, list_media_tags


router = APIRouter(prefix="/api/libraries/{lib_id}", tags=["media"])


def _library_root_or_404(lib_id: str):
    cfg = get_config()
    lib_root = cfg.libraries_root / lib_id
    if not lib_root.exists():
        raise HTTPException(status_code=404, detail="library not found")
    # Ensure DB exists (in case library was copied in)
    bootstrap_library_db(lib_root)
    return lib_root


@router.post("/upload")
async def upload_media(lib_id: str, files: List[UploadFile] = File(...)) -> JSONResponse:
    lib_root = _library_root_or_404(lib_id)
    if not files:
        raise HTTPException(status_code=400, detail="no files provided")
    logging.info("upload: library=%s files=%s", lib_id, [f.filename for f in files])
    try:
        ids = ingest_files(lib_root, get_config().ffprobe_path, files)
        logging.info("upload: inserted=%s", ids)
        return JSONResponse({"inserted": ids})
    except Exception as e:
        logging.exception("upload failed: %s", e)
        raise HTTPException(status_code=500, detail="upload failed")


@router.get("/media")
def get_media(
    lib_id: str,
    page: int = 1,
    size: int = 50,
    sort: str = "newest",
    type: Optional[str] = None,
    q: Optional[str] = None,
    takenFrom: Optional[int] = None,
    takenTo: Optional[int] = None,
    tagIds: Optional[List[str]] = None,
    tagMode: str = "and",
):
    lib_root = _library_root_or_404(lib_id)
    data = list_media(
        lib_root,
        page=page,
        size=size,
        sort=sort,
        mtype=type,
        q=q,
        taken_from=takenFrom,
        taken_to=takenTo,
        tag_ids=tagIds,
        tag_mode=tagMode,
    )
    return JSONResponse(data)


@router.delete("/media/{media_id}")
def delete_one(lib_id: str, media_id: str):
    lib_root = _library_root_or_404(lib_id)
    delete_media(lib_root, media_id)
    return JSONResponse({"ok": True})


@router.post("/media/batch-delete")
def delete_many(lib_id: str, ids: List[str]):
    lib_root = _library_root_or_404(lib_id)
    res = delete_media_batch(lib_root, ids or [])
    return JSONResponse(res)


@router.get("/media/{media_id}/download")
def download_one(lib_id: str, media_id: str):
    cfg = get_config()
    lib_root = _library_root_or_404(lib_id)
    media = get_media_by_id(lib_root, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="media not found")
    path = raw_media_path(lib_root, media)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{media['original_filename']}"}
    return FileResponse(str(path), headers=headers)


@router.post("/media/batch-download")
def download_many(lib_id: str, ids: List[str]):
    lib_root = _library_root_or_404(lib_id)
    items = []
    for mid in ids or []:
        m = get_media_by_id(lib_root, mid)
        if not m:
            continue
        items.append((raw_media_path(lib_root, m), m['original_filename']))

    def stream():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for p, name in items:
                if p.exists():
                    zf.write(str(p), arcname=name)
        buf.seek(0)
        data = buf.read()
        yield data

    headers = {"Content-Disposition": "attachment; filename=media.zip"}
    return StreamingResponse(stream(), media_type='application/zip', headers=headers)


@router.get("/media/{media_id}")
def get_media_detail(lib_id: str, media_id: str):
    lib_root = _library_root_or_404(lib_id)
    media = get_media_by_id(lib_root, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="media not found")
    tags = list_media_tags(lib_root, media_id)
    media["tags"] = tags
    return JSONResponse(media)


