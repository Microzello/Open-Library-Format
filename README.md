# Open Library Format

Open Library Format is a self-hosted photo and document library designed to live on a local network.  
Each library is a portable folder that contains its SQLite database, manifest, media files, and generated thumbnails.  
The web UI runs entirely in the browser, while a Python FastAPI backend handles ingest, metadata extraction, and file serving.

## Features
- 📁 **Portable libraries** — every library is stored in its own folder with a `library.json` manifest and SQLite database.
- 🖼️ **Optimised storage** — media files are renamed to UUIDv4 values and sharded into 256 sub-folders for fast lookup.
- 🧭 **Metadata extraction** — images automatically capture EXIF camera and GPS information; taken/imported timestamps use Unix epoch seconds.
- 🏷️ **Tag management** — create, apply, and filter by tags from both the gallery view and item detail modal.
- 🔍 **Filtering & search** — browse by filename search, multiple tags, taken-date range, and different sort orders.
- 🗑️ **Bulk actions** — delete or download multiple items in one click; downloads preserve the original filenames inside a ZIP archive.
- 🎞️ **Responsive UI** — lightweight HTML/CSS/JS interface with a detail modal for previews, metadata, and tag editing.

## Requirements
- Python 3.10 or later
- [Pillow](https://python-pillow.org/) for image metadata/thumbnail generation (installed via requirements below)
- Optional but recommended: [`python-dotenv`](https://github.com/theskumar/python-dotenv) so `.env` files are loaded automatically

## Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install fastapi uvicorn[standard] pillow python-multipart python-dotenv
```

## Configuration
Create a `.env` file at the project root (or export environment variables) with at least:
```ini
OLF_LIBRARY_ROOT=./libraries
OLF_THUMBNAIL_SIZE=320  # optional, defaults to 320px on the longest side
```
The root folder will be created automatically if it does not exist.

## Running the server
```bash
uvicorn server.api:create_app --reload
```
Then open `http://127.0.0.1:8000/` to access the web UI served from the `/web` directory.

## Publishing your code to GitHub
This repository only exists on your machine until you push it to GitHub (or another remote).
To publish it:

```bash
git init              # if you have not already initialised a repo
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

Replace `<username>/<repo>` with your own GitHub account and repository name. After the push
completes you will see the code on GitHub.

## Project layout
```
server/
  api.py              # FastAPI application and routes
  config.py           # Environment-driven settings
  ingest.py           # Upload pipeline, EXIF parsing, thumbnails
  library_manager.py  # Library discovery and manifest helpers
  repository.py       # SQLite queries for media and tags
  storage.py          # Database initialisation and folder helpers
web/
  index.html          # Single-page interface
  styles.css          # UI styling
  app.js              # Front-end logic
```

## Library structure
Each library folder contains:
```
<library_id>/
  library.json        # Manifest (id, name, created_at)
  media.db            # SQLite database with media + tag tables
  media/
    raw/aa/<uuid>.<ext>         # Original uploads, sharded by first byte of UUID
    thumbnails/aa/<uuid>.jpg    # Generated thumbnails for photos
    proxies/                   # Reserved for future video proxy support
```

Original filenames are preserved in the database so downloads and UI labels always show the name the user uploaded.

## API overview
Key endpoints exposed by the backend:
- `GET /api/libraries` — list existing libraries
- `POST /api/libraries` — create a new library
- `GET /api/libraries/{id}/media` — list/filter media items
- `POST /api/libraries/{id}/media` — upload one or more files
- `GET /api/libraries/{id}/media/{media_id}` — fetch metadata for a single item
- `POST /api/libraries/{id}/media/{media_id}/tags` — replace tags for an item
- `POST /api/libraries/{id}/media/delete` — bulk delete
- `POST /api/libraries/{id}/download` — download selected media as a ZIP
- `GET /api/libraries/{id}/media/{media_id}/thumbnail|content` — fetch previews or original files

These endpoints are consumed by the static front-end but can also be scripted directly for automation.

## Development tips
- The application stores timestamps in Unix epoch seconds; convert to/from local time zones on the client as needed.
- Because libraries are self-contained, you can back up or move them by copying the folder referenced in the manifest.
- When testing uploads, remember that large images will take a moment to thumbnail on first ingest.
