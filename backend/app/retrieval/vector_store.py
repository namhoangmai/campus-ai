"""The `VectorStore` interface and its two implementations: local Chroma (default, zero extra
infra) and self-hosted Qdrant (ARCHITECTURE.md §2's scaling-ceiling swap, §9's table).

This is the file ARCHITECTURE.md §2 refers to when it says physical tenant isolation is
implemented as "one store per tenant" — and the file §9 refers to as the single swap point for
moving to a managed multi-tenant vector database later. That swap is exactly what
`QdrantVectorStore` below is: `get_store()` picks it over `ChromaVectorStore` purely based on
whether `QDRANT_URL` is configured, so local dev/tests are entirely unaffected (they never set
it, so they never even import `qdrant_client` — see `QdrantVectorStore.__init__`). No other
module in the codebase is allowed to import `chromadb`/`qdrant_client` directly; every caller
goes through `get_store(tenant_slug)`.

Isolation model is preserved identically across both backends: **one collection per tenant,
named by tenant slug** (Chroma: one `PersistentClient` directory per tenant, each holding a
single `documents` collection; Qdrant: one collection per tenant slug on the shared Qdrant
service) — never a shared collection with a `tenant_id` metadata/payload filter. That distinction
is the actual guarantee ARCHITECTURE.md §2 chose over the cheaper "shared store, filtered query"
alternative: there is still no query path from tenant A's code into tenant B's vectors without
asking for tenant B's collection by name explicitly, exactly as before.
"""

import hashlib
import uuid
from functools import lru_cache
from typing import Protocol

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.config import get_settings
from app.ingestion.base import Chunk
from app.tenancy.store_paths import vector_dir

_COLLECTION_NAME = "documents"  # Chroma only -- one per tenant *directory*, so the name itself
                                 # need not be tenant-specific. Qdrant has no equivalent per-tenant
                                 # directory, so QdrantVectorStore uses the tenant slug itself as
                                 # the collection name instead (see its docstring).
_FAKE_EMBEDDING_DIM = 64


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk]) -> None: ...
    def delete_by_source(self, source_id: str) -> None: ...
    def query(self, query_text: str, k: int) -> list[dict]: ...


class _FakeHashEmbeddingFunction:
    """Deterministic, dependency-free stand-in for the real embedding model, used only when
    `settings.test_fake_embeddings` is true (set exclusively by tests/conftest.py). Hashes each
    word into one of 64 buckets and accumulates a sign per occurrence — crude, but good enough
    to make semantically distinct test documents land in different regions of the vector space,
    which is all the tenant-isolation test needs. Never used outside a test run: production
    always uses the real `SentenceTransformerEmbeddingFunction` below."""

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors = []
        for text in input:
            vec = [0.0] * _FAKE_EMBEDDING_DIM
            for word in text.lower().split():
                h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
                vec[h % _FAKE_EMBEDDING_DIM] += 1.0 if (h // _FAKE_EMBEDDING_DIM) % 2 == 0 else -1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    @staticmethod
    def name() -> str:
        # chromadb 1.5.x's EmbeddingFunction protocol requires this (used to detect a mismatch
        # between the embedding function passed in and whatever was persisted for an existing
        # collection) — without it, get_or_create_collection raises AttributeError on any
        # collection created under test (see chromadb/api/collection_configuration.py).
        return "fake_hash"

    def embed_query(self, input: list[str]) -> list[list[float]]:
        # chromadb's real EmbeddingFunction base class provides this (defaulting to __call__)
        # for classes that subclass it; this class doesn't, so it needs its own — chromadb's
        # Collection.query() calls embed_query(), not __call__(), on the query side.
        return self(input)


@lru_cache(maxsize=1)
def _embedding_function():
    if get_settings().test_fake_embeddings:
        return _FakeHashEmbeddingFunction()
    # One real embedding model instance shared by every tenant's store (loading the model is
    # the expensive part; the per-tenant isolation is about *where vectors are stored*, not
    # about having a separate model per tenant, which would be pure waste).
    return SentenceTransformerEmbeddingFunction(
        model_name=get_settings().embedding_model, normalize_embeddings=True
    )


class ChromaVectorStore:
    """One instance per tenant. `client` is a `PersistentClient` rooted at that tenant's own
    `data/tenants/<slug>/vector/` directory — a genuinely separate on-disk store, not a shared
    Chroma instance with a per-tenant collection inside it. See ARCHITECTURE.md §2 for why that
    distinction is the actual isolation guarantee, not a cosmetic one."""

    def __init__(self, tenant_slug: str) -> None:
        self._tenant_slug = tenant_slug
        self._client = chromadb.PersistentClient(path=str(vector_dir(tenant_slug)))
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME, embedding_function=_embedding_function()
        )

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[c.metadata for c in chunks],
        )

    def delete_by_source(self, source_id: str) -> None:
        self._collection.delete(where={"source_id": source_id})

    def query(self, query_text: str, k: int) -> list[dict]:
        results = self._collection.query(query_texts=query_text, n_results=k)
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        return [
            {"content": doc, **(meta or {})}
            for doc, meta in zip(documents, metadatas)
        ]


