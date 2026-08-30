"""Read-only access to the vector index built by build_index.py"""

import chromadb

from build_index import COLLECTION_NAME, VECTORSTORE_DIR, get_embedding_function

def get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
    return client.get_collection(name=COLLECTION_NAME, embedding_function=get_embedding_function())

def retrieve(query: str, k: int = 4) -> list[dict]:
    collection = get_collection()
    results = collection.query(query_texts=query, n_results=k)
    
    chunks = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    
    for content, meta in zip(documents, metadatas):
        chunks.append(
            {
                "content": content,
                "source": meta.get("source"),
                "title": meta.get("title"),
                "source_url": meta.get("source_url"),
            }
        )
    return chunks