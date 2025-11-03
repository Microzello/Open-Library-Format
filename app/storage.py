"""Content-addressed storage operations."""
import hashlib
import os
import shutil
from pathlib import Path
from typing import Tuple


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(8192), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def shard_path(sha256: str) -> str:
    """
    Convert SHA-256 hash to sharded path.
    Returns: "aa/bb/<sha256>" for hash starting with aabb...
    """
    if len(sha256) < 4:
        raise ValueError("SHA-256 hash too short")
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}"


def get_file_path(library_path: Path, sha256: str) -> Path:
    """Get full path to file in content-addressed storage."""
    return library_path / "files" / shard_path(sha256)


def get_trash_path(library_path: Path, sha256: str) -> Path:
    """Get full path to file in trash."""
    return library_path / "trash" / shard_path(sha256)


def get_thumb_path(library_path: Path, sha256: str, kind: str = "img") -> Path:
    """Get full path to thumbnail."""
    return library_path / "thumbs" / kind / shard_path(sha256)


def atomic_move(src: Path, dest: Path) -> None:
    """
    Atomically move a file from src to dest.
    Creates parent directories if needed.
    Performs fsync before rename for durability.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    # If destination exists, that's OK (content-addressed, same hash)
    if dest.exists():
        src.unlink()
        return
    
    # Sync file contents to disk
    try:
        with open(src, 'rb') as f:
            os.fsync(f.fileno())
    except OSError:
        # On some systems/fsync may not be available, continue anyway
        pass
    
    # Atomic rename (same filesystem)
    shutil.move(str(src), str(dest))


def trash_file(library_path: Path, sha256: str) -> None:
    """Move file from files/ to trash/."""
    src = get_file_path(library_path, sha256)
    dest = get_trash_path(library_path, sha256)
    
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")
    
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def restore_file(library_path: Path, sha256: str) -> None:
    """Move file from trash/ back to files/."""
    src = get_trash_path(library_path, sha256)
    dest = get_file_path(library_path, sha256)
    
    if not src.exists():
        raise FileNotFoundError(f"File not found in trash: {src}")
    
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def ensure_library_structure(library_path: Path) -> None:
    """Ensure all required directories exist for a library."""
    dirs = [
        library_path / "files",
        library_path / "trash",
        library_path / "thumbs" / "img",
        library_path / "thumbs" / "vid",
        library_path / "locks",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def get_file_size(filepath: Path) -> int:
    """Get file size in bytes."""
    return filepath.stat().st_size


def file_exists_in_storage(library_path: Path, sha256: str) -> Tuple[bool, bool]:
    """
    Check if file exists in storage.
    Returns: (exists_in_files, exists_in_trash)
    """
    in_files = get_file_path(library_path, sha256).exists()
    in_trash = get_trash_path(library_path, sha256).exists()
    return in_files, in_trash

