"""Authentication and session management."""
import secrets
import bcrypt
from typing import Optional
from fastapi import Request, HTTPException, status
from itsdangerous import URLSafeTimedSerializer, BadSignature


class AuthManager:
    """Manages sessions and CSRF tokens."""

    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.serializer = URLSafeTimedSerializer(secret_key)
        self.session_cookie_name = "session"
        self.csrf_header_name = "X-CSRF-Token"

    def hash_password(self, password: str) -> str:
        """Hash a password with bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against a hash."""
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    def create_session(self, user_id: int, username: str) -> str:
        """Create a signed session token."""
        data = {"user_id": user_id, "username": username}
        return self.serializer.dumps(data)

    def verify_session(self, token: str, max_age: int = 86400 * 7) -> Optional[dict]:
        """
        Verify a session token.
        Returns user data if valid, None otherwise.
        Default max_age: 7 days
        """
        try:
            data = self.serializer.loads(token, max_age=max_age)
            return data
        except BadSignature:
            return None

    def generate_csrf_token(self) -> str:
        """Generate a CSRF token."""
        return secrets.token_urlsafe(32)

    def generate_bootstrap_token(self) -> str:
        """Generate a bootstrap token for first-time setup."""
        return secrets.token_hex(32)


def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from session cookie."""
    auth_manager = request.app.state.auth_manager
    session_token = request.cookies.get(auth_manager.session_cookie_name)
    
    if not session_token:
        return None
    
    user_data = auth_manager.verify_session(session_token)
    return user_data


def require_auth(request: Request) -> dict:
    """Require authentication, raise 401 if not logged in."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user


def verify_csrf(request: Request) -> None:
    """Verify CSRF token on write operations."""
    auth_manager = request.app.state.auth_manager
    
    # Get token from header
    token = request.headers.get(auth_manager.csrf_header_name)
    
    # Get expected token from session
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    # For now, we'll generate CSRF per-session and store in app state
    # A more robust approach would use signed tokens or database storage
    session_token = request.cookies.get(auth_manager.session_cookie_name)
    expected_token = request.app.state.csrf_tokens.get(session_token)
    
    if not token or token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed"
        )

