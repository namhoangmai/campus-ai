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

    # --- Deployment ---
    # "development" (default) is the zero-config local flow (bare uvicorn + docker-compose
    # Postgres) and is never validated. Set ENVIRONMENT=production in any real deployment
    # (ARCHITECTURE.md §9 Tier 1: single instance) to turn on validate_production_settings()
    # below. Deliberately opt-in rather than "not under pytest": local dev's documented default
    # DATABASE_URL is byte-for-byte the same as docker-compose's, so a bare "not a test" guard
    # would also fail a correctly configured local dev environment.
    environment: str = "development"

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


def validate_production_settings(settings: Settings) -> None:
    """Fail fast at startup if ENVIRONMENT=production but the deployment still carries
    local/insecure defaults. A no-op unless ENVIRONMENT is explicitly set to "production" (see
    the `environment` field's docstring for why that's opt-in, not "outside pytest") — called
    from app/main.py before the app starts serving requests.
    """
    if settings.environment != "production":
        return

    problems: list[str] = []
    if not settings.admin_api_key:
        problems.append("ADMIN_API_KEY is empty")
    if not settings.openrouter_api_key:
        problems.append("OPENROUTER_API_KEY is empty")
    local_default = Settings.model_fields["database_url"].default
    if settings.database_url == local_default:
        problems.append(
            "DATABASE_URL still points at the local docker-compose default "
            f"({local_default!r}); point it at your production database"
        )

    if problems:
        raise RuntimeError(
            "Refusing to start with ENVIRONMENT=production due to unsafe configuration: "
            + "; ".join(problems)
        )
