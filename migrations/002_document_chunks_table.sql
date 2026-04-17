-- Create document_chunks table for RAG semantic chunks
-- Stores text chunks extracted from documents with position metadata

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_number INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_tokens INTEGER,
    start_char INTEGER,
    end_char INTEGER,
    is_embedded BOOLEAN DEFAULT false,
    embedding_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX idx_document_chunks_chunk_number ON document_chunks(document_id, chunk_number);
CREATE INDEX idx_document_chunks_is_embedded ON document_chunks(is_embedded);
CREATE CONSTRAINT unique_chunk_per_doc UNIQUE (document_id, chunk_number);
