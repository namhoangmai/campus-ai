"""Top-k retrieval, always scoped to one tenant.

`retrieve()` takes `tenant_slug` as a required positional argument with no default, on purpose:
ARCHITECTURE.md §5 explains this is so "retrieve with no tenant specified" is a type error
callers hit at review/test time, not a runtime bug that silently falls back to some default
store.
"""

from app.config import get_settings
from app.retrieval.vector_store import get_store


def retrieve(tenant_slug: str, query: str, k: int | None = None) -> list[dict]:
    k = k or get_settings().retrieval_k
    store = get_store(tenant_slug)
    return store.query(query, k=k)
