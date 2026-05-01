-- Migration 007: Add last_activity_at to handoff_queue for inactivity timeout
-- Jalankan manual: psql -U postgres -d rag_kjri -f migrations/007_handoff_last_activity.sql

ALTER TABLE handoff_queue
    ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_handoff_last_activity ON handoff_queue(last_activity_at)
    WHERE status IN ('pending', 'in_progress');
