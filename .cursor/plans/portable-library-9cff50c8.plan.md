<!-- 9cff50c8-d7b4-4d2d-8ef7-9e7850d0e791 5abc8817-7117-4609-8d09-a60d861cf79b -->
# Portable Library Manager - MVP Implementation Plan

## Phase 1: Foundation & Bootstrap System

### Docker & Environment Setup

- Create `Dockerfile` with multi-stage build for `:slim` and `:full` variants
- `:slim`: Python 3.11-slim + Pillow + mutagen + libmagic
- `:full`: adds ffmpeg, exiftool, poppler-utils
- Create `docker-compose.yml` (uses `:full`) and `compose.slim.yml` override
- Create `.env.example` with all config keys from spec (APP_SECRET, LIBRARIES_ROOT, BOOTSTRAP_MODE, DEFAULT_TZ, etc.)
- Create `.gitignore` for Python, Docker, SQLite, and runtime artifacts

### Bootstrap & Authentication System

- `app/auth.py`: bcrypt password hashing, session cookie management, CSRF token generation
- `app/cli.py`: `create-user --admin <username> <password>` command
- Bootstrap flow in `app/main.py`:
- Check `registry.db` for users; if empty, enter bootstrap mode
- Generate/use BOOTSTRAP_TOKEN, bind to 127.0.0.1
- Create `/setup` route (wizard UI) requiring token
- Write `var/bootstrap_done` sentinel after first admin created
- Middleware: redirect to `/setup` if no admin exists and route != `/setup`

### Database Schema & Helpers

- `app/db/schema_registry.sql`: users table + libraries table
- `app/db/schema_library.sql`: files, tags, file_tags, attributes, file_fts (FTS5)
- `app/db/registry_db.py`: init registry, scan LIBRARIES_ROOT for library.json, CRUD for users/libraries
- `app/db/library_db.py`: per-library connection pool, WAL mode setup, CRUD for files/tags/attributes
- Add indexes per spec (captured_at DESC, deleted_at, file_tags tag_id)

## Phase 2: Storage & Ingest Pipeline

### Content-Addressed Storage

- `app/storage.py`:
- `compute_sha256(filepath)` → hex digest
- `shard_path(sha256)` → `aa/bb/<sha256>` (two-level fan-out)
- `atomic_move(src, dest)` → safe rename with parent mkdir
- `trash_file(lib_path, sha256)` → move to trash/, mark deleted_at
- `restore_file(lib_path, sha256)` → move back to files/, clear deleted_at

### Feature Detection & Media Utilities

- `app/utils/features.py`: detect ffmpeg, exiftool, poppler at runtime; return capability dict
- `app/utils/exif.py`: parse EXIF DateTimeOriginal with library/default TZ, return UTC + raw string
- `app/utils/mime.py`: sniff MIME using python-magic (libmagic)

### Ingest Service

- `app/services/ingest.py`:
- `ingest_file(library_id, upload: UploadFile)`:

1. Save to temp
2. Compute sha256, size, MIME, read EXIF if image
3. Check duplicate by sha256 in DB (dedupe policy: skip if exists)
4. Atomic move to `files/aa/bb/<sha256>`
5. Insert row in transaction (files + attributes for EXIF raw)
6. Queue thumbnail job
7. Return file record

- Handle rollback on failure (clean temp, no partial DB writes)

### Thumbnail Generator

- `app/services/thumbnails.py`:
- `generate_image_thumb(sha256, lib_path)` → Pillow resize to 512px, save to `thumbs/img/aa/bb/<sha256>.jpg`
- `generate_video_poster(sha256, lib_path)` → ffmpeg extract first frame if available
- Background task queue (APScheduler) processes on ingest
- Idempotent: skip if thumb exists

## Phase 3: REST API

### Library Endpoints

- `app/routes/libraries.py`:
- `GET /api/libraries` → list from registry
- `POST /api/libraries {name, type, slug?}` → create folder structure, library.json, init index.db
- `GET /api/libraries/{id}` → details + stats (file count, tag count, trash count)
- `DELETE /api/libraries/{id}` → soft-remove from registry (folder stays on disk)

