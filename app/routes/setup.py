"""Bootstrap setup endpoint."""
from fastapi import APIRouter, Request, HTTPException, status, Response
from pathlib import Path

from app.models import SetupRequest

router = APIRouter(tags=["setup"])


@router.post("/api/setup")
def bootstrap_setup(request: Request, response: Response, data: SetupRequest):
    """Bootstrap wizard - create first admin user."""
    # Check if already bootstrapped
    bootstrap_sentinel = Path("var/bootstrap_done")
    if bootstrap_sentinel.exists():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "ALREADY_BOOTSTRAPPED",
                    "message": "System already initialized"
                }
            }
        )
    
    # Verify token
    expected_token = request.app.state.bootstrap_token
    if data.token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "Invalid bootstrap token"
                }
            }
        )
    
    # Create user
    registry = request.app.state.registry_db
    auth_manager = request.app.state.auth_manager
    
    password_hash = auth_manager.hash_password(data.password)
    user_id = registry.create_user(data.username, password_hash, role="admin")
    
    # Mark bootstrap complete
    bootstrap_sentinel.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_sentinel.touch()
    
    # Update app state
    request.app.state.bootstrap_needed = False
    request.app.state.bootstrap_token = None
    
    # Create session
    session_token = auth_manager.create_session(user_id, data.username)
    
    response.set_cookie(
        key=auth_manager.session_cookie_name,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
    )
    
    # Generate CSRF token
    csrf_token = auth_manager.generate_csrf_token()
    request.app.state.csrf_tokens[session_token] = csrf_token
    
    return {
        "status": "bootstrapped",
        "user": {
            "id": user_id,
            "username": data.username,
        },
        "csrf_token": csrf_token,
    }

