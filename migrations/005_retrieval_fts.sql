-- Migration 005: Phase 2 — Full-text search index for retrieval pipeline
-- Jalankan manual: psql -U postgres -d rag_kjri -f migrations/005_retrieval_fts.sql

-- Tambah generated column tsvector ke document_chunks (schema aktual: kolom chunk_text)
ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', coalesce(chunk_text, ''))) STORED;

-- GIN index untuk performa FTS
CREATE INDEX IF NOT EXISTS idx_document_chunks_fts
    ON document_chunks USING GIN (search_vector);
