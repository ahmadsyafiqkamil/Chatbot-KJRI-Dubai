-- Migration 001: Tabel chat_sessions untuk logging penggunaan chatbot
-- Jalankan manual: psql -U postgres -d rag_kjri -f migrations/001_chat_sessions.sql
-- Atau otomatis via docker-entrypoint-initdb.d (hanya saat init pertama kali)

CREATE TABLE IF NOT EXISTS chat_sessions (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      VARCHAR(255)    NOT NULL,
    nama_pengguna   VARCHAR(255),
    layanan_diminta VARCHAR(255),
    pesan_user      TEXT,
    pesan_agent     TEXT,
    jumlah_pesan    INTEGER         DEFAULT 1,
    tools_dipanggil JSONB           DEFAULT '[]'::jsonb,
    channel         VARCHAR(50)     DEFAULT 'web',
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_session_id ON chat_sessions (session_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_created_at ON chat_sessions (created_at);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_layanan ON chat_sessions (layanan_diminta);
