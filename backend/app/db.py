"""SQLAlchemy engine/session setup for the control-plane Postgres database.

One engine per process, one `SessionLocal` factory, and a `get_db()` FastAPI dependency that
yields a session and always closes it — the standard SQLAlchemy-with-FastAPI pattern. This file
intentionally knows nothing about tenants or documents (see models.py) or about the content
plane (vector stores, raw files) — it is exclusively the control-plane database connection.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings

Base = declarative_base()

_settings = get_settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
