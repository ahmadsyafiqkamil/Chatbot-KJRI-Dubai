"""Phase 2 RAG: Multi-stage retrieval pipeline.

Stages:
  1. Keyword Search  — PostgreSQL FTS via plainto_tsquery('simple', ...)
  2. Semantic Search — ChromaDB cosine similarity via Gemini embeddings
  3. Hybrid Rerank   — Score fusion: alpha*keyword + (1-alpha)*semantic
"""

import os
from typing import List, Optional

import psycopg2

from .chromadb_client import ChromaDBClient
from .embeddings import embed_text

_KEYWORD_SEARCH_SQL = """
    SELECT id, chunk_text, document_id,
           ts_rank(search_vector, plainto_tsquery('simple', %s)) AS score
    FROM document_chunks
    WHERE search_vector @@ plainto_tsquery('simple', %s)
    ORDER BY score DESC
    LIMIT %s
"""


def _normalize_scores(results: List[dict]) -> List[dict]:
    """Normalize scores to [0, 1]. Does not mutate input dicts."""
    if not results:
        return []
    scores = [r["score"] for r in results]
    min_s, max_s = min(scores), max(scores)
    if max_s == min_s:
        normalized = 1.0 if max_s > 0 else 0.0
        return [{**r, "score": normalized} for r in results]
    return [{**r, "score": (r["score"] - min_s) / (max_s - min_s)} for r in results]


class Retriever:
    def __init__(
        self,
        conn_string: str,
        chroma_host: str = "localhost",
        chroma_port: int = 8001,
        gemini_api_key: Optional[str] = None,
    ):
        self._conn_string = conn_string
        self._chroma = ChromaDBClient(host=chroma_host, port=chroma_port)
        self._api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")

    def keyword_search(self, query: str, top_k: int = 10) -> List[dict]:
        """Search document_chunks using PostgreSQL FTS (language: simple)."""
        with psycopg2.connect(self._conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(_KEYWORD_SEARCH_SQL, (query, query, top_k))
                rows = cur.fetchall()
        return [
            {
                "chunk_id": str(row[0]),
                "chunk_text": row[1],
                "document_id": str(row[2]),
                "score": float(row[3]),
            }
            for row in rows
        ]

    def semantic_search(self, query: str, top_k: int = 10) -> List[dict]:
        """Search document_chunks using ChromaDB cosine similarity."""
        embedding = embed_text(query, api_key=self._api_key)
        collection = self._chroma.get_or_create_collection("document_chunks")
        raw = self._chroma.query_chunks(collection, embedding, n_results=top_k)
        return [
            {
                "chunk_id": r["id"],
                "chunk_text": r["content"],
                "document_id": r["metadata"].get("document_id", ""),
                "score": max(0.0, 1.0 - r["distance"]),
            }
            for r in raw
        ]

    def hybrid_retrieve(
        self,
        query: str,
        top_k: int = 10,
        alpha: float = 0.4,
    ) -> List[dict]:
        """Merge keyword + semantic results with score fusion.

        Score = alpha * keyword_norm + (1 - alpha) * semantic_norm
        Chunks appearing in both stages are deduplicated.
        """
        kw_results = self.keyword_search(query, top_k=top_k)
        sem_results = self.semantic_search(query, top_k=top_k)

        kw_norm = _normalize_scores(kw_results)
        sem_norm = _normalize_scores(sem_results)

        merged: dict = {}
        for r in kw_norm:
            cid = r["chunk_id"]
            merged[cid] = {
                "chunk_id": cid,
                "chunk_text": r["chunk_text"],
                "document_id": r["document_id"],
                "kw_score": r["score"],
                "sem_score": 0.0,
            }
        for r in sem_norm:
            cid = r["chunk_id"]
            if cid in merged:
                merged[cid]["sem_score"] = r["score"]
            else:
                merged[cid] = {
                    "chunk_id": cid,
                    "chunk_text": r["chunk_text"],
                    "document_id": r["document_id"],
                    "kw_score": 0.0,
                    "sem_score": r["score"],
                }

        results = [
            {
                "chunk_id": v["chunk_id"],
                "chunk_text": v["chunk_text"],
                "document_id": v["document_id"],
                "score": alpha * v["kw_score"] + (1 - alpha) * v["sem_score"],
            }
            for v in merged.values()
        ]
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
