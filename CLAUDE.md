# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A consular services chatbot for KJRI Dubai (Indonesian Consulate General in Dubai) that helps Indonesian citizens find information about available services, requirements, and costs. Built with Google ADK (Agent Development Kit), it responds in Bahasa Indonesia.

## Development Commands

### Setup
```bash
# Full server setup (Debian/Ubuntu)
chmod +x install.sh && ./install.sh

# Manual setup
cp .env.example .env
# Edit .env with your values, then:
docker compose up -d
```

### Running the Agent
```bash
# Start all services (PostgreSQL, Toolbox, pgAdmin, Agent, Ngrok)
docker compose up -d

# Run agent locally for development (requires LiteLLM/Ollama running)
adk web --host 0.0.0.0 --port 8000

# View logs
docker compose logs -f agent
docker compose logs -f toolbox
docker compose logs -f ngrok  # shows the public HTTPS URL
```

### Service URLs
- Agent API/UI: `http://localhost:8000`
- MCP Toolbox: `http://localhost:5001`
- pgAdmin: `http://localhost:5050`
- ChromaDB: `http://localhost:8001`
- Ollama: `http://localhost:11434`
- Ngrok dashboard: `http://localhost:4040` (shows public tunnel URL)

## Architecture

### Stack
- **Framework**: Google ADK (`google-adk`)
- **LLM routing**: LiteLLM (abstracts Ollama/Gemini)
- **Database tools**: `toolbox-adk` (MCP Toolbox v0.28.0)
- **Database**: PostgreSQL 16 with pgvector, initialized from `rag_kjri_dubai.sql` (gitignored)
- **Vector store**: ChromaDB (port 8001) — available in agent via `CHROMA_URL`
- **Containers**: Docker Compose with 6 services: `postgres`, `toolbox`, `pgadmin`, `chromadb`, `agent`, `ngrok`

### How It Works

```
User → ADK Agent (port 8000)
          ↓ tool calls
       MCP Toolbox (port 5001) → PostgreSQL (port 5432)
          ↓ LLM calls
       Ollama (local) OR Google Gemini (cloud)
```

The agent in [chatbot_kjri_dubai/agent.py](chatbot_kjri_dubai/agent.py) is the only source of agent logic. It:
1. Loads LLM config from environment (`LLM_PROVIDER`, `LLM_MODEL`)
2. Connects to MCP Toolbox at `TOOLBOX_URL` to get SQL-backed tools (search + logging)
3. Runs as a `google.adk.Agent` with an Indonesian-language system prompt

### Available Tools (via MCP Toolbox)
Defined in [toolbox/config/tools.yaml](toolbox/config/tools.yaml):
- `cari-layanan` — keyword search over consular services (returns code, name, cost in AED)
- `get-detail-layanan` — full detail for a service (requirements, costs, notes) by code or name
- `cari-layanan-semantik` — pgvector semantic search using Gemini embeddings (`gemini-embedding-001`); used when keyword search fails or user describes a situation without naming a service

Identity & logging tools:
- `simpan-identitas` — INSERT user identity (name, passport, IC, phone, email, address) into `pengguna` table; called at the start of each session after collecting user data
- `simpan-interaksi` — INSERT interaction data (session, user, service requested, messages, pengguna_id FK) into `chat_sessions` table; called automatically by the agent after answering
- `get-statistik-penggunaan` — admin tool to query usage statistics by date range

### Conversation Flow
1. **Identity collection** — Agent greets user and asks for identity (minimum: full name) at session start
2. **Save identity** — Calls `simpan-identitas`, gets back `pengguna.id` UUID
3. **Service search** — Try `cari-layanan` first, fall back to `cari-layanan-semantik`, then `get-detail-layanan`
4. **Log interaction** — Calls `simpan-interaksi` with `pengguna_id` linking to the user's identity record

### LLM Configuration
Set in `.env`:
```
LLM_PROVIDER=ollama        # or "gemini"
LLM_MODEL=qwen2.5:0.5b    # any Ollama model, or gemini model name
GEMINI_API_KEY=            # ALWAYS required — used for semantic search embeddings even when LLM_PROVIDER=ollama
OLLAMA_API_BASE=http://localhost:11434
```

LiteLLM model string is constructed as `ollama_chat/<model>` for Ollama or `gemini/<model>` for Gemini.

