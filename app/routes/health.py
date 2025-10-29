"""Health and setup endpoints."""
from fastapi import APIRouter, Request, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path

from app.models import HealthResponse, LoginRequest, SetupRequest
from app.utils.features import get_features
from app.auth import get_current_user

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health_check(request: Request):
    """Health check endpoint with feature detection."""
    features = get_features()
    
    # Include library schema versions if user is authenticated
    user = get_current_user(request)
    libraries_info = None
    
    if user:
        registry = request.app.state.registry_db
        libraries = registry.list_libraries()
        
        libraries_info = []
        for lib in libraries:
            lib_path = Path(lib["path"])
            if lib_path.exists():
                try:
                    from app.db.library_db import LibraryDB
                    lib_db = LibraryDB(str(lib_path))
                    schema_version = lib_db.get_schema_version()
                    libraries_info.append({
                        "id": lib["id"],
                        "slug": lib["slug"],
                        "schema_version": schema_version,
                    })
                except:
                    pass
    
    return {
        "status": "ok",
        "features": features,
        "libraries": libraries_info,
    }


@router.post("/api/login")
def login(request: Request, response: Response, data: LoginRequest):
    """Login endpoint."""
    registry = request.app.state.registry_db
    auth_manager = request.app.state.auth_manager
    
    # Get user
    user = registry.get_user_by_username(data.username)
    if not user or not auth_manager.verify_password(data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "Invalid username or password"
                }
            }
        )
    
    # Create session
    session_token = auth_manager.create_session(user["id"], user["username"])
    
    # Set cookie
    response.set_cookie(
        key=auth_manager.session_cookie_name,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=request.headers.get("X-Forwarded-Proto") == "https",
        max_age=86400 * 7,  # 7 days
    )
    
    # Generate CSRF token
    csrf_token = auth_manager.generate_csrf_token()
    request.app.state.csrf_tokens[session_token] = csrf_token
    
    # Update last login
    registry.update_last_login(user["id"])
    
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
        },
        "csrf_token": csrf_token,
    }


@router.post("/api/logout")
def logout(request: Request, response: Response):
    """Logout endpoint."""
    auth_manager = request.app.state.auth_manager
    session_token = request.cookies.get(auth_manager.session_cookie_name)
    
    # Remove CSRF token
    if session_token and session_token in request.app.state.csrf_tokens:
        del request.app.state.csrf_tokens[session_token]
    
    # Clear cookie
    response.delete_cookie(auth_manager.session_cookie_name)
    
    return {"status": "logged_out"}


@router.get("/api/me")
def get_current_user_info(request: Request):
    """Get current user info."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    
    return {"user": user}

