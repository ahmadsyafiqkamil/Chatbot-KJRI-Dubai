## Learned User Preferences

- User prefers direct, honest feedback without diplomatic softening ("review jujur, tanpa basa-basi") — apply this to code reviews and technical critique.
- User prefers incremental feature development; build lightweight first ("tidak perlu terlalu advance, tapi akan mengarah ke sana") before advanced implementations.
- When given multiple options/steps, user tends to prefer the simpler or first option; present simpler recommendations first.
- User communicates in Bahasa Indonesia; respond in the same language when they write in Indonesian.
- When asked to implement a plan, execute all todos without stopping until complete; do not re-create existing todos.
- Do not edit plan/spec files themselves when implementing a plan — only edit implementation files.

## Learned Workspace Facts

- DB schema columns: `chunk_number` (not `chunk_index`), `chunk_text` (not `content`), `source` (not `file_type`); valid `source` values: `'pdf'`, `'markdown'`, `'txt'`.
- DB driver is `psycopg2-binary` — do not use plain `psycopg2`.
- Embedding model: `gemini-embedding-001` with **3072 dimensions** (not 768 — this was an earlier incorrect assumption).
- ChromaDB port: `localhost:8001` for local dev, `chromadb:8000` inside Docker; handled via env, not hardcoded hostname logic. Docker Compose Chroma healthcheck uses the HTTP API (`/api/v2/heartbeat`); `agent` may depend on `chromadb` with `service_started` instead of `service_healthy` when avoiding flaky health gates.
- Phase 1 RAG complete: document upload/parse/chunk/embed pipeline, 51 tests, 99.3% coverage.
- Phase 2 RAG implemented: PostgreSQL FTS + BM25 (keyword) → ChromaDB similarity (semantic) → RRF hybrid ranking in `retrieval.py`.
- BM25 uses Robertson-Sparck Jones IDF formula; RRF used for hybrid score fusion — do not change formula without benchmarking.
- `retrieval.py` BM25: document-frequency lookup is batched (e.g. unnest of query terms in one SQL round-trip), not one query per token; average document length for BM25 uses word-based splitting aligned with `_tokenize`, not raw `char_length` alone.
- Active branch is `sebelum-fase-1`; masterplan has Phase 0 (Konsuler & Kepercayaan) as priority before advanced RAG phases.
- Agent uses Google ADK + LiteLLM with `ToolboxToolset`; tools loaded from `toolbox/config/tools.yaml`. Monolith `agent.py` was refactored into a multi-agent architecture under `chatbot_kjri_dubai/agents/`: `shared.py` (model/toolbox/RAG init with thread-safe double-checked locking), `identity_agent.py`, `router_agent.py`, `triage_agent.py`, `lookup_formatter_agent.py` — merged to `sebelum-fase-1`.
- `pengguna_id` from `simpan-identitas` is propagated between agents via `[ID:<uuid>]` pattern embedded in `identity_agent` confirmation message; `lookup_formatter_agent` extracts it from conversation history. Set `CHANNEL=telegram` env var for Telegram deployment (default: `'web'`).
- `handoff_queue` PostgreSQL table and `forward_user_message_to_staff` function handle Telegram staff handoff; requires `KJRI_STAFF_TELEGRAM_GROUP_ID` env var.
- `pytest.ini` configured with `asyncio_mode = auto` — no need to add `@pytest.mark.asyncio` decorator to individual async test functions; `pytest-asyncio` must be installed in the project venv.
- Local RAG smoke/upload from host: `requirements-rag.txt` plus `scripts/upload_document.py` (PDF/TXT/MD via `DocumentManager`), `scripts/upload_test_doc.py`, and `scripts/test_rag_retrieval.py` (expects Postgres + Chroma on localhost ports from compose).
