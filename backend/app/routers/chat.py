"""The public, widget-key-authenticated chat endpoint.

This is the one route a university's own webpage actually calls (via the widget). Tenant is
resolved exclusively from the widget key (`resolve_tenant_from_widget_key`, app/deps.py) — the
request body carries no tenant identifier, so there is no field a caller could tamper with to
read a different tenant's documents. Rate limiting is applied per widget key, since the widget
key is designed to be public (ARCHITECTURE.md §7) and this endpoint spends the operator's LLM
budget on every call.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import resolve_tenant_from_widget_key
from app.generation.llm import generate_answer
from app.generation.prompts import build_messages
from app.models import ChatLog, Tenant
from app.retrieval.retriever import retrieve
from app.schemas import ChatRequest, ChatResponse, Source
from app.security import get_rate_limiter

router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    tenant: Tenant = Depends(resolve_tenant_from_widget_key),
    db: Session = Depends(get_db),
) -> ChatResponse:
    if not get_rate_limiter().allow(tenant.widget_key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded.")

    start = time.monotonic()
    try:
        retrieved_chunks = retrieve(tenant.slug, req.question)
        messages = build_messages(
            tenant, req.question, [m.model_dump() for m in req.chat_history], retrieved_chunks
        )
        reply = generate_answer(messages)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not generate an answer: {exc}") from exc
    latency_ms = int((time.monotonic() - start) * 1000)

    seen: set[tuple[str, str | None, int | None]] = set()
    sources: list[Source] = []
    for chunk in retrieved_chunks:
        title = chunk.get("title", "Untitled")
        doc_type = chunk.get("doc_type", "markdown")
        url = chunk.get("source_url") or None
        page = chunk.get("page")
        key = (title, url, page)
        if key not in seen:
            seen.add(key)
            sources.append(Source(title=title, doc_type=doc_type, url=url, page=page))

    db.add(
        ChatLog(
            tenant_id=tenant.id,
            question=req.question,
            retrieved_doc_ids=[c.get("source_id", "") for c in retrieved_chunks],
            answered=bool(sources),
            latency_ms=latency_ms,
        )
    )
    db.commit()

    return ChatResponse(reply=reply, sources=sources)
