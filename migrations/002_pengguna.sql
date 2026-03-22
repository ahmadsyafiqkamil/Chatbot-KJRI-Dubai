-- Migration 002: Tabel pengguna untuk identitas user chatbot
-- Jalankan manual: psql -U postgres -d rag_kjri -f migrations/002_pengguna.sql

CREATE TABLE IF NOT EXISTS pengguna (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              VARCHAR(255)    NOT NULL,
    nama_lengkap            VARCHAR(255)    NOT NULL,
    nomor_paspor            VARCHAR(20),
    nomor_ic                VARCHAR(30),
    nomor_telepon           VARCHAR(20),
    email                   VARCHAR(255),
    alamat_domisili         TEXT,
    kota_domisili           VARCHAR(100),
    jenis_identitas_lain    VARCHAR(50),
    nomor_identitas_lain    VARCHAR(50),
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pengguna_session_id ON pengguna (session_id);
CREATE INDEX IF NOT EXISTS idx_pengguna_nomor_paspor ON pengguna (nomor_paspor);
CREATE INDEX IF NOT EXISTS idx_pengguna_nama ON pengguna (nama_lengkap);

-- Tambahkan FK pengguna_id ke chat_sessions
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS pengguna_id UUID REFERENCES pengguna(id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_pengguna ON chat_sessions (pengguna_id);
