# Advanced RAG Implementation Masterplan
**Date:** 2026-04-17
**Project:** Chatbot-KJRI-Dubai
**Approach:** Hybrid (ChromaDB + PostgreSQL) with Advanced Retrieval Pipeline
**Total Estimated Duration:** 8-10 weeks (~15-20 hrs/week)

---

## 1. Executive Summary

This masterplan outlines a comprehensive **General Knowledge Base + Advanced RAG implementation** for the KJRI Dubai chatbot. The system will support:
- Multi-stage retrieval (keyword → semantic → reranking)
- Chat history management with context windows
- Advanced prompt engineering for consistent responses
- Document management (PDF, TXT, Markdown parsing via LlamaIndex)
- Semantic chunking for optimal retrieval accuracy
- Analytics and optimization tracking

**Architecture:** Hybrid approach using ChromaDB (vectors) + PostgreSQL (metadata, history, audit)

---

## 2. Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Embedding Model** | Gemini (`gemini-embedding-001`) | Already integrated, 768-dim vectors, good quality |
| **PDF Parser** | LlamaIndex | Robust PDF extraction, supports complex layouts, built-in chunking strategies |
| **Chunking Strategy** | Semantic (paragraph-aware) | Better retrieval accuracy, respects document structure |
| **Vector Store** | ChromaDB | Direct integration, supports metadata filtering, good for semantic search |
| **Metadata Storage** | PostgreSQL | Audit trail, chat history, permissions, analytics |
| **Reranking** | Cross-encoder (Phase 2) | Improve ranking quality for ambiguous queries |
| **LLM Provider** | Keep Gemini (`.env`: `LLM_PROVIDER=gemini`) | Consistent with current setup |

---

## 3. Database Schema Changes

### New Tables

#### `documents` (PostgreSQL)
```sql
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title VARCHAR(255) NOT NULL,
  source VARCHAR(100) NOT NULL,  -- 'pdf', 'markdown', 'txt', 'web'
  original_filename VARCHAR(255),
  content_text TEXT,
  file_size_bytes INT,
  uploaded_by VARCHAR(100),
  upload_date TIMESTAMP DEFAULT NOW(),
  last_modified TIMESTAMP DEFAULT NOW(),
  version INT DEFAULT 1,
  tags JSONB DEFAULT '{}',  -- {'category': 'consular', 'language': 'id'}
  metadata JSONB DEFAULT '{}',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_documents_source ON documents(source);
CREATE INDEX idx_documents_tags ON documents USING GIN(tags);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
```

#### `document_chunks` (PostgreSQL)
```sql
CREATE TABLE document_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_number INT NOT NULL,
  chunk_text TEXT NOT NULL,
  chunk_tokens INT,
  start_char INT,
  end_char INT,
  is_embedded BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
```

#### `chat_history` (PostgreSQL)
```sql
CREATE TABLE chat_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id VARCHAR(255) NOT NULL,
  user_id UUID,
  role VARCHAR(10) NOT NULL,  -- 'user' or 'agent'
  message_text TEXT NOT NULL,
  embedding_id VARCHAR(255),  -- reference to ChromaDB
  retrieved_doc_ids UUID[],  -- which documents were retrieved for this message
  tools_called JSONB,  -- {'cari-layanan': {'params': {...}, 'result': {...}}}
  confidence_score FLOAT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_history_session ON chat_history(session_id);
CREATE INDEX idx_history_user ON chat_history(user_id);
CREATE INDEX idx_history_created_at ON chat_history(created_at DESC);
```

#### `retrieval_analytics` (PostgreSQL)
```sql
CREATE TABLE retrieval_analytics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_text TEXT NOT NULL,
  query_embedding_id VARCHAR(255),
  retrieved_doc_ids UUID[],
  retrieval_score FLOAT,
  user_satisfaction INT,  -- 1-5 rating (optional)
  is_successful BOOLEAN,
  execution_time_ms INT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_analytics_created_at ON retrieval_analytics(created_at DESC);
```

### ChromaDB Collections

#### `document_chunks` collection
```
{
  id: "chunk-<document_id>-<chunk_number>",
  embedding: [...],
  metadata: {
    document_id: "<uuid>",
    document_title: "...",
    chunk_number: 1,
    source: "pdf",
    tags: {...},
    uploaded_date: "2026-04-17"
  }
}
```

