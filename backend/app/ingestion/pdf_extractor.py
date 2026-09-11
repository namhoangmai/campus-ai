"""Extract text (and per-character font sizes, for the chunker's heading heuristic) from a PDF.

Uses `pdfplumber` rather than `PyMuPDF` — see ARCHITECTURE.md §4.3 for the licensing (AGPL vs.
MIT) reasoning behind that choice. OCR is explicitly out of scope: a PDF that extracts no text
at all is reported as a failed document rather than silently indexing nothing (ARCHITECTURE.md
§4.3), so a bad upload is visible to the admin instead of surfacing later as "the chatbot
doesn't know about this" from a confused university.
"""

import io

import pdfplumber

from app.ingestion.base import ExtractedDocument


class NoExtractableTextError(Exception):
    """Raised when a PDF yields no text at all — most likely a scanned/image-only PDF, which
    requires OCR (explicitly out of scope, ARCHITECTURE.md §4.3/§12)."""


def extract_pdf(source_id: str, filename: str, content: bytes) -> ExtractedDocument:
    page_texts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_texts.append(page.extract_text() or "")

    if not any(t.strip() for t in page_texts):
        raise NoExtractableTextError(
            f"{filename!r} yielded no extractable text — likely a scanned/image-only PDF (OCR is out of scope)."
        )

    body = "\n\n".join(page_texts)
    title = filename.rsplit(".", 1)[0]

    return ExtractedDocument(
        source_id=source_id,
        title=title,
        doc_type="pdf",
        body=body,
        page_texts=page_texts,
        metadata={"page_count": len(page_texts)},
    )


def extract_heading_candidates(content: bytes) -> list[tuple[int, str, float]]:
    """Return (page_number, line_text, dominant_font_size) for every line in the PDF, so the
    chunker can apply the font-size heuristic described in ARCHITECTURE.md §4.4 without
    re-opening the PDF itself. page_number is 1-indexed.
    """
    lines: list[tuple[int, str, float]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for line in _group_chars_into_lines(page.chars):
                text = "".join(c["text"] for c in line).strip()
                if not text:
                    continue
                dominant_size = _dominant_font_size(line)
                lines.append((page_number, text, dominant_size))
    return lines


def _group_chars_into_lines(chars: list[dict], y_tolerance: float = 3.0) -> list[list[dict]]:
    """Group pdfplumber's flat character list into visual lines by vertical position. A
    from-scratch line-reconstruction, not a pdfplumber built-in, because pdfplumber gives
    characters, not lines, and the heading heuristic needs per-line font size."""
    if not chars:
        return []
    sorted_chars = sorted(chars, key=lambda c: (round(c["top"] / y_tolerance), c["x0"]))
    lines: list[list[dict]] = []
    current_line: list[dict] = []
    current_top: float | None = None
    for c in sorted_chars:
        if current_top is None or abs(c["top"] - current_top) <= y_tolerance:
            current_line.append(c)
            current_top = c["top"] if current_top is None else current_top
        else:
            lines.append(current_line)
            current_line = [c]
            current_top = c["top"]
    if current_line:
        lines.append(current_line)
    return lines


def _dominant_font_size(line: list[dict]) -> float:
    sizes = [round(c.get("size", 0.0), 1) for c in line if c.get("size")]
    if not sizes:
        return 0.0
    return max(set(sizes), key=sizes.count)