def _qdrant_point_id(chunk_id: str) -> str:
    """Qdrant point IDs must be an unsigned integer or a UUID; `chunk_id` is an arbitrary string
    (f"{source_id}::{chunk_index}", see ingestion/base.py), so derive a stable UUID from it
    deterministically -- same chunk_id always maps to the same point id, so re-upserting a
    chunk (e.g. on re-ingestion) overwrites it in place rather than duplicating it. The original
    chunk_id string is preserved in the payload for anything that needs it."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantVectorStore:
    """One instance per tenant, one Qdrant *collection per tenant slug* -- never a shared
    collection filtered by a tenant_id payload field. This is the same physical-isolation model
    ARCHITECTURE.md §2 chose for local Chroma (one store per tenant), just backed by a shared
    remote service instead of a local directory: each tenant's vectors live in their own named
    collection on the Qdrant instance, so there is still no query path from tenant A's
    code/credentials into tenant B's vectors without asking for tenant B's collection by name
    explicitly -- swapping *where* the one-store-per-tenant model is hosted, not the model
    itself. See ARCHITECTURE.md §2's scaling-ceiling note and §9's table for why this is the
    documented next step, not a new decision.

    Embeddings are computed here (via the same `_embedding_function()` every tenant already
    shares) and sent to Qdrant as plain vectors -- unlike Chroma, Qdrant has no notion of a
    collection-attached embedding function, so this class owns that step explicitly instead of
    delegating it to the store.
    """

    def __init__(self, tenant_slug: str) -> None:
        # Imported lazily, inside __init__, specifically so importing this module -- and every
        # test/local-dev run that never sets QDRANT_URL and therefore never constructs this
        # class -- never requires `qdrant-client` to be installed at all.
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import Distance, VectorParams

        settings = get_settings()
        self._tenant_slug = tenant_slug
        self._collection_name = tenant_slug
        self._embed = _embedding_function()
        self._client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)

        if not self._client.collection_exists(self._collection_name):
            vector_size = len(self._embed([" "])[0])  # probe once; avoids hardcoding a model's dim
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        from qdrant_client.http.models import PointStruct

        vectors = self._embed([c.text for c in chunks])
        points = [
            PointStruct(
                id=_qdrant_point_id(c.chunk_id),
                vector=vector,
                payload={"content": c.text, "chunk_id": c.chunk_id, **c.metadata},
            )
            for c, vector in zip(chunks, vectors)
        ]
        self._client.upsert(collection_name=self._collection_name, points=points)

    def delete_by_source(self, source_id: str) -> None:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        self._client.delete(
            collection_name=self._collection_name,
            points_selector=Filter(must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]),
        )

    def query(self, query_text: str, k: int) -> list[dict]:
        vector = self._embed([query_text])[0]
        results = self._client.query_points(
            collection_name=self._collection_name, query=vector, limit=k
        ).points
        return [point.payload for point in results]


@lru_cache(maxsize=None)
def get_store(tenant_slug: str) -> "ChromaVectorStore | QdrantVectorStore":
    """Cached per tenant slug — each tenant's store client/collection is opened once per process
    and reused, not reopened on every request. Backend choice is a pure config switch: QDRANT_URL
    set -> self-hosted Qdrant (ARCHITECTURE.md §2/§9's documented scaling swap); unset (the
    default) -> local Chroma, so local dev/tests need no Qdrant instance and no qdrant-client
    install."""
    if get_settings().qdrant_url:
        return QdrantVectorStore(tenant_slug)
    return ChromaVectorStore(tenant_slug)
