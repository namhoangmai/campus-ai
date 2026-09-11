"""Pydantic request/response models for the HTTP API.

Kept separate from models.py (the SQLAlchemy ORM layer) on purpose: an API response shape and
a database row shape are different concerns that happen to overlap today (e.g. we never want to
accidentally serialize `Tenant.widget_key` back out on a route that shouldn't reveal it) — one
file for each keeps that distinction enforced rather than implicit.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Admin: tenants ---

class TenantCreateRequest(BaseModel):
    slug: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$", description="URL/path-safe, e.g. 'tue'")
    name: str = Field(..., min_length=1, max_length=255)


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    status: str
    created_at: datetime


class TenantCreatedResponse(TenantResponse):
    """Only returned once, at creation time — the widget key is not re-displayed on later reads
    of a tenant (the operator is expected to store it when creating the tenant), mirroring how
    API-key-issuing services usually behave."""
    widget_key: str


# --- Admin: documents ---

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    filename: str
    doc_type: Literal["markdown", "pdf"]
    title: str
    status: Literal["processing", "indexed", "failed"]
    error_message: str | None = None
    chunk_count: int | None = None
    page_count: int | None = None
    uploaded_at: datetime
    indexed_at: datetime | None = None


# --- Chat (widget-key authenticated) ---

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    chat_history: list[ChatMessage] = []


class Source(BaseModel):
    title: str
    doc_type: Literal["markdown", "pdf"]
    url: str | None = None       # markdown documents that carry a source_url
    page: int | None = None      # pdf documents


class ChatResponse(BaseModel):
    reply: str
    sources: list[Source]
