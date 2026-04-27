-- Migration 003: Phase 0 RAG tables (chat_history + retrieval_analytics)
-- Jalankan manual: psql -U postgres -d rag_kjri -f migrations/003_rag_phase0.sql
-- Atau otomatis via docker-entrypoint-initdb.d (hanya saat init pertama kali)

-- Pastikan extensions tersedia
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- Chat history untuk RAG context (berbeda dari chat_sessions yang untuk logging)
CREATE TABLE IF NOT EXISTS public.chat_history (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      VARCHAR(255)    NOT NULL,
    role            VARCHAR(20)     NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content         TEXT            NOT NULL,
    metadata        JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON public.chat_history (session_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON public.chat_history (created_at DESC);

-- Retrieval analytics: mencatat performa pipeline retrieval
CREATE TABLE IF NOT EXISTS public.retrieval_analytics (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          VARCHAR(255),
    query               TEXT            NOT NULL,
    retrieval_method    VARCHAR(50)     NOT NULL,
    top_k               INTEGER,
    latency_ms          INTEGER,
    results             JSONB           NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_analytics_session_id  ON public.retrieval_analytics (session_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_analytics_created_at  ON public.retrieval_analytics (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_retrieval_analytics_method      ON public.retrieval_analytics (retrieval_method);
