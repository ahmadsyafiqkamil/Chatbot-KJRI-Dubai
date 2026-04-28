"""ChromaDB CRUD client."""

from typing import Any, Dict, List

import chromadb


class ChromaDBClient:
    def __init__(self, host: str = "localhost", port: int = 8001):
        self._client = chromadb.HttpClient(host=host, port=port)

    def get_or_create_collection(self, name: str):
        return self._client.get_or_create_collection(name=name)

    def upsert_chunks(self, collection, chunks: List[Dict[str, Any]]) -> None:
        if not chunks:
            return
        collection.upsert(
            ids=[c["id"] for c in chunks],
            documents=[c["content"] for c in chunks],
            embeddings=[c["embedding"] for c in chunks],
            metadatas=[c.get("metadata", {}) for c in chunks],
        )

    def query_chunks(self, collection, query_embedding: List[float], n_results: int = 5) -> List[Dict]:
        raw = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
        )
        results = []
        for i, chunk_id in enumerate(raw["ids"][0]):
            results.append({
                "id": chunk_id,
                "content": raw["documents"][0][i],
                "metadata": raw["metadatas"][0][i],
                "distance": raw["distances"][0][i],
            })
        return results

    def delete_document(self, collection, doc_id: str) -> None:
        collection.delete(where={"document_id": doc_id})
