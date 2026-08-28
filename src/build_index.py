from pathlib import Path

import chromadb
import frontmatter
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_text_splitters import MarkdownHeaderTextSplitter

RAW_DIR = Path("data/TUE/raw")
VECTORSTORE_DIR = Path("data/TUE/vector")
COLLECTION_NAME = "tue"

EMBEDDING_MODEL = "BAAI/bge-m3"

HEADERS = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", h3),
]

def get_client() -> chromadb.ClientAPI:
    VECTORSTORE_DIR.mkdir(parents=True, exists_ok=True)
    return chromadb.PersistentClient(path=str(VECTORSTORE_DIR))

def get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    return SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL, normalize_embeddings=True)

def load_raw_docs(raw_dir: Path) -> list[dict]:
    docs = []
    for md_file in sorted(raw_dir.glob("*.md")):
        try:
            post = frontmatter.load(md_file)
            title = post.get("title", md_file.stem)
            source_url = post.get("source_url", "")
            content = post.content
        except Exception as e:
            print(f"[build index] WARNING: malformed front matter in {md_file.name} ({e}); indexing raw text")
            title = md_file.stem
            source_url = ""
            content = md_file.read_text(encoding="utf-8")
        docs.append({"source": md_file.name, "title": title, "source_url": source_url, "content": content})
    
def chunk_document(doc: dict) -> tuple[list[str], list[str], list[dict]]:
    """
    Split one doc into chunk ids / texts / metadatas
    """
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS, strip_headers=False)
    chunks = splitter.split_text(doc["content"])
    
    ids, texts, metadatas = [], [], []
    for i, chunk in enumerate(chunks):
        if not chunk.page_content.strip():
            continue
        ids.append(f"{doc['source']}::{i}")
        texts.append(chunk.page_content)
        metadata = {
            "source": doc["source"],
            "title": doc["title"],
            "source_url": doc.get("source_url", ""),
            "chunk_index": i,
        }
        metadata.update(doc.get("extra_metadata") or {})
        metadata.update(chunk.metadata)
        metadatas.append(metadata)
    return ids, texts, metadatas

