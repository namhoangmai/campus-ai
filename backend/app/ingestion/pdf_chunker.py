"""Two-tier PDF chunking: heading-heuristic first, fixed-size fallback second.

Full rationale in ARCHITECTURE.md §4.4. Short version: PDFs vary wildly in whether they carry
real, extractable heading structure. When the font-size heuristic below finds enough heading
candidates to build a usable outline, splitting follows that outline (mirrors the Markdown
path). When it doesn't (a dense regulations PDF, a table-heavy form), the document falls back
to fixed-size overlapping chunks tagged with page numbers, so PDFs with no detectable structure
still produce correctly-cited, retrievable chunks instead of one giant unstructured blob.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.base import Chunk, ExtractedDocument
from app.ingestion.pdf_extractor import extract_heading_candidates

_HEADING_FONT_RATIO = 1.15   # heading font must be >= 1.15x the modal body font size
_HEADING_MAX_CHARS = 80      # headings are short lines, not full sentences
_MIN_HEADING_DENSITY = 1 / 1500  # need >= 1 heading per ~1500 chars of body to trust the outline

_FALLBACK_CHUNK_SIZE = 800
_FALLBACK_CHUNK_OVERLAP = 150


def chunk_pdf(doc: ExtractedDocument, raw_bytes: bytes) -> list[Chunk]:
    candidates = extract_heading_candidates(raw_bytes)
    body_font_size = _modal_font_size(candidates)
    headings = [
        (page, text) for page, text, size in candidates
        if size >= body_font_size * _HEADING_FONT_RATIO and len(text) <= _HEADING_MAX_CHARS
    ]

    if len(doc.body) > 0 and (len(headings) / max(len(doc.body), 1)) >= _MIN_HEADING_DENSITY:
        return _chunk_by_headings(doc, headings)
    return _chunk_fixed_size(doc)


def _modal_font_size(candidates: list[tuple[int, str, float]]) -> float:
    sizes = [size for _page, _text, size in candidates if size]
    if not sizes:
        return 0.0
    return max(set(sizes), key=sizes.count)


def _chunk_by_headings(doc: ExtractedDocument, headings: list[tuple[int, str]]) -> list[Chunk]:
    """Split doc.page_texts at detected heading lines, section = from one heading to the next."""
    assert doc.page_texts is not None
    heading_set = {text for _page, text in headings}

    sections: list[tuple[int, list[str]]] = []  # (start_page, lines)
    current_page = 1
    current_lines: list[str] = []

    for page_number, page_text in enumerate(doc.page_texts, start=1):
        for line in page_text.splitlines():
            if line.strip() in heading_set and current_lines:
                sections.append((current_page, current_lines))
                current_lines = []
                current_page = page_number
            current_lines.append(line)
        if not current_lines:
            current_page = page_number
    if current_lines:
        sections.append((current_page, current_lines))

    chunks: list[Chunk] = []
    for i, (start_page, lines) in enumerate(sections):
        text = "\n".join(lines).strip()
        if not text:
            continue
        metadata = {
            "source_id": doc.source_id,
            "title": doc.title,
            "doc_type": "pdf",
            "page": start_page,
            **doc.metadata,
        }
        chunks.append(Chunk(chunk_id=f"{doc.source_id}::{i}", text=text, chunk_index=i, metadata=metadata))
    return chunks


def _chunk_fixed_size(doc: ExtractedDocument) -> list[Chunk]:
    """Fixed-size overlapping chunks over the full document text, with each chunk tagged with
    the page number its *starting* character falls on (computed from doc.page_texts lengths)."""
    assert doc.page_texts is not None
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_FALLBACK_CHUNK_SIZE, chunk_overlap=_FALLBACK_CHUNK_OVERLAP
    )
    pieces = splitter.split_text(doc.body)

    # Precompute cumulative character offsets per page so we can map a chunk's start offset
    # back to a page number without re-scanning the whole document for every chunk.
    page_boundaries: list[int] = []
    offset = 0
    for page_text in doc.page_texts:
        offset += len(page_text) + 2  # +2 for the "\n\n" join separator in extract_pdf
        page_boundaries.append(offset)

    chunks: list[Chunk] = []
    search_from = 0
    for i, text in enumerate(pieces):
        start = doc.body.find(text, search_from)
        if start == -1:
            start = doc.body.find(text)
        search_from = max(start, 0)
        page = _page_for_offset(start if start != -1 else 0, page_boundaries)
        metadata = {
            "source_id": doc.source_id,
            "title": doc.title,
            "doc_type": "pdf",
            "page": page,
            **doc.metadata,
        }
        chunks.append(Chunk(chunk_id=f"{doc.source_id}::{i}", text=text, chunk_index=i, metadata=metadata))
    return chunks


def _page_for_offset(offset: int, page_boundaries: list[int]) -> int:
    for page_number, boundary in enumerate(page_boundaries, start=1):
        if offset < boundary:
            return page_number
    return len(page_boundaries) or 1
