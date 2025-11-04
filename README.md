Portable Media Library (FastAPI + SQLite)
=========================================

What is this?
- A local, portable photo/video library with per-library SQLite, on-demand video proxies, thumbnails, tags, and a simple web UI.

Requirements
- Python 3.10+
- ffmpeg/ffprobe installed and on PATH (or set FFMPEG_PATH/FFPROBE_PATH)

Install
```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install fastapi uvicorn[standard] pillow exifread python-dotenv
```

Configure
- Create a `.env` file next to this README with:
```
LIBRARIES_ROOT=C:\\Users\\<you>\\MediaLibraries
FFMPEG_PATH=ffmpeg
FFPROBE_PATH=ffprobe
THUMB_SIZE=512
HOST=127.0.0.1
PORT=8000
```

Run
```bash
uvicorn server.main:app --reload --host %HOST% --port %PORT%
```
Then open `http://127.0.0.1:8000/`.

Notes
- Libraries are stored under `LIBRARIES_ROOT`, each as a folder with `library.json` and `db/library.sqlite`.
- Upload goes to `media/raw/<aa>/<uuid>.<ext>`; thumbnails and proxies are cached under `media/`.
- Downloads preserve original filenames.

