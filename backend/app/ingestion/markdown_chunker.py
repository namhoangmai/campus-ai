"""Header-aware chunking for Markdown documents. Unchanged approach from v1.

Clean Markdown reliably carries real heading structure, so splitting on `#`/`##`/`###` produces
chunks that align with how a human would section the document — the strongest available signal,
used whenever the source format guarantees it exists. See ARCHITECTURE.md §4.4.
"""

from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.ingestion.base import Chunk, ExtractedDocument

_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


def chunk_markdown(doc: ExtractedDocument) -> list[Chunk]:
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS, strip_headers=False)
    raw_chunks = splitter.split_text(doc.body)

    chunks: list[Chunk] = []
    for i, raw in enumerate(raw_chunks):
        text = raw.page_content.strip()
        if not text:
            continue
        metadata = {
            "source_id": doc.source_id,
            "title": doc.title,
            "doc_type": "markdown",
            "source_url": doc.source_url or "",
            **doc.metadata,
            **raw.metadata,  # h1/h2/h3 header path from the splitter
        }
        chunks.append(
            Chunk(chunk_id=f"{doc.source_id}::{i}", text=text, chunk_index=i, metadata=metadata)
        )
    return chunks