#### `chat_history` collection
```
{
  id: "msg-<session_id>-<timestamp>",
  embedding: [...],
  metadata: {
    session_id: "...",
    user_id: "<uuid>",
    role: "user|agent",
    retrieved_doc_ids: ["...", "..."],
    timestamp: "2026-04-17T10:30:00Z"
  }
}
```

---

## 4. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          User / Agent                               │
└────────────┬────────────────────────────────────────────────────────┘
             │
             │ Query
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Query Processing Layer                           │
├─────────────────────────────────────────────────────────────────────┤
│  1. Expand Query (generate variants with LLM)                       │
│  2. Multi-Stage Retrieval:                                          │
│     Stage 1: Keyword Search (PostgreSQL FTS)                        │
│     Stage 2: Semantic Search (ChromaDB)                             │
│     Stage 3: Reranking (combine scores)                             │
│  3. Retrieve Relevant Chat History (ChromaDB similarity)            │
│  4. Assemble Context (with token counting)                          │
└────────────┬────────────────────────────────────────────────────────┘
             │
        ┌────┴──────────────────────────────────┐
        │                                       │
        ▼                                       ▼
┌──────────────────────────────┐     ┌──────────────────────────────┐
│      PostgreSQL              │     │      ChromaDB                │
├──────────────────────────────┤     ├──────────────────────────────┤
│ ✓ documents                  │     │ ✓ document_chunks            │
│ ✓ document_chunks            │     │ ✓ chat_history               │
│ ✓ chat_history               │     │ ✓ metadata filtering         │
│ ✓ retrieval_analytics        │     │ ✓ vector similarity search   │
│ ✓ FTS (keyword search)       │     │                              │
│ ✓ Metadata + Audit Trail     │     │                              │
└──────────────────────────────┘     └──────────────────────────────┘
        │                                       │
        └────────────┬─────────────────────────┘
                     │
                     ▼
        ┌──────────────────────────────┐
        │   LLM (Gemini)               │
        │  + Structured Prompt         │
        │  + Few-shot Examples         │
        │  + Chat History Context      │
        └──────────────────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │  Agent Response│
            └────────────────┘
