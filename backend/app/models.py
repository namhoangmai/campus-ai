"""Control-plane ORM models: Tenant, Document, ChatLog.

These tables hold *metadata only* — no document content, no chunk text, no embeddings. See
ARCHITECTURE.md §3 for why that split exists (control plane vs. content plane) and exactly what
belongs in each. If you're tempted to add a column here that stores chunk text or a vector,
that content belongs in the tenant's own vector store instead (retrieval/vector_store.py) —
adding it here would recreate the "one bug leaks everyone's content" risk this design
specifically avoids.

Note on column types: ids are `String(36)` (a stringified UUID4), not Postgres's native `UUID`
type, and `retrieved_doc_ids` is a portable `JSON` column, not Postgres's `ARRAY`. This is a
deliberate portability choice: the exact same schema runs against Postgres in production and
against SQLite in tests (backend/tests/conftest.py), so the tenant-isolation test suite — the
release gate ARCHITECTURE.md §13 describes — runs in any environment with no Postgres server
required, at the cost of losing native UUID/array column types Postgres would otherwise give us.
That trade was worth it: a test suite that only runs where Postgres happens to be installed is a
test suite that quietly stops running in more environments than one that only needs a file.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    """One row per onboarded university. `slug` is the single identifier used everywhere:
    the on-disk directory name, the widget URL segment, and the CLI's `--tenant` argument —
    deliberately one name, not three, to avoid drift between them (see ARCHITECTURE.md §3)."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    widget_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    documents: Mapped[list["Document"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class Document(Base):
    """One row per uploaded document. Tracks ingestion status and lightweight metadata only —
    the chunk text and embeddings for this document live exclusively in this tenant's vector
    store (see retrieval/vector_store.py), not here. `checksum` makes re-uploading the same
    file idempotent (ingestion/pipeline.py checks it before doing any parsing work)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "markdown" | "pdf"
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processing")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="documents")


class ChatLog(Base):
    """Anonymous per-question usage record: no user identity, no session id, no IP. Exists so
    the operator (and eventually a tenant) can see usage volume and, importantly, which
    questions the assistant abstained on — a strong signal of a documentation gap. See
    ARCHITECTURE.md §3 for why this table is deliberately limited to non-identifying fields."""

    __tablename__ = "chat_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_doc_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    answered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
