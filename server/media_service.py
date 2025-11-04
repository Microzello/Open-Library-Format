from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Optional, Tuple, List

from .db import get_connection
from .libraries import library_db_path


def get_media_by_id(library_root: Path, media_id: str) -> Optional[dict]:
    conn = get_connection(library_db_path(library_root))
    cur = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,))
    row = cur.fetchone()
    if not row:
        return None
    cols = [c[0] for c in cur.description]
    return {k: row[i] for i, k in enumerate(cols)}


def raw_media_path(library_root: Path, media: dict) -> Path:
    shard = media["shard"]
    stored = media["stored_filename"]
    return library_root / 'media' / 'raw' / shard / stored


def list_media(
    library_root: Path,
    page: int = 1,
    size: int = 50,
    sort: str = "newest",
    mtype: Optional[str] = None,
    q: Optional[str] = None,
    taken_from: Optional[int] = None,
    taken_to: Optional[int] = None,
    tag_ids: Optional[list[str]] = None,
    tag_mode: str = "and",
) -> dict:
    conn = get_connection(library_db_path(library_root))
    where: list[str] = []
    params: list = []
    join_sql = ""

    if mtype in {"photo", "video"}:
        where.append("type = ?")
        params.append(mtype)
    if q:
        where.append("original_filename LIKE ?")
        params.append(f"%{q}%")
    if taken_from is not None:
        where.append("(taken_at_epoch IS NOT NULL AND taken_at_epoch >= ?)")
        params.append(taken_from)
    if taken_to is not None:
        where.append("(taken_at_epoch IS NOT NULL AND taken_at_epoch <= ?)")
        params.append(taken_to)

    # Tag filtering
    if tag_ids:
        tag_ids = [t for t in tag_ids if t]
        if tag_ids:
            if tag_mode == "or":
                join_sql += " JOIN media_tags mt ON mt.media_id = media.id"
                where.append(f"mt.tag_id IN ({','.join('?' for _ in tag_ids)})")
                params.extend(tag_ids)
            else:  # and
                # intersection via multiple joins
                for idx, tid in enumerate(tag_ids):
                    alias = f"mt{idx}"
                    join_sql += f" JOIN media_tags {alias} ON {alias}.media_id = media.id AND {alias}.tag_id = ?"
                    params.append(tid)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    order_sql = {
        "newest": "ORDER BY COALESCE(taken_at_epoch, created_at_epoch) DESC",
        "oldest": "ORDER BY COALESCE(taken_at_epoch, created_at_epoch) ASC",
    }.get(sort, "ORDER BY created_at_epoch DESC")

    limit = max(1, min(size, 200))
    offset = max(0, (max(1, page) - 1) * limit)

    total = conn.execute(f"SELECT COUNT(*) FROM media {join_sql} {where_sql}", params).fetchone()[0]

    cur = conn.execute(
        f"SELECT media.* FROM media {join_sql} {where_sql} {order_sql} LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )
    cols = [c[0] for c in cur.description]
    rows = [
        {k: r[i] for i, k in enumerate(cols)}
        for r in cur.fetchall()
    ]
    return {"total": total, "page": page, "size": limit, "items": rows}


def create_tag(library_root: Path, name: str, tag_id: Optional[str] = None) -> dict:
    conn = get_connection(library_db_path(library_root))
    tid = tag_id or __import__('uuid').uuid4().hex
    conn.execute("INSERT OR IGNORE INTO tags (id, name) VALUES (?, ?)", (tid, name))
    conn.commit()
    row = conn.execute("SELECT id, name FROM tags WHERE id = ?", (tid,)).fetchone()
    return {"id": row[0], "name": row[1]}


def list_tags(library_root: Path) -> list[dict]:
    conn = get_connection(library_db_path(library_root))
    cur = conn.execute("SELECT id, name FROM tags ORDER BY name ASC")
    return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]


def add_tags_to_media(library_root: Path, media_id: str, tag_ids: list[str]) -> None:
    conn = get_connection(library_db_path(library_root))
    for tid in tag_ids:
        conn.execute("INSERT OR IGNORE INTO media_tags (media_id, tag_id) VALUES (?, ?)", (media_id, tid))
    conn.commit()


def remove_tag_from_media(library_root: Path, media_id: str, tag_id: str) -> None:
    conn = get_connection(library_db_path(library_root))
    conn.execute("DELETE FROM media_tags WHERE media_id = ? AND tag_id = ?", (media_id, tag_id))
    conn.commit()


def list_media_tags(library_root: Path, media_id: str) -> list[dict]:
    conn = get_connection(library_db_path(library_root))
    cur = conn.execute(
        "SELECT t.id, t.name FROM tags t JOIN media_tags mt ON mt.tag_id = t.id WHERE mt.media_id = ? ORDER BY t.name",
        (media_id,),
    )
    return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]


def _thumb_file(library_root: Path, media_id: str) -> Path:
    return library_root / 'media' / 'thumbs' / f'{media_id}.jpg'


def _proxy_files(library_root: Path, media_id: str) -> list[Path]:
    mp4 = library_root / 'media' / 'proxies' / 'mp4' / f'{media_id}.mp4'
    hls_dir = library_root / 'media' / 'proxies' / 'hls' / media_id
    files: list[Path] = []
    if mp4.exists():
        files.append(mp4)
    if hls_dir.exists():
        files.extend(hls_dir.rglob('*'))
        files.append(hls_dir)
    return files


def delete_media(library_root: Path, media_id: str) -> None:
    media = get_media_by_id(library_root, media_id)
    conn = get_connection(library_db_path(library_root))
    if media:
        # remove files
        try:
            raw = raw_media_path(library_root, media)
            if raw.exists():
                raw.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            _thumb_file(library_root, media_id).unlink(missing_ok=True)
        except Exception:
            pass
        for p in _proxy_files(library_root, media_id):
            try:
                if p.is_dir():
                    p.rmdir()
                else:
                    p.unlink(missing_ok=True)
            except Exception:
                pass
    conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
    conn.commit()


def delete_media_batch(library_root: Path, ids: list[str]) -> dict:
    for mid in ids:
        delete_media(library_root, mid)
    return {"deleted": len(ids)}


