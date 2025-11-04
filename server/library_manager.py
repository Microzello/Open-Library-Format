from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .config import settings
from .storage import ensure_media_folders
from .storage import initialize_database


@dataclass
class Library:
    id: str
    name: str
    path: Path

    @property
    def db_path(self) -> Path:
        return self.path / "media.db"

    @property
    def manifest_path(self) -> Path:
        return self.path / "library.json"

    @property
    def media_root(self) -> Path:
        return self.path / "media"


class LibraryManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.library_root
        self.root.mkdir(parents=True, exist_ok=True)

    def list_libraries(self) -> List[Library]:
        libraries: List[Library] = []
        for manifest in self.root.glob("*/library.json"):
            with manifest.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            libraries.append(
                Library(id=data["id"], name=data["name"], path=manifest.parent)
            )
        libraries.sort(key=lambda lib: lib.name.lower())
        return libraries

    def load(self, library_id: str) -> Library:
        manifest = next(
            (path for path in self.root.glob("*/library.json") if _manifest_id(path) == library_id),
            None,
        )
        if manifest is None:
            raise FileNotFoundError(f"Library {library_id} not found")
        with manifest.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return Library(id=data["id"], name=data["name"], path=manifest.parent)

    def create(self, name: str) -> Library:
        identifier = str(uuid.uuid4())
        folder = self.root / identifier
        folder.mkdir(parents=True, exist_ok=False)
        ensure_media_folders(folder)
        manifest = {
            "id": identifier,
            "name": name,
            "created_at": int(time.time()),
        }
        with (folder / "library.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        initialize_database(folder / "media.db")
        return Library(id=identifier, name=name, path=folder)


def _manifest_id(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("id")
    except (OSError, json.JSONDecodeError):
        return None
