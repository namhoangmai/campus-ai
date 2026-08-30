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
    ("###", "h3"),
]

def get_client() -> chromadb.ClientAPI:
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
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

def build_index() -> int:
    client = get_client()
    existing = {c.name for c in client.list_collections()}
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
        
    collection = client.create_collection(
        name=COLLECTION_NAME, embedding_function=get_embedding_function()
    )
    
    docs = load_raw_docs(RAW_DIR)
    print(f"[build_index] loaded {len(docs)} file(s) from {RAW_DIR}")
    
    ids, texts, metadatas = [], [], []
    for doc in docs:
        doc_ids, doc_texts, docs_metadata = chunk_document(doc)
        ids.extend(doc_ids)
        texts.extend(doc_texts)
        metadatas.extend(doc_metadatas)
        
    if not texts:
        print("[build index] no chunks to index")
        return 0
    
    collection.add(ids=ids, documents=texts, metadatas=metadatas)
    print(f"[build index] indexed {len(texts)} chunks into '{COLLECTION_NAME}' at {VECTORSTORE_DIR}")
    return len(texts)

def upsert_document(
    source: str,
    title: str,
    source_url: str,
    content: str,
    extra_metadata: dict | None = None,
) -> int:
    """
    Add or update one document's chunks in the persistent collection
    
    Used by live scraping
    """
    client = get_client()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME, embedding_function=get_embedding_function()
    )
    
    # rescraping can change its chunk, so drop previous chunks and add new ones
    collection.delete(where={"source": source})
    
    ids, texts, metadatas = chunk_document(
        {
            "source": source,
            "title": title,
            "source_url": source_url,
            "content": content,
            "extra_metadata": extra_metadata,
        }
    )
    if not texts:
        print(f"[build index] upsert_document({source!r}) -> no chunks, nothing to index")
        return 0
    
    collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
    print(f"[build index] upsert_document({source!r}) -> {len(texts)} chunk(s) indexed at {VECTORSTORE_DIR}")
    
if __name__ == "__main__":
    build_index()