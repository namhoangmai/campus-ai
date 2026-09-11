"""Credential generation/validation and rate limiting.

See ARCHITECTURE.md §7 for the full reasoning behind the two-tier credential model. This file
is the only place that knows what an admin key or a widget key *is* — routers never compare
raw strings themselves.

Also the single place that turns REDIS_URL into a client (`get_redis_connection`) — used by the
rate limiter below, and imported from here by routers/admin.py (enqueuing an ingestion job) and
scripts/worker.py (consuming it), so all three agree on how to reach the same Redis instance
(ARCHITECTURE.md §9/§12's Tier 2 swap).
"""

import secrets
import time
from collections import defaultdict

import redis

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


def get_redis_connection() -> redis.Redis:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is not set.")
    return redis.Redis.from_url(settings.redis_url)


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


class RedisRateLimiter:
    """Same `allow(key) -> bool` fixed-window shape as `InMemoryRateLimiter`, but the counters
    live in Redis instead of process memory, so every backend process/instance shares them —
    the Tier 2 swap ARCHITECTURE.md §9 names for the moment there's more than one instance.
    INCR-then-EXPIRE isn't perfectly atomic on the very first request of a new window (a second
    process could INCR before the first process's EXPIRE lands), but that's the same
    approximate-fixed-window behavior `InMemoryRateLimiter` already has, not a regression.
    """

    def __init__(self, client: redis.Redis, limit_per_minute: int) -> None:
        self._client = client
        self._limit = limit_per_minute

    def allow(self, key: str) -> bool:
        redis_key = f"campus_ai:ratelimit:{key}"
        count = self._client.incr(redis_key)
        if count == 1:
            self._client.expire(redis_key, 60)
        return count <= self._limit


_rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter | RedisRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        if settings.redis_url:
            _rate_limiter = RedisRateLimiter(get_redis_connection(), settings.chat_rate_limit_per_minute)
        else:
            _rate_limiter = InMemoryRateLimiter(settings.chat_rate_limit_per_minute)
    return _rate_limiter
