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

    def raw_ref(self, tenant_slug: str, checksum: str, filename: str) -> str:
        """Reconstructs the same reference `save_raw` would have returned for a given
        (tenant, checksum, filename), without that original return value having been persisted
        anywhere. `Document` (app/models.py) doesn't store save_raw()'s return value today, so a
        caller that needs to delete a raw file later (routers/admin.py's document-delete route)
        has to rebuild the reference from the checksum + filename it already has on the Document
        row, using the exact same convention ingestion/pipeline.py:ingest_document used to build
        the `filename` argument it originally passed to `save_raw`. This is a reconstruction,
        not a lookup — if that convention ever changes, this must change with it. The more
        robust fix is persisting `save_raw`'s return value as a real Document column, but that
        needs an ingestion/pipeline.py + models.py change outside this agent's lane; flagged,
        not made, here."""
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

    def raw_ref(self, tenant_slug: str, checksum: str, filename: str) -> str:
        return str(raw_dir(tenant_slug) / f"{checksum}__{filename}")


def get_storage() -> Storage:
    # Single call site to swap in an S3-backed implementation later (ARCHITECTURE.md §9) without
    # touching any caller.
    return LocalDiskStorage()
