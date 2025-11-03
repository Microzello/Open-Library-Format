"""Media serving endpoints with caching and range support."""
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, status, Header
from fastapi.responses import FileResponse, StreamingResponse
from typing import Optional
import os

from app.auth import require_auth
from app.storage import get_file_path, get_thumb_path

router = APIRouter(prefix="/media", tags=["media"])


def parse_range_header(range_header: Optional[str], file_size: int) -> tuple:
    """Parse Range header and return (start, end)."""
    if not range_header:
        return 0, file_size - 1
    
    # Format: bytes=start-end
    try:
        range_str = range_header.replace("bytes=", "")
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        return start, end
    except:
        return 0, file_size - 1


@router.get("/{library_slug}/file/{sha256}")
def serve_file(
    request: Request,
    library_slug: str,
    sha256: str,
    range_header: Optional[str] = Header(None, alias="Range"),
):
    """Serve original file with range request support."""
    require_auth(request)
    
    # Find library by slug
    registry = request.app.state.registry_db
    lib = registry.get_library_by_slug(library_slug)
    
    if not lib:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    
    lib_path = Path(lib["path"])
    file_path = get_file_path(lib_path, sha256)
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "FILE_NOT_FOUND",
                    "message": "File not found"
                }
            }
        )
    
    file_size = file_path.stat().st_size
    
    # Handle range requests for video streaming
    if range_header:
        start, end = parse_range_header(range_header, file_size)
        
        def iterfile():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                chunk_size = 8192
                while remaining > 0:
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
        }
        
        return StreamingResponse(
            iterfile(),
            status_code=206,
            headers=headers,
            media_type="application/octet-stream",
        )
    else:
        # Full file
        return FileResponse(
            path=str(file_path),
            media_type="application/octet-stream",
            headers={"Accept-Ranges": "bytes"},
        )


@router.get("/{library_slug}/thumbs/{kind}/{sha256}.jpg")
def serve_thumbnail(
    request: Request,
    library_slug: str,
    kind: str,
    sha256: str,
):
    """Serve thumbnail with caching headers."""
    require_auth(request)
    
    # Find library
    registry = request.app.state.registry_db
    lib = registry.get_library_by_slug(library_slug)
    
    if not lib:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    
    lib_path = Path(lib["path"])
    thumb_path = get_thumb_path(lib_path, sha256, kind=kind).with_suffix(".jpg")
    
    if not thumb_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "THUMBNAIL_NOT_FOUND",
                    "message": "Thumbnail not found"
                }
            }
        )
    
    # Immutable caching
    headers = {
        "ETag": f'"{sha256}"',
        "Cache-Control": "public, max-age=31536000, immutable",
    }
    
    return FileResponse(
        path=str(thumb_path),
        media_type="image/jpeg",
        headers=headers,
    )

