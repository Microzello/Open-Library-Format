from __future__ import annotations

from pathlib import Path
import json
import time
import uuid

from .db import get_connection
from .models import create_schema


def library_db_path(library_root: Path) -> Path:
    return library_root / "db" / "library.sqlite"


def ensure_library_dirs(library_root: Path) -> None:
    # Core directory layout
    (library_root / "db").mkdir(parents=True, exist_ok=True)
    (library_root / "media" / "raw").mkdir(parents=True, exist_ok=True)
    (library_root / "media" / "thumbs").mkdir(parents=True, exist_ok=True)
    (library_root / "media" / "proxies" / "mp4").mkdir(parents=True, exist_ok=True)
    (library_root / "media" / "proxies" / "hls").mkdir(parents=True, exist_ok=True)


def bootstrap_library_db(library_root: Path) -> None:
    ensure_library_dirs(library_root)
    conn = get_connection(library_db_path(library_root))
    create_schema(conn)


def library_json_path(library_root: Path) -> Path:
    return library_root / "library.json"


def list_libraries(libraries_root: Path) -> list[dict]:
    results: list[dict] = []
    if not libraries_root.exists():
        return results
    for child in libraries_root.iterdir():
        if not child.is_dir():
            continue
        lj = library_json_path(child)
        if not lj.exists():
            continue
        try:
            data = json.loads(lj.read_text(encoding="utf-8"))
            data["path"] = str(child.resolve())
            results.append(data)
        except Exception:
            continue
    # newest first by created_at
    results.sort(key=lambda d: d.get("created_at", 0), reverse=True)
    return results


def create_library(libraries_root: Path, name: str) -> dict:
    lib_uuid = uuid.uuid4().hex
    lib_root = libraries_root / lib_uuid
    ensure_library_dirs(lib_root)
    bootstrap_library_db(lib_root)
    payload = {
        "id": lib_uuid,
        "name": name,
        "created_at": int(time.time()),
    }
    library_json_path(lib_root).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["path"] = str(lib_root.resolve())
    return payload


