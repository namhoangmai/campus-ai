"""The single source of truth for where a tenant's files live on disk.

Every other module that needs a tenant's raw-file directory or vector-store directory calls
these functions rather than constructing a path itself. That's the concrete mechanism behind
the "physical isolation" claim in ARCHITECTURE.md §2: if there is exactly one function that
turns a tenant slug into a directory path, there is exactly one place to verify that a tenant's
data can never resolve outside its own directory (see `_safe_slug` below), instead of trusting
every call site to have done that correctly on its own.
"""

import re
from pathlib import Path

from app.config import get_settings

_SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


def _safe_slug(slug: str) -> str:
    """Reject anything that isn't a plain, validated tenant slug before it ever touches a
    filesystem path. This is what stands between a bug elsewhere (or a malicious tenant slug
    somehow reaching here) and a path-traversal read/write outside `tenant_data_dir` — e.g. a
    slug of '../other-tenant' or an absolute path must never reach `Path.joinpath`."""
    if not _SAFE_SLUG_RE.match(slug):
        raise ValueError(f"Refusing to build a filesystem path from an unsafe tenant slug: {slug!r}")
    return slug


def tenant_root(slug: str) -> Path:
    return get_settings().tenant_data_dir / _safe_slug(slug)


def raw_dir(slug: str) -> Path:
    d = tenant_root(slug) / "raw"
    d.mkdir(parents=True, exist_ok=True)
    return d


def vector_dir(slug: str) -> Path:
    d = tenant_root(slug) / "vector"
    d.mkdir(parents=True, exist_ok=True)
    return d
