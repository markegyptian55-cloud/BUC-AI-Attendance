"""Authentication and public health check endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from ..db import get_db
    from ..models import User, FaceEmbedding
    from ..schemas import Token, UserLogin, UserOut, HealthCheck
    from ..auth import verify_password, create_access_token, get_current_user
except (ImportError, ValueError):
    try:
        from backend.app.db import get_db
        from backend.app.models import User, FaceEmbedding
        from backend.app.schemas import Token, UserLogin, UserOut, HealthCheck
        from backend.app.auth import verify_password, create_access_token, get_current_user
    except ModuleNotFoundError:
        from app.db import get_db
        from app.models import User, FaceEmbedding
        from app.schemas import Token, UserLogin, UserOut, HealthCheck
        from app.auth import verify_password, create_access_token, get_current_user


router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """Authenticate using OAuth2 form fields and return a bearer token."""
    user = db.query(User).filter(User.username == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    return Token(access_token=access_token, token_type="bearer")


@router.post("/auth/login-json", response_model=Token)
def login_json(credentials: UserLogin, db: Session = Depends(get_db)) -> Token:
    """Authenticate using JSON credentials and return a bearer token."""
    user = db.query(User).filter(User.username == credentials.username).first()
    if user is None or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    return Token(access_token=access_token, token_type="bearer")


@router.get("/auth/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Return the profile for the authenticated user."""
    return UserOut.model_validate(current_user)


@router.get("/health", response_model=HealthCheck)
def health_check(request: Request, db: Session = Depends(get_db)) -> HealthCheck:
    """Report database connectivity, model availability, and embedding count."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {str(exc)}"

    face_engine = getattr(request.app.state, "face_engine", None)
    model_loaded = face_engine is not None

    try:
        cached_vectors_count = db.query(FaceEmbedding).count()
    except Exception:
        cached_vectors_count = 0

    return HealthCheck(
        status="healthy" if db_status == "ok" else "degraded",
        model_loaded=model_loaded,
        cached_vectors_count=cached_vectors_count,
        database=db_status,
    )
