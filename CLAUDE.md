# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KJRI Dubai Chatbot: A Bahasa Indonesia consular services advisor for Indonesian citizens, built with Google ADK (Agent Development Kit). The chatbot directs users to the correct consular service based on their needs, provides requirements and costs, and logs interactions for analytics.

**Current Branch**: `sebelum-fase-1`
**Key Design**: Service Navigator (approved 2026-04-21) — multi-agent pipeline: identity → router → triage → lookup/format.
**Human Handoff**: Escalation to KJRI staff via Telegram group (`handoff_queue` table + `handoff.py`).

## Development Commands

### Setup
```bash
# Full system setup (includes all services)
cp .env.example .env
# Edit .env with credentials (POSTGRES_PASSWORD, GEMINI_API_KEY, NGROK_AUTHTOKEN, TELEGRAM_BOT_TOKEN)
docker compose up -d
```

**`GEMINI_API_KEY` is mandatory for `docker compose up`**: the `layanan-embedding-seed` one-shot container runs `scripts/seed_embeddings.py` after Postgres is healthy and fills `layanan_konsuler.embedding`; `toolbox`, `agent`, and `telegram-bot` wait until it completes successfully (`service_completed_successfully`). If embedding fails or the key is unset, Compose reports an error — avoiding “silent broken” `cari-layanan-semantik`. Optional: set `SEED_EMBEDDINGS_SKIP_IF_FULL=1` in `.env` to skip Gemini calls when every row already has an embedding (still requires `GEMINI_API_KEY` in the file for Compose variable substitution).


### Running
```bash
# Start all services (PostgreSQL, Toolbox, pgAdmin, ChromaDB, Agent, Telegram, Ngrok)
make start

# Stop all services
make stop

# Restart all services
make restart

# View logs (all services)
make logs

# Check status & get public ngrok URL
make status

# Telegram bot logs only
make telegram-logs

# Rebuild & restart Telegram bot
make telegram-restart

# Clean up (remove containers + volumes)
make clean
```

### Local Development
```bash
# Start Docker services only (no rebuilds)
docker compose up -d

# Access agent UI: http://localhost:8000
# Access toolbox: http://localhost:5001
# Access pgAdmin: http://localhost:5050
```

### LLM Configuration
Set in `.env` before running:
```bash
LLM_PROVIDER=ollama    # or "gemini"
LLM_MODEL=qwen2.5:0.5b # any Ollama model or gemini model name
GEMINI_API_KEY=xxx     # REQUIRED for semantic search (even if LLM_PROVIDER=ollama)
OLLAMA_API_BASE=http://localhost:11434
```

## Architecture

### System Components

```
User (Web UI / Telegram)
    ↓ HTTP
Agent (ADK, port 8000)
    ↓ tool calls (native functions)
MCP Toolbox (port 5001)
    ↓ SQL queries
PostgreSQL (port 5432) + pgvector
    ↓ (future)
ChromaDB (port 8001)
```

### Service Stack

| Service | Port | Purpose | Config |
|---------|------|---------|--------|
| `agent` | 8000 | Main ADK agent (web UI) | `Dockerfile` |
| `telegram-bot` | 8080 | Telegram Bot API handler | `Dockerfile.telegram` |
| `toolbox` | 5001 | MCP SQL tool provider | `toolbox/config/tools.yaml` |
| `postgres` | 5432 | Primary database (pgvector) | `rag_kjri_dubai.sql` + `migrations/` |
| `layanan-embedding-seed` | — | One-shot: Gemini embeddings for `layanan_konsuler` | `Dockerfile.embedding-seed`, `scripts/seed_embeddings.py` |
| `chromadb` | 8001 | Vector store (future RAG) | `docker-compose.yml` |
| `pgadmin` | 5050 | Database UI (admin) | `docker-compose.yml` |
| `ngrok` | 4040 | Public tunnel (Telegram webhook) | `.env` (NGROK_AUTHTOKEN) |
| `ollama` | 11434 | Local LLM (optional) | host machine |

### Agent Architecture

**Multi-agent pipeline** via Google ADK (`chatbot_kjri_dubai/agents/`):

