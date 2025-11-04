from __future__ import annotations

import sqlite3
from pathlib import Path


def ensure_media_folders(library_root: Path) -> None:
    (library_root / "media" / "raw").mkdir(parents=True, exist_ok=True)
    (library_root / "media" / "thumbnails").mkdir(parents=True, exist_ok=True)
    (library_root / "media" / "proxies").mkdir(parents=True, exist_ok=True)


def initialize_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        cursor = connection.cursor()
        cursor.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS media (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                extension TEXT NOT NULL,
                media_type TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                taken_at INTEGER,
                imported_at INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                width INTEGER,
                height INTEGER,
                duration REAL,
                camera_make TEXT,
                camera_model TEXT,
                gps_lat REAL,
                gps_lon REAL,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS tags (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS media_tags (
                media_id TEXT NOT NULL,
                tag_id TEXT NOT NULL,
                PRIMARY KEY (media_id, tag_id),
                FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_media_taken_at ON media(taken_at);
            CREATE INDEX IF NOT EXISTS idx_media_imported_at ON media(imported_at);
            """
        )
        connection.commit()
    finally:
        connection.close()
