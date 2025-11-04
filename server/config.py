from __future__ import annotations

from pathlib import Path
from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    """Runtime configuration for the API server."""

    library_root: Path = Path("./libraries")
    thumbnail_size: int = 320

    class Config:
        env_prefix = "OLF_"
        env_file = ".env"
        env_file_encoding = "utf-8"

    @validator("library_root", pre=True)
    def _expand_library_root(cls, value: str | Path) -> Path:
        return Path(value).expanduser().resolve()

    @validator("thumbnail_size")
    def _ensure_positive_thumbnail(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("thumbnail_size must be positive")
        return value


settings = Settings()
