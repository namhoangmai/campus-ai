"""The common shape every extractor produces, regardless of source document type.

See ARCHITECTURE.md §4.1 for why this shape exists and how it differs from v1's assumption
that everything was already clean Markdown with a `source_url`. `Chunk` is the corresponding
common shape every chunker produces, consumed uniformly by `retrieval/vector_store.py`.
"""

from dataclasses import dataclass, field


@dataclass
class ExtractedDocument:
    source_id: str          # stable identifier for this "document slot" within its tenant --
                             # derived from filename, deliberately NOT content/checksum, so an
                             # edited re-upload keeps the same source_id and its old chunks can
                             # be found and replaced (see ingestion/pipeline.py:ingest_document)
    title: str
    doc_type: str            # "markdown" | "pdf"
    body: str                # full extracted text (markdown: file body; pdf: concatenated page text)
    source_url: str | None = None       # markdown documents only, when known
    page_texts: list[str] | None = None  # pdf only: body text per page, in order (index 0 = page 1)
    metadata: dict = field(default_factory=dict)


@dataclass
class Chunk:
    chunk_id: str             # f"{source_id}::{chunk_index}"
    text: str
    chunk_index: int
    metadata: dict            # always includes: source_id, title, doc_type; pdf: page; markdown: source_url, headers
