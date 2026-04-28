"""Phase 2 RAG: Multi-stage retrieval pipeline.

Stages:
  1. Keyword — PostgreSQL FTS untuk kandidat + Okapi BM25 di Python
  2. Semantic — ChromaDB cosine similarity via Gemini embeddings
  3. Hybrid — score fusion (bobot alpha) atau Reciprocal Rank Fusion (RRF)
"""

import math
import os
import re
from typing import Dict, List, Literal, Optional, Tuple
from urllib.parse import urlparse

import psycopg2

from .chromadb_client import ChromaDBClient
from .embeddings import embed_text

_COUNT_CHUNKS_SQL = "SELECT COUNT(*)::bigint FROM document_chunks"

_AVG_DOC_LEN_SQL = """
    SELECT COALESCE(
        AVG(
            GREATEST(
                array_length(
                    regexp_split_to_array(trim(coalesce(chunk_text, '')), '\\s+'),
                    1
                ),
                1
            )
        )::float,
        1.0
    )
    FROM document_chunks
    WHERE chunk_text IS NOT NULL AND trim(chunk_text) <> ''
"""

_DF_BATCH_SQL = """
    SELECT t.term, COUNT(dc.id)::bigint
    FROM unnest(%s::text[]) AS t(term)
    LEFT JOIN document_chunks dc
        ON dc.search_vector @@ plainto_tsquery('simple', t.term)
    GROUP BY t.term
"""

_KEYWORD_CANDIDATES_SQL = """
    SELECT id, chunk_text, document_id
    FROM document_chunks
    WHERE search_vector @@ plainto_tsquery('simple', %s)
    LIMIT %s
"""

# Legacy: single-query ts_rank (dipakai jika use_bm25=False)
_KEYWORD_SEARCH_TS_RANK_SQL = """
    SELECT id, chunk_text, document_id,
           ts_rank(search_vector, plainto_tsquery('simple', %s)) AS score
    FROM document_chunks
    WHERE search_vector @@ plainto_tsquery('simple', %s)
    ORDER BY score DESC
    LIMIT %s
"""

WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

_DEFAULT_BM25_K1 = 1.2
_DEFAULT_BM25_B = 0.75
_DEFAULT_CANDIDATE_POOL = 80


def _parse_chroma_host_port(
    chroma_url: Optional[str] = None,
) -> Tuple[str, int]:
    raw = chroma_url or os.environ.get("CHROMA_URL", "http://localhost:8000")
    parsed = urlparse(raw)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000
    return host, port


def _tokenize(text: str) -> List[str]:
    return [m.group(0).lower() for m in WORD_RE.finditer(text or "")]


def _okapi_bm25_for_doc(
    chunk_text: str,
    query_terms: List[str],
    df_by_term: Dict[str, int],
    n_docs: int,
    avg_doc_len: float,
    k1: float = _DEFAULT_BM25_K1,
    b: float = _DEFAULT_BM25_B,
) -> float:
    """Okapi BM25 untuk satu dokumen (chunk). query_terms sudah lowercased."""
    if not query_terms or n_docs <= 0 or avg_doc_len <= 0:
        return 0.0
    doc_tokens = _tokenize(chunk_text)
    if not doc_tokens:
        return 0.0
    dl = float(len(doc_tokens))
    score = 0.0
    for term in query_terms:
        df = df_by_term.get(term, 0)
        # IDF Robertson-Sparck Jones (bounded)
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        tf = sum(1 for w in doc_tokens if w == term)
        if tf == 0:
            continue
        denom = tf + k1 * (1.0 - b + b * (dl / avg_doc_len))
        score += idf * ((tf * (k1 + 1.0)) / denom)
    return score


def _normalize_scores(results: List[dict]) -> List[dict]:
    """Normalize scores to [0, 1]. Does not mutate input dicts."""
    if not results:
        return []
    scores = [r["score"] for r in results]
    min_s, max_s = min(scores), max(scores)
    if max_s == min_s:
        # Multiple equal items → neutral 0.5 (can't distinguish them).
        # Single item still gets 1.0 (it's the only comparison available).
        neutral = 0.5 if (max_s > 0 and len(results) > 1) else (1.0 if max_s > 0 else 0.0)
        return [{**r, "score": neutral} for r in results]
    return [{**r, "score": (r["score"] - min_s) / (max_s - min_s)} for r in results]


