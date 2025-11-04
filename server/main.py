from __future__ import annotations

from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_config
from .routes.libraries import router as libraries_router
from .routes.media import router as media_router
from .routes.thumbnails import router as thumbs_router
from .routes.tags import router as tags_router
from .routes.stream import router as stream_router


def create_app() -> FastAPI:
    cfg = get_config()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    app = FastAPI(title="Portable Media Library", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Healthcheck
    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "libraries_root": str(cfg.libraries_root.resolve()),
        })

    # Quiet favicon
    @app.get("/favicon.ico")
    def favicon() -> JSONResponse:
        return JSONResponse({}, status_code=204)

    # API routers
    app.include_router(libraries_router)
    app.include_router(media_router)
    app.include_router(thumbs_router)
    app.include_router(tags_router)
    app.include_router(stream_router)

    # Serve basic web UI if present
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app


app = create_app()


