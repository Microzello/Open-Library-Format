from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config import get_config
from ..media_service import create_tag, list_tags, add_tags_to_media, remove_tag_from_media


router = APIRouter(prefix="/api/libraries/{lib_id}", tags=["tags"])


def _lib_root_or_404(lib_id: str):
    root = get_config().libraries_root / lib_id
    if not root.exists():
        raise HTTPException(status_code=404, detail="library not found")
    return root


@router.get("/tags")
def get_tags(lib_id: str):
    root = _lib_root_or_404(lib_id)
    return JSONResponse(list_tags(root))


@router.post("/tags")
def post_tag(lib_id: str, name: str):
    root = _lib_root_or_404(lib_id)
    name = (name or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    return JSONResponse(create_tag(root, name))


class LinkTagsPayload(BaseModel):
    tagIds: List[str]


@router.post("/media/{media_id}/tags")
def link_tags(lib_id: str, media_id: str, payload: LinkTagsPayload):
    root = _lib_root_or_404(lib_id)
    add_tags_to_media(root, media_id, payload.tagIds or [])
    return JSONResponse({"ok": True})


@router.delete("/media/{media_id}/tags/{tag_id}")
def unlink_tag(lib_id: str, media_id: str, tag_id: str):
    root = _lib_root_or_404(lib_id)
    remove_tag_from_media(root, media_id, tag_id)
    return JSONResponse({"ok": True})


