#!/usr/bin/env python3
"""
Script verifikasi RAG retrieval pipeline.

Jalankan dari root project setelah upload_test_doc.py:
  python scripts/test_rag_retrieval.py

Catatan: Koneksi lokal (bukan dari dalam Docker).
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

POSTGRES_USER     = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB       = os.environ.get("POSTGRES_DB", "rag_kjri")
POSTGRES_HOST     = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT     = os.environ.get("POSTGRES_PORT", "5432")

CONN_STRING = (
    f"host={POSTGRES_HOST} port={POSTGRES_PORT} "
    f"dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
)
CHROMA_URL    = "http://localhost:8001"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def print_results(label: str, results: list):
    print(f"\n{'='*60}")
    print(f"  {label} — {len(results)} hasil")
    print(f"{'='*60}")
    if not results:
        print("  (tidak ada hasil)")
        return
    for i, r in enumerate(results, 1):
        snippet = (r.get("chunk_text") or r.get("content", ""))[:120].replace("\n", " ")
        score   = r.get("score", 0)
        doc_id  = r.get("document_id", "?")
        print(f"  [{i}] score={score:.4f} | doc={doc_id}")
        print(f"      {snippet}...")


def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY tidak di-set.")
        sys.exit(1)

    from chatbot_kjri_dubai.rag.retrieval import retriever_from_env

    os.environ.setdefault("CHROMA_URL", CHROMA_URL)
    os.environ.setdefault("POSTGRES_HOST", POSTGRES_HOST)
    os.environ.setdefault("POSTGRES_PORT", POSTGRES_PORT)
    os.environ.setdefault("POSTGRES_DB", POSTGRES_DB)
    os.environ.setdefault("POSTGRES_USER", POSTGRES_USER)
    os.environ.setdefault("POSTGRES_PASSWORD", POSTGRES_PASSWORD)

    print("Membuat Retriever...")
    r = retriever_from_env()

    # 1. Keyword search
    q1 = "paspor hilang laporan polisi"
    kw = r.keyword_search(q1, top_k=5)
    print_results(f"Keyword: '{q1}'", kw)

    # 2. Semantic search
    q2 = "dokumen yang diperlukan jika paspor tidak ada"
    sem = r.semantic_search(q2, top_k=5)
    print_results(f"Semantic: '{q2}'", sem)

    # 3. Hybrid search
    q3 = "berapa biaya paspor hilang"
    hyb = r.hybrid_retrieve(q3, top_k=5, alpha=0.4)
    print_results(f"Hybrid: '{q3}'", hyb)

    print("\n✓ RAG retrieval pipeline berfungsi dengan baik.")


if __name__ == "__main__":
    main()
