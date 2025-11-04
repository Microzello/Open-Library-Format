from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import get_config
from ..libraries import list_libraries, create_library
from ..schemas import CreateLibraryRequest, LibraryInfo


router = APIRouter(prefix="/api/libraries", tags=["libraries"])


@router.get("", response_model=list[LibraryInfo])
def get_libraries() -> list[LibraryInfo]:
    cfg = get_config()
    items = list_libraries(cfg.libraries_root)
    return [LibraryInfo(**it) for it in items]


@router.post("", response_model=LibraryInfo)
def post_library(payload: CreateLibraryRequest) -> LibraryInfo:
    cfg = get_config()
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    created = create_library(cfg.libraries_root, name)
    return LibraryInfo(**created)


