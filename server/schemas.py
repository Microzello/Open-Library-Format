from __future__ import annotations

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class LibraryInfo(BaseModel):
    id: str = Field(description="Library UUID")
    name: str
    created_at: int
    path: str


class CreateLibraryRequest(BaseModel):
    name: str


