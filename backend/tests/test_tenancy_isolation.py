"""The release-gate test: proves two tenants' content plane is actually isolated.

ARCHITECTURE.md §13 treats this suite as a required pass on any change to `ingestion/`,
`retrieval/`, or `security.py`/`deps.py` — it's what actually verifies the product's core
promise ("your documents, never another university's"), not just an architecture diagram's
claim about it. Every assertion here checks a real, observable outcome (files on disk, chunks
returned by a real query, a real credential resolving to a real tenant) rather than a mock.
"""

import uuid

import pytest

from app.deps import resolve_tenant_from_widget_key
from app.ingestion.pipeline import ingest_document
from app.models import Tenant
from app.retrieval.retriever import retrieve
from app.retrieval.vector_store import get_store
from app.security import generate_widget_key
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

    get_store(tenant_a.slug).delete_by_source(f"{doc_a.checksum}__a.md")

    results_for_a = retrieve(tenant_a.slug, "marker", k=20)
    results_for_b = retrieve(tenant_b.slug, "marker", k=20)

    assert not any("KEEP_ME_A" in r["content"] for r in results_for_a)
    assert any("KEEP_ME_B" in r["content"] for r in results_for_b)


@pytest.mark.parametrize("malicious_slug", ["../other-tenant", "/etc/passwd", "a/../../b", ""])
def test_unsafe_tenant_slugs_are_rejected_before_touching_the_filesystem(malicious_slug):
    with pytest.raises(ValueError):
        _safe_slug(malicious_slug)
