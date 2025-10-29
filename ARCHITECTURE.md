# Architecture Documentation

## Overview

Portable Library Manager is a self-hosted file management system built with FastAPI, SQLite, and content-addressed storage. It prioritizes portability, data integrity, and simplicity.

## Core Principles

1. **Portability First**: Each library is self-contained on disk
2. **Content Addressing**: Files are stored by SHA-256 hash
3. **No Permanent Deletion**: Files move to trash, never lost
4. **SQLite Everything**: No external databases
5. **Single Process**: All background jobs run in-process (APScheduler)

## System Architecture

```
┌─────────────────┐
│   Browser UI    │
│ (Tailwind +     │
│  Vanilla JS)    │
└────────┬────────┘
         │ HTTP/REST
         ▼
┌─────────────────────────────────────┐
│         FastAPI App                 │
│  ┌────────────┐  ┌────────────┐    │
│  │  Routes    │  │  Services  │    │
│  │            │  │            │    │
│  │ libraries  │  │  ingest    │    │
│  │ files      │  │  thumbs    │    │
│  │ tags       │  │  reconcile │    │
│  │ media      │  │            │    │
│  └────────────┘  └────────────┘    │
│                                     │
│  ┌────────────────────────────┐    │
│  │  APScheduler (in-process)  │    │
│  │  - Daily reconciliation    │    │
│  │  - WAL checkpointing       │    │
│  └────────────────────────────┘    │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│    Storage Layer                    │
│                                     │
│  var/registry.db (global)           │
│                                     │
│  LIBRARIES_ROOT/                    │
│    <slug>/                          │
│      library.json                   │
│      index.db (per-library)         │
│      files/aa/bb/<sha256>           │
│      thumbs/img|vid/aa/bb/<sha>.jpg │
│      trash/aa/bb/<sha256>           │
│      locks/                         │
└─────────────────────────────────────┘
```

## Data Flow

### File Upload

```
1. Browser → POST /api/libraries/{id}/files (multipart)
2. FastAPI receives upload
3. IngestService:
   a. Save to temp file
   b. Compute SHA-256 hash
   c. Sniff MIME type (libmagic)
   d. Validate MIME against library type
   e. Check for duplicates in DB:
      - If exists & active → return {status: "exists"}
      - If exists & in trash → restore blob + DB, return {status: "restored"}
      - If new → continue
   f. Parse EXIF (if image) with library TZ
   g. fsync + atomic rename to files/aa/bb/<sha256>
   h. Insert into index.db (transaction)
   i. Set attributes (EXIF raw, etc.)
4. ThumbnailService (synchronous for MVP):
   - Generate thumbnail (Pillow for images, ffmpeg for videos)
5. Return {status: "uploaded", file_id, sha256}
```

### Browsing Files

```
1. Browser → GET /api/libraries/{id}/files?page=0&sort=captured_at_desc
2. LibraryDB.list_files():
   - Query with pagination (100/page)
   - Sort by captured_at DESC, id DESC (stable tie-breaker)
   - Include deleted_at=NULL filter
3. For each file:
   - Load tags (join file_tags)
4. Return {files: [...], total, page, page_size}
5. Browser renders grid with /media/{slug}/thumbs/img/{sha}.jpg
```

### Search (Documents)

```
1. Browser → GET /api/libraries/{id}/files?q=search+terms
2. LibraryDB.search_files():
   - FTS5 query: SELECT * FROM file_fts WHERE file_fts MATCH ?
   - Rank by relevance
3. Return matching files
```

### Trash & Restore

```
Delete:
1. POST /api/libraries/{id}/files/{file_id} (DELETE)
2. trash_file(library_path, sha256):
   - Move blob from files/aa/bb/ → trash/aa/bb/
3. DB: UPDATE files SET deleted_at = NOW() WHERE id = ?

Restore:
1. POST /api/libraries/{id}/files/{file_id}/restore
2. restore_file(library_path, sha256):
   - Move blob from trash/aa/bb/ → files/aa/bb/
3. DB: UPDATE files SET deleted_at = NULL WHERE id = ?
```

## Database Schema

### Global Registry (`var/registry.db`)

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,  -- bcrypt
  role TEXT NOT NULL DEFAULT 'admin',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_login_at TEXT
);

