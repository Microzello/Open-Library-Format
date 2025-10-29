"""File ingest service."""
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from fastapi import UploadFile, HTTPException

from app.storage import (
    compute_sha256,
    atomic_move,
    get_file_path,
    restore_file,
    file_exists_in_storage,
)
from app.utils.mime import sniff_mime, is_mime_allowed, is_image
from app.utils.exif import parse_exif_datetime, get_file_mtime_utc
from app.db.library_db import LibraryDB


class IngestService:
    """Handles file upload and ingestion."""

    def __init__(self, library_db: LibraryDB, library_path: Path, library_type: str, library_tz: str = "UTC"):
        self.db = library_db
        self.library_path = library_path
        self.library_type = library_type
        self.library_tz = library_tz

    async def ingest_file(
        self, upload: UploadFile, tags: Optional[list[int]] = None
    ) -> Tuple[str, int, str]:
        """
        Ingest an uploaded file.
        
        Returns:
            (status, file_id, sha256)
            status: "uploaded", "exists", "restored"
        """
        # Save to temp
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(upload.filename or "").suffix) as tmp:
            tmp_path = Path(tmp.name)
            content = await upload.read()
            tmp.write(content)
            tmp.flush()

        try:
            # Compute hash and metadata
            sha256 = compute_sha256(tmp_path)
            size = tmp_path.stat().st_size
            ext = tmp_path.suffix.lstrip(".")
            mime = sniff_mime(tmp_path)

            # Validate MIME type
            if not is_mime_allowed(mime, self.library_type):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "INVALID_FILE_TYPE",
                            "message": f"File type {mime} not allowed for {self.library_type} library"
                        }
                    }
                )

            # Check if file exists
            in_files, in_trash = file_exists_in_storage(self.library_path, sha256)
            existing_record = self.db.get_file_by_sha256(sha256)

            # Case 1: File exists and is active
            if existing_record and existing_record["deleted_at"] is None:
                # Merge tags if provided
                if tags:
                    for tag_id in tags:
                        self.db.add_tag_to_file(existing_record["id"], tag_id)
                
                tmp_path.unlink()  # Clean up temp
                return "exists", existing_record["id"], sha256

            # Case 2: File is in trash, restore it
            if existing_record and existing_record["deleted_at"] is not None:
                # Restore blob if needed
                if in_trash and not in_files:
                    restore_file(self.library_path, sha256)
                
                # Clear deleted_at
                self.db.restore_file(existing_record["id"])
                
                # Merge tags
                if tags:
                    for tag_id in tags:
                        self.db.add_tag_to_file(existing_record["id"], tag_id)
                
                tmp_path.unlink()
                return "restored", existing_record["id"], sha256

            # Case 3: New file
            # Parse metadata
            captured_at = None
            captured_at_raw = None
            
            if is_image(mime):
                captured_at, captured_at_raw = parse_exif_datetime(tmp_path, self.library_tz)
            
            if not captured_at:
                # Fallback to file mtime
                captured_at = get_file_mtime_utc(tmp_path)

            # Move to storage
            dest = get_file_path(self.library_path, sha256)
            atomic_move(tmp_path, dest)

            # Insert into DB
            file_id = self.db.insert_file(
                sha256=sha256,
                size=size,
                ext=ext or None,
                mime=mime,
                original_name=upload.filename or "unknown",
                captured_at=captured_at,
            )

            # Store raw EXIF if present
            if captured_at_raw:
                self.db.set_attribute(file_id, "captured_at_raw", captured_at_raw)

            # Add tags
            if tags:
                for tag_id in tags:
                    self.db.add_tag_to_file(file_id, tag_id)

            return "uploaded", file_id, sha256

        except Exception as e:
            # Clean up temp file on error
            if tmp_path.exists():
                tmp_path.unlink()
            raise

