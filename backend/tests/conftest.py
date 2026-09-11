"""Shared test fixtures.

Uses a temporary SQLite file as the control-plane database for the whole test session (see the
portability note in app/models.py) and a fresh temporary directory for the content plane
(per-tenant raw files + vector stores) on every test, so tests never touch real tenant data and
never leak state between tests. The environment variables below MUST be set before anything
under `app.*` is imported anywhere in the test session (settings are cached via `lru_cache` and
the DB engine is created at import time), which is why this happens at module level, above the
`from app...` imports.
"""

import os
import tempfile
from pathlib import Path

import pytest

_TEST_DB_PATH = Path(tempfile.mkdtemp()) / "test_control_plane.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-used-in-tests")
os.environ["TEST_FAKE_EMBEDDINGS"] = "true"  # see retrieval/vector_store.py

from app.db import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402, F401  (import registers models with Base.metadata)


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _isolated_content_plane(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("TENANT_DATA_DIR", str(tmp_path / "tenants"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

    from app.retrieval.vector_store import get_store
    get_store.cache_clear()


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
