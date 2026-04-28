# Phase 1 RAG Implementation Plan
**Status**: APPROVED — Ready to implement
**Branch**: `sebelum-fase-1`
**Date**: 2026-04-28

---

## Objective

Build `chatbot_kjri_dubai/rag/` module:
1. Parse PDF/TXT/MD → plain text
2. Chunk semantically (500 token, 100 overlap)
3. Generate embedding via Gemini (`gemini-embedding-001`)
4. Store to PostgreSQL (`documents` + `document_chunks`)
5. Store to ChromaDB collection `document_chunks`

---

## Package Audit (as of 2026-04-28)

| Package | Status | Note |
|---------|--------|------|
| `pypdf` | ✅ | PDF parser |
| `llama_index.core` 0.14.20 | ✅ | SentenceSplitter, SimpleDirectoryReader |
| `tiktoken` | ✅ | Token counting |
| `chromadb` 1.5.8 | ✅ | Vector store |
| `google.genai` | ✅ | Gemini embedding |
| `markdown-it-py` | ✅ | MD parsing |
| `sqlalchemy` 2.0.49 | ✅ | ORM available |
| `psycopg2` | ❌ MISSING | Tambah `psycopg2-binary` ke requirements.txt |

---

## File Structure Target

```
chatbot_kjri_dubai/rag/
├── __init__.py
├── parsers.py            # PDF/TXT/MD → str
├── chunking.py           # 500-token chunks, 100 overlap
├── embeddings.py         # Gemini embedding wrapper
├── chromadb_client.py    # ChromaDB CRUD
└── document_manager.py   # Orchestrator

tests/rag/
├── __init__.py
├── test_parsers.py
├── test_chunking.py
├── test_embeddings.py
├── test_chromadb_client.py
└── test_document_manager.py

migrations/
└── 004_documents_phase1.sql  # documents + document_chunks tables
```

---

## Implementation Order (TDD — strict RED→GREEN→REFACTOR)

### Step 0 — Pre-code setup
- [ ] Tambah `psycopg2-binary` ke `requirements.txt`
- [ ] Buat `migrations/004_documents_phase1.sql` (tabel `documents` + `document_chunks`)
- [ ] Buat folder `tests/rag/` dengan `__init__.py`
- [ ] Buat folder `chatbot_kjri_dubai/rag/` dengan `__init__.py`

### Step 1 — parsers.py
- [ ] Tulis `tests/rag/test_parsers.py` DULU (RED)
  - `parse_pdf(path)` → non-empty str
  - `parse_txt(path)` → preserves content
  - `parse_markdown(path)` → strips MD syntax
  - `parse_file(path)` → routes by extension
  - Unknown extension → `ValueError`
- [ ] Implement `chatbot_kjri_dubai/rag/parsers.py` (GREEN)

### Step 2 — chunking.py
- [ ] Tulis `tests/rag/test_chunking.py` DULU (RED)
  - Setiap chunk ≤ 500 token (verified via tiktoken)
  - Tidak ada chunk kosong
  - Short text → exactly 1 chunk
  - Long text → multiple chunks dengan overlap
- [ ] Implement `chatbot_kjri_dubai/rag/chunking.py` (GREEN)
  - Gunakan `llama_index.core.node_parser.SentenceSplitter(chunk_size=500, chunk_overlap=100)`

### Step 3 — embeddings.py
- [ ] Tulis `tests/rag/test_embeddings.py` DULU (RED) — mock Gemini API
  - Return `list[float]`
  - Dimensi konsisten 3072
  - Empty text → `ValueError`
  - API error → `EmbeddingError`
- [ ] Implement `chatbot_kjri_dubai/rag/embeddings.py` (GREEN)
  - `google.genai`, model `gemini-embedding-001`, task `RETRIEVAL_DOCUMENT`

### Step 4 — chromadb_client.py
- [ ] Tulis `tests/rag/test_chromadb_client.py` DULU (RED) — mock ChromaDB
  - `get_or_create_collection(name)` → collection
  - `upsert_chunks(collection, chunks)` → no error
  - `query_chunks(collection, embedding, n_results)` → list
  - `delete_document(collection, doc_id)` → no error
- [ ] Implement `chatbot_kjri_dubai/rag/chromadb_client.py` (GREEN)
  - Connect via `CHROMA_URL` env (default: `http://localhost:8001`)

### Step 5 — document_manager.py
- [ ] Tulis `tests/rag/test_document_manager.py` DULU (RED) — mock all deps
  - `upload_document(file_path, title, tags) → doc_id`
  - Full pipeline dipanggil secara berurutan
  - INSERT ke `documents` tabel → dapat `doc_id`
  - Setiap chunk INSERT ke `document_chunks`
  - Setiap chunk upsert ke ChromaDB
- [ ] Implement `chatbot_kjri_dubai/rag/document_manager.py` (GREEN)

---

## Acceptance Criteria

- [ ] `pytest tests/rag/ -v` → ≥80% coverage, 0 failures
- [ ] `from chatbot_kjri_dubai.rag import DocumentManager` → no import error
- [ ] Upload PDF dummy → `documents` + `document_chunks` di PostgreSQL terisi
- [ ] Upload PDF dummy → ChromaDB collection `document_chunks` terisi
- [ ] `bash scripts/smoke_phase0.sh` → masih semua PASS (no regression)

---

## Key Decisions

- PDF: `pypdf` (already installed, simple API)
- Chunking: `SentenceSplitter` from llama_index
- Token counting: `tiktoken` encoder `cl100k_base`
- Embedding: `gemini-embedding-001` via `google.genai`
- ChromaDB: `HttpClient` connects to Docker service
- PostgreSQL: `psycopg2` (need to install psycopg2-binary)
- Tests: unit tests mock all external deps; no Docker required for tests

---

## Scope Boundaries (JANGAN dilakukan)

- Jangan buat retrieval pipeline (Phase 2)
- Jangan modifikasi `agent.py` atau `telegram_bot.py`
- Jangan buat API endpoint untuk upload
- Jangan install package baru kecuali `psycopg2-binary`
- Jangan push/PR dulu

---

## Resume Instructions (jika context hilang)

1. Baca file ini: `docs/phase1-rag-plan.md`
2. Cek checklist di atas — temukan step terakhir yang sudah ✅
3. Lanjutkan dari step berikutnya yang masih `[ ]`
4. Selalu TDD: tulis test dulu, baru implementasi
5. Setelah semua step selesai, jalankan acceptance criteria

```bash
# Check current state:
ls chatbot_kjri_dubai/rag/
ls tests/rag/
pytest tests/rag/ -v --tb=short 2>/dev/null || echo "tests belum ada"
```
