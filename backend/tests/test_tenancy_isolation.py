"""The release-gate test: proves two tenants' content plane is actually isolated.

ARCHITECTURE.md §13 treats this suite as a required pass on any change to `ingestion/`,
`retrieval/`, or `security.py`/`deps.py` — it's what actually verifies the product's core
promise ("your documents, never another university's"), not just an architecture diagram's
claim about it. Every assertion here checks a real, observable outcome (files on disk, chunks
returned by a real query, a real credential resolving to a real tenant) rather than a mock.
"""

import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.deps import resolve_tenant_from_widget_key
from app.ingestion.pipeline import ingest_document
from app.models import Document, Tenant
from app.retrieval.retriever import retrieve
from app.retrieval.vector_store import get_store
from app.routers.admin import delete_document
from app.security import generate_widget_key
from app.storage import get_storage
from app.tenancy.store_paths import _safe_slug, vector_dir


def _make_tenant(db_session, slug: str, name: str) -> Tenant:
    # conftest.py uses one SQLite file for the whole test session (not one per test, and not a
    # per-test rollback) — so slugs need a random suffix here to stay unique across every test
    # in this module, the same way two real universities can't both register "tue". The suffix
    # is purely a test-isolation detail; it has no bearing on the production uniqueness
    # constraint being exercised.
    unique_slug = f"{slug}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant(slug=unique_slug, name=name, widget_key=generate_widget_key(unique_slug))
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def _markdown(title: str, marker: str) -> bytes:
    return f"""---
title: "{title}"
source_url: "https://example.edu/{title.lower()}"
---

# {title}

This document contains the unique marker {marker} which must never be retrievable
by any tenant other than the one it was uploaded to.
""".encode()


@pytest.fixture
def two_tenants(db_session):
    tenant_a = _make_tenant(db_session, "tenant-a", "Tenant A University")
    tenant_b = _make_tenant(db_session, "tenant-b", "Tenant B University")
    return tenant_a, tenant_b


def test_tenant_stores_are_physically_separate_directories(two_tenants):
    tenant_a, tenant_b = two_tenants
    dir_a = vector_dir(tenant_a.slug)
    dir_b = vector_dir(tenant_b.slug)

    assert dir_a != dir_b
    assert dir_a.resolve() != dir_b.resolve()
    # Neither tenant's directory is nested inside the other's.
    assert dir_b.resolve() not in dir_a.resolve().parents
    assert dir_a.resolve() not in dir_b.resolve().parents


def test_retrieval_never_crosses_tenant_boundary(db_session, two_tenants):
    tenant_a, tenant_b = two_tenants

    doc_a = ingest_document(db_session, tenant_a, "handbook-a.md", _markdown("Handbook A", "ALPHA_MARKER_998877"))
    doc_b = ingest_document(db_session, tenant_b, "handbook-b.md", _markdown("Handbook B", "BETA_MARKER_112233"))

    assert doc_a.status == "indexed"
    assert doc_b.status == "indexed"

    # High k on purpose: with physically separate stores, tenant B's content is not merely
    # ranked lower for tenant A's queries -- it is structurally absent from tenant A's
    # collection, so no value of k can surface it.
    results_for_a = retrieve(tenant_a.slug, "unique marker", k=20)
    results_for_b = retrieve(tenant_b.slug, "unique marker", k=20)

    assert any("ALPHA_MARKER_998877" in r["content"] for r in results_for_a)
    assert not any("BETA_MARKER_112233" in r["content"] for r in results_for_a)

    assert any("BETA_MARKER_112233" in r["content"] for r in results_for_b)
    assert not any("ALPHA_MARKER_998877" in r["content"] for r in results_for_b)


def test_vector_store_query_is_scoped_to_its_own_collection(db_session, two_tenants):
    """Same claim as above, checked one layer lower: querying tenant A's VectorStore object
    directly (bypassing retriever.py entirely) still cannot see tenant B's chunks, because the
    two stores are backed by different Chroma clients rooted at different directories."""
    tenant_a, tenant_b = two_tenants
    ingest_document(db_session, tenant_a, "a.md", _markdown("A", "ONLY_IN_A_555"))
    ingest_document(db_session, tenant_b, "b.md", _markdown("B", "ONLY_IN_B_666"))

    store_a = get_store(tenant_a.slug)
    store_b = get_store(tenant_b.slug)

    a_results = store_a.query("marker", k=20)
    b_results = store_b.query("marker", k=20)

    assert any("ONLY_IN_A_555" in r["content"] for r in a_results)
    assert all("ONLY_IN_B_666" not in r["content"] for r in a_results)
    assert any("ONLY_IN_B_666" in r["content"] for r in b_results)
    assert all("ONLY_IN_A_555" not in r["content"] for r in b_results)


def test_widget_key_resolves_only_its_own_tenant(db_session, two_tenants):
    tenant_a, tenant_b = two_tenants

    resolved_a = resolve_tenant_from_widget_key(x_widget_key=tenant_a.widget_key, db=db_session)
    resolved_b = resolve_tenant_from_widget_key(x_widget_key=tenant_b.widget_key, db=db_session)

    assert resolved_a.slug == tenant_a.slug
    assert resolved_b.slug == tenant_b.slug
    assert resolved_a.slug != resolved_b.slug