> **Note**: `GEMINI_API_KEY` is passed to the MCP Toolbox container as `GOOGLE_API_KEY` and is required for the `cari-layanan-semantik` tool regardless of which LLM provider is used.

### Database
The PostgreSQL schema and data live in `rag_kjri_dubai.sql` (gitignored — do not commit). The `toolbox` service mounts this file and runs it on first start. To add/modify services, edit the SQL file and reinitialize the database.

Migration files in `migrations/` are also mounted as init scripts (prefixed `02_`, `03_`, etc.) and run automatically on fresh database init. For existing databases, run migrations manually:
```bash
docker exec -i kjri_postgres psql -U postgres -d rag_kjri < migrations/001_chat_sessions.sql
```

#### pengguna table
Stores user identity collected at session start: `id` (UUID PK), `session_id`, `nama_lengkap` (required), `nomor_paspor`, `nomor_ic`, `nomor_telepon`, `email`, `alamat_domisili`, `kota_domisili`, `jenis_identitas_lain`, `nomor_identitas_lain`, `created_at`. Indexed on `session_id`, `nomor_paspor`, `nama_lengkap`.

#### chat_sessions table
Tracks chatbot usage with columns: `id` (UUID), `session_id`, `nama_pengguna`, `layanan_diminta`, `pesan_user`, `pesan_agent`, `jumlah_pesan`, `tools_dipanggil` (JSONB), `channel`, `ip_address`, `user_agent`, `pengguna_id` (FK → pengguna), `created_at`, `updated_at`. Indexed on `session_id`, `created_at`, `layanan_diminta`, `pengguna_id`.

### Adding New Tools
1. Add a new SQL query tool in [toolbox/config/tools.yaml](toolbox/config/tools.yaml)
2. Register it in the `tools` list inside [chatbot_kjri_dubai/agent.py](chatbot_kjri_dubai/agent.py) by adding it to the `toolbox.load_toolset()` call or individual tool loads
3. Update the agent's instruction prompt if the tool changes response behavior

## RAG Implementation (In Progress)

**Status**: ✅ Phase 1 COMPLETE | ⏳ Phase 2 Next (MVP Features)
**Updated**: 2026-04-21 | **Approach**: Tier-Based Phases for faster delivery
**Reference**: [Advanced RAG Masterplan](docs/superpowers/specs/2026-04-17-advanced-rag-masterplan.md)

### Overview
A comprehensive **Retrieval-Augmented Generation (RAG)** system to enhance the chatbot with:
- **Document management**: Upload & parse PDF/TXT/Markdown documents via LlamaIndex ✅
- **Multi-stage retrieval**: Keyword search (PostgreSQL FTS) → Semantic search (ChromaDB) → Reranking
- **Chat history context**: Store & retrieve relevant past conversations for context-aware responses
- **Advanced prompting**: Structured prompt templates with few-shot examples

### Current Phase Status

| Phase | Status | Duration | Target Completion |
|-------|--------|----------|-------------------|
| **1: Foundation** | ✅ COMPLETE | 3 weeks | Apr 20 ✓ |
| **2: MVP Features** | ⏳ NEXT | 2 weeks | May 5 |
| **3: Production-Ready** | 📋 Planned | 2 weeks | May 19 |
| **4: Agent Integration** | 📋 Planned | 1 week | May 26 |
| **5: Analytics & Ops** | 📋 Planned | 1 week | Jun 2 |

**MVP Ready**: End of Phase 2 (May 5)  
**Full Production**: End of Phase 4 (May 26)

### Phase 1 (COMPLETE) ✅
**Documentation**: Document parsing, semantic chunking, ChromaDB setup
- ✅ All 22 tests passing (396 LOC)
- ✅ PostgreSQL tables created (documents, document_chunks, chat_history, retrieval_analytics)
- ✅ ChromaDB collections setup (document_chunks, chat_history)
- ✅ LlamaIndex PDF/TXT/Markdown parsers implemented
- ✅ Semantic chunking (500 tokens, 100-token overlap)
- ✅ DocumentManager with token estimation
- ✅ Full integration test suite

### Phase 2 (NEXT) — MVP Features ⏳
**Duration**: 2 weeks (Apr 21 - May 5) | **Tier 1-2 features**

