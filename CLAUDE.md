# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KJRI Dubai Chatbot: A Bahasa Indonesia consular services advisor for Indonesian citizens, built with Google ADK (Agent Development Kit). The chatbot directs users to the correct consular service based on their needs, provides requirements and costs, and logs interactions for analytics.

**Current Branch**: `sebelum-fase-1` (before Phase 1 implementation)
**Key Design**: Service Navigator (approved 2026-04-21) — two-stage triage system that routes users to correct services before tool lookup.

## Development Commands

### Setup
```bash
# Full system setup (includes all services)
cp .env.example .env
# Edit .env with credentials (POSTGRES_PASSWORD, GEMINI_API_KEY, NGROK_AUTHTOKEN, TELEGRAM_BOT_TOKEN)
docker compose up -d
```

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
| `chromadb` | 8001 | Vector store (future RAG) | `docker-compose.yml` |
| `pgadmin` | 5050 | Database UI (admin) | `docker-compose.yml` |
| `ngrok` | 4040 | Public tunnel (Telegram webhook) | `.env` (NGROK_AUTHTOKEN) |
| `ollama` | 11434 | Local LLM (optional) | host machine |

### Agent Architecture

**File**: `chatbot_kjri_dubai/agent.py`

The agent is a Google ADK `Agent` with:
1. **LLM Model**: Flexible backend via LiteLLM (Ollama or Gemini)
2. **Monkey-patch**: Workaround for toolbox-adk 0.5.8 FunctionDeclaration generation
3. **ToolboxToolset**: Loads SQL-backed tools from MCP Toolbox
4. **Instruction Prompt**: 4-stage conversation flow (see below)

**Imported Tools**:
- `cari-layanan` — keyword search (SQL FTS)
- `cari-layanan-semantik` — semantic search via pgvector + Gemini embeddings
- `get-detail-layanan` — fetch full service details (JSON structure)
- `simpan-identitas` — store user identity (name, passport, phone, etc.)
- `simpan-interaksi` — log interaction for analytics
- `get-statistik-penggunaan` — admin query tool

### Conversation Flow (Stages)

**TAHAP 1 — Identity Collection** (mandatory at session start)
- Agent requests minimal identity (name), offers optional fields
- Parses flexible input (all at once or piecemeal)
- Confirms when name is captured

**TAHAP 2 — Identity Storage**
- Calls `simpan-identitas` with name + optional data (JSON)
- Stores in `pengguna` table, gets back UUID `id`
- Confirms to user, asks what service they need

**TAHAP 3 — Service Search** (Tool Strategy)
1. Try `cari-layanan` if user mentions service keyword (paspor, nikah, dll)
2. Fall back to `cari-layanan-semantik` if no results or user describes situation
3. Call `get-detail-layanan` to fetch full details
4. Format response with structured template (see Design)

**TAHAP 4 — Interaction Logging**
- Calls `simpan-interaksi` with session/user/service/messages/tools
- Logs to `chat_sessions` table for analytics
- Silent failure (error ignored, conversation continues)

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

**`pengguna`** (user identity, `chatbot_kjri_dubai.rag.document_manager`)
- Columns: `id` (UUID PK), `session_id`, `nama_lengkap` (required), `nomor_paspor`, `nomor_ic`, `nomor_telepon`, `email`, `alamat_domisili`, `kota_domisili`, `jenis_identitas_lain`, `nomor_identitas_lain`, `created_at`
- Indexes: `session_id`, `nomor_paspor`, `nama_lengkap`
- Used by: `simpan-identitas` (INSERT), agent prompt (FK reference)

**`chat_sessions`** (interaction log)
- Columns: `id` (UUID), `session_id`, `nama_pengguna`, `layanan_diminta`, `pesan_user`, `pesan_agent`, `jumlah_pesan`, `tools_dipanggil` (JSONB), `channel`, `ip_address`, `user_agent`, `pengguna_id` (FK → pengguna), `created_at`, `updated_at`
- Indexes: `session_id`, `created_at`, `layanan_diminta`, `pengguna_id`
- Used by: `simpan-interaksi` (INSERT), analytics queries

### Migrations

