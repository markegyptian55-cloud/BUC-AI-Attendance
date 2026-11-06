"""Password hashing, JWT handling, and role-based authorization."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

try:
    from .config import settings
    from .db import get_db
    from .models import User
    from .schemas import TokenData
except (ImportError, ValueError):
    try:
        from backend.app.config import settings
        from backend.app.db import get_db
        from backend.app.models import User
        from backend.app.schemas import TokenData
    except ModuleNotFoundError:
        from app.config import settings
        from app.db import get_db
        from app.models import User
        from app.schemas import TokenData


try:
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher

    _password_hash = PasswordHash((Argon2Hasher(),))

    def hash_password(password: str) -> str:
        """Hash a password using Argon2id."""
        return _password_hash.hash(password)

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Return whether a plaintext password matches its Argon2id hash."""
        try:
            return _password_hash.verify(plain_password, hashed_password)
        except (ValueError, TypeError):
            return False

except ImportError:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError

    _password_hasher = PasswordHasher()

    def hash_password(password: str) -> str:
        """Hash a password using Argon2id."""
        return _password_hasher.hash(password)

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Return whether a plaintext password matches its Argon2id hash."""
        try:
            return _password_hasher.verify(hashed_password, plain_password)
        except (VerifyMismatchError, InvalidHashError, ValueError, TypeError):
            return False


ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    """Create a signed JWT with UTC issued-at and expiration timestamps."""
    now = datetime.now(timezone.utc)
    expires_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = data.copy()
    payload.update({"iat": now, "exp": expires_at})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Validate and decode an access token, returning a consistent 401 on failure."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """Resolve the authenticated user represented by a bearer token."""
    payload = decode_access_token(token)
    username: Optional[str] = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*allowed_roles: str):
    """Build a dependency that permits only users with one of the given roles."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Operation not permitted. Required role: "
                    f"{', '.join(allowed_roles)}"
                ),
            )
        return current_user

    return role_checker

