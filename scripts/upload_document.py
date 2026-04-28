#!/usr/bin/env python3
"""
Unggah PDF, TXT, atau Markdown ke PostgreSQL + ChromaDB (RAG).

Penggunaan:
  python3 scripts/upload_document.py /path/ke/dokumen.pdf --title "Panduan Paspor 2025"
  python3 scripts/upload_document.py ./faq.md --title FAQ --tags panduan,faq

Prasyarat (jalankan dari host, bukan di dalam container agent):
  pip install -r requirements-rag.txt
  Atau minimal: psycopg2-binary chromadb google-generativeai tiktoken pypdf python-dotenv

Layanan Docker harus menyala (postgres + chromadb). Port lokal: Postgres 5432, Chroma 8001.
"""

from __future__ import annotations

import argparse
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


def _conn_params():
    return {
        "conn_string": (
            f"host={os.environ.get('POSTGRES_HOST', 'localhost')} "
            f"port={os.environ.get('POSTGRES_PORT', '5432')} "
            f"dbname={os.environ.get('POSTGRES_DB', 'rag_kjri')} "
            f"user={os.environ.get('POSTGRES_USER', 'postgres')} "
            f"password={os.environ.get('POSTGRES_PASSWORD', 'postgres')}"
        ),
        "chroma_host": "localhost",
        "chroma_port": int(os.environ.get("CHROMA_LOCAL_PORT", "8001")),
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload dokumen ke RAG (PDF / TXT / MD).")
    parser.add_argument("file", type=Path, help="Path ke .pdf, .txt, .md")
    parser.add_argument("--title", type=str, default=None, help="Judul di database (default: nama file)")
    parser.add_argument(
        "--tags",
        type=str,
        default="",
        help="Tag dipisah koma, contoh: paspor,2025",
    )
    args = parser.parse_args()

    file_path: Path = args.file.resolve()
    if not file_path.exists():
        print(f"ERROR: file tidak ada: {file_path}", file=sys.stderr)
        return 1

    suffix_supported = {".pdf", ".txt", ".md", ".markdown"}
    if file_path.suffix.lower() not in suffix_supported:
        print(f"ERROR: ekstensi tidak didukung. Gunakan: {sorted(suffix_supported)}", file=sys.stderr)
        return 1

    params = _conn_params()
    if not params["gemini_api_key"]:
        print("ERROR: set GEMINI_API_KEY di .env atau environment.", file=sys.stderr)
        return 1

    title = args.title or file_path.stem
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    from chatbot_kjri_dubai.rag.document_manager import DocumentManager

    dm = DocumentManager(
        conn_string=params["conn_string"],
        chroma_host=params["chroma_host"],
        chroma_port=params["chroma_port"],
        gemini_api_key=params["gemini_api_key"],
    )

    print(f"Upload: {file_path} → title={title!r}")
    doc_id = dm.upload_document(file_path, title=title, tags=tags or None)
    print(f"Selesai. document_id={doc_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
