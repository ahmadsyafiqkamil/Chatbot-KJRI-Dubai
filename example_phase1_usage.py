#!/usr/bin/env python3
"""
Example script to demonstrate Phase 1 RAG functionality.

Usage:
    python example_phase1_usage.py

This script shows:
1. Document parsing (TXT, PDF, Markdown)
2. Semantic chunking
3. Token estimation
4. Chunk metadata storage
"""

import tempfile
import os
from chatbot_kjri_dubai.rag.document_manager import DocumentManager
from chatbot_kjri_dubai.rag.chromadb_client import ChromaDBClient


def create_sample_txt():
    """Create a sample TXT file for testing."""
    content = """
    Layanan Konsulat Jenderal Indonesia di Dubai

    KJRI Dubai menyediakan berbagai layanan untuk warga negara Indonesia:

    1. Pembuatan Paspor
       Paspor Indonesia adalah dokumen perjalanan resmi yang diperlukan untuk meninggalkan Indonesia.
       Pemohon harus membawa KTP, akte kelahiran, surat izin orang tua (untuk anak-anak),
       dan dokumen pendukung lainnya.

    2. Legalisasi Dokumen
       Legalisasi adalah pengesahan surat atau dokumen yang dikeluarkan oleh lembaga
       pemerintah Indonesia agar diakui di luar negeri.
       Dokumen yang dapat dilegalisasi antara lain: ijazah, sertifikat, akta pernikahan.

    3. Pembuatan Akta Pernikahan
       Bagi warga negara Indonesia yang menikah di luar negeri, dapat membuat akta
       pernikahan melalui konsulat.
       Biaya pembuatan akta pernikahan adalah AED 150.

    4. Pengurusan Visa
       Konsulat membantu warga negara Indonesia dalam pengurusan visa untuk keperluan
       bisnis, kunjungan keluarga, atau bekerja.

    Untuk informasi lebih lanjut, silakan hubungi:
    KJRI Dubai - Tel: +971-4-XXX-XXXX
    Email: kjridubai@kemlu.go.id
    """
    return content


def create_sample_markdown():
    """Create a sample Markdown file for testing."""
    content = """# Persyaratan Paspor Indonesia

## Dokumen yang Dibutuhkan

- **KTP asli** (Kartu Identitas Penduduk)
- **Akte kelahiran asli** atau surat pengganti akte kelahiran
- **Buku nikah asli** (jika status sudah menikah)
- **Surat izin dari orang tua** (untuk anak di bawah 18 tahun)
- **Pas foto berwarna 4x6 cm** sebanyak 6 lembar
- **Surat keterangan sehat** dari dokter

## Biaya Pembuatan Paspor

| Tipe | Durasi Berlaku | Biaya (AED) |
|------|----------------|------------|
| Biasa | 5 tahun | 250 |
| Cepat (3 hari) | 5 tahun | 500 |
| Praktis (1 hari) | 5 tahun | 750 |

## Proses Pendaftaran

1. Ambil nomor antrian di loket pendaftaran
2. Isi formulir aplikasi
3. Serahkan dokumen ke petugas
4. Lakukan pembayaran
5. Tunggu waktu proses sesuai layanan yang dipilih

## Waktu Layanan

Konsulat buka pada hari kerja (Minggu-Kamis) jam 08:00-12:00 WIB.
"""
    return content


def main():
    """Run Phase 1 demonstration."""
    print("=" * 70)
    print("PHASE 1 RAG DEMONSTRATION - Document Parsing & Chunking")
    print("=" * 70)

    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"\n📁 Using temporary directory: {temp_dir}\n")

        # Initialize DocumentManager (without ChromaDB for demo)
        print("1️⃣ Initializing DocumentManager...")
        try:
            manager = DocumentManager(chroma_url="http://localhost:8001")
            print("   ✅ DocumentManager initialized\n")
        except Exception as e:
            print(f"   ⚠️  Warning: ChromaDB not available (expected for demo): {e}\n")
            # Continue demo even if ChromaDB is unavailable
            manager = None

        # Demo 1: TXT File Processing
        print("2️⃣ Processing TXT File...")
        print("-" * 70)
        txt_path = os.path.join(temp_dir, "layanan.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(create_sample_txt())

        print(f"   📄 Created: {txt_path}")
        print(f"   📊 File size: {os.path.getsize(txt_path)} bytes\n")

        if manager:
            doc_id = manager.process_and_store_document(
                txt_path,
                document_title="Layanan KJRI Dubai",
                source="txt"
            )
            print(f"   ✅ Document ID: {doc_id}")

            chunks = manager.get_processed_chunks()
            print(f"   📦 Total chunks: {len(chunks)}")

            for i, chunk in enumerate(chunks[:3]):  # Show first 3 chunks
                print(f"\n   Chunk {i}:")
                print(f"      • Position: chars {chunk.start_char}-{chunk.end_char}")
                print(f"      • Tokens: {chunk.tokens}")
                print(f"      • Text preview: {chunk.text[:80]}...")

            if len(chunks) > 3:
                print(f"   ... and {len(chunks) - 3} more chunks")

            doc_info = manager.get_processed_document_info()
            total_tokens = sum(chunk.tokens for chunk in chunks)
            print(f"\n   📋 Document Info:")
            print(f"      • Title: {doc_info['title']}")
            print(f"      • Source: {doc_info['source']}")
            print(f"      • Chunks: {doc_info['chunk_count']}")
            print(f"      • Total tokens: {total_tokens}")

        # Demo 2: Markdown File Processing
        print("\n3️⃣ Processing Markdown File...")
        print("-" * 70)
        md_path = os.path.join(temp_dir, "persyaratan.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(create_sample_markdown())

        print(f"   📄 Created: {md_path}")
        print(f"   📊 File size: {os.path.getsize(md_path)} bytes\n")

        if manager:
            doc_id = manager.process_and_store_document(
                md_path,
                document_title="Persyaratan Paspor",
                source="markdown"
            )
            print(f"   ✅ Document ID: {doc_id}")

            chunks = manager.get_processed_chunks()
            print(f"   📦 Total chunks: {len(chunks)}")

            doc_info = manager.get_processed_document_info()
            total_tokens = sum(chunk.tokens for chunk in chunks)
            print(f"   📋 Document Stats:")
            print(f"      • Chunks: {doc_info['chunk_count']}")
            print(f"      • Total tokens: {total_tokens}")
            print(f"      • Avg chunk size: {total_tokens // max(1, doc_info['chunk_count'])} tokens")

        # Demo 3: ChromaDB Client Demo (if available)
        print("\n4️⃣ ChromaDB Client Capabilities...")
        print("-" * 70)
        try:
            ChromaDBClient(chroma_url="http://localhost:8001")
            print("   ✅ ChromaDB connected")
            print("   Available methods:")
            print("      • add_document() - Add vectors to collection")
            print("      • query() - Search similar documents")
            print("      • delete_document() - Remove documents")
            print("      • get_collection_info() - Collection statistics")
        except Exception as e:
            print(f"   ⚠️  ChromaDB not available: {e}")
            print("   To use ChromaDB, run: docker compose up -d chromadb")

    print("\n" + "=" * 70)
    print("PHASE 1 DEMO COMPLETE")
    print("=" * 70)
    print("\nNext Steps:")
    print("  1. Run tests: python -m pytest tests/test_rag_integration.py -v")
    print("  2. Start Phase 2: Implement multi-stage retrieval pipeline")
    print("  3. Check masterplan: docs/superpowers/specs/2026-04-17-advanced-rag-masterplan.md")


if __name__ == "__main__":
    main()
