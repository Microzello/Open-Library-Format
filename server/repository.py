from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List


@dataclass
class MediaRow:
    id: str
    original_filename: str
    stored_filename: str
    extension: str
    media_type: str
    mime_type: str
    taken_at: int | None
    imported_at: int
    size_bytes: int
    width: int | None
    height: int | None
    duration: float | None
    camera_make: str | None
    camera_model: str | None
    gps_lat: float | None
    gps_lon: float | None
    description: str | None

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class TagRow:
    id: str
    name: str


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(db_path)
    try:
        connection.row_factory = sqlite3.Row
        yield connection
    finally:
        connection.close()


def fetch_media(
    db_path: Path,
    *,
    search: str | None = None,
    tags: List[str] | None = None,
    taken_from: int | None = None,
    taken_to: int | None = None,
    sort: str = "newest",
) -> List[MediaRow]:
    query_parts: List[str] = ["SELECT m.* FROM media m"]
    params: List[object] = []
    where_parts: List[str] = []

    if tags:
        placeholders = ",".join("?" for _ in tags)
        query_parts.append("JOIN media_tags mt ON m.id = mt.media_id")
        query_parts.append("JOIN tags t ON t.id = mt.tag_id")
        where_parts.append(f"t.name IN ({placeholders})")
        params.extend(tags)

    if search:
        where_parts.append("LOWER(m.original_filename) LIKE ?")
        params.append(f"%{search.lower()}%")

    if taken_from is not None:
        where_parts.append("(m.taken_at IS NOT NULL AND m.taken_at >= ?)")
        params.append(taken_from)

    if taken_to is not None:
        where_parts.append("(m.taken_at IS NOT NULL AND m.taken_at <= ?)")
        params.append(taken_to)

    if where_parts:
        query_parts.append("WHERE " + " AND ".join(where_parts))

    if tags:
        query_parts.append("GROUP BY m.id HAVING COUNT(DISTINCT t.name) = ?")
        params.append(len(set(tags)))

    if sort == "oldest":
        order = "m.imported_at ASC"
    elif sort == "taken":
        order = "COALESCE(m.taken_at, m.imported_at) DESC"
    else:
        order = "m.imported_at DESC"
    query_parts.append(f"ORDER BY {order}")

    statement = " ".join(query_parts)

    with connect(db_path) as conn:
        rows = conn.execute(statement, params).fetchall()
    return [MediaRow(**dict(row)) for row in rows]


def get_media(db_path: Path, media_id: str) -> MediaRow | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
    return MediaRow(**dict(row)) if row else None


def get_media_by_ids(db_path: Path, media_ids: Iterable[str]) -> List[MediaRow]:
    ids = [*media_ids]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    query = f"SELECT * FROM media WHERE id IN ({placeholders})"
    with connect(db_path) as conn:
        rows = conn.execute(query, ids).fetchall()
    return [MediaRow(**dict(row)) for row in rows]


def insert_media(db_path: Path, data: Dict[str, object]) -> None:
    columns = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    values = list(data.values())
    with connect(db_path) as conn:
        conn.execute(f"INSERT INTO media ({columns}) VALUES ({placeholders})", values)
        conn.commit()


def delete_media(db_path: Path, media_ids: Iterable[str]) -> None:
    ids = [*media_ids]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    with connect(db_path) as conn:
        conn.execute(f"DELETE FROM media WHERE id IN ({placeholders})", ids)
        conn.commit()


def list_tags(db_path: Path) -> List[TagRow]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT id, name FROM tags ORDER BY LOWER(name)").fetchall()
    return [TagRow(**dict(row)) for row in rows]


def ensure_tags(db_path: Path, tag_names: Iterable[str]) -> List[TagRow]:
    names = [name.strip() for name in tag_names if name.strip()]
    if not names:
        return []

    existing = {tag.name: tag for tag in list_tags(db_path)}

    with connect(db_path) as conn:
        for name in names:
            if name in existing:
                continue
            tag_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO tags (id, name) VALUES (?, ?)",
                (tag_id, name),
            )
            existing[name] = TagRow(id=tag_id, name=name)
        conn.commit()

    ordered = []
    for name in names:
        tag = existing.get(name)
        if tag and tag not in ordered:
            ordered.append(tag)
    return ordered


def set_media_tags(db_path: Path, media_id: str, tag_names: Iterable[str]) -> List[TagRow]:
    tags = ensure_tags(db_path, tag_names)
    tag_lookup = {tag.name: tag.id for tag in tags}
    normalized = [name.strip() for name in tag_names if name.strip()]

    with connect(db_path) as conn:
        conn.execute("DELETE FROM media_tags WHERE media_id = ?", (media_id,))
        for name in normalized:
            conn.execute(
                "INSERT OR IGNORE INTO media_tags (media_id, tag_id) VALUES (?, ?)",
                (media_id, tag_lookup[name]),
            )
        conn.commit()

    return [TagRow(id=tag_lookup[name], name=name) for name in normalized]


def get_media_tags(db_path: Path, media_id: str) -> List[TagRow]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT t.id, t.name FROM tags t "
            "JOIN media_tags mt ON mt.tag_id = t.id "
            "WHERE mt.media_id = ? ORDER BY LOWER(t.name)",
            (media_id,),
        ).fetchall()
    return [TagRow(**dict(row)) for row in rows]


def tags_for_media(db_path: Path, media_ids: Iterable[str]) -> Dict[str, List[str]]:
    ids = [*media_ids]
    if not ids:
        return {}

    placeholders = ",".join("?" for _ in ids)
    query = (
        "SELECT mt.media_id, t.name FROM media_tags mt "
        "JOIN tags t ON t.id = mt.tag_id "
        f"WHERE mt.media_id IN ({placeholders})"
    )

    result: Dict[str, List[str]] = {media_id: [] for media_id in ids}
    with connect(db_path) as conn:
        for row in conn.execute(query, ids):
            result[row["media_id"]].append(row["name"])
    return result
