"""Orchestrates one document's journey: raw bytes -> Document row -> extract -> chunk -> upsert.

Deliberately has no FastAPI/HTTP awareness — `ingest_document()` takes plain arguments and a
SQLAlchemy session, so it's callable identically from a route handler (today, synchronously) or
from a background-job worker (later, per ARCHITECTURE.md §9's async-ingestion upgrade path)
without any change to this file.
"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ingestion.base import ExtractedDocument
from app.ingestion.markdown_chunker import chunk_markdown
from app.ingestion.markdown_extractor import extract_markdown
from app.ingestion.pdf_chunker import chunk_pdf
from app.ingestion.pdf_extractor import NoExtractableTextError, extract_pdf
from app.models import Document, Tenant
from app.retrieval.vector_store import get_store
from app.storage import get_storage


class UnsupportedDocumentType(Exception):
    pass


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _doc_type_for(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".md") or lower.endswith(".markdown"):
        return "markdown"
    if lower.endswith(".pdf"):
        return "pdf"
    raise UnsupportedDocumentType(f"Unsupported file extension: {filename!r} (expected .md or .pdf)")


def ingest_document(db: Session, tenant: Tenant, filename: str, content: bytes) -> Document:
    """Idempotent per (tenant, filename) -- that pair is "this document slot," independent of
    content. Re-uploading identical bytes for an already-indexed document returns the existing
    row untouched. Re-uploading an *edited* file (same filename, different content) reuses the
    same Document row and the same `source_id` (see below) so the old chunks can actually be
    found and replaced, instead of leaving a stale orphaned set behind under a source_id nothing
    else references any more -- see ARCHITECTURE.md §4.6."""
    checksum = _checksum(content)
    doc_type = _doc_type_for(filename)
    # Stable per (tenant, filename), NOT derived from content -- a tenant's vector store is
    # already its own isolated collection, so filename alone is a safe, sufficient key within
    # it. This has to stay content-independent specifically so `delete_by_source()` below finds
    # the *previous* version's chunks on a re-upload rather than a source_id nothing was ever
    # upserted under.
    source_id = filename

    document = (
        db.query(Document)
        .filter(Document.tenant_id == tenant.id, Document.filename == filename)
        .first()
    )
    if document is not None and document.checksum == checksum and document.status == "indexed":
        return document

    if document is None:
        document = Document(
            tenant_id=tenant.id,
            filename=filename,
            doc_type=doc_type,
            title=filename,
            status="processing",
            checksum=checksum,
        )
        db.add(document)
    else:
        # Same (tenant, filename) slot, different content (or a retry of a failed/incomplete
        # previous attempt) -- update this row in place rather than inserting a second one, so
        # there is exactly one Document row per logical document, not one per upload.
        document.doc_type = doc_type
        document.status = "processing"
        document.checksum = checksum
        document.error_message = None
    db.commit()
    db.refresh(document)

    try:
        storage = get_storage()
        storage.save_raw(tenant.slug, f"{checksum}__{filename}", content)

        extracted: ExtractedDocument
        if doc_type == "markdown":
            extracted = extract_markdown(source_id, filename, content)
            chunks = chunk_markdown(extracted)
        else:
            extracted = extract_pdf(source_id, filename, content)
            chunks = chunk_pdf(extracted, content)
            document.page_count = extracted.metadata.get("page_count")

        store = get_store(tenant.slug)
        store.delete_by_source(source_id)  # re-ingesting an edited doc must not leave stale chunks
        store.upsert(chunks)

        document.title = extracted.title
        document.chunk_count = len(chunks)
        document.status = "indexed"
        document.indexed_at = datetime.now(timezone.utc)

    except NoExtractableTextError as exc:
        document.status = "failed"
        document.error_message = str(exc)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: one bad document must not
        # crash a batch upload; see ARCHITECTURE.md §4.6 ("log and skip a malformed document").
        document.status = "failed"
        document.error_message = f"{type(exc).__name__}: {exc}"

    db.add(document)
    db.commit()
    db.refresh(document)
    return document
