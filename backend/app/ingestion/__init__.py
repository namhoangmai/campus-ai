"""Document ingestion: extractors (raw file -> ExtractedDocument), chunkers
(ExtractedDocument -> chunks), and pipeline.py (orchestrates extract -> chunk -> embed -> upsert
for one tenant). See ARCHITECTURE.md §4 for the design rationale.
"""