| Agent | File | Role |
|-------|------|------|
| `identity_agent` | `agents/identity_agent.py` | TAHAP 1 & 2 — collect & store user identity |
| `router_agent` | `agents/router_agent.py` | Step 0 — keyword domain detection (paspor/sipil/legalisasi/darurat) |
| `triage_agent` | `agents/triage_agent.py` | Step 1 — up to 4 targeted triage questions per domain |
| `lookup_formatter_agent` | `agents/lookup_formatter_agent.py` | Step 2 — search tools, format output, log interaction |
| Shared config | `agents/shared.py` | LLM model, toolbox instances, channel constant |

**Legacy entrypoint**: `chatbot_kjri_dubai/agent.py` — still present as ADK root agent.

**Tools used by agents**:
- `cari-layanan` — keyword search (SQL FTS)
- `cari-layanan-semantik` — semantic search via pgvector + Gemini embeddings
- `get-detail-layanan` — fetch full service details (JSON structure)
- `simpan-identitas` — store user identity (name, passport, phone, etc.)
- `simpan-interaksi` — log interaction for analytics
- `get-statistik-penggunaan` — admin query tool

### Conversation Flow

1. **identity_agent** — greets user, collects name (+ optional: paspor, IC, phone, email), calls `simpan-identitas`, stores `pengguna_id`
2. **router_agent** — detects domain from user message keywords; if ambiguous asks 1 A/B/C/D choice question
3. **triage_agent** — asks ≤4 domain-specific questions to pin down exact service
4. **lookup_formatter_agent** — calls search tools → `get-detail-layanan` → formats per Output Contract → calls `simpan-interaksi`

### Human Agent Handoff

**File**: `chatbot_kjri_dubai/handoff.py`

Escalation triggers (keyword detection + crisis keywords) route the user to KJRI staff:
- Detects: `agen`, `petugas`, `tidak membantu`, `disiksa`, `paspor ditahan`, etc.
- Saves to `handoff_queue` (PostgreSQL) with status: `pending` → `in_progress` → `resolved`
- Notifies KJRI staff Telegram group with `/reply <session_id> <pesan>` instructions
- Auto-resolves inactive handoffs after 10 minutes (configurable)
- Bot-failure handoff: if ADK returns empty reply N times, triggers handoff (cooldown: 300s default)

**Env vars for handoff**:
- `KJRI_STAFF_TELEGRAM_GROUP_ID` — Telegram group ID for staff notifications
- `HANDOFF_BOT_FAILURE_COOLDOWN_SEC` — cooldown between bot-failure tickets (default: 300)

## Service Navigator Design

