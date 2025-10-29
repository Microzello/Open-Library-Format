"""Library management endpoints."""
import json
import uuid
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, status
from typing import List

from app.models import LibraryCreate, LibraryResponse, ErrorResponse
from app.auth import require_auth, verify_csrf
from app.db.library_db import LibraryDB
from app.storage import ensure_library_structure
import os

router = APIRouter(prefix="/api/libraries", tags=["libraries"])


@router.get("", response_model=List[LibraryResponse])
def list_libraries(request: Request):
    """List all libraries."""
    require_auth(request)
    
    registry = request.app.state.registry_db
    libraries = registry.list_libraries()
    
    # Enrich with stats
    result = []
    for lib in libraries:
        lib_path = Path(lib["path"])
        if not lib_path.exists():
            # Library folder missing
            stats = {"status": "missing"}
        else:
            try:
                lib_db = LibraryDB(str(lib_path))
                stats = lib_db.get_stats()
            except Exception:
                stats = {"status": "error"}
        
        result.append({
            **lib,
            "stats": stats
        })
    
    return result


@router.post("", response_model=LibraryResponse, status_code=status.HTTP_201_CREATED)
def create_library(request: Request, data: LibraryCreate):
    """Create a new library."""
    require_auth(request)
    verify_csrf(request)
    
    registry = request.app.state.registry_db
    libraries_root = Path(os.getenv("LIBRARIES_ROOT", "/data/libraries"))
    
    # Generate slug if not provided
    slug = data.slug or data.name.lower().replace(" ", "-").replace("/", "-")
    
    # Check slug uniqueness
    existing = registry.get_library_by_slug(slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "SLUG_EXISTS",
                    "message": f"Library with slug '{slug}' already exists"
                }
            }
        )
    
    # Create directory structure
    lib_path = libraries_root / slug
    if lib_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "PATH_EXISTS",
                    "message": f"Directory already exists: {lib_path}"
                }
            }
        )
    
    lib_path.mkdir(parents=True, exist_ok=True)
    ensure_library_structure(lib_path)
    
    # Create library.json manifest
    lib_id = str(uuid.uuid4())
    manifest = {
        "id": lib_id,
        "name": data.name,
        "type": data.type,
        "schema_version": 1,
        "tz": data.tz or "UTC",
    }
    
    manifest_path = lib_path / "library.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    # Initialize database
    lib_db = LibraryDB(str(lib_path))
    
    # Create default "Favorites" tag
    lib_db.create_tag("Favorites")
    
    # Register in global registry
    registry.add_library(
        lib_id=lib_id,
        slug=slug,
        name=data.name,
        lib_type=data.type,
        path=str(lib_path.absolute())
    )
    
    # Return library info
    lib_info = registry.get_library_by_id(lib_id)
    stats = lib_db.get_stats()
    
    return {
        **lib_info,
        "stats": stats
    }


@router.get("/{library_id}", response_model=LibraryResponse)
def get_library(request: Request, library_id: str):
    """Get library details."""
    require_auth(request)
    
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
    if lib_path.exists():
        try:
            lib_db = LibraryDB(str(lib_path))
            stats = lib_db.get_stats()
        except Exception:
            stats = {"status": "error"}
    else:
        stats = {"status": "missing"}
    
    return {
        **lib,
        "stats": stats
    }


@router.delete("/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library(request: Request, library_id: str):
    """Soft-delete library from registry (folder stays on disk)."""
    require_auth(request)
    verify_csrf(request)
    
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
    
    registry.remove_library(library_id)
    return None

