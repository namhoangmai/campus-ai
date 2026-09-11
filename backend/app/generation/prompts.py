"""Tenant-aware system prompt and context assembly.

v1 hardcoded "You are the TU/e admission and enrollment assistant" directly into the system
prompt string. v2 templates the institution name in per tenant (`build_system_prompt`) so the
same code serves every tenant correctly instead of copy-pasting/branching the prompt file per
university. `build_context` also now branches on `doc_type` to render PDF citations (title +
page) alongside markdown citations (title + URL) — see ARCHITECTURE.md §6 for why this replaces
v1's implicit "URL or silently blank" behavior.
"""

import textwrap

from app.models import Tenant


def build_system_prompt(tenant: Tenant) -> str:
    return textwrap.dedent(
        f"""
        You are the {tenant.name} assistant. Answer the student's question using ONLY the
        context provided below, which comes exclusively from documents {tenant.name} has
        provided. If the context does not contain the answer, say so clearly instead of
        guessing, and suggest the student check with {tenant.name} directly. Do not include a
        "Sources" section or citation links yourself -- the app displays source links
        separately below your answer. Be concise.
        """
    ).strip()


def build_context(retrieved_chunks: list[dict]) -> str:
    if not retrieved_chunks:
        return "(no context available)"

    parts = []
    for chunk in retrieved_chunks:
        title = chunk.get("title", "Untitled")
        if chunk.get("doc_type") == "pdf":
            locator = f"page {chunk.get('page')}" if chunk.get("page") else "page unknown"
        else:
            locator = chunk.get("source_url") or "no URL available"
        parts.append(f"### {title} ({locator})\n\n{chunk.get('content', '')}")
    return "\n\n---\n\n".join(parts)


def build_messages(tenant: Tenant, question: str, chat_history: list[dict], retrieved_chunks: list[dict]):
    context = build_context(retrieved_chunks)
    messages = [{"role": "system", "content": build_system_prompt(tenant)}]
    messages.extend(chat_history)
    messages.append({"role": "user", "content": f"Context:\n\n{context}\n\n---\n\nQuestion: {question}"})
    return messages