Tier 1 Features (Essentials):
- [ ] Chat history storage — Store user messages, retrieve last 5 per session
- [ ] Query logging — Log to `retrieval_analytics` for analytics

Tier 2 Features (Basic Search):
- [ ] PostgreSQL keyword search (FTS) — Search documents by title/content/tags
- [ ] Metadata filtering — Filter by source, date range, tags
- [ ] Simple analytics — Dashboard for top queries, search volume

**MVP Deliverables**: Keyword search API, chat history, query logging, basic dashboard

### Phase 3 (PLANNED) — Production-Ready 📋
**Duration**: 2 weeks (May 6 - May 19) | **Tier 3-4 features**

Tier 3 Features (Semantic Search):
- [ ] Query embedding generation (Gemini API)
- [ ] ChromaDB semantic search + metadata filtering
- [ ] Hybrid ranking (keyword + semantic, 40/60 weighted)
- [ ] Chat history embeddings + context retrieval
- [ ] Deduplication & top-5 ranking

Tier 4 Features (Advanced):
- [ ] Query expansion (LLM generates 3-5 variants)
- [ ] Cross-encoder reranking
- [ ] Context window management + token counting
- [ ] Fallback strategies

**Deliverables**: Complete retrieval pipeline, E2E semantic search, context assembly

### Phase 4 (PLANNED) — Agent Integration 📋
**Duration**: 1 week (May 20 - May 26)
- [ ] Integrate retrieval pipeline into `agent.py`
- [ ] E2E flow testing (query → retrieval → response)
- [ ] Fallback scenarios, performance testing
**Deliverables**: RAG fully integrated in agent, all flows tested

### Phase 5 (PLANNED) — Analytics & Optimization 📋
**Duration**: 1 week (May 27 - Jun 2)
- [ ] Analytics dashboard (precision@5, recall@10, MRR)
- [ ] Performance optimization & A/B testing
- [ ] Load testing, documentation
**Deliverables**: Production monitoring, continuous improvement

### Database Tables (RAG Phase)

#### `documents` (PostgreSQL)
Stores uploaded documents: `id`, `title`, `source` (pdf/markdown/txt), `original_filename`, `content_text`, `file_size_bytes`, `uploaded_by`, `upload_date`, `version`, `tags` (JSONB), `metadata` (JSONB), `is_active`, `created_at`.

#### `document_chunks` (PostgreSQL)
Semantic chunks: `id`, `document_id` (FK), `chunk_number`, `chunk_text`, `chunk_tokens`, `start_char`, `end_char`, `is_embedded`, `created_at`.

#### `chat_history` (PostgreSQL)
Enhanced chat tracking: `id`, `session_id`, `user_id`, `role` (user/agent), `message_text`, `embedding_id`, `retrieved_doc_ids`, `tools_called` (JSONB), `confidence_score`, `metadata`, `created_at`.

#### `retrieval_analytics` (PostgreSQL)
Retrieval metrics: `id`, `query_text`, `query_embedding_id`, `retrieved_doc_ids`, `retrieval_score`, `user_satisfaction` (1-5), `is_successful`, `execution_time_ms`, `created_at`.

### ChromaDB Collections
- `document_chunks` — embeddings of document chunks with metadata
- `chat_history` — embeddings of messages for context retrieval

### RAG Module Structure

```
chatbot_kjri_dubai/
├── rag/
│   ├── __init__.py
│   ├── document_manager.py    # Upload, parse, chunk documents ✅
│   ├── chromadb_client.py     # ChromaDB connection & queries ✅
│   ├── embeddings.py          # Gemini embedding integration
│   ├── retrieval.py           # Multi-stage retrieval pipeline
│   ├── history_manager.py     # Chat history storage & retrieval
│   └── prompt_templates.py    # Structured prompt templates
├── migrations/
│   ├── 001_documents_table.sql
│   ├── 002_chunks_table.sql
│   ├── 003_chat_history_table.sql
│   └── 004_analytics_table.sql
├── tests/
│   ├── test_document_manager.py ✅ (13 tests passing)
│   ├── test_rag_integration.py ✅ (8 tests passing)
│   └── test_retrieval.py (Phase 3)
```

**Full Masterplan**: See [Advanced RAG Masterplan](docs/superpowers/specs/2026-04-17-advanced-rag-masterplan.md) for detailed user stories, technical decisions, and success metrics.
