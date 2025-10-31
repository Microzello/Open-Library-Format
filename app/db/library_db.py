"""Per-library database management."""
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager


class LibraryDB:
    """Manages a single library's index.db."""

    def __init__(self, library_path: str):
        self.library_path = Path(library_path)
        self.db_path = self.library_path / "index.db"
        self._init_db()

    def _init_db(self):
        """Initialize library database with schema."""
        schema_path = Path(__file__).parent / "schema_library.sql"
        with self.get_connection() as conn:
            try:
                with open(schema_path, "r") as f:
                    conn.executescript(f.read())
                conn.commit()
            except sqlite3.OperationalError as e:
                # Tables might already exist, which is fine
                # The schema uses CREATE TABLE IF NOT EXISTS, so this should rarely happen
                error_msg = str(e).lower()
                if "already exists" not in error_msg and "duplicate" not in error_msg:
                    raise
                conn.commit()

    @contextmanager
    def get_connection(self):
        """Get a database connection context."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def get_schema_version(self) -> int:
        """Get current schema version."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def update_schema_version(self, version: int):
        """Update schema version."""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(version),),
            )
            conn.commit()

    # File operations

    def get_file_by_sha256(self, sha256: str) -> Optional[Dict[str, Any]]:
        """Get file record by SHA256 hash."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM files WHERE sha256 = ?", (sha256,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_file_by_id(self, file_id: int) -> Optional[Dict[str, Any]]:
        """Get file record by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def insert_file(
        self,
        sha256: str,
        size: int,
        ext: Optional[str],
        mime: Optional[str],
        original_name: str,
        captured_at: Optional[str] = None,
    ) -> int:
        """Insert a new file record. Returns file ID."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO files (sha256, size, ext, mime, original_name, captured_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sha256, size, ext, mime, original_name, captured_at),
            )
            conn.commit()
            return cursor.lastrowid

    def update_file(self, file_id: int, notes: Optional[str] = None):
        """Update file metadata."""
        with self.get_connection() as conn:
            if notes is not None:
                conn.execute(
                    "UPDATE files SET notes = ? WHERE id = ?", (notes, file_id)
                )
            conn.commit()

    def mark_deleted(self, file_id: int):
        """Mark file as deleted (move to trash)."""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE files SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
                (file_id,),
            )
            conn.commit()

    def restore_file(self, file_id: int):
        """Restore file from trash."""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE files SET deleted_at = NULL WHERE id = ?", (file_id,)
            )
            conn.commit()

    def list_files(
        self,
        page: int = 0,
        page_size: int = 100,
        include_deleted: bool = False,
        tag_id: Optional[int] = None,
        sort: str = "captured_at_desc",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List files with pagination.
        Returns (files, total_count).
        """
        offset = page * page_size

        # Build query
        where_clauses = []
        params = []

        if not include_deleted:
            where_clauses.append("f.deleted_at IS NULL")

        if tag_id:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM file_tags ft WHERE ft.file_id = f.id AND ft.tag_id = ?)"
            )
            params.append(tag_id)

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # Sort order
        if sort == "captured_at_desc":
            order_sql = "ORDER BY f.captured_at DESC, f.id DESC"
        elif sort == "captured_at_asc":
            order_sql = "ORDER BY f.captured_at ASC, f.id ASC"
        elif sort == "added_at_desc":
            order_sql = "ORDER BY f.added_at DESC, f.id DESC"
        else:
            order_sql = "ORDER BY f.added_at DESC, f.id DESC"

        with self.get_connection() as conn:
            # Get total count
            count_cursor = conn.execute(
                f"SELECT COUNT(*) FROM files f {where_sql}", params
            )
            total = count_cursor.fetchone()[0]

            # Get page
            cursor = conn.execute(
                f"""SELECT f.* FROM files f
                    {where_sql}
                    {order_sql}
                    LIMIT ? OFFSET ?""",
                params + [page_size, offset],
            )
            files = [dict(row) for row in cursor.fetchall()]

        return files, total

    def search_files(self, query: str, page: int = 0, page_size: int = 100) -> Tuple[List[Dict[str, Any]], int]:
        """Full-text search on files (excludes deleted files)."""
        offset = page * page_size

        with self.get_connection() as conn:
            # Count matches (excluding deleted)
            count_cursor = conn.execute(
                """SELECT COUNT(*) FROM files f
                   JOIN file_fts fts ON f.id = fts.rowid
                   WHERE fts MATCH ? AND f.deleted_at IS NULL""",
                (query,),
            )
            total = count_cursor.fetchone()[0]

            # Get matches (excluding deleted)
            cursor = conn.execute(
                """SELECT f.* FROM files f
                   JOIN file_fts fts ON f.id = fts.rowid
                   WHERE fts MATCH ? AND f.deleted_at IS NULL
                   ORDER BY fts.rank
                   LIMIT ? OFFSET ?""",
                (query, page_size, offset),
            )
            files = [dict(row) for row in cursor.fetchall()]

        return files, total

    # Tag operations

    def create_tag(self, name: str) -> int:
        """Create a tag. Returns tag ID."""
        with self.get_connection() as conn:
            try:
                cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Tag exists, return existing ID
                cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (name,))
                return cursor.fetchone()[0]

    def get_tag_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get tag by name."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM tags WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_tag_by_id(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """Get tag by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_tags(self) -> List[Dict[str, Any]]:
        """List all tags with file counts (excluding deleted files)."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT t.id, t.name, COUNT(ft.file_id) as file_count
                   FROM tags t
                   LEFT JOIN file_tags ft ON t.id = ft.tag_id
                   LEFT JOIN files f ON ft.file_id = f.id AND f.deleted_at IS NULL
                   GROUP BY t.id, t.name
                   ORDER BY t.name"""
            )
            return [dict(row) for row in cursor.fetchall()]

    def add_tag_to_file(self, file_id: int, tag_id: int):
        """Add tag to file."""
        with self.get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO file_tags (file_id, tag_id) VALUES (?, ?)",
                    (file_id, tag_id),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                # Already tagged
                pass

    def remove_tag_from_file(self, file_id: int, tag_id: int):
        """Remove tag from file."""
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM file_tags WHERE file_id = ? AND tag_id = ?",
                (file_id, tag_id),
            )
            conn.commit()

    def get_file_tags(self, file_id: int) -> List[Dict[str, Any]]:
        """Get all tags for a file."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT t.* FROM tags t
                   JOIN file_tags ft ON t.id = ft.tag_id
                   WHERE ft.file_id = ?
                   ORDER BY t.name""",
                (file_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # Attributes

    def set_attribute(self, file_id: int, key: str, value: str):
        """Set a file attribute."""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO attributes (file_id, key, value) VALUES (?, ?, ?)",
                (file_id, key, value),
            )
            conn.commit()

    def get_attribute(self, file_id: int, key: str) -> Optional[str]:
        """Get a file attribute."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT value FROM attributes WHERE file_id = ? AND key = ?",
                (file_id, key),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_all_attributes(self, file_id: int) -> Dict[str, str]:
        """Get all attributes for a file."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT key, value FROM attributes WHERE file_id = ?", (file_id,)
            )
            return {row[0]: row[1] for row in cursor.fetchall()}

    # Stats

    def get_stats(self) -> Dict[str, int]:
        """Get library statistics."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM files WHERE deleted_at IS NULL")
            total_files = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM files WHERE deleted_at IS NOT NULL")
            trash_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM tags")
            tag_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT SUM(size) FROM files WHERE deleted_at IS NULL")
            total_size = cursor.fetchone()[0] or 0

            return {
                "total_files": total_files,
                "trash_count": trash_count,
                "tag_count": tag_count,
                "total_size": total_size,
            }

    # Maintenance

    def checkpoint_wal(self):
        """Checkpoint and truncate WAL file."""
        with self.get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()