### File Endpoints

- `app/routes/files.py`:
- `GET /api/libraries/{id}/files?tag=&q=&page=&sort=` → paginated list (default 100/page), filter by tag/search, sort by captured_at desc
- `POST /api/libraries/{id}/files` → multipart upload, call ingest service
- `GET /api/libraries/{id}/files/{file_id}` → single file detail
- `GET /api/libraries/{id}/files/{file_id}/download` → stream original blob
- `DELETE /api/libraries/{id}/files/{file_id}` → move to trash
- `POST /api/libraries/{id}/files/{file_id}/restore` → restore from trash
- `PATCH /api/libraries/{id}/files/{file_id} {notes, attributes}` → update metadata

### Tag Endpoints

- `app/routes/tags.py`:
- `GET /api/libraries/{id}/tags` → list all tags with counts
- `POST /api/libraries/{id}/tags {name}` → create tag
- `POST /api/libraries/{id}/files/{file_id}/tags {tag_id}` → add tag to file
- `DELETE /api/libraries/{id}/files/{file_id}/tags/{tag_id}` → remove tag from file

### Media Serving

- `app/routes/media.py`:
- `GET /media/{library_slug}/file/{sha256}` → serve original (auth check, stream from files/)
- `GET /media/{library_slug}/thumbs/{kind}/{sha256}.jpg` → serve thumbnail (img/vid)
- Set proper Content-Type headers, implement range requests for video streaming

### Health & Setup

- `app/routes/health.py`: `GET /api/health` → status + features dict (ffmpeg, exiftool, fts)
- `app/routes/setup.py`: `GET /setup` + `POST /setup` wizard endpoints (token validation, create admin)

## Phase 4: UI Templates & Frontend

### Base Templates

- `app/templates/base.html`: Jinja2 base with Tailwind CDN, nav bar, CSRF meta tag, toast notifications
- `app/templates/login.html`: username/password form
- `app/templates/setup.html`: bootstrap wizard (username, password, confirm)

### Library Views

- `app/templates/libraries.html`: grid of library cards with stats (files, tags, trash), create library modal
- `app/templates/browse_photos.html`: masonry grid, infinite scroll, tag filter chips, multi-select toolbar, upload button
- `app/templates/browse_docs.html`: table view (title, type, size, modified, tags), search box (FTS), pagination
- `app/templates/browse_music.html`: grouped by album/artist, simple player fallback
- `app/templates/trash.html`: grid/table of deleted files, restore/purge actions (purge gated + confirm modal)

### Static Assets

- `app/static/css/tailwind.css`: compiled Tailwind (or use CDN for MVP)
- `app/static/js/upload.js`: drag-drop upload, FormData, progress bar, append new items to grid
- `app/static/js/grid.js`: multi-select logic, infinite scroll, tag filter state
- `app/static/js/modal.js`: detail drawer (preview, metadata editor, tags selector, download button)

### Vanilla JS Patterns

- Use `fetch()` for all API calls
- DOM manipulation for dynamic updates (append thumbs, update counts, remove from grid)
- Event delegation for multi-select checkboxes
- CSRF token from meta tag injected into POST/DELETE headers

## Phase 5: Background Jobs & Reconciliation

### Job Scheduler

- `app/services/scheduler.py`: APScheduler setup with in-memory store (MVP)
- Thumbnail queue: process pending thumbs on startup + new uploads
- Daily reconciler: verify DB ↔ disk consistency

### Reconciler

- `app/services/reconcilers.py`:
- `reconcile_library(library_id)`:
- Scan files/ for orphaned blobs (not in DB) → log warnings
- Check DB for missing blobs → mark as broken, add to report
- Verify random sample sha256 hashes (integrity check)
- Detect inconsistent file_tags (orphaned tag refs) → cleanup
- Run daily at 2 AM UTC, log results to `var/reconcile_{date}.log`

## Phase 6: Library-Type Specific Features

### Photo/Video Library