Located in `migrations/`:
- `001_chat_sessions.sql` — create `chat_sessions` table
- `002_pengguna.sql` — create `pengguna` table
- Mounted as Docker init scripts (`02_`, `03_`); auto-run on fresh database
- For existing databases, apply manually: `docker exec -i kjri_postgres psql -U postgres -d rag_kjri < migrations/001_chat_sessions.sql`

### Service Data

Located in `rag_kjri_dubai.sql` (gitignored — do not commit)
- Contains: `layanan` (services) with code, name, cost (AED), requirements (JSON), notes
- Mounted as Docker init script (`01_`); auto-run on fresh start
- To modify services, edit the SQL file and rebuild database

## RAG Implementation (Phases, Planned)

**Current Status**: Infrastructure completed (Phase 0), no Phase 1 work started
**Branch**: `phase1-rag` (worktree for Phase 1 development)

### Phase Timeline
- **Phase 0** ✅ DONE: PostgreSQL + pgvector, ChromaDB, basic schema
- **Phase 1** ⏳ NEXT: Document upload, PDF/TXT/MD parsing, semantic chunking
- **Phase 2**: Multi-stage retrieval (keyword → semantic → rerank)
- **Phase 3**: Chat history management
- **Phase 4**: Agent integration
- **Phase 5**: Analytics

### Future Modules

When Phase 1 begins, will add:
```
chatbot_kjri_dubai/
├── rag/
│   ├── document_manager.py      # Upload & parse documents (PDF/TXT/MD)
│   ├── embeddings.py            # Gemini embedding integration
│   ├── retrieval.py             # Multi-stage retrieval pipeline
│   ├── chromadb_client.py       # Vector store client
│   ├── history_manager.py       # Chat context storage
│   └── prompt_templates.py      # Structured prompt templates
```

### Future Database Tables

- **`documents`**: uploaded file metadata (title, source, file_size, tags, version)
- **`document_chunks`**: semantic chunks with token counts, char positions
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

## Code Organization

- **`chatbot_kjri_dubai/agent.py`** — Main agent logic (identity → search → logging flow)
- **`chatbot_kjri_dubai/telegram_bot.py`** — Telegram Bot API handler
- **`chatbot_kjri_dubai/markdown_converter.py`** — Markdown ↔ Telegram format conversion
- **`toolbox/config/tools.yaml`** — Tool definitions (SQL queries, descriptions)
- **`migrations/`** — Database schema migrations
- **`scripts/seed_embeddings.py`** — Future: bulk embedding generator (not in use yet)
- **`ollama/`** — Ollama Docker entrypoint (optional local LLM)

## Development Notes

### Branch Strategy

- **`main`** — production-ready, stable
- **`sebelum-fase-1`** (current) — pre-Phase 1, preparing Service Navigator implementation
- **`phase1-rag`** — Phase 1 RAG development (worktree)

### When Implementing Service Navigator

1. **Update agent prompt** in `chatbot_kjri_dubai/agent.py:instruction`:
   - Add Step 0 keyword routing logic
   - Add Step 1 triage question-set per domain
   - Reference seed keyword mapping (above)
   - Preserve TAHAP 2–4 (existing flow)

2. **Test with golden set**: 20 test queries covering all domains
   - Expected outcome: router picks correct domain + triage questions converge to 1 service
   - Measure: 16/20 correct (≥80% accuracy)

3. **Monitor token usage**: Triage questions may increase turns
   - Token budget: Ollama small model (7B) vs. Gemini
   - Fallback: reduce max triage questions or use Gemini for Step 1 only

### When Implementing Phase 1 (RAG)

1. Create `chatbot_kjri_dubai/rag/` module
2. Add migrations for `documents`, `document_chunks` tables
3. Implement `DocumentManager` (PDF/TXT/MD parsing + chunking)
4. Wire into agent as optional step before service search
5. Run tests: document upload → chunking → retrieval

## Debugging Tips

- **Agent not responding**: Check `docker compose logs agent`
- **Tools not loading**: Verify `TOOLBOX_URL` and `toolbox` service health (`docker compose logs toolbox`)
- **Semantic search fails**: Confirm `GEMINI_API_KEY` is set and valid
- **Telegram webhook timeout**: Check `docker compose logs telegram-bot` and ngrok URL (`make status`)
- **Database locked**: Stop containers cleanly (`make stop`, not docker kill)

