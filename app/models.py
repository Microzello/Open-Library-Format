"""Pydantic models for API requests and responses."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Error responses

class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


# Auth models

class LoginRequest(BaseModel):
    username: str
    password: str


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)
    token: str


# Library models

class LibraryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(pattern="^(photo_video|documents|music)$")
    slug: Optional[str] = None
    tz: Optional[str] = "UTC"


class LibraryResponse(BaseModel):
    id: str
    slug: str
    name: str
    type: str
    path: str
    created_at: str
    stats: Optional[Dict[str, int]] = None


# File models

class FileResponse(BaseModel):
    id: int
    sha256: str
    size: int
    ext: Optional[str]
    mime: Optional[str]
    original_name: str
    added_at: str
    captured_at: Optional[str]
    deleted_at: Optional[str]
    notes: Optional[str]
    tags: Optional[List[Dict[str, Any]]] = None
    attributes: Optional[Dict[str, str]] = None


class FileUpdateRequest(BaseModel):
    notes: Optional[str] = None
    attributes: Optional[Dict[str, str]] = None


class UploadResponse(BaseModel):
    status: str  # "uploaded", "exists", "restored"
    file_id: int
    sha256: str


# Tag models

class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TagResponse(BaseModel):
    id: int
    name: str
    file_count: Optional[int] = 0


class AddTagRequest(BaseModel):
    tag_id: int


# Health

class HealthResponse(BaseModel):
    status: str
    features: Dict[str, bool]
    libraries: Optional[List[Dict[str, Any]]] = None