**Reference**: [ahmadsyafiqkamil-sebelum-fase-1-design-20260421-140619.md](https://file-reference)
**Status**: APPROVED (2026-04-21)

### What It Solves

Users come with everyday language ("paspor hilang", "anak lahir di Dubai") and are confused about which service applies. The navigator rapidly routes them to the correct service without requiring knowledge of official terminology.

### Implementation Strategy (Pending)

**Step 0 — Quick Routing** (domain detection from keywords)
- Auto-route on keyword match: `paspor` → Paspor domain, `lahir` → Catatan Sipil, etc.
- Fallback to 1-choice question if ambiguous: "(A) Paspor (B) Catatan Sipil (C) Legalisasi (D) Darurat?"

**Step 1 — Triage** (2–4 targeted questions per domain)
- Paspor: lost vs. damaged vs. expired? child vs. adult? urgent?
- Catatan Sipil: birth vs. marriage vs. divorce? location? have local docs?
- Legalisasi/Dokumen: which doc? for which country? need translation?
- Darurat/Kepulangan: document lost + need to return soon? ticket status? police report?
- Outcome: pick 1 service OR return 2–3 ambiguous options with 1 clarification Q

**Step 2 — Tool Lookup** (existing flow)
- Call search tools, fetch detail, format response per output contract

### Output Contract (User-Visible Format)

Markdown sections (order required):
1. `## Konteks singkat` — 1–2 sentences of empathy; NO costs mentioned
2. `## Ringkasan layanan` — service name + 1–3 sentences
3. `## Persyaratan` — from tool (wajib / kondisional / catatan)
4. `## Biaya (AED)` — **ONLY from tool output**; if missing, say "Biaya tidak tercantum"
5. `## Jika situasi Anda tidak pasti` — only if ambiguous/not found/error
6. `## Langkah berikutnya` — safe checklist (prepare docs, confirm data, etc.)

### Forbidden Rules

**Zero Hallucination**: Costs (AED) and official requirements MUST come from tool output only. NEVER invent numbers or rules.

**No Service Mixing**: Don't combine requirements from 2 services. Clarify instead.

**State Preservation**: Track minimal state during triage:
- `domain` (paspor / sipil / legalisasi / darurat)
- `triage_q_count` (0–4)
- `triage_facts` (user's answers, e.g., "hilang", "anak", "urgent")
- Reset to Step 0 if user jumps topics or state is lost

**Seed Keyword Mapping** (starting point, iterate with domain experts):
- **Paspor**: paspor, passport, hilang, kehilangan, rusak, sobek, habis, expired, perpanjang
- **Catatan Sipil**: lahir, kelahiran, akte, akta, nikah, pernikahan, cerai, perceraian
- **Legalisasi**: legalisasi, legalisir, pengesahan, surat keterangan, SK, dokumen, terjemah, translation, attestation
- **Darurat/Kepulangan**: darurat, pulang, kepulangan, SPLP, kehilangan dokumen, ditahan, deport, tiket

**Edge Case Handling**:
| Scenario | Behavior |
|----------|----------|
| Search not found | Acknowledge missing data, ask specific clarification + example |
| >1 plausible service | Show 2–3 options + 1 clarification question (don't merge) |
| Tool error/timeout | Say data unavailable, suggest retry, don't guess costs |
| Biaya field empty | Use neutral text ("tidak tercantum"), not placeholder |
| After 1 retry still ambiguous | Summarize understood context + 2 example good questions + escalation |

## Database Schema

### Core Tables

**`pengguna`** (user identity)
- Columns: `id` (UUID PK), `session_id`, `nama_lengkap` (required), `nomor_paspor`, `nomor_ic`, `nomor_telepon`, `email`, `alamat_domisili`, `kota_domisili`, `jenis_identitas_lain`, `nomor_identitas_lain`, `created_at`
- Indexes: `session_id`, `nomor_paspor`, `nama_lengkap`
- Used by: `simpan-identitas` (INSERT), agent prompt (FK reference)

**`chat_sessions`** (interaction log)
- Columns: `id` (UUID), `session_id`, `nama_pengguna`, `layanan_diminta`, `pesan_user`, `pesan_agent`, `jumlah_pesan`, `tools_dipanggil` (JSONB), `channel`, `ip_address`, `user_agent`, `pengguna_id` (FK → pengguna), `created_at`, `updated_at`
- Indexes: `session_id`, `created_at`, `layanan_diminta`, `pengguna_id`
- Used by: `simpan-interaksi` (INSERT), analytics queries

**`handoff_queue`** (human agent escalation)
- Columns: `id` (UUID PK), `session_id`, `pengguna_id` (FK → pengguna), `user_chat_id` (BIGINT), `nama_user`, `pertanyaan_terakhir`, `layanan_dicari`, `status` (pending/in_progress/resolved), `created_at`, `updated_at`, `last_activity_at`
- Indexes: `session_id`, `status`, `last_activity_at` (partial: active only)
- Used by: `handoff.py` (INSERT/UPDATE), Telegram bot `/reply` command

**`conversation_archives`** (conversation closure transcripts)
- Columns: `id` (UUID PK), `session_id` (TEXT), `channel` (TEXT, e.g. "telegram"), `"on"` (TEXT, closure reason code e.g. "gratitude"), `transcript` (JSONB: `{schema_version, closure_reason, messages[{role, text, at}]}`), `pengguna_id` (UUID NULL FK → pengguna), `created_at` TIMESTAMPTZ
- Indexes: `session_id`, `created_at`
- Used by: `conversation_archive.py` (INSERT on closure detection in Telegram webhook)
- Note: `"on"` is a PostgreSQL reserved word — must be double-quoted in all SQL statements

### Migrations

Located in `migrations/`:
- `001_chat_sessions.sql` — create `chat_sessions` table
- `002_pengguna.sql` — create `pengguna` table
- `003_rag_phase0.sql` — RAG phase 0: `documents`, `document_chunks`, `chat_history`, `retrieval_analytics`
- `004_documents_phase1.sql` — Phase 1 document schema refinements
- `005_retrieval_fts.sql` — Full-text search: `search_vector` generated column + GIN index on `document_chunks`
- `006_handoff_queue.sql` — Human handoff: `handoff_queue` table (status: pending/in_progress/resolved)
- `007_handoff_last_activity.sql` — Add `last_activity_at` column to `handoff_queue` (inactivity timeout)
- `008_conversation_archives.sql` — Conversation closure archives: `conversation_archives` table (`session_id`, `channel`, `"on"` closure reason code, `transcript` JSONB, `pengguna_id` FK)

All migrations (001–008) mounted as Docker init scripts (`02_` through `09_`); auto-run on fresh database in order.
For existing databases (already have data), apply missing migrations manually:
```bash
docker exec -i kjri_postgres psql -U postgres -d rag_kjri < migrations/006_handoff_queue.sql
docker exec -i kjri_postgres psql -U postgres -d rag_kjri < migrations/007_handoff_last_activity.sql
docker exec -i kjri_postgres psql -U postgres -d rag_kjri < migrations/008_conversation_archives.sql
```

### Service Data

Located in `rag_kjri_dubai.sql` (gitignored — do not commit)
- Contains: `layanan` (services) with code, name, cost (AED), requirements (JSON), notes
- Mounted as Docker init script (`01_`); auto-run on fresh start
- To modify services, edit the SQL file and rebuild database

## RAG Implementation (Phases, Planned)

**Current Status**: Phase 1 complete (2026-04-28). Phase 2 is next.

### Phase Timeline
- **Phase 0** ✅ DONE: PostgreSQL + pgvector, ChromaDB, basic schema (migration 003)
- **Phase 1** ✅ DONE: Document upload, PDF/TXT/MD parsing, semantic chunking — 51 tests, 99.3% coverage
- **Phase 2** ⏳ NEXT: Multi-stage retrieval (FTS keyword → semantic → rerank); migration 005 already adds FTS index
- **Phase 3**: Chat history management
- **Phase 4**: Agent integration
- **Phase 5**: Analytics

### RAG Module (Implemented)

```
chatbot_kjri_dubai/rag/
├── document_manager.py  # Upload & parse documents (PDF/TXT/MD); stores to PostgreSQL + ChromaDB
├── embeddings.py        # Gemini embedding integration (gemini-embedding-001, 3072 dims)
├── chunking.py          # SentenceSplitter (500 tokens, 100 overlap); tiktoken cl100k_base
├── chromadb_client.py   # ChromaDB vector store client
├── parsers.py           # PDF/TXT/MD file parsers
├── retrieval.py         # Multi-stage retrieval pipeline (Phase 2)
└── __init__.py
```

**Schema notes** (actual DB columns differ from some migration comments):
- `documents`: `source` (not `file_type`), `original_filename`, `content_text` — no `status` column
- `document_chunks`: `chunk_number` (not `chunk_index`), `chunk_text` (not `content`), `chunk_tokens`
- `source` CHECK constraint values: `'pdf'`, `'markdown'`, `'txt'`

### RAG Database Tables

- **`documents`**: uploaded file metadata (title, source, file_size, tags, version)
- **`document_chunks`**: semantic chunks with token counts, char positions, `search_vector` (FTS)
- **`chat_history`**: enhanced session tracking with embedding refs
- **`retrieval_analytics`**: retrieval quality metrics (score, user satisfaction, timing)

### Vector Collections (ChromaDB)

- **`document_chunks`**: embeddings of parsed document chunks
- **`chat_history`**: embeddings of messages for context retrieval

## Key Integration Points

### Tool Output Format

All tools return structured JSON; agent parses and formats for user.

**`cari-layanan` / `cari-layanan-semantik` response**:
```json
{
  "success": true,
  "results": [
    {"code": "PASPOR_HILANG", "name": "Laporan Paspor Hilang", "cost_aed": 50, "time_days": 3}
  ]
}
```

**`get-detail-layanan` response**:
```json
{
  "code": "PASPOR_HILANG",
  "name": "Laporan Paspor Hilang",
  "cost_aed": 50,
  "requirements": {
    "wajib": ["Bukti identitas lokal (EID / VISA)", "Laporan polisi"],
    "kondisional": ["Foto 4x6 jika ingin passport baru segera"],
    "catatan": "Proses 3 hari kerja jika laporan polisi sudah ada"
  }
}
```

### Adding/Modifying Services

1. Edit `rag_kjri_dubai.sql` (gitignored)
2. Reinitialize database:
   ```bash
   docker compose down -v
   docker compose up -d
   ```
3. Or manually insert:
   ```bash
   docker exec -i kjri_postgres psql -U postgres -d rag_kjri -c "INSERT INTO layanan (...) VALUES (...);"
   ```

### Environment Variables

**Critical** (must set before `docker compose up`):
- `POSTGRES_PASSWORD` — database password
- `GEMINI_API_KEY` — for semantic search embeddings (required always)
- `NGROK_AUTHTOKEN` — for public Telegram webhook (required for Telegram)
- `TELEGRAM_BOT_TOKEN` — Telegram bot token

**Optional**:
- `LLM_PROVIDER` — "ollama" (default) or "gemini"
- `LLM_MODEL` — model name (default: `qwen2.5:0.5b`)
- `AGENT_PORT` — Agent API port (default: 8000)
- `TELEGRAM_BOT_PORT` — Telegram service port (default: 8080)
- `KJRI_STAFF_TELEGRAM_GROUP_ID` — Telegram group ID for handoff staff notifications
- `HANDOFF_BOT_FAILURE_COOLDOWN_SEC` — cooldown between bot-failure handoff tickets (default: 300)

## Code Organization

- **`chatbot_kjri_dubai/agent.py`** — ADK root agent entrypoint
- **`chatbot_kjri_dubai/agents/`** — Multi-agent pipeline (identity, router, triage, lookup_formatter, shared)
- **`chatbot_kjri_dubai/handoff.py`** — Human agent handoff (escalation detection, DB, Telegram notify)
- **`chatbot_kjri_dubai/conversation_archive.py`** — Gratitude/farewell closure detection (`detect_gratitude_closure`) + transcript archive DB insert (`save_conversation_archive`)
- **`chatbot_kjri_dubai/rag/`** — RAG module (document_manager, embeddings, chunking, parsers, chromadb_client, retrieval)
- **`chatbot_kjri_dubai/telegram_bot.py`** — Telegram Bot API handler
- **`chatbot_kjri_dubai/markdown_converter.py`** — Markdown ↔ Telegram format conversion
- **`toolbox/config/tools.yaml`** — Tool definitions (SQL queries, descriptions)
- **`migrations/`** — Database schema migrations (001–008)
- **`scripts/seed_embeddings.py`** — Embeds rows in `layanan_konsuler` for `cari-layanan-semantik`; invoked automatically via `layanan-embedding-seed` in `docker-compose.yml` (manual run still supported for debugging)
- **`ollama/`** — Ollama Docker entrypoint (optional local LLM)

## Development Notes

### Branch Strategy

- **`main`** — production-ready, stable
- **`sebelum-fase-1`** (current) — pre-Phase 1, preparing Service Navigator implementation
- **`phase1-rag`** — Phase 1 RAG development (worktree)

### Service Navigator (Implemented)

Multi-agent pipeline is in place (`agents/`). To iterate:
1. **Keyword mapping**: Edit `router_agent.py` keyword lists to add/refine domain routing
2. **Triage questions**: Edit `triage_agent.py` per-domain question sets (max 4 per domain)
3. **Test with golden set**: 20 queries covering all domains — target ≥80% accuracy (16/20)
4. **Token budget**: Triage adds turns; use Gemini if Ollama small model struggles

### When Implementing Phase 2 (Multi-stage Retrieval)

1. Implement retrieval pipeline in `chatbot_kjri_dubai/rag/retrieval.py` (scaffold exists)
2. Strategy: PostgreSQL FTS (`search_vector` column, migration 005) → ChromaDB semantic → rerank
3. Wire into `lookup_formatter_agent` as step before `cari-layanan-semantik`
4. Add `retrieval_analytics` logging for quality metrics

## Debugging Tips

- **Agent not responding**: Check `docker compose logs agent`
- **Tools not loading**: Verify `TOOLBOX_URL` and `toolbox` service health (`docker compose logs toolbox`)
- **Semantic search fails**: Confirm `GEMINI_API_KEY` is set and valid
- **Telegram webhook timeout**: Check `docker compose logs telegram-bot` and ngrok URL (`make status`)
- **Database locked**: Stop containers cleanly (`make stop`, not docker kill)

