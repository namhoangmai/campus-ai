"""Raw-document storage, behind an interface deliberately narrow enough to swap implementations.

`LocalDiskStorage` is what runs today. ARCHITECTURE.md §9 names the cloud equivalent (S3-compatible
object storage, one prefix per tenant) as a later swap; `ingestion/pipeline.py` depends only on the
`Storage` protocol below, never on `pathlib` directly, so that swap touches this file and nothing
that calls it.
"""

from pathlib import Path
from typing import Protocol

from app.tenancy.store_paths import raw_dir


class Storage(Protocol):
    def save_raw(self, tenant_slug: str, filename: str, content: bytes) -> str:
        """Persist raw document bytes for a tenant; returns a storage-implementation-specific
        reference (a local path today, an object key later) that callers should treat as opaque."""
        ...

    def delete_raw(self, tenant_slug: str, ref: str) -> None:
        ...


class LocalDiskStorage:
    """Local-disk implementation used for the current (localhost) deployment target."""

    def save_raw(self, tenant_slug: str, filename: str, content: bytes) -> str:
        path = raw_dir(tenant_slug) / filename
        path.write_bytes(content)
        return str(path)

    def delete_raw(self, tenant_slug: str, ref: str) -> None:
        path = Path(ref)
        if path.exists():
            path.unlink()


def get_storage() -> Storage:
    # Single call site to swap in an S3-backed implementation later (ARCHITECTURE.md §9) without
    # touching any caller.
    return LocalDiskStorage()
