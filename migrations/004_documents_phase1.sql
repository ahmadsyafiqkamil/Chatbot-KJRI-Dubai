-- Migration 004: Phase 1 RAG document storage tables
-- Jalankan manual: psql -U postgres -d rag_kjri -f migrations/004_documents_phase1.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- Metadata dokumen yang diupload
CREATE TABLE IF NOT EXISTS public.documents (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(500)    NOT NULL,
    source_path     TEXT,
    file_type       VARCHAR(20)     NOT NULL CHECK (file_type IN ('pdf', 'txt', 'md')),
    file_size_bytes INTEGER,
    tags            JSONB           NOT NULL DEFAULT '[]'::jsonb,
    status          VARCHAR(20)     NOT NULL DEFAULT 'processed' CHECK (status IN ('processing', 'processed', 'error')),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_title      ON public.documents (title);
CREATE INDEX IF NOT EXISTS idx_documents_file_type  ON public.documents (file_type);
CREATE INDEX IF NOT EXISTS idx_documents_status     ON public.documents (status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON public.documents (created_at DESC);

-- Chunk teks hasil parsing + chunking dokumen
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID            NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER         NOT NULL,
    content         TEXT            NOT NULL,
    token_count     INTEGER         NOT NULL,
    char_start      INTEGER,
    char_end        INTEGER,
    metadata        JSONB           NOT NULL DEFAULT '{}'::jsonb,
    embedding       vector(3072),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id  ON public.document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_chunk_index  ON public.document_chunks (document_id, chunk_index);