- Default sort: `captured_at DESC`
- On ingest: parse EXIF DateTimeOriginal with library TZ (or DEFAULT_TZ), store UTC in captured_at + raw in attributes
- Generate image thumb (Pillow) + video poster (ffmpeg if available)
- Grid UI: lazy-load thumbs, lightbox for preview

### Documents Library

- Enable FTS5 on title + notes (populate from original_name stem + user notes)
- Search endpoint uses MATCH query on file_fts
- Table view with sortable columns (name, size, modified)
- Optional: PDF text extraction (pdftotext) as background job if poppler-utils available

### Music Library

- Parse ID3/metadata with mutagen: title, artist, album, year → store in attributes
- Group by album in UI, show album art if embedded
- Basic HTML5 audio player for preview (browser-native)

## Phase 7: Testing & Polish

### Acceptance Tests

- Script: `tests/acceptance.sh` (or Python pytest with requests)

1. Create three libraries (photos, docs, music) via API
2. Upload 10 mixed photos, verify deduplication (upload same file twice)
3. Create tags "Favorites", "Vacation", add to files, query by tag
4. Delete file → verify in trash, restore → verify back in main grid
5. Remove library folder from disk, restart, check registry marks missing

### Minimal Unit Tests

- `tests/test_storage.py`: shard_path, sha256, atomic_move
- `tests/test_ingest.py`: upload flow, duplicate handling, rollback on error
- `tests/test_auth.py`: bcrypt hash, session creation, CSRF validation

### Documentation

- `README.md`: 
- What it is (1-2 sentences)
- Quick start (Docker Compose up, access /setup)
- Config (.env keys)
- Library types and constraints
- Storage layout diagram
- Known limitations (single-user MVP, no external sync)
- `ARCHITECTURE.md`: content addressing, SQLite schema, ingest pipeline, background jobs
- `docker-compose.yml` inline comments for key services/volumes

## Implementation Order

1. **Bootstrap & Auth** (setup wizard, CLI, session management)
2. **Storage & DB** (schema init, registry scan, library creation)
3. **Ingest Pipeline** (upload, sha256, atomic move, DB insert)
4. **REST API** (libraries, files, tags endpoints with pagination)
5. **UI Templates** (base, login, libraries list, photo grid)
6. **Thumbnails & Jobs** (Pillow, APScheduler, background queue)
7. **Type-Specific** (EXIF parsing, FTS for docs, music tags)
8. **Testing & Docs** (acceptance tests, README)

Each phase builds on previous; can deploy incrementally after Phase 4 for manual testing.

### To-dos

- [ ] Create Dockerfile (multi-stage slim/full), docker-compose.yml, .env.example, .gitignore
- [ ] Implement bootstrap wizard, CLI user creation, session auth, CSRF middleware
- [ ] Create SQL schemas (registry.db + library index.db), init helpers, WAL mode setup
- [ ] Implement content-addressed storage (sha256, shard_path, atomic_move, trash/restore)
- [ ] Build ingest service (upload → temp → hash → move → DB insert → thumbnail queue)
- [ ] Implement library REST endpoints (list, create, get, soft-delete)
- [ ] Implement file REST endpoints (list, upload, download, delete, restore, patch)
- [ ] Implement tag REST endpoints (list, create, add to file, remove from file)
- [ ] Implement media routes (serve original files, serve thumbnails, range requests)
- [ ] Create base Jinja2 templates (base.html, login, setup wizard) with Tailwind
- [ ] Build library list view and create library modal
- [ ] Build browse views (photo grid, docs table, music player) with multi-select and filters
- [ ] Implement drag-drop upload with progress and grid updates
- [ ] Build thumbnail generator (Pillow for images, ffmpeg for video posters)
- [ ] Setup APScheduler, thumbnail queue, daily reconciler
- [ ] Implement EXIF parsing with timezone handling (library TZ override, store UTC + raw)
- [ ] Enable FTS5 for documents, implement search endpoint
- [ ] Parse music tags with mutagen, store in attributes, build album grouping UI
- [ ] Write and run acceptance test suite (create libs, upload, dedupe, tag, trash, restore)
- [ ] Write README.md with quick start, config reference, and ARCHITECTURE.md