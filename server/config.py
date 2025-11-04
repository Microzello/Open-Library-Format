from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    # Optional dependency; if missing, we rely on OS env only
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - optional
    load_dotenv = None  # type: ignore


@dataclass(frozen=True)
class AppConfig:
    libraries_root: Path
    ffmpeg_path: str
    ffprobe_path: str
    thumb_size: int
    host: str
    port: int


def _get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    # Load .env if python-dotenv is available
    if load_dotenv is not None:
        # Do not error if missing; local-only convenience
        load_dotenv(override=False)

    libraries_root_env = os.getenv("LIBRARIES_ROOT", "").strip()
    if not libraries_root_env:
        # Default to a folder named 'libraries' in the project directory if not set
        default_root = Path.cwd() / "libraries"
        libraries_root = default_root
    else:
        libraries_root = Path(libraries_root_env)

    # Prepare root directory eagerly to reduce runtime surprises
    _ensure_dir(libraries_root)

    ffmpeg_path = os.getenv("FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg"
    ffprobe_path = os.getenv("FFPROBE_PATH", "ffprobe").strip() or "ffprobe"
    thumb_size = _get_env_int("THUMB_SIZE", 512)
    host = os.getenv("HOST", "127.0.0.1")
    port = _get_env_int("PORT", 8000)

    return AppConfig(
        libraries_root=libraries_root,
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        thumb_size=thumb_size,
        host=host,
        port=port,
    )


# Singleton-like access pattern
_CONFIG: Optional[AppConfig] = None


def get_config() -> AppConfig:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_config()
    return _CONFIG


