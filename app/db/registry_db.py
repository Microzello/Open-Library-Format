"""Global registry database management."""
import sqlite3
import json
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class RegistryDB:
    """Manages the global registry database."""

    def __init__(self, db_path: str = "var/registry.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the registry database with schema."""
        schema_path = Path(__file__).parent / "schema_registry.sql"
        with self.get_connection() as conn:
            with open(schema_path, "r") as f:
                conn.executescript(f.read())
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

    # User management

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_user(self, username: str, password_hash: str, role: str = "admin") -> int:
        """Create a new user."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
            )
            conn.commit()
            return cursor.lastrowid

    def has_any_users(self) -> bool:
        """Check if any users exist."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM users")
            count = cursor.fetchone()[0]
            return count > 0

    def update_last_login(self, user_id: int):
        """Update user's last login timestamp."""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id,),
            )
            conn.commit()

    # Library management

    def add_library(
        self, lib_id: str, slug: str, name: str, lib_type: str, path: str
    ) -> None:
        """Register a library in the registry."""
        with self.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO libraries (id, slug, name, type, path, last_scanned_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (lib_id, slug, name, lib_type, path),
            )
            conn.commit()

    def get_library_by_id(self, lib_id: str) -> Optional[Dict[str, Any]]:
        """Get library by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM libraries WHERE id = ?", (lib_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_library_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Get library by slug."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM libraries WHERE slug = ?", (slug,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_libraries(self) -> List[Dict[str, Any]]:
        """List all registered libraries."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM libraries ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    def remove_library(self, lib_id: str) -> None:
        """Remove library from registry (soft delete, folder stays on disk)."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM libraries WHERE id = ?", (lib_id,))
            conn.commit()

    def scan_libraries_root(self, libraries_root: str) -> List[Dict[str, Any]]:
        """
        Scan LIBRARIES_ROOT for directories containing library.json.
        Register any unknown libraries.
        Returns list of discovered libraries.
        """
        root = Path(libraries_root)
        if not root.exists():
            root.mkdir(parents=True, exist_ok=True)
            return []

        discovered = []
        for item in root.iterdir():
            if not item.is_dir():
                continue

            manifest_path = item / "library.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)

                lib_id = manifest["id"]
                slug = item.name
                name = manifest["name"]
                lib_type = manifest["type"]

                # Check if already registered
                existing = self.get_library_by_id(lib_id)
                if not existing:
                    self.add_library(lib_id, slug, name, lib_type, str(item.absolute()))
                    discovered.append(
                        {
                            "id": lib_id,
                            "slug": slug,
                            "name": name,
                            "type": lib_type,
                            "path": str(item.absolute()),
                        }
                    )
            except (json.JSONDecodeError, KeyError) as e:
                # Invalid manifest, skip
                print(f"Warning: Invalid library.json in {item}: {e}")
                continue

        return discovered

