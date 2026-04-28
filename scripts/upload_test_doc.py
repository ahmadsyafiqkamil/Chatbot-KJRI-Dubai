#!/usr/bin/env python3
"""
Script upload dokumen test untuk verifikasi RAG pipeline.

Jalankan dari root project:
  python scripts/upload_test_doc.py

Prasyarat:
  - PostgreSQL berjalan di localhost:5432
  - ChromaDB berjalan di localhost:8001
  - GEMINI_API_KEY di environment (atau .env)
  - pip install -r requirements-rag.txt  (atau: psycopg2-binary chromadb google-genai tiktoken pypdf python-dotenv)

Catatan: Koneksi lokal (bukan dari dalam Docker).
"""

import os
import sys
import tempfile
from pathlib import Path

# Load .env jika ada
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Tambah root project ke sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

POSTGRES_USER     = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB       = os.environ.get("POSTGRES_DB", "rag_kjri")
POSTGRES_HOST     = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT     = os.environ.get("POSTGRES_PORT", "5432")

CHROMA_HOST = "localhost"
CHROMA_PORT = 8001  # port lokal (docker-compose maps 8001->8000)

CONN_STRING = (
    f"host={POSTGRES_HOST} port={POSTGRES_PORT} "
    f"dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY tidak di-set. Tambahkan ke .env atau environment.")
    sys.exit(1)

TEST_CONTENT = """Panduan Layanan Paspor KJRI Dubai

== PASPOR HILANG ==
Persyaratan wajib:
- Laporan polisi dari kepolisian setempat (asli + fotokopi)
- Bukti identitas: Emirates ID / Visa UAE (asli + fotokopi)
- Formulir permohonan dari KJRI (diisi di lokasi)
- Pas foto 4x6 cm, background merah, 2 lembar

Biaya: AED 50
Proses: 3 hari kerja setelah berkas lengkap.

Catatan: Jika perlu paspor segera (emergency), sampaikan saat pengajuan.

== PASPOR HABIS MASA BERLAKU (EXPIRED) ==
Persyaratan wajib:
- Paspor lama (asli + fotokopi halaman data diri)
- Emirates ID / Visa UAE (asli + fotokopi)
- Formulir permohonan KJRI
- Pas foto 4x6 cm, background merah, 2 lembar

Biaya: AED 200 (paspor 5 tahun), AED 300 (paspor 10 tahun)
Proses: 7–14 hari kerja.

== PASPOR RUSAK ==
Persyaratan sama dengan paspor hilang, tambahkan paspor rusak (asli).
Biaya: AED 50.

== JAM OPERASIONAL ==
Senin–Jumat: 09.00–12.00 (penerimaan berkas)
Pengambilan: 14.00–16.00
Sabtu, Minggu, Hari Libur UAE & Indonesia: TUTUP

== KONTAK ==
KJRI Dubai
Telepon: +971-4-3971222
Email: kjridubai@kemlu.go.id
Alamat: Jl. Al Mina, Dubai, UAE
"""

def main():
    from chatbot_kjri_dubai.rag.document_manager import DocumentManager

    print(f"Menghubungkan ke PostgreSQL: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    print(f"Menghubungkan ke ChromaDB: {CHROMA_HOST}:{CHROMA_PORT}")

    dm = DocumentManager(
        conn_string=CONN_STRING,
        chroma_host=CHROMA_HOST,
        chroma_port=CHROMA_PORT,
        gemini_api_key=GEMINI_API_KEY,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(TEST_CONTENT)
        tmp_path = f.name

    try:
        print("\nMeng-upload dokumen test 'Panduan Paspor KJRI Dubai'...")
        doc_id = dm.upload_document(
            tmp_path,
            title="Panduan Paspor KJRI Dubai",
            tags=["paspor", "panduan", "test"],
        )
        print(f"Berhasil! Document ID: {doc_id}")
        return doc_id
    finally:
        Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
