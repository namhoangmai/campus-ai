"""Raw-document storage, behind an interface deliberately narrow enough to swap implementations.

`LocalDiskStorage` is the local-dev/test default; `S3Storage` is the Tier 2 cloud swap
(ARCHITECTURE.md §9/§12) for a real deployment, targeting Cloudflare R2 by default (any
S3-compatible endpoint works). `get_storage()` picks between them based on `settings.s3_bucket`
alone, so `ingestion/pipeline.py` (the only caller) never knows or cares which is active.
"""

from pathlib import Path
from typing import Protocol

from app.config import get_settings
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


class S3Storage:
    """S3-compatible object storage. One key prefix per tenant (`<tenant_slug>/raw/...`) inside
    a single shared bucket -- object storage has no real filesystem, so this is the S3 analogue
    of `LocalDiskStorage`'s per-tenant directory, not a weaker form of isolation: two tenants'
    keys can never collide (their slugs are unique, ARCHITECTURE.md §3) and nothing here ever
    lists or reads a key outside a caller-supplied tenant_slug's own prefix.

    boto3's S3 client talks to any S3-compatible endpoint (not just AWS) -- pointing
    `endpoint_url` at Cloudflare R2 (the default target for this job) or another provider is a
    config change, not a code change.
    """

    def __init__(
        self, bucket: str, endpoint_url: str, access_key_id: str, secret_access_key: str, region: str
    ) -> None:
        import boto3  # imported lazily so LocalDiskStorage (the default) never needs boto3 installed

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            region_name=region,
        )

    def _key(self, tenant_slug: str, filename: str) -> str:
        return f"{tenant_slug}/raw/{filename}"

    def save_raw(self, tenant_slug: str, filename: str, content: bytes) -> str:
        key = self._key(tenant_slug, filename)
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content)
        return key

    def delete_raw(self, tenant_slug: str, ref: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=ref)

    def raw_ref(self, tenant_slug: str, checksum: str, filename: str) -> str:
        return self._key(tenant_slug, f"{checksum}__{filename}")


def get_storage() -> Storage:
    # Single call site that picks the active backend (ARCHITECTURE.md §9's Tier 2 swap): empty
    # S3_BUCKET (default) keeps every existing caller on LocalDiskStorage untouched; setting it
    # switches to S3Storage with no change anywhere else. Not cached -- both implementations are
    # cheap/stateless to construct (S3Storage's boto3 client holds no per-request state), unlike
    # e.g. retrieval/vector_store.py's per-tenant Chroma client, which is genuinely expensive.
    settings = get_settings()
    if settings.s3_bucket:
        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            region=settings.s3_region,
        )
    return LocalDiskStorage()