def test_deleting_one_tenants_document_does_not_touch_the_other(db_session, two_tenants):
    tenant_a, tenant_b = two_tenants
    doc_a = ingest_document(db_session, tenant_a, "a.md", _markdown("A", "KEEP_ME_A"))
    ingest_document(db_session, tenant_b, "b.md", _markdown("B", "KEEP_ME_B"))

    # source_id is the filename alone (ingestion/pipeline.py:ingest_document), not
    # f"{checksum}__{filename}" -- it has to stay content-independent so a re-upload of an
    # edited file can find and replace its own previous chunks (see the regression test below).
    get_store(tenant_a.slug).delete_by_source("a.md")

    results_for_a = retrieve(tenant_a.slug, "marker", k=20)
    results_for_b = retrieve(tenant_b.slug, "marker", k=20)

    assert not any("KEEP_ME_A" in r["content"] for r in results_for_a)
    assert any("KEEP_ME_B" in r["content"] for r in results_for_b)


@pytest.mark.parametrize("malicious_slug", ["../other-tenant", "/etc/passwd", "a/../../b", ""])
def test_unsafe_tenant_slugs_are_rejected_before_touching_the_filesystem(malicious_slug):
    with pytest.raises(ValueError):
        _safe_slug(malicious_slug)


def test_reuploading_an_edited_document_updates_the_same_row_with_no_orphaned_chunks(db_session, two_tenants):
    """Regression test for the document-edit bug in ingest_document (app/ingestion/pipeline.py).

    Before the fix: re-uploading an edited file under the same filename (a) matched the existing
    Document row only by checksum, so it always inserted a *second* row for the same logical
    document instead of updating the first, and (b) derived source_id from the checksum, so
    delete_by_source() -- called with the *new* content's source_id, which nothing was ever
    upserted under -- never found the previous version's chunks, leaving them orphaned in the
    vector store forever under a source_id nothing referenced any more. This test fails against
    that pre-fix behavior and passes against the current fix."""
    tenant_a, _ = two_tenants

    original = ingest_document(
        db_session, tenant_a, "handbook.md", _markdown("Handbook", "ORIGINAL_CONTENT_MARKER_444")
    )
    assert original.status == "indexed"

    edited = ingest_document(
        db_session, tenant_a, "handbook.md", _markdown("Handbook", "EDITED_CONTENT_MARKER_555")
    )
    assert edited.status == "indexed"

    # Exactly one current Document row for this (tenant, filename) -- not one per upload.
    assert edited.id == original.id
    rows = (
        db_session.query(Document)
        .filter(Document.tenant_id == tenant_a.id, Document.filename == "handbook.md")
        .all()
    )
    assert len(rows) == 1

    # No orphaned chunks left behind from the pre-edit version.
    results = get_store(tenant_a.slug).query("marker", k=20)
    assert any("EDITED_CONTENT_MARKER_555" in r["content"] for r in results)
    assert not any("ORIGINAL_CONTENT_MARKER_444" in r["content"] for r in results)


def test_delete_document_removes_it_for_its_tenant_without_touching_the_other(db_session, two_tenants):
    """Coverage for the DELETE endpoint (routers/admin.py:delete_document): removes the Document
    row, the raw file, and the vector-store chunks for the deleted document, and touches none of
    that for a different tenant -- same isolation guarantee the rest of this module exercises for
    ingestion and retrieval, extended to the deletion path."""
    tenant_a, tenant_b = two_tenants
    doc_a = ingest_document(db_session, tenant_a, "a.md", _markdown("A", "DELETE_ME_A"))
    doc_b = ingest_document(db_session, tenant_b, "b.md", _markdown("B", "KEEP_ME_B"))

    storage = get_storage()
    raw_ref_a = Path(storage.raw_ref(tenant_a.slug, doc_a.checksum, doc_a.filename))
    raw_ref_b = Path(storage.raw_ref(tenant_b.slug, doc_b.checksum, doc_b.filename))
    assert raw_ref_a.exists()
    assert raw_ref_b.exists()

    delete_document(document_id=doc_a.id, tenant=tenant_a, db=db_session)

    # Document row gone for tenant A; tenant B's row untouched.
    assert db_session.query(Document).filter(Document.id == doc_a.id).first() is None
    assert db_session.query(Document).filter(Document.id == doc_b.id).first() is not None

    # Raw file gone for tenant A only.
    assert not raw_ref_a.exists()
    assert raw_ref_b.exists()

    # Chunks gone from tenant A's store; tenant B's store untouched.
    results_for_a = retrieve(tenant_a.slug, "marker", k=20)
    results_for_b = retrieve(tenant_b.slug, "marker", k=20)
    assert not any("DELETE_ME_A" in r["content"] for r in results_for_a)
    assert any("KEEP_ME_B" in r["content"] for r in results_for_b)


def test_delete_document_is_scoped_to_the_owning_tenant(db_session, two_tenants):
    """A document id belonging to tenant B must 404 under tenant A's slug rather than delete it --
    same "don't even confirm it exists across tenants" posture as resolve_tenant_from_widget_key
    and get_tenant_by_slug."""
    tenant_a, tenant_b = two_tenants
    doc_b = ingest_document(db_session, tenant_b, "b.md", _markdown("B", "CROSS_TENANT_MARKER_777"))

    with pytest.raises(HTTPException) as exc_info:
        delete_document(document_id=doc_b.id, tenant=tenant_a, db=db_session)
    assert exc_info.value.status_code == 404

    # Untouched: tenant B's document and chunks are still there.
    assert db_session.query(Document).filter(Document.id == doc_b.id).first() is not None
    results_for_b = retrieve(tenant_b.slug, "marker", k=20)
    assert any("CROSS_TENANT_MARKER_777" in r["content"] for r in results_for_b)
