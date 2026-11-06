"""SQLite engine and session configuration."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

try:
    from .config import settings
except (ImportError, ValueError):
    try:
        from backend.app.config import settings
    except ModuleNotFoundError:
        from app.config import settings


def _resolve_database_url(url: str) -> str:
    """Anchor relative SQLite database files to the repository root."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url

    raw_path = url[len(prefix):]
    if raw_path == ":memory:":
        return url

    database_path = Path(raw_path)
    if database_path.is_absolute():
        return url

    project_root = Path(__file__).resolve().parents[2]
    resolved_path = project_root / "data" / database_path.name
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{resolved_path.as_posix()}"


engine = create_engine(
    _resolve_database_url(settings.DATABASE_URL),
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    """Apply SQLite concurrency and integrity settings to each connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Yield a database session and always close it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