```

---

## 5. Project Phases & Timeline

### **PHASE 1: Foundation & Infrastructure (Weeks 1-3)**

#### Phase 1.1: Database Schema & ChromaDB Setup (Week 1)
- [ ] Create PostgreSQL tables (documents, chunks, chat_history, analytics)
- [ ] Setup ChromaDB collections (document_chunks, chat_history)
- [ ] Create indexes for performance
- [ ] Write migration scripts

#### Phase 1.2: LlamaIndex Integration & Document Parsing (Week 2)
- [ ] Install & configure LlamaIndex
- [ ] Implement PDF parser (handle images, multi-page)
- [ ] Implement TXT parser
- [ ] Implement Markdown parser
- [ ] Error handling for malformed documents
- [ ] Test with sample KJRI documents

#### Phase 1.3: Semantic Chunking Pipeline (Week 3)
- [ ] Implement semantic chunking (paragraph-aware)
- [ ] Configure chunk size (500 tokens target)
- [ ] Implement overlap strategy (100-token overlap)
- [ ] Batch embedding generation (Gemini API)
- [ ] Store chunks in PostgreSQL + ChromaDB
- [ ] Test chunking quality on various document types

**Deliverables:**
- ✅ Document upload API endpoint
- ✅ Chunking pipeline working
- ✅ Embeddings stored in both databases

---

### **PHASE 2: Multi-Stage Retrieval Pipeline (Weeks 4-5)**

#### Phase 2.1: Keyword Search (Week 4)
- [ ] Implement PostgreSQL full-text search (FTS)
- [ ] BM25 scoring algorithm
- [ ] Fuzzy matching (handle typos)
- [ ] Metadata filtering (by source, date, tags)
- [ ] Return top 10 results with scores

#### Phase 2.2: Semantic Search (Week 4)
- [ ] Query embedding generation
- [ ] ChromaDB similarity search
- [ ] Metadata filtering support
- [ ] Configurable similarity threshold (default 0.5)
- [ ] Return top 10 results with similarity scores

#### Phase 2.3: Hybrid Ranking & Reranking (Week 5)
- [ ] Combine keyword + semantic scores (weighted average)
- [ ] Deduplicate results
- [ ] Final ranking (top 5)
- [ ] Fallback logic (if semantic fails, keyword only)
- [ ] Logging & metrics collection

**Deliverables:**
- ✅ Retrieval pipeline working end-to-end
- ✅ Support multi-stage retrieval
- ✅ Metrics: precision, recall, execution time

---

### **PHASE 3: Chat History & Context Management (Weeks 6-7)**

#### Phase 3.1: Chat History Storage (Week 6)
- [ ] Store all user-agent messages in PostgreSQL + ChromaDB
- [ ] Embed each message for similarity search
- [ ] Link to session + user
- [ ] Store metadata (retrieved docs, tools called)
- [ ] Implement retention policy (90 days)

#### Phase 3.2: Relevant History Retrieval (Week 6)
- [ ] Similarity search in chat history
- [ ] Rank by recency + relevance
- [ ] Return top 5 relevant messages
- [ ] Support session/user filtering
- [ ] Anonymization (optional)

#### Phase 3.3: Context Window Management (Week 7)
- [ ] Token counting utility
- [ ] Select last N messages (configurable, default 5)
- [ ] Or select top K by relevance
- [ ] Truncate if exceeds budget (4000 tokens)
- [ ] Maintain conversation coherence when truncating

**Deliverables:**
- ✅ Chat history fully integrated
- ✅ Context assembly for LLM input
- ✅ Token budget management

---

### **PHASE 4: Agent Integration & E2E Testing (Weeks 8-9)**

#### Phase 4.1: Agent Integration (Week 8)
- [ ] Integrate retrieval pipeline into `agent.py`
- [ ] Update agent tools (add retrieval tools)
- [ ] Implement query expansion (LLM generates variants)
- [ ] Structured prompt template for RAG
- [ ] Fallback strategies for low-confidence retrievals

#### Phase 4.2: E2E Flow Testing (Week 8-9)
- [ ] Test complete flow: query → retrieval → LLM response
- [ ] Test with various query types (specific vs. vague)
- [ ] Test fallback scenarios (no results, low confidence)
- [ ] Performance testing (response latency)
- [ ] Integration with existing KJRI tools

#### Phase 4.3: Optimization & Tuning (Week 9)
- [ ] Profile retrieval pipeline (identify bottlenecks)
- [ ] Optimize chunking strategy (A/B test)
- [ ] Tune ranking weights
- [ ] Cache optimization (ChromaDB queries)
- [ ] Load testing

**Deliverables:**
- ✅ Agent fully integrated with RAG pipeline
- ✅ All flows tested and working
- ✅ Performance benchmarks documented

---

### **PHASE 5: Analytics, Monitoring & Polish (Week 10)**

#### Phase 5.1: Analytics Dashboard
- [ ] Implement query analytics (top queries, zero-results, failed queries)
- [ ] Retrieval metrics (precision@5, recall@10, MRR)
- [ ] User satisfaction tracking
- [ ] Export functionality for analysis

#### Phase 5.2: Monitoring & Logging
- [ ] Structured logging for all retrieval operations
- [ ] Error tracking & alerting
- [ ] Performance monitoring (latency, throughput)
- [ ] Data quality checks (embeddings, chunks)

#### Phase 5.3: Documentation & Demo
- [ ] System architecture documentation
- [ ] API documentation
- [ ] Operational guide (how to add documents, manage KB)
- [ ] Demo & deployment guide

**Deliverables:**
- ✅ Analytics dashboard live
- ✅ Monitoring alerts configured
- ✅ Complete documentation

---

## 6. Epics & User Stories (with Progress Tracking)

### **EPIC 1: Document Management & Ingestion**

#### US 1.1: Upload & Parse Documents
**Status:** ⬜ Not Started
**Phase:** 1.2
**Effort:** 3 days

```
As a knowledge base admin
I want to upload PDF/TXT/Markdown documents
So that I can expand the knowledge base without manual data entry

