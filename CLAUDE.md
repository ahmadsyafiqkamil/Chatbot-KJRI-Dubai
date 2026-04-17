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

**Status**: 📋 Masterplan approved, awaiting Phase 1 implementation
**Reference**: [Advanced RAG Masterplan](docs/superpowers/specs/2026-04-17-advanced-rag-masterplan.md)

### Overview
A comprehensive **Retrieval-Augmented Generation (RAG)** system is planned to enhance the chatbot with:
- **Document management**: Upload & parse PDF/TXT/Markdown documents via LlamaIndex
- **Multi-stage retrieval**: Keyword search (PostgreSQL FTS) → Semantic search (ChromaDB) → Reranking
- **Chat history context**: Store & retrieve relevant past conversations for context-aware responses
- **Advanced prompting**: Structured prompt templates with few-shot examples

### Architecture (Enhanced)
```
User Query
    ↓
Query Expansion (LLM generates variants)
    ↓
┌─────────────────────────────────────────────┐
│ Multi-Stage Retrieval Pipeline              │
├─────────────────────────────────────────────┤
│ Stage 1: Keyword Search (PostgreSQL FTS)   │
│ Stage 2: Semantic Search (ChromaDB)        │
│ Stage 3: Reranking & Deduplication         │
└─────────────────────────────────────────────┘
    ↓
Assemble Context (documents + chat history + query)
    ↓
LLM (Gemini) with Structured Prompt
    ↓
Agent Response
```

### New Database Tables (RAG Phase)
When RAG Phase 1 is implemented, these tables will be added:

#### `documents` (PostgreSQL)
Stores uploaded documents with metadata: `id`, `title`, `source` (pdf/markdown/txt), `original_filename`, `content_text`, `file_size_bytes`, `uploaded_by`, `upload_date`, `version`, `tags` (JSONB), `metadata` (JSONB), `is_active`, `created_at`.

#### `document_chunks` (PostgreSQL)
Semantic chunks from documents: `id`, `document_id` (FK), `chunk_number`, `chunk_text`, `chunk_tokens`, `start_char`, `end_char`, `is_embedded`, `created_at`.

#### `chat_history` (PostgreSQL)
Enhanced chat tracking for RAG context: `id`, `session_id`, `user_id`, `role` (user/agent), `message_text`, `embedding_id` (ChromaDB ref), `retrieved_doc_ids` (which documents), `tools_called` (JSONB), `confidence_score`, `metadata`, `created_at`.

#### `retrieval_analytics` (PostgreSQL)
Tracks retrieval quality: `id`, `query_text`, `query_embedding_id`, `retrieved_doc_ids`, `retrieval_score`, `user_satisfaction` (1-5), `is_successful`, `execution_time_ms`, `created_at`.

### New ChromaDB Collections (RAG Phase)
- `document_chunks` — embeddings of all document chunks with metadata
- `chat_history` — embeddings of messages for context retrieval

### New RAG Module Structure
When Phase 1 begins, this module will be created:

```
chatbot_kjri_dubai/
├── rag/
│   ├── __init__.py
│   ├── document_manager.py    # Upload, parse, chunk documents
│   ├── embeddings.py          # Gemini embedding integration
│   ├── retrieval.py           # Multi-stage retrieval pipeline
│   ├── chromadb_client.py     # ChromaDB connection & queries
│   ├── history_manager.py     # Chat history storage & retrieval
│   └── prompt_templates.py    # Structured prompt templates
├── migrations/
│   ├── 001_documents_table.sql
│   ├── 002_chunks_table.sql
│   ├── 003_chat_history_table.sql
│   └── 004_analytics_table.sql
```

### RAG Timeline
- **Phase 1 (Weeks 1-3)**: Database schema, ChromaDB setup, document parsing
- **Phase 2 (Weeks 4-5)**: Multi-stage retrieval pipeline
- **Phase 3 (Weeks 6-7)**: Chat history & context management
- **Phase 4 (Weeks 8-9)**: Agent integration & E2E testing
- **Phase 5 (Week 10)**: Analytics & monitoring

See [masterplan](docs/superpowers/specs/2026-04-17-advanced-rag-masterplan.md) for detailed user stories, technical decisions, and success metrics.
