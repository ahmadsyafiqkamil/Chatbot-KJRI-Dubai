-- Create documents table for RAG system
-- Stores metadata about uploaded documents

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL CHECK (source IN ('pdf', 'markdown', 'txt')),
    original_filename VARCHAR(255) NOT NULL,
    content_text TEXT NOT NULL,
    file_size_bytes INTEGER,
    uploaded_by UUID,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,
    tags JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_documents_title ON documents USING GIN (to_tsvector('english', title));
CREATE INDEX idx_documents_is_active ON documents(is_active);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX idx_documents_source ON documents(source);
