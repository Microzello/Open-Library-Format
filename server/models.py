from __future__ import annotations

import sqlite3


SCHEMA_SQL = [
    # media table
    """
    CREATE TABLE IF NOT EXISTS media (
        id TEXT PRIMARY KEY,
        type TEXT CHECK(type IN ('photo','video')),
        original_filename TEXT NOT NULL,
        stored_filename TEXT NOT NULL,
        ext TEXT NOT NULL,
        shard TEXT NOT NULL,
        mime_type TEXT,
        filesize INTEGER,
        width INTEGER,
        height INTEGER,
        duration_ms INTEGER,
        camera_make TEXT,
        camera_model TEXT,
        gps_lat REAL,
        gps_lon REAL,
        taken_at_epoch INTEGER,
        created_at_epoch INTEGER NOT NULL
    );
    """,
    # tags table
    """
    CREATE TABLE IF NOT EXISTS tags (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    """,
    # media_tags join table
    """
    CREATE TABLE IF NOT EXISTS media_tags (
        media_id TEXT NOT NULL,
        tag_id TEXT NOT NULL,
        PRIMARY KEY (media_id, tag_id),
        FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE,
        FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
    );
    """,
    # proxies table
    """
    CREATE TABLE IF NOT EXISTS proxies (
        media_id TEXT PRIMARY KEY,
        kind TEXT CHECK(kind IN ('mp4','hls')) NOT NULL,
        path TEXT NOT NULL,
        width INTEGER,
        height INTEGER,
        bitrate_kbps INTEGER,
        created_at_epoch INTEGER NOT NULL,
        FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE
    );
    """,
    # thumbnails table
    """
    CREATE TABLE IF NOT EXISTS thumbnails (
        media_id TEXT PRIMARY KEY,
        path TEXT NOT NULL,
        width INTEGER,
        height INTEGER,
        created_at_epoch INTEGER NOT NULL,
        FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE
    );
    """,
]


def create_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    for stmt in SCHEMA_SQL:
        cur.execute(stmt)
    conn.commit()


