"""Library reconciliation and integrity checks."""
from pathlib import Path
import random
from typing import Dict, List

from app.storage import compute_sha256, get_file_path
from app.db.library_db import LibraryDB


class ReconcilerService:
    """Reconciles library database with filesystem."""

    def __init__(self, library_db: LibraryDB, library_path: Path):
        self.db = library_db
        self.library_path = library_path

    def reconcile(self, sample_size: int = 100) -> Dict[str, any]:
        """
        Run full reconciliation.
        
        Returns report with:
        - orphaned_files: files on disk not in DB
        - missing_files: files in DB but not on disk
        - integrity_errors: hash mismatches
        - orphaned_tag_refs: file_tags pointing to deleted files
        """
        report = {
            "orphaned_files": [],
            "missing_files": [],
            "integrity_errors": [],
            "orphaned_tag_refs": 0,
        }

        # Check for missing files
        files, _ = self.db.list_files(page=0, page_size=10000, include_deleted=False)
        for file_rec in files:
            file_path = get_file_path(self.library_path, file_rec["sha256"])
            if not file_path.exists():
                report["missing_files"].append(file_rec["sha256"])

        # Sample integrity check (verify hashes)
        if len(files) > 0:
            sample = random.sample(files, min(sample_size, len(files)))
            for file_rec in sample:
                file_path = get_file_path(self.library_path, file_rec["sha256"])
                if file_path.exists():
                    actual_hash = compute_sha256(file_path)
                    if actual_hash != file_rec["sha256"]:
                        report["integrity_errors"].append({
                            "file_id": file_rec["id"],
                            "expected": file_rec["sha256"],
                            "actual": actual_hash,
                        })

        # Check for orphaned blobs (files on disk not in DB)
        files_dir = self.library_path / "files"
        if files_dir.exists():
            db_hashes = {f["sha256"] for f in files}
            for shard1 in files_dir.iterdir():
                if not shard1.is_dir():
                    continue
                for shard2 in shard1.iterdir():
                    if not shard2.is_dir():
                        continue
                    for blob in shard2.iterdir():
                        if blob.is_file() and blob.name not in db_hashes:
                            report["orphaned_files"].append(blob.name)

        # Cleanup orphaned file_tags (shouldn't happen with FK constraints, but check anyway)
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT COUNT(*) FROM file_tags ft
                   WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = ft.file_id)"""
            )
            report["orphaned_tag_refs"] = cursor.fetchone()[0]

        return report

    def checkpoint_wal(self):
        """Checkpoint and truncate WAL file."""
        self.db.checkpoint_wal()

