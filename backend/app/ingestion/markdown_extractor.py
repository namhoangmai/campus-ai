"""Extract title + body + metadata from a Markdown file with YAML front matter.

Carried over from v1 almost unchanged (v1's `load_raw_docs()` in `build_index.py`) — this path
was already correct and simple; the only change is returning the shared `ExtractedDocument`
shape (ingestion/base.py) instead of a bespoke dict, so it plugs into the same chunking/pipeline
code the PDF path uses.
"""

import io

import frontmatter

from app.ingestion.base import ExtractedDocument


def extract_markdown(source_id: str, filename: str, content: bytes) -> ExtractedDocument:
    try:
        post = frontmatter.load(io.BytesIO(content))
        title = post.get("title") or filename
        source_url = post.get("source_url") or None
        body = post.content
        extra_metadata = {k: v for k, v in post.metadata.items() if k not in ("title", "source_url")}
    except Exception:
        # Malformed front matter: index the raw text rather than failing the whole upload,
        # matching v1's documented fallback behavior in build_index.py's load_raw_docs().
        title = filename
        source_url = None
        body = content.decode("utf-8", errors="replace")
        extra_metadata = {}

    return ExtractedDocument(
        source_id=source_id,
        title=title,
        doc_type="markdown",
        body=body,
        source_url=source_url,
        metadata=extra_metadata,
    )
