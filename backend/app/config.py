"""Centralized application settings, loaded once from environment variables / .env.

Replaces v1's pattern of reading `os.getenv(...)` ad hoc in whichever module happened to need
a value (see ARCHITECTURE-ESSENTIALS.md's v1 "gotchas" list). Every setting the app depends on
is declared here, with a type and a default (where a sane default exists), so a missing
required variable fails fast at startup with a clear pydantic validation error instead of a
confusing `None` surfacing three layers deep at request time.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Control plane ---
    database_url: str = "postgresql+psycopg2://campus_ai:campus_ai@localhost:5432/campus_ai"

    # --- Content plane (local-disk implementation; see ARCHITECTURE.md §9 for the cloud swap) ---
    tenant_data_dir: Path = REPO_ROOT / "data" / "tenants"

    # --- Auth ---
    # Operator-only credential. Never shipped to a browser. See ARCHITECTURE.md §7.
    admin_api_key: str = ""

    # --- CORS ---
    frontend_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Generation (OpenRouter) ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    generation_model: str = "deepseek/deepseek-v4-flash-0731"

    # --- Retrieval ---
    embedding_model: str = "BAAI/bge-m3"
    retrieval_k: int = 4

    # --- Rate limiting (in-memory; see ARCHITECTURE.md §9 for the Redis swap) ---
    chat_rate_limit_per_minute: int = 30

    # --- Testing only ---
    # When true, retrieval/vector_store.py substitutes a tiny deterministic hash-based embedding
    # function for the real BAAI/bge-m3 model, so the test suite (backend/tests/) runs without
    # downloading a multi-GB model or needing network access. Set only by tests/conftest.py;
    # never set true outside a test run — see retrieval/vector_store.py for the implementation.
    test_fake_embeddings: bool = False

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton — settings are read from the environment once per process."""
    return Settings()
