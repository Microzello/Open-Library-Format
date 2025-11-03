"""FastAPI application entry point."""
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.auth import AuthManager, get_current_user
from app.db.registry_db import RegistryDB
from app.services.scheduler import SchedulerService
from app.routes import libraries, files, tags, media, health, setup

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown."""
    # Startup
    logger.info("Starting Portable Library Manager")
    
    # Initialize registry DB
    registry_db = RegistryDB()
    app.state.registry_db = registry_db
    secret = os.getenv("APP_SECRET", "change_me")
    if secret == "change_me":
        logger.warning("Using default APP_SECRET - change this in production!")
    
    auth_manager = AuthManager(secret)
    app.state.auth_manager = auth_manager
    
    # CSRF token store (in-memory for MVP)
    app.state.csrf_tokens = {}
    
    # Check if bootstrap needed
    bootstrap_sentinel = Path("/app/var/bootstrap_done")
    bootstrap_sentinel.parent.mkdir(parents=True, exist_ok=True)
    app.state.bootstrap_needed = not bootstrap_sentinel.exists() and not registry_db.has_any_users()
    
    if app.state.bootstrap_needed:
        # Bootstrap mode
        bootstrap_token = os.getenv("BOOTSTRAP_TOKEN") or auth_manager.generate_bootstrap_token()
        app.state.bootstrap_token = bootstrap_token
        logger.warning(f"Bootstrap mode active. Token: {bootstrap_token}")
        logger.warning(f"Visit http://127.0.0.1:{os.getenv('PORT', '8080')}/setup?token={bootstrap_token}")
        
        # Check for env-based bootstrap
        if os.getenv("BOOTSTRAP_MODE") == "env":
            admin_user = os.getenv("ADMIN_USERNAME")
            admin_pass_hash = os.getenv("ADMIN_PASSWORD_BCRYPT")
            
            if admin_user and admin_pass_hash:
                logger.info("Creating admin user from environment")
                registry_db.create_user(admin_user, admin_pass_hash, role="admin")
                bootstrap_sentinel.touch()
                app.state.bootstrap_needed = False
    else:
        app.state.bootstrap_token = None
    
    # Scan for libraries
    libraries_root = os.getenv("LIBRARIES_ROOT", "/data/libraries")
    discovered = registry_db.scan_libraries_root(libraries_root)
    if discovered:
        logger.info(f"Discovered {len(discovered)} libraries")
    
    # Start background scheduler (only if bootstrapped)
    if not app.state.bootstrap_needed:
        scheduler = SchedulerService(registry_db)
        scheduler.start()
        app.state.scheduler = scheduler
    else:
        app.state.scheduler = None
    
    yield
    
    # Shutdown
    logger.info("Shutting down")
    if app.state.scheduler:
        app.state.scheduler.shutdown()


# Create app
app = FastAPI(
    title="Portable Library Manager",
    description="Self-hosted file library manager with content-addressed storage",
    version="0.1.0",
    lifespan=lifespan,
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # CSP
    csp = os.getenv(
        "CONTENT_SECURITY_POLICY",
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com"
    )
    response.headers["Content-Security-Policy"] = csp
    
    # Other security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    return response


# Bootstrap redirect middleware
@app.middleware("http")
async def bootstrap_redirect(request: Request, call_next):
    if app.state.bootstrap_needed:
        # Allow only setup and static routes
        if request.url.path.startswith("/api/setup") or request.url.path.startswith("/static") or request.url.path.startswith("/api/health"):
            return await call_next(request)
        elif request.url.path == "/setup":
            return await call_next(request)
        else:
            # Redirect to setup
            return RedirectResponse(url="/setup", status_code=302)
    
    return await call_next(request)


# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(health.router)
app.include_router(setup.router)
app.include_router(libraries.router)
app.include_router(files.router)
app.include_router(tags.router)
app.include_router(media.router)


# UI routes
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Home page - redirect to libraries or login."""
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/libraries")
    else:
        return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Login page."""
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/libraries")
    
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, token: str = ""):
    """Bootstrap setup wizard."""
    if not app.state.bootstrap_needed:
        return RedirectResponse(url="/libraries")
    
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "token": token,
        "expected_token": app.state.bootstrap_token,
    })


@app.get("/libraries", response_class=HTMLResponse)
def libraries_page(request: Request):
    """Libraries list page."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    
    # Get CSRF token
    auth_manager = app.state.auth_manager
    session_token = request.cookies.get(auth_manager.session_cookie_name)
    if not session_token:
        csrf_token = None
    else:
        csrf_token = app.state.csrf_tokens.get(session_token)
        if not csrf_token:
            csrf_token = auth_manager.generate_csrf_token()
            app.state.csrf_tokens[session_token] = csrf_token
    
    return templates.TemplateResponse("libraries.html", {
        "request": request,
        "user": user,
        "csrf_token": csrf_token,
    })


