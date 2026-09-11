"""The `VectorStore` interface and its current (local Chroma) implementation.

This is the file ARCHITECTURE.md §2 refers to when it says physical tenant isolation is
implemented as "one Chroma PersistentClient per tenant, pointed at that tenant's own
directory" — and the file §9 refers to as the single swap point for moving to a managed
multi-tenant vector database later. No other module in the codebase is allowed to import
`chromadb` directly; every caller goes through `get_store(tenant_slug)`.
"""

import hashlib
from functools import lru_cache
from typing import Protocol

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.config import get_settings
from app.ingestion.base import Chunk
from app.tenancy.store_paths import vector_dir

_COLLECTION_NAME = "documents"
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


@lru_cache(maxsize=None)
def get_store(tenant_slug: str) -> ChromaVectorStore:
    """Cached per tenant slug — each tenant's Chroma client/collection is opened once per
    process and reused, not reopened on every request."""
    return ChromaVectorStore(tenant_slug)
