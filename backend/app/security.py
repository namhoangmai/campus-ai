"""Credential generation/validation and rate limiting.

See ARCHITECTURE.md §7 for the full reasoning behind the two-tier credential model. This file
is the only place that knows what an admin key or a widget key *is* — routers never compare
raw strings themselves.
"""

import secrets
import time
from collections import defaultdict

from app.config import get_settings


def generate_widget_key(tenant_slug: str) -> str:
    """Public, per-tenant credential. Prefixed with the tenant slug for operator readability
    (so `pk_tue_...` is recognizable in logs) — the prefix is not itself a secret; the random
    suffix is what makes it unguessable."""
    return f"pk_{tenant_slug}_{secrets.token_urlsafe(24)}"


def is_admin_key_valid(presented_key: str | None) -> bool:
    """Constant-time-ish comparison against the operator's single admin key. There is
    deliberately no per-admin-user table yet (see ARCHITECTURE.md §12) — self-serve admin
    accounts are future work; today there is exactly one operator and one key."""
    settings = get_settings()
    if not settings.admin_api_key or not presented_key:
        return False
    return secrets.compare_digest(presented_key, settings.admin_api_key)


class InMemoryRateLimiter:
    """Per-key fixed-window token bucket, held in process memory.

    Explicitly a local-only shortcut: this only works correctly with a single backend process,
    because the counters live in this process's memory. ARCHITECTURE.md §9 names the Redis
    swap needed the moment there is more than one backend instance — this class exists as its
    own object (rather than inlined into the chat route) specifically so that swap is
    "replace this class," not "rewrite the route."
    """

    def __init__(self, limit_per_minute: int) -> None:
        self._limit = limit_per_minute
        self._window_start: dict[str, float] = defaultdict(float)
        self._count: dict[str, int] = defaultdict(int)

    def allow(self, key: str) -> bool:
        now = time.time()
        window = 60.0
        if now - self._window_start[key] >= window:
            self._window_start[key] = now
            self._count[key] = 0
        self._count[key] += 1
        return self._count[key] <= self._limit


_rate_limiter: InMemoryRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = InMemoryRateLimiter(get_settings().chat_rate_limit_per_minute)
    return _rate_limiter
