"""File management endpoints."""
import json
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Optional

from app.models import FileResponse, FileUpdateRequest, UploadResponse
from app.auth import require_auth, verify_csrf
from app.db.library_db import LibraryDB
from app.services.ingest import IngestService
from app.services.thumbnails import ThumbnailService
from app.storage import trash_file, get_file_path

router = APIRouter(prefix="/api/libraries/{library_id}/files", tags=["files"])


def get_library_info(request: Request, library_id: str):
    """Helper to get library info and validate it exists."""
    registry = request.app.state.registry_db
    lib = registry.get_library_by_id(library_id)
    
    if not lib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "LIBRARY_NOT_FOUND",
                    "message": f"Library {library_id} not found"
                }
            }
        )
    
    lib_path = Path(lib["path"])
    if not lib_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "LIBRARY_UNAVAILABLE",
                    "message": f"Library path not found: {lib_path}"
                }
            }
        )
    
    # Load library.json for TZ
    manifest_path = lib_path / "library.json"
    manifest = {}
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    
    return lib, lib_path, manifest.get("tz", "UTC")


@router.get("", response_model=dict)
def list_files(
    request: Request,
    library_id: str,
    page: int = Query(0, ge=0),
    page_size: int = Query(100, ge=1, le=500),
    tag: Optional[str] = None,
    q: Optional[str] = None,
    sort: str = Query("captured_at_desc", pattern="^(captured_at_desc|captured_at_asc|added_at_desc)$"),
    include_deleted: bool = False,
):
    """List files in a library with pagination and filtering."""
    require_auth(request)
    
    lib, lib_path, _ = get_library_info(request, library_id)
    lib_db = LibraryDB(str(lib_path))
    
    # Resolve tag ID if tag name provided
    tag_id = None
    if tag:
        tag_rec = lib_db.get_tag_by_name(tag)
        if tag_rec:
            tag_id = tag_rec["id"]
        else:
            # Tag doesn't exist, return empty
            return {"files": [], "total": 0, "page": page, "page_size": page_size}
    
    # Search or list
    if q:
        files, total = lib_db.search_files(q, page, page_size)
    else:
        files, total = lib_db.list_files(page, page_size, include_deleted, tag_id, sort)
    
    # Enrich with tags
    for f in files:
        f["tags"] = lib_db.get_file_tags(f["id"])
    
    return {
        "files": files,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    library_id: str,
    file: UploadFile = File(...),
    tags: Optional[str] = Form(None),  # JSON array of tag IDs
):
    """Upload a file to the library."""
    require_auth(request)
    verify_csrf(request)
    
    lib, lib_path, lib_tz = get_library_info(request, library_id)
    lib_db = LibraryDB(str(lib_path))
    
    # Parse tags
    tag_ids = []
    if tags:
        try:
            tag_ids = json.loads(tags)
        except json.JSONDecodeError:
            pass
    
    # Ingest
    ingest_service = IngestService(lib_db, lib_path, lib["type"], lib_tz)
    status_str, file_id, sha256 = await ingest_service.ingest_file(file, tag_ids)
    
    # Generate thumbnail asynchronously (for MVP, do it sync)
    file_rec = lib_db.get_file_by_id(file_id)
    if file_rec:
        thumb_service = ThumbnailService(lib_path)
        thumb_service.generate_thumbnail(sha256, file_rec["mime"])
    
    return {
        "status": status_str,
        "file_id": file_id,
        "sha256": sha256,
    }


@router.get("/{file_id}", response_model=FileResponse)
def get_file(request: Request, library_id: str, file_id: int):
    """Get file details."""
    require_auth(request)
    
    lib, lib_path, _ = get_library_info(request, library_id)
    lib_db = LibraryDB(str(lib_path))
    
    file_rec = lib_db.get_file_by_id(file_id)
    if not file_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "FILE_NOT_FOUND",
                    "message": f"File {file_id} not found"
                }
            }
        )
    
    # Enrich
    file_rec["tags"] = lib_db.get_file_tags(file_id)
    file_rec["attributes"] = lib_db.get_all_attributes(file_id)
    
    return file_rec


@router.get("/{file_id}/download")
def download_file(request: Request, library_id: str, file_id: int):
    """Download original file."""
    require_auth(request)
    
    lib, lib_path, _ = get_library_info(request, library_id)
    lib_db = LibraryDB(str(lib_path))
    
    file_rec = lib_db.get_file_by_id(file_id)
    if not file_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    
    file_path = get_file_path(lib_path, file_rec["sha256"])
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "FILE_BLOB_MISSING",
                    "message": "File blob not found on disk"
                }
            }
        )
    
    return FileResponse(
        path=str(file_path),
        media_type=file_rec["mime"] or "application/octet-stream",
        filename=file_rec["original_name"],
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(request: Request, library_id: str, file_id: int):
    """Move file to trash."""
    require_auth(request)
    verify_csrf(request)
    
    lib, lib_path, _ = get_library_info(request, library_id)
    lib_db = LibraryDB(str(lib_path))
    
    file_rec = lib_db.get_file_by_id(file_id)
    if not file_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    
    # Move to trash
    trash_file(lib_path, file_rec["sha256"])
    lib_db.mark_deleted(file_id)
    
    return None


@router.post("/{file_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_file(request: Request, library_id: str, file_id: int):
    """Restore file from trash."""
    require_auth(request)
    verify_csrf(request)
    
    lib, lib_path, _ = get_library_info(request, library_id)
    lib_db = LibraryDB(str(lib_path))
    
    file_rec = lib_db.get_file_by_id(file_id)
    if not file_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    
    # Restore
    from app.storage import restore_file as restore_blob
    restore_blob(lib_path, file_rec["sha256"])
    lib_db.restore_file(file_id)
    
    return None


@router.patch("/{file_id}", response_model=FileResponse)
def update_file(request: Request, library_id: str, file_id: int, data: FileUpdateRequest):
    """Update file metadata."""
    require_auth(request)
    verify_csrf(request)
    
    lib, lib_path, _ = get_library_info(request, library_id)
    lib_db = LibraryDB(str(lib_path))
    
    file_rec = lib_db.get_file_by_id(file_id)
    if not file_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    
    # Update notes
    if data.notes is not None:
        lib_db.update_file(file_id, notes=data.notes)
    
    # Update attributes
    if data.attributes:
        for key, value in data.attributes.items():
            lib_db.set_attribute(file_id, key, value)
    
    # Return updated record
    updated = lib_db.get_file_by_id(file_id)
    updated["tags"] = lib_db.get_file_tags(file_id)
    updated["attributes"] = lib_db.get_all_attributes(file_id)
    
    return updated