def _reciprocal_rank_fusion(
    kw_results: List[dict],
    sem_results: List[dict],
    k: int = 60,
) -> List[dict]:
    """RRF: sum 1/(k+rank) per daftar; chunk_text dari entri pertama yang ada."""
    accum: Dict[str, dict] = {}
    for rank, r in enumerate(kw_results):
        cid = r["chunk_id"]
        accum[cid] = {
            "chunk_id": cid,
            "chunk_text": r["chunk_text"],
            "document_id": r["document_id"],
            "score": 1.0 / (k + rank + 1),
        }
    for rank, r in enumerate(sem_results):
        cid = r["chunk_id"]
        contrib = 1.0 / (k + rank + 1)
        if cid in accum:
            accum[cid]["score"] += contrib
        else:
            accum[cid] = {
                "chunk_id": cid,
                "chunk_text": r["chunk_text"],
                "document_id": r["document_id"],
                "score": contrib,
            }
    out = list(accum.values())
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


class Retriever:
    def __init__(
        self,
        conn_string: str,
        chroma_host: Optional[str] = None,
        chroma_port: Optional[int] = None,
        gemini_api_key: Optional[str] = None,
        chroma_url: Optional[str] = None,
    ):
        self._conn_string = conn_string
        if chroma_host is not None and chroma_port is not None:
            host, port = chroma_host, chroma_port
        else:
            host, port = _parse_chroma_host_port(chroma_url)
        self._chroma = ChromaDBClient(host=host, port=port)
        self._api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")

    def keyword_search(
        self,
        query: str,
        top_k: int = 10,
        *,
        use_bm25: bool = True,
        candidate_pool: int = _DEFAULT_CANDIDATE_POOL,
    ) -> List[dict]:
        """Keyword stage: FTS untuk kandidat, lalu Okapi BM25 (atau ts_rank legacy)."""
        if not use_bm25:
            return self._keyword_search_ts_rank(query, top_k)

        terms = _tokenize(query)
        if not terms:
            return []

        with psycopg2.connect(self._conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(_COUNT_CHUNKS_SQL)
                row = cur.fetchone()
                n_docs = int(row[0]) if row else 0
                if n_docs == 0:
                    return []

                cur.execute(_AVG_DOC_LEN_SQL)
                row = cur.fetchone()
                avg_doc_len = float(row[0]) if row else 1.0

                cur.execute(_DF_BATCH_SQL, (terms,))
                df_by_term: Dict[str, int] = {
                    row[0]: int(row[1]) for row in cur.fetchall()
                }

                cur.execute(_KEYWORD_CANDIDATES_SQL, (query, candidate_pool))
                raw_rows = cur.fetchall()

        scored: List[dict] = []
        for row in raw_rows:
            cid, ctext, doc_id = str(row[0]), row[1], str(row[2])
            s = _okapi_bm25_for_doc(
                ctext or "",
                terms,
                df_by_term,
                n_docs,
                avg_doc_len,
            )
            scored.append(
                {
                    "chunk_id": cid,
                    "chunk_text": ctext,
                    "document_id": doc_id,
                    "score": s,
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _keyword_search_ts_rank(self, query: str, top_k: int) -> List[dict]:
        with psycopg2.connect(self._conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(_KEYWORD_SEARCH_TS_RANK_SQL, (query, query, top_k))
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
        *,
        fusion: Literal["weighted", "rrf"] = "weighted",
        rrf_k: int = 60,
        keyword_use_bm25: bool = True,
    ) -> List[dict]:
        """Gabungkan keyword + semantic: bobot linear atau RRF."""
        kw_results = self.keyword_search(
            query, top_k=top_k, use_bm25=keyword_use_bm25
        )
        sem_results = self.semantic_search(query, top_k=top_k)

        if fusion == "rrf":
            merged = _reciprocal_rank_fusion(kw_results, sem_results, k=rrf_k)
            return merged[:top_k]

        kw_norm = _normalize_scores(kw_results)
        sem_norm = _normalize_scores(sem_results)

        merged_lists: dict = {}
        for r in kw_norm:
            cid = r["chunk_id"]
            merged_lists[cid] = {
                "chunk_id": cid,
                "chunk_text": r["chunk_text"],
                "document_id": r["document_id"],
                "kw_score": r["score"],
                "sem_score": 0.0,
            }
        for r in sem_norm:
            cid = r["chunk_id"]
            if cid in merged_lists:
                merged_lists[cid]["sem_score"] = r["score"]
            else:
                merged_lists[cid] = {
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
            for v in merged_lists.values()
        ]
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


def retriever_from_env() -> Retriever:
    """Bangun Retriever dari env: DATABASE_URL atau komponen POSTGRES_* + CHROMA_URL."""
    url = os.environ.get("DATABASE_URL")
    if url:
        conn = url
    else:
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", "postgres")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ.get("POSTGRES_DB", "rag_kjri")
        conn = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return Retriever(conn)
