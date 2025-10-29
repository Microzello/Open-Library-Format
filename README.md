# Portable Library Manager

A self-hosted, Dockerized file library manager with content-addressed storage, SQLite metadata, and browser-based UI.

## What is this?

A portable, self-contained system for managing collections of files (photos/videos, documents, music). Each library is a standalone folder on disk that can be copied between machines without breaking. No external databases, no cloud dependencies—just files, SQLite, and a clean web interface.

## Features

- **Content-addressed storage**: Files are deduplicated by SHA-256 hash
- **Portable libraries**: Each library is self-contained with its own SQLite database
- **No permanent deletion**: Files move to trash, not destroyed (purge disabled by default)
- **Tags & collections**: Organize files with tags (including favorites)
- **Full-text search**: FTS5-powered search for documents
- **EXIF timezone handling**: Parse and normalize photo timestamps with per-library timezone
- **Thumbnails & previews**: Auto-generate thumbnails for images and video posters
- **Multi-format support**:
  - **photo_video**: JPEG, PNG, WebP, HEIC, MP4, MOV, MKV, WebM
  - **documents**: Any file type (with FTS search)
  - **music**: MP3, FLAC, WAV, M4A, OGG
- **Background jobs**: Daily reconciliation, WAL checkpointing
- **Docker-ready**: Two variants (slim/full), single-command deploy

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url>
cd Open-Library-Format

# Copy environment template
cp .env.example .env

# Edit .env - MUST change APP_SECRET for production!
nano .env
```

### 2. Run with Docker Compose

```bash
docker-compose up -d
```

### 3. Bootstrap setup

1. Check logs for bootstrap token:
   ```bash
   docker-compose logs app | grep "Token:"
   ```

2. Visit `http://localhost:8080/setup?token=<YOUR_TOKEN>`

3. Create your admin account

4. Start creating libraries and uploading files!

## Configuration (.env)

### Required

```bash
APP_SECRET=change_me_to_a_random_string  # CRITICAL: Change this!
LIBRARIES_ROOT=/data/libraries           # Where library folders live
```

### Optional

```bash
# Server
HOST=0.0.0.0
PORT=8080
WORKERS=1  # Keep at 1 for scheduler

# Bootstrap
BOOTSTRAP_MODE=wizard  # or 'env' for headless
BOOTSTRAP_TOKEN=       # Auto-generated if empty
ADMIN_USERNAME=        # Only for BOOTSTRAP_MODE=env
ADMIN_PASSWORD_BCRYPT= # Bcrypt hash only

# Timezone
DEFAULT_TZ=UTC  # Default for libraries (e.g., America/Los_Angeles)

# Features (auto-detected)
ENABLE_FFMPEG=auto   # auto|true|false
ENABLE_EXIFTOOL=auto

# Safety
ALLOW_PURGE=false  # NEVER set true unless you really mean it

# Security
CONTENT_SECURITY_POLICY="default-src 'self'; img-src 'self' data: blob:; ..."
```

## Docker Images

Two build targets:

- **`:slim`** (default): Python + Pillow + mutagen (~200MB)
- **`:full`**: Adds ffmpeg, exiftool, poppler (~400MB)

Switch to slim:
```bash
docker-compose -f docker-compose.yml -f compose.slim.yml up -d
```

## Library Types

| Type | Allowed Files | Default Sort | Features |
|------|--------------|--------------|----------|
| `photo_video` | Images, videos | `captured_at` DESC | EXIF parsing, thumbnails |
| `documents` | All files | `added_at` DESC | Full-text search (FTS5) |
| `music` | Audio files | `added_at` DESC | Tag parsing (mutagen) |

## Storage Layout

```
LIBRARIES_ROOT/
  my-photos/
    library.json      # Manifest (id, name, type, schema_version, tz)
    index.db          # SQLite database (WAL mode)
    files/            # Content-addressed blobs: aa/bb/<sha256>
    thumbs/           # Thumbnails: img|vid/aa/bb/<sha256>.jpg
    trash/            # Soft-deleted files
    locks/            # Advisory locks
```

## CLI Commands

Create a user manually (bypass wizard):
```bash
docker exec app python -m app.cli create-user --admin <username> <password>
```

## API Endpoints

### Libraries
- `GET /api/libraries` - List all
- `POST /api/libraries` - Create `{name, type, slug?, tz?}`
- `GET /api/libraries/{id}` - Get details
- `DELETE /api/libraries/{id}` - Remove from registry (folder stays)

### Files
- `GET /api/libraries/{id}/files?tag=&q=&page=&sort=` - List/search
- `POST /api/libraries/{id}/files` - Upload (multipart)
- `GET /api/libraries/{id}/files/{file_id}` - Details
- `GET /api/libraries/{id}/files/{file_id}/download` - Download
- `DELETE /api/libraries/{id}/files/{file_id}` - Move to trash
- `POST /api/libraries/{id}/files/{file_id}/restore` - Restore
- `PATCH /api/libraries/{id}/files/{file_id}` - Update metadata

### Tags
- `GET /api/libraries/{id}/tags` - List with counts
- `POST /api/libraries/{id}/tags` - Create `{name}`
- `POST /api/libraries/{id}/files/{file_id}/tags` - Add `{tag_id}`
- `DELETE /api/libraries/{id}/files/{file_id}/tags/{tag_id}` - Remove

### Media
- `GET /media/{slug}/file/{sha256}` - Serve original (with range support)
- `GET /media/{slug}/thumbs/{kind}/{sha256}.jpg` - Serve thumbnail

## Constraints & Known Limitations

- **Single-user MVP**: One admin account per instance
- **No external sync**: WebDAV/S3 not implemented
- **No collaboration**: No shared editing or multi-user access
- **SQLite concurrency**: Suitable for personal use; write-heavy loads may need tuning
- **Purge disabled by default**: `ALLOW_PURGE=false` enforces no-permanent-delete rule

## Backup & Portability

### Backup a library
```bash
cp -r libraries/my-photos /backup/my-photos-$(date +%Y%m%d)
```

### Move to another machine
```bash
# On machine A
tar -czf my-photos.tar.gz libraries/my-photos

# On machine B
tar -xzf my-photos.tar.gz -C /data/libraries/
# Restart app to auto-discover
```

## Development

### Run locally (without Docker)
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export APP_SECRET=dev
export LIBRARIES_ROOT=./libraries
python -m app.main
```

Visit `http://127.0.0.1:8080`

## License

See [LICENSE](LICENSE) file.

## Security Notes

- Change `APP_SECRET` before production
- Run behind a reverse proxy (nginx/Caddy) for TLS
- Bind to `127.0.0.1` if local-only; use firewall for remote access
- Bootstrap token is one-time use and invalidated after setup
- CSRF protection on all write endpoints
- Session cookies are HttpOnly and SameSite=Lax

## Troubleshooting

**Library not discovered after copying?**
- Check `library.json` exists and is valid JSON
- Restart app to trigger library scan

**Thumbnails not generating?**
- Check logs: `docker-compose logs app`
- Verify ffmpeg/exiftool if using `:full` image

**WAL file growing too large?**
- Background checkpoint runs nightly at 3 AM UTC
- Manual: `docker exec app sqlite3 /data/libraries/<slug>/index.db "PRAGMA wal_checkpoint(TRUNCATE);"`

**Upload fails with "Invalid file type"?**
- MIME type must match library type (sniffed, not extension-based)
- Check allowed types in docs above

