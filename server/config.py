from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API server."""

    library_root: Path = Path("./libraries")
    thumbnail_size: int = 320

    model_config = SettingsConfigDict(
        env_prefix="OLF_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @field_validator("library_root", mode="before")
    @classmethod
    def _expand_library_root(cls, value: str | Path) -> Path:
        return Path(value).expanduser().resolve()

    @field_validator("thumbnail_size")
    @classmethod
    def _ensure_positive_thumbnail(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("thumbnail_size must be positive")
        return value


settings = Settings()
