from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ingest import ingest_upload
from .library_manager import Library, LibraryManager
from .repository import (
    delete_media,
    fetch_media,
    get_media,
    get_media_by_ids,
    get_media_tags,
    insert_media,
    list_tags,
    set_media_tags,
    tags_for_media,
)


library_manager = LibraryManager()


class LibraryInfo(BaseModel):
    id: str
    name: str


class CreateLibraryRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class MediaResponse(BaseModel):
    id: str
    original_filename: str
    media_type: str
    mime_type: str
    taken_at: Optional[int]
    imported_at: int
    size_bytes: int
    width: Optional[int]
    height: Optional[int]
    duration: Optional[float]
    camera_make: Optional[str]
    camera_model: Optional[str]
    gps_lat: Optional[float]
    gps_lon: Optional[float]
    description: Optional[str]
    tags: List[str]


class MediaDetailResponse(MediaResponse):
    stored_filename: str
    extension: str


class TagResponse(BaseModel):
    id: str
    name: str


class UpdateTagsRequest(BaseModel):
    tags: List[str]


class BulkDeleteRequest(BaseModel):
    ids: List[str]


class DownloadRequest(BaseModel):
    ids: List[str]


def create_app() -> FastAPI:
    app = FastAPI(title="Open Library Format", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_library(library_id: str) -> Library:
        try:
            return library_manager.load(library_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Library not found") from exc

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "timestamp": int(time.time())}

    @app.get("/api/libraries", response_model=List[LibraryInfo])
    def list_libraries() -> List[LibraryInfo]:
        return [LibraryInfo(id=lib.id, name=lib.name) for lib in library_manager.list_libraries()]

    @app.post("/api/libraries", response_model=LibraryInfo, status_code=201)
    def create_library(payload: CreateLibraryRequest) -> LibraryInfo:
        library = library_manager.create(payload.name.strip())
        return LibraryInfo(id=library.id, name=library.name)

    @app.get("/api/libraries/{library_id}", response_model=LibraryInfo)
    def get_library_info(library: Library = Depends(get_library)) -> LibraryInfo:
        return LibraryInfo(id=library.id, name=library.name)

    @app.get("/api/libraries/{library_id}/tags", response_model=List[TagResponse])
    def get_tags(library: Library = Depends(get_library)) -> List[TagResponse]:
        return [TagResponse(id=tag.id, name=tag.name) for tag in list_tags(library.db_path)]

    @app.get("/api/libraries/{library_id}/media", response_model=List[MediaResponse])
    def list_media(
        library: Library = Depends(get_library),
        search: Optional[str] = None,
        tags: List[str] | None = Query(None),
        taken_from: Optional[int] = Query(None, alias="takenFrom"),
        taken_to: Optional[int] = Query(None, alias="takenTo"),
        sort: Optional[str] = Query("newest"),
    ) -> List[MediaResponse]:
        rows = fetch_media(
            library.db_path,
            search=search,
            tags=tags,
            taken_from=taken_from,
            taken_to=taken_to,
            sort=sort or "newest",
        )
        tag_lookup = tags_for_media(library.db_path, [row.id for row in rows])
        return [
            MediaResponse(
                id=row.id,
                original_filename=row.original_filename,
                media_type=row.media_type,
                mime_type=row.mime_type,
                taken_at=row.taken_at,
                imported_at=row.imported_at,
                size_bytes=row.size_bytes,
                width=row.width,
                height=row.height,
                duration=row.duration,
                camera_make=row.camera_make,
                camera_model=row.camera_model,
                gps_lat=row.gps_lat,
                gps_lon=row.gps_lon,
                description=row.description,
                tags=tag_lookup.get(row.id, []),
            )
            for row in rows
        ]

    @app.post("/api/libraries/{library_id}/media", response_model=List[MediaDetailResponse])
    async def upload_media(
        library: Library = Depends(get_library),
        files: List[UploadFile] = File(...),
    ) -> List[MediaDetailResponse]:
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded")

        created: List[MediaDetailResponse] = []
        for upload in files:
            ingested = ingest_upload(library, upload)
            record = ingested["record"]
            insert_media(library.db_path, record)
            created.append(MediaDetailResponse(tags=[], **record))
        return created

    @app.get("/api/libraries/{library_id}/media/{media_id}", response_model=MediaDetailResponse)
    def get_media_item(library: Library = Depends(get_library), media_id: str = "") -> MediaDetailResponse:
        row = get_media(library.db_path, media_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Media not found")
        tags = [tag.name for tag in get_media_tags(library.db_path, media_id)]
        return MediaDetailResponse(
            id=row.id,
            original_filename=row.original_filename,
            media_type=row.media_type,
            mime_type=row.mime_type,
            taken_at=row.taken_at,
            imported_at=row.imported_at,
            size_bytes=row.size_bytes,
            width=row.width,
            height=row.height,
            duration=row.duration,
            camera_make=row.camera_make,
            camera_model=row.camera_model,
            gps_lat=row.gps_lat,
            gps_lon=row.gps_lon,
            description=row.description,
            tags=tags,
            stored_filename=row.stored_filename,
            extension=row.extension,
        )

    @app.post("/api/libraries/{library_id}/media/{media_id}/tags", response_model=List[str])
    def set_tags(
        payload: UpdateTagsRequest,
        library: Library = Depends(get_library),
        media_id: str = "",
    ) -> List[str]:
        if get_media(library.db_path, media_id) is None:
            raise HTTPException(status_code=404, detail="Media not found")
        tags = set_media_tags(library.db_path, media_id, payload.tags)
        return [tag.name for tag in tags]

    @app.delete("/api/libraries/{library_id}/media/{media_id}", status_code=204)
    def remove_media(library: Library = Depends(get_library), media_id: str = "") -> None:
        row = get_media(library.db_path, media_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Media not found")
        delete_media(library.db_path, [media_id])
        _delete_media_files(library, row.stored_filename)

    @app.post("/api/libraries/{library_id}/media/delete", status_code=204)
    def bulk_delete(payload: BulkDeleteRequest, library: Library = Depends(get_library)) -> None:
        rows = get_media_by_ids(library.db_path, payload.ids)
        delete_media(library.db_path, payload.ids)
        for row in rows:
            _delete_media_files(library, row.stored_filename)

    @app.post("/api/libraries/{library_id}/download")
    def download(payload: DownloadRequest, library: Library = Depends(get_library)) -> StreamingResponse:
        rows = get_media_by_ids(library.db_path, payload.ids)
        if not rows:
            raise HTTPException(status_code=404, detail="No media found")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for row in rows:
                raw_path = _raw_path(library, row.stored_filename)
                if not raw_path.exists():
                    continue
                archive.write(raw_path, arcname=row.original_filename)
        buffer.seek(0)

        filename = f"{library.name.replace(' ', '_')}_download.zip"
        headers = {
            "Content-Disposition": f"attachment; filename=\"{filename}\""
        }
        return StreamingResponse(buffer, media_type="application/zip", headers=headers)

    @app.get("/api/libraries/{library_id}/media/{media_id}/thumbnail")
    def thumbnail(library: Library = Depends(get_library), media_id: str = "") -> FileResponse:
        row = get_media(library.db_path, media_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Media not found")
        thumb_path = _thumbnail_path(library, row.stored_filename)
        if not thumb_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        return FileResponse(thumb_path)

    @app.get("/api/libraries/{library_id}/media/{media_id}/content")
    def media_content(library: Library = Depends(get_library), media_id: str = "") -> FileResponse:
        row = get_media(library.db_path, media_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Media not found")
        raw_path = _raw_path(library, row.stored_filename)
        if not raw_path.exists():
            raise HTTPException(status_code=404, detail="Media file missing")
        return FileResponse(raw_path, media_type=row.mime_type, filename=row.original_filename)

    web_dir = Path(__file__).resolve().parent.parent / "web"
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


def _raw_path(library: Library, stored_filename: str) -> Path:
    stem = Path(stored_filename).stem
    return library.media_root / "raw" / stem[:2] / stored_filename


def _thumbnail_path(library: Library, stored_filename: str) -> Path:
    stem = Path(stored_filename).stem
    return library.media_root / "thumbnails" / stem[:2] / f"{stem}.jpg"


def _delete_media_files(library: Library, stored_filename: str) -> None:
    for path in (_raw_path(library, stored_filename), _thumbnail_path(library, stored_filename)):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
