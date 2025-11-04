from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict


_connections: Dict[Path, sqlite3.Connection] = {}


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Allow use across threads (FastAPI workers)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = _connections.get(db_path)
    if conn is None:
        conn = _connect(db_path)
        _connections[db_path] = conn
    return conn