Acceptance Criteria:
- [ ] Upload single or multiple files via API (`POST /api/documents/upload`)
- [ ] Support PDF, TXT, Markdown formats
- [ ] Extract text from PDFs using LlamaIndex (handle images gracefully)
- [ ] Store original file + metadata in PostgreSQL `documents` table
- [ ] Return success/error with document ID
- [ ] Error handling (invalid format, corrupted file, size limit)
- [ ] File size limit: 50MB per document
```

#### US 1.2: Document Chunking with Semantic Strategy
**Status:** ⬜ Not Started
**Phase:** 1.3
**Effort:** 4 days

```
As a RAG system
I want to automatically chunk documents into optimal sizes
So that semantic search is accurate and efficient

Acceptance Criteria:
- [ ] Implement semantic chunking (split on paragraph boundaries)
- [ ] Target chunk size: ~500 tokens (configurable)
- [ ] Overlap between chunks: 100 tokens
- [ ] Store chunk mappings (which chunk from which document)
- [ ] Preserve original text positions (start_char, end_char)
- [ ] Support reconfigurable chunk size for A/B testing
- [ ] Performance: chunk 1000-page PDF in <2 minutes
```

#### US 1.3: Batch Embedding Generation
**Status:** ⬜ Not Started
**Phase:** 1.3
**Effort:** 3 days

```
As a RAG system
I want to generate embeddings for all document chunks
So that I can perform semantic search

Acceptance Criteria:
- [ ] Batch embed chunks (1000 chunks at a time)
- [ ] Use Gemini `gemini-embedding-001` API
- [ ] Store embeddings in ChromaDB with metadata
- [ ] Handle API rate limits (implement backoff)
- [ ] Support re-embedding when document updated
- [ ] Cost tracking (log embedding cost per document)
- [ ] Retry logic for failed embeddings
```

---

### **EPIC 2: Multi-Stage Retrieval Pipeline**

#### US 2.1: Keyword Search with BM25
**Status:** ⬜ Not Started
**Phase:** 2.1
**Effort:** 3 days

```
As a retrieval system
I want to search documents using keyword matching
So that users get fast, exact-match results when available

Acceptance Criteria:
- [ ] PostgreSQL full-text search (FTS) implementation
- [ ] BM25 scoring algorithm
- [ ] Fuzzy matching (Levenshtein distance for typos)
- [ ] Metadata filtering (by source, date, tags)
- [ ] Return top 10 matching documents with scores
- [ ] Performance: search 10,000 chunks in <200ms
- [ ] Support AND/OR/NOT operators
```

#### US 2.2: Semantic Search via ChromaDB
**Status:** ⬜ Not Started
**Phase:** 2.2
**Effort:** 3 days

```
As a retrieval system
I want to search documents using vector similarity
So that users get results even with different wording

Acceptance Criteria:
- [ ] Query embedding generation (Gemini API)
- [ ] ChromaDB similarity search (top 10)
- [ ] Return similarity scores (0-1)
- [ ] Metadata filtering support (source, date, tags)
- [ ] Configurable similarity threshold (default 0.5)
- [ ] Performance: semantic search in <300ms
- [ ] Handle empty queries gracefully
```

#### US 2.3: Hybrid Ranking & Reranking
**Status:** ⬜ Not Started
**Phase:** 2.3
**Effort:** 4 days

```
As a retrieval system
I want to combine keyword + semantic scores
So that I return the most relevant documents

Acceptance Criteria:
- [ ] Combine BM25 + semantic scores (weighted average)
- [ ] Configurable weights (default: 0.3 keyword + 0.7 semantic)
- [ ] Deduplicate results (same document from both stages)
- [ ] Return final top 5 documents
- [ ] Fallback logic (if semantic fails → keyword only)
- [ ] Support A/B testing different weight combinations
- [ ] Log all retrieval operations with scores
```

---

### **EPIC 3: Chat History & Context Management**

#### US 3.1: Store & Retrieve Chat History
**Status:** ⬜ Not Started
**Phase:** 3.1
**Effort:** 3 days

```
As a system
I want to store all user-agent interactions
So that I can provide context-aware responses

Acceptance Criteria:
- [ ] Store all messages (user + agent) in PostgreSQL
- [ ] Embed each message in ChromaDB for similarity search
- [ ] Link to session + user ID
- [ ] Store metadata (retrieved docs, tools called, confidence)
- [ ] Retention policy: keep 90 days, archive older
- [ ] Support querying history by session/user
- [ ] Performance: insert 1000 messages/hour without lag
```

#### US 3.2: Retrieve Relevant History
**Status:** ⬜ Not Started
**Phase:** 3.2
**Effort:** 2 days

```
As an agent
I want to find previous messages related to current query
So that I can maintain conversation continuity