CREATE TABLE libraries (
  id TEXT PRIMARY KEY,  -- UUID
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,  -- photo_video | documents | music
  path TEXT NOT NULL,  -- absolute path
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_scanned_at TEXT
);
```

### Per-Library (`index.db`)

```sql
-- Schema versioning
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Files (one row per unique SHA-256)
CREATE TABLE files (
  id INTEGER PRIMARY KEY,
  sha256 TEXT NOT NULL UNIQUE,
  size INTEGER NOT NULL,
  ext TEXT,
  mime TEXT,
  original_name TEXT NOT NULL,
  added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  captured_at TEXT,  -- UTC ISO8601
  deleted_at TEXT,   -- NULL if active
  notes TEXT
);

-- Indexes
CREATE INDEX idx_files_captured_at ON files(captured_at DESC, id DESC);
CREATE INDEX idx_files_deleted_at ON files(deleted_at);

-- Tags (normalized)
CREATE TABLE tags (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

-- Many-to-many
CREATE TABLE file_tags (
  file_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(file_id, tag_id),
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
  FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- Sparse key-value metadata
CREATE TABLE attributes (
  file_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  value TEXT,
  PRIMARY KEY(file_id, key),
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- Full-text search (external content)
CREATE VIRTUAL TABLE file_fts USING fts5(title, notes, content='');

-- Triggers to maintain FTS
CREATE TRIGGER files_ai AFTER INSERT ON files BEGIN
  INSERT INTO file_fts(rowid, title, notes)
  VALUES (new.id, COALESCE(new.original_name, ''), COALESCE(new.notes, ''));
END;

CREATE TRIGGER files_au AFTER UPDATE OF original_name, notes ON files BEGIN
  INSERT INTO file_fts(file_fts, rowid, title, notes) VALUES('delete', old.id, '', '');
  INSERT INTO file_fts(rowid, title, notes)
  VALUES (new.id, COALESCE(new.original_name, ''), COALESCE(new.notes, ''));
END;

CREATE TRIGGER files_ad AFTER DELETE ON files BEGIN
  INSERT INTO file_fts(file_fts, rowid, title, notes) VALUES('delete', old.id, '', '');
END;
```

## Content-Addressed Storage

### Shard Path Calculation

```python
def shard_path(sha256: str) -> str:
    # SHA-256: "aabbccdd..."
    # Returns: "aa/bb/aabbccdd..."
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}"
```

**Rationale**: Two-level fan-out creates 256×256 = 65,536 buckets, preventing directory size issues even with millions of files.

### Deduplication

Files with identical SHA-256 are stored once. The `files` table has `UNIQUE(sha256)` constraint. On upload:
- If hash exists and `deleted_at IS NULL` → merge tags, return {status: "exists"}
- If hash exists and `deleted_at IS NOT NULL` → restore, return {status: "restored"}
- Otherwise → new insert

## Authentication & Security

### Bootstrap Flow

1. On first startup, check if `users` table is empty
2. If empty:
   - Generate random 32-byte hex bootstrap token (or use `BOOTSTRAP_TOKEN` from env)
   - Log token to stdout
   - Bind to `127.0.0.1` only
   - Redirect all routes to `/setup`
3. `/setup` requires token in URL query
4. After admin creation:
   - Write `var/bootstrap_done` sentinel
   - Invalidate token
   - Restart normal operation (bind to configured HOST)

### Sessions & CSRF

- **Sessions**: Signed with `itsdangerous.URLSafeTimedSerializer` using `APP_SECRET`
- **Cookie**: `HttpOnly`, `SameSite=Lax`, `Secure` when `X-Forwarded-Proto: https`
- **CSRF**: Token generated per session, stored in-memory dict `{session_token: csrf_token}`
- **Write endpoints**: Require `X-CSRF-Token` header matching session's token

### Security Headers

- CSP: `default-src 'self'; img-src 'self' data: blob:; ...`
- X-Content-Type-Options: `nosniff`
- X-Frame-Options: `DENY`
- X-XSS-Protection: `1; mode=block`

## Background Jobs

Powered by `APScheduler` (BackgroundScheduler):

### Daily Reconciliation (2 AM UTC)

For each library:
1. Scan `files/` for orphaned blobs (on disk but not in DB)
2. Check DB for missing blobs (in DB but not on disk)
3. Verify random sample of SHA-256 hashes (integrity check)
4. Detect orphaned `file_tags` (shouldn't happen with FK constraints)
5. Write report to `var/reconcile_{slug}_{date}.log`

### WAL Checkpoint (3 AM UTC)

For each library:
- Run `PRAGMA wal_checkpoint(TRUNCATE);`
- Prevents WAL file from growing indefinitely

## EXIF & Timezone Handling

1. Read `library.json` for `"tz": "America/Los_Angeles"` (fallback: `DEFAULT_TZ` from env)
2. If image, run `exiftool -DateTimeOriginal -json <file>`
3. Parse EXIF date as **naive datetime** (no timezone info in EXIF)
4. Localize to library TZ: `dt_naive.replace(tzinfo=ZoneInfo(library_tz))`
5. Convert to UTC: `dt_local.astimezone(ZoneInfo("UTC"))`
6. Store UTC ISO string in `files.captured_at`
7. Store raw EXIF string in `attributes(file_id, 'captured_at_raw', value)`

**Recompute**: If library TZ changes, a migration job can reprocess raw EXIF strings with new TZ.

## Media Serving

### Thumbnails

- `GET /media/{slug}/thumbs/img/{sha256}.jpg`
- Headers: `ETag: "<sha256>"`, `Cache-Control: public, max-age=31536000, immutable`
- Rationale: Thumbnails never change (content-addressed), safe to cache forever

### Original Files

- `GET /media/{slug}/file/{sha256}`
- Supports HTTP Range requests for video streaming
- Content-Disposition uses `original_name` from DB

## Scalability Considerations

### SQLite Limits

- **Concurrent writes**: SQLite WAL mode allows 1 writer + multiple readers
- **File count**: Tested with 100K+ files per library
- **Database size**: Typical 10KB/file → 1GB for 100K files

### If You Outgrow SQLite

Replace `LibraryDB` with PostgreSQL/MySQL adapter. Schema is simple, migration is straightforward.

### If You Need Distributed Storage

Replace `storage.py` functions with S3/MinIO client. Content addressing remains the same.

## Testing Strategy

### Unit Tests

- `test_storage.py`: shard_path, compute_sha256, atomic_move
- `test_ingest.py`: upload flow, duplicate handling, rollback
- `test_auth.py`: bcrypt, session signing, CSRF

### Integration Tests

- `test_api.py`: Full request/response cycle for all endpoints
- `test_library_lifecycle.py`: Create library → upload → tag → trash → restore

### Acceptance Tests

See `tests/acceptance.sh` (or Python equivalent):
1. Create three libraries (photos, docs, music)
2. Upload 10 photos, verify deduplication
3. Create tags, add to files, query by tag
4. Delete file → check trash, restore → check main
5. Remove library folder, restart, verify registry marks it missing

## Deployment Checklist

- [ ] Change `APP_SECRET` to strong random value
- [ ] Set `DEFAULT_TZ` to your local timezone
- [ ] Choose Docker target (`:slim` or `:full`)
- [ ] Set up reverse proxy (nginx/Caddy) for TLS
- [ ] Configure firewall (allow 8080 only from trusted IPs)
- [ ] Test backup/restore procedure
- [ ] Enable monitoring (check `/api/health`)
- [ ] Review logs (`docker-compose logs -f app`)

## Extension Points

### Adding a New Library Type

1. Update `ALLOWED_MIMES` in `app/utils/mime.py`
2. Add ingest logic in `app/services/ingest.py`
3. Create new browse template (e.g., `browse_ebooks.html`)
4. Register route in `app/main.py`

### Adding External Storage

1. Implement `StorageAdapter` interface (get_file_path, atomic_move, etc.)
2. Inject adapter into `IngestService` and `MediaRouter`
3. Update `library.json` with `"storage": "s3"` flag

### Adding Multi-User Support

1. Add `library_permissions` table (user_id, library_id, role)
2. Update auth middleware to check permissions
3. Add library sharing UI

## Performance Tips

- Enable SQLite query planner: `PRAGMA optimize;` on startup
- Use prepared statements (already done via SQLite3 API)
- Monitor WAL file size (checkpoint if >100MB)
- Paginate aggressively (current: 100/page)
- Lazy-load thumbnails (use `loading="lazy"` in img tags)

## Known Issues

- Thumbnail generation blocks upload response (should be async)
- In-memory CSRF token store doesn't survive restarts (use DB or signed tokens)
- No rate limiting on upload endpoint (add nginx limit_req)
- No virus scanning (integrate ClamAV if needed)

