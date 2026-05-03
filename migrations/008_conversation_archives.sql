-- Migration 008: Conversation closure archives
-- Jalankan manual: docker exec -i kjri_postgres psql -U postgres -d rag_kjri < migrations/008_conversation_archives.sql

CREATE TABLE IF NOT EXISTS conversation_archives (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  TEXT        NOT NULL,
    channel     TEXT        NOT NULL,
    "on"        TEXT        NOT NULL,
    transcript  JSONB       NOT NULL,
    pengguna_id UUID        REFERENCES pengguna(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_archives_session_id  ON conversation_archives(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_archives_created_at  ON conversation_archives(created_at);