@app.get("/libraries/{library_id}/browse", response_class=HTMLResponse)
def browse_library(request: Request, library_id: str):
    """Browse library files."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    
    # Get library
    registry = app.state.registry_db
    lib = registry.get_library_by_id(library_id)
    
    if not lib:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Library not found"
        }, status_code=404)
    
    # Get CSRF token
    auth_manager = app.state.auth_manager
    session_token = request.cookies.get(auth_manager.session_cookie_name)
    if not session_token:
        csrf_token = None
    else:
        csrf_token = app.state.csrf_tokens.get(session_token)
        if not csrf_token:
            csrf_token = auth_manager.generate_csrf_token()
            app.state.csrf_tokens[session_token] = csrf_token
    
    # Choose template based on library type
    if lib["type"] == "photo_video":
        template = "browse_photos.html"
    elif lib["type"] == "documents":
        template = "browse_docs.html"
    elif lib["type"] == "music":
        template = "browse_music.html"
    else:
        template = "browse_photos.html"
    
    return templates.TemplateResponse(template, {
        "request": request,
        "user": user,
        "library": lib,
        "csrf_token": csrf_token,
    })


@app.get("/libraries/{library_id}/tags", response_class=HTMLResponse)
def tags_page(request: Request, library_id: str):
    """Tags management page."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    
    # Get library
    registry = app.state.registry_db
    lib = registry.get_library_by_id(library_id)
    
    if not lib:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Library not found"
        }, status_code=404)
    
    # Get CSRF token
    auth_manager = app.state.auth_manager
    session_token = request.cookies.get(auth_manager.session_cookie_name)
    if not session_token:
        csrf_token = None
    else:
        csrf_token = app.state.csrf_tokens.get(session_token)
        if not csrf_token:
            csrf_token = auth_manager.generate_csrf_token()
            app.state.csrf_tokens[session_token] = csrf_token
    
    return templates.TemplateResponse("tags.html", {
        "request": request,
        "user": user,
        "library": lib,
        "csrf_token": csrf_token,
    })


@app.get("/libraries/{library_id}/trash", response_class=HTMLResponse)
def trash_page(request: Request, library_id: str):
    """Trash view."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    
    # Get library
    registry = app.state.registry_db
    lib = registry.get_library_by_id(library_id)
    
    if not lib:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Library not found"
        }, status_code=404)
    
    # Get CSRF token
    auth_manager = app.state.auth_manager
    session_token = request.cookies.get(auth_manager.session_cookie_name)
    if not session_token:
        csrf_token = None
    else:
        csrf_token = app.state.csrf_tokens.get(session_token)
        if not csrf_token:
            csrf_token = auth_manager.generate_csrf_token()
            app.state.csrf_tokens[session_token] = csrf_token
    
    # Check if purge is allowed
    allow_purge = os.getenv("ALLOW_PURGE", "false").lower() == "true"
    
    return templates.TemplateResponse("trash.html", {
        "request": request,
        "user": user,
        "library": lib,
        "csrf_token": csrf_token,
        "allow_purge": allow_purge,
    })


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    workers = int(os.getenv("WORKERS", "1"))
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=workers,
        reload=False,
    )

