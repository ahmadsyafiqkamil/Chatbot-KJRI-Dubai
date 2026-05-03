-- Migration 006: Human Agent Handoff queue table
-- Jalankan manual: psql -U postgres -d rag_kjri -f migrations/006_handoff_queue.sql

CREATE TABLE IF NOT EXISTS handoff_queue (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          TEXT        NOT NULL,
    pengguna_id         UUID        REFERENCES pengguna(id),
    user_chat_id        BIGINT      NOT NULL,
    nama_user           TEXT,
    pertanyaan_terakhir TEXT,
    layanan_dicari      TEXT,
    status              TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'in_progress', 'resolved')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_handoff_session_id ON handoff_queue(session_id);
CREATE INDEX IF NOT EXISTS idx_handoff_status     ON handoff_queue(status);
