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
- Agent uses Google ADK + LiteLLM with `ToolboxToolset` for SQL-backed MCP tools; tools loaded from `toolbox/config/tools.yaml`. RAG tool `cari_dokumen_rag` uses a lazy-init singleton `Retriever` in `agent.py` (`_get_retriever`), not a top-level import that runs on module load.
- Local RAG smoke/upload from host: `requirements-rag.txt` plus `scripts/upload_document.py` (PDF/TXT/MD via `DocumentManager`), `scripts/upload_test_doc.py`, and `scripts/test_rag_retrieval.py` (expects Postgres + Chroma on localhost ports from compose).
