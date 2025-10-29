"""Tag management endpoints."""
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, status
from typing import List

from app.models import TagCreate, TagResponse, AddTagRequest
from app.auth import require_auth, verify_csrf
from app.db.library_db import LibraryDB

router = APIRouter(prefix="/api/libraries/{library_id}/tags", tags=["tags"])


def get_library_db(request: Request, library_id: str) -> tuple:
    """Helper to get library DB."""
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
                    "message": "Library path not found"
                }
            }
        )
    
    return LibraryDB(str(lib_path)), lib


@router.get("", response_model=List[TagResponse])
def list_tags(request: Request, library_id: str):
    """List all tags with file counts."""
    require_auth(request)
    
    lib_db, _ = get_library_db(request, library_id)
    tags = lib_db.list_tags()
    
    return tags


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(request: Request, library_id: str, data: TagCreate):
    """Create a new tag."""
    require_auth(request)
    verify_csrf(request)
    
    lib_db, _ = get_library_db(request, library_id)
    
    # Check if tag exists
    existing = lib_db.get_tag_by_name(data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "TAG_EXISTS",
                    "message": f"Tag '{data.name}' already exists"
                }
            }
        )
    
    tag_id = lib_db.create_tag(data.name)
    tag = lib_db.get_tag_by_id(tag_id)
    tag["file_count"] = 0
    
    return tag


@router.post("/../files/{file_id}/tags", status_code=status.HTTP_204_NO_CONTENT)
def add_tag_to_file(request: Request, library_id: str, file_id: int, data: AddTagRequest):
    """Add a tag to a file."""
    require_auth(request)
    verify_csrf(request)
    
    lib_db, _ = get_library_db(request, library_id)
    
    # Verify file exists
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
    
    # Verify tag exists
    tag = lib_db.get_tag_by_id(data.tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "TAG_NOT_FOUND",
                    "message": f"Tag {data.tag_id} not found"
                }
            }
        )
    
    lib_db.add_tag_to_file(file_id, data.tag_id)
    return None


@router.delete("/../files/{file_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_tag_from_file(request: Request, library_id: str, file_id: int, tag_id: int):
    """Remove a tag from a file."""
    require_auth(request)
    verify_csrf(request)
    
    lib_db, _ = get_library_db(request, library_id)
    
    lib_db.remove_tag_from_file(file_id, tag_id)
    return None