Acceptance Criteria:
- [ ] Similarity search in chat history (ChromaDB)
- [ ] Return top 5 relevant messages
- [ ] Rank by recency (recent > old) + relevance (similar > dissimilar)
- [ ] Support filtering by session/user
- [ ] Exclude personal data (optional anonymization)
- [ ] Performance: retrieve history in <100ms
```

#### US 3.3: Context Window Management
**Status:** ⬜ Not Started
**Phase:** 3.3
**Effort:** 3 days

```
As an agent
I want to assemble optimal context for LLM
So that responses are accurate without overloading token budget

Acceptance Criteria:
- [ ] Token counting utility (estimate LLM input size)
- [ ] Select last N messages (configurable, default 5)
- [ ] Or select top K by relevance score
- [ ] Assemble context: system prompt + history + retrieved docs + query
- [ ] Truncate if exceeds budget (4000 tokens for Gemini)
- [ ] Maintain conversation coherence when truncating
- [ ] Log context assembly (tokens used, documents included)
```

---

### **EPIC 4: Agent Integration & Advanced Features**

#### US 4.1: Integrate Retrieval Pipeline into Agent
**Status:** ⬜ Not Started
**Phase:** 4.1
**Effort:** 4 days

```
As an agent
I want to use the retrieval pipeline for all queries
So that I provide accurate, document-backed responses

Acceptance Criteria:
- [ ] Create retrieval service module (Python)
- [ ] Integrate into `chatbot_kjri_dubai/agent.py`
- [ ] Add retrieval tools to agent tools list
- [ ] Test integration with existing KJRI tools
- [ ] Support fallback (if retrieval fails, use LLM knowledge)
- [ ] Log all retrieval operations
```

#### US 4.2: Implement Query Expansion
**Status:** ⬜ Not Started
**Phase:** 4.1
**Effort:** 2 days

```
As a retrieval system
I want to expand user queries with variants
So that I catch more relevant documents

Acceptance Criteria:
- [ ] Use LLM to generate 3-5 query variants
- [ ] Search with all variants
- [ ] Merge and deduplicate results
- [ ] Measure improvement in recall
- [ ] Optional feature (can disable if too slow)
```

#### US 4.3: Structured Prompt Template for RAG
**Status:** ⬜ Not Started
**Phase:** 4.1
**Effort:** 2 days

```
As an agent
I want to use structured prompts for RAG
So that responses are consistent and actionable

Acceptance Criteria:
- [ ] Design prompt template with sections:
  - System instruction (role, behavior)
  - Retrieved context (documents with source attribution)
  - Chat history (relevant past messages)
  - Current query
- [ ] Include few-shot examples (3-5)
- [ ] Output formatting instructions
- [ ] Support prompt versioning/A/B testing
```

#### US 4.4: Fallback & Error Handling
**Status:** ⬜ Not Started
**Phase:** 4.1
**Effort:** 2 days

```
As a system
I want to handle cases where retrieval fails
So that agent always provides helpful response

Acceptance Criteria:
- [ ] Detect low-confidence retrievals (similarity < 0.5)
- [ ] Fall back to keyword-only search
- [ ] If still no results, use general LLM knowledge
- [ ] Tell user "I don't have specific documents, but here's general guidance"
- [ ] Log failed retrievals (for future KB improvement)
- [ ] Test all fallback paths
```

---

### **EPIC 5: Analytics & Optimization**

#### US 5.1: Query Analytics Dashboard
**Status:** ⬜ Not Started
**Phase:** 5.1
**Effort:** 3 days

```
As an admin
I want to see which queries are searched and their success rate
So that I can identify gaps in the knowledge base

Acceptance Criteria:
- [ ] Log all queries (text, results, execution time)
- [ ] Dashboard showing:
  - Top 20 queries (by frequency)
  - Failed queries (zero results)
  - Slow queries (>500ms)
  - User satisfaction (optional rating)
- [ ] Filterable by date range, query type
- [ ] Export to CSV
```

#### US 5.2: Retrieval Quality Metrics
**Status:** ⬜ Not Started
**Phase:** 5.1
**Effort:** 3 days

```
As a system
I want to measure retrieval quality
So that I can optimize the pipeline

