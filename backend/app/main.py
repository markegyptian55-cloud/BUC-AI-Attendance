"""FastAPI application entry point for Attendance AI."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from .config import settings
    from .db import Base, SessionLocal, engine
    from .routers import auth, courses, faces, reports, sessions, students
    from .services.face_engine import get_face_engine
    from .services.matcher import vector_cache
except (ImportError, ValueError):
    try:
        from backend.app.config import settings
        from backend.app.db import Base, SessionLocal, engine
        from backend.app.routers import auth, courses, faces, reports, sessions, students
        from backend.app.services.face_engine import get_face_engine
        from backend.app.services.matcher import vector_cache
    except ModuleNotFoundError:
        from app.config import settings
        from app.db import Base, SessionLocal, engine
        from app.routers import auth, courses, faces, reports, sessions, students
        from app.services.face_engine import get_face_engine
        from app.services.matcher import vector_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize persistent storage and shared face services at startup."""
    Base.metadata.create_all(bind=engine)
    app.state.face_engine = get_face_engine()
    with SessionLocal() as db:
        vector_cache.load_from_db(db)
    yield


app = FastAPI(
    title="Attendance AI API",
    version="1.0.0",
    description=(
        "Automated Face-Recognition University Attendance System for Badr "
        "University in Cairo (BUC)"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(students.router)
app.include_router(faces.router)
app.include_router(courses.router)
app.include_router(sessions.router)
app.include_router(reports.router)


@app.get("/", tags=["root"])
def root():
    return {
        "name": "Attendance AI API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
