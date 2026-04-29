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
- ChromaDB port: `localhost:8001` for local dev, `chromadb:8000` inside Docker; handled via env, not hardcoded hostname logic.
- Phase 1 RAG complete: document upload/parse/chunk/embed pipeline, 51 tests, 99.3% coverage.
- Phase 2 RAG implemented: PostgreSQL FTS + BM25 (keyword) → ChromaDB similarity (semantic) → RRF hybrid ranking in `retrieval.py`.
- BM25 uses Robertson-Sparck Jones IDF formula; RRF used for hybrid score fusion — do not change formula without benchmarking.
- Known open issue in `retrieval.py`: N+1 queries in BM25 DF lookup (one query per token); should batch with `= ANY(%s)`.
- Known open issue: `avg_doc_len` uses `char_length` (characters) not token count — incorrect for BM25 length normalization.
- Active branch is `sebelum-fase-1`; masterplan has Phase 0 (Konsuler & Kepercayaan) as priority before advanced RAG phases.
- Agent uses Google ADK + LiteLLM with `ToolboxToolset` for SQL-backed MCP tools; tools loaded from `toolbox/config/tools.yaml`.