Acceptance Criteria:
- [ ] Implement metrics:
  - Precision@5 (are top 5 relevant?)
  - Recall@10 (are all relevant docs in top 10?)
  - MRR (Mean Reciprocal Rank)
- [ ] A/B test different chunking strategies
- [ ] A/B test different ranking weights
- [ ] Track metrics over time
```

---

## 7. Dependencies & Risks

### Critical Dependencies
1. **Gemini API availability** (for embeddings) → Mitigation: fallback to open-source embeddings
2. **ChromaDB stability** → Mitigation: regular backups to PostgreSQL
3. **LlamaIndex PDF parsing** → Mitigation: handle edge cases with fallback parsers
4. **PostgreSQL performance** (FTS on large documents) → Mitigation: indexes, query optimization

### Technical Risks
| Risk | Impact | Mitigation |
|------|--------|-----------|
| **PDF parsing failures** (complex layouts, images, corrupted) | Medium | Implement robust error handling, test with diverse PDFs |
| **Embedding API rate limits/costs** | Medium | Batch processing, cost tracking, optional caching |
| **Vector similarity not matching user intent** | Medium | Implement reranking, user feedback loop, prompt engineering |
| **Token budget overflow** | Low | Implement token counting, context window management |
| **ChromaDB memory issues with large KB** | Low | Implement pagination, metadata filtering |

---

## 8. Success Metrics

### Functional Metrics
- ✅ All user stories completed with acceptance criteria met
- ✅ E2E flow working (query → retrieval → response)
- ✅ All 5 phases delivered

### Performance Metrics
- **Retrieval latency:** < 300ms (semantic search) + < 200ms (keyword search)
- **Embedding generation:** 1000 chunks in < 2 minutes
- **Database query:** < 100ms (history retrieval)
- **Context assembly:** < 50ms (token counting + truncation)

### Quality Metrics
- **Retrieval precision@5:** > 80% (manually evaluated)
- **Recall@10:** > 85%
- **Zero-result queries:** < 5% of total queries
- **Fallback usage:** < 10% of queries

### Learning Outcomes
- ✅ Understand embedding models & vector similarity
- ✅ Master chunking strategies (fixed vs. semantic)
- ✅ Implement multi-stage retrieval pipeline
- ✅ Learn prompt engineering for RAG systems
- ✅ Understand reranking & ranking algorithms
- ✅ Know chat history management & context windows
- ✅ Can build RAG system from scratch

---

## 9. Progress Tracking Template

Use this format when updating progress:

```
# Session: [Date] [Focus Area]
## Completed
- [US-X.X] Task description ✅

## In Progress
- [US-X.X] Task description (X% complete)

## Blocked
- [US-X.X] Task description (reason)

## Notes
- [Learning notes, decisions made]
```

---

## 10. File Structure & Setup

```
Chatbot-KJRI-Dubai/
├── docs/superpowers/specs/
│   └── 2026-04-17-advanced-rag-masterplan.md (THIS FILE)
├── chatbot_kjri_dubai/
│   ├── agent.py (update with RAG integration)
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── document_manager.py (upload, parse, chunk)
│   │   ├── embeddings.py (Gemini embedding)
│   │   ├── retrieval.py (multi-stage retrieval)
│   │   ├── chromadb_client.py (ChromaDB integration)
│   │   ├── history_manager.py (chat history)
│   │   └── prompt_templates.py (structured prompts)
│   └── migrations/
│       ├── 001_documents_table.sql
│       ├── 002_chunks_table.sql
│       ├── 003_chat_history_table.sql
│       └── 004_analytics_table.sql
├── tests/
│   ├── test_rag_pipeline.py
│   ├── test_retrievals.py
│   └── test_e2e_flow.py
└── README-RAG.md (usage guide)
```

---

## 11. Next Steps

1. ✅ **Approve this masterplan** (review, ask questions, suggest changes)
2. ⬜ **Write implementation plan** (detailed technical tasks, code structure)
3. ⬜ **Begin Phase 1** (Week 1: PostgreSQL schema, ChromaDB setup)
4. ⬜ **Regular progress updates** (track in this file)

---

**Last Updated:** 2026-04-17
**Status:** ⏳ Awaiting Approval
