## Learned User Preferences

- User prefers direct, honest feedback without diplomatic softening ("review jujur, tanpa basa-basi") — apply this to code reviews and technical critique.
- User prefers incremental feature development; build lightweight first ("tidak perlu terlalu advance, tapi akan mengarah ke sana") before advanced implementations.
- When given multiple options/steps, user tends to prefer the simpler or first option; present simpler recommendations first.
- User communicates in Bahasa Indonesia; respond in the same language when they write in Indonesian.
- When asked to implement a plan, execute all todos without stopping until complete; do not re-create existing todos.
- Do not edit plan/spec files themselves when implementing a plan — only edit implementation files.
- User prefers escalating to human staff when the bot cannot produce a usable answer; pair that with dedupe/active-handoff checks and cooldown so staff queues are not spammed by technical glitches.

## Learned Workspace Facts

- DB schema columns: `chunk_number` (not `chunk_index`), `chunk_text` (not `content`), `source` (not `file_type`); valid `source` values: `'pdf'`, `'markdown'`, `'txt'`.
- DB driver is `psycopg2-binary` — do not use plain `psycopg2`.
- Embedding model: `gemini-embedding-001` with **3072 dimensions** (not 768 — this was an earlier incorrect assumption).
- ChromaDB port: `localhost:8001` for local dev, `chromadb:8000` inside Docker; handled via env. Compose healthcheck hits `/api/v2/heartbeat`; `agent` may use `chromadb` with `service_started` instead of `service_healthy` if health gates are flaky.
- RAG Phase 1 (upload → chunk → embed) is shipped; Phase 2 in `retrieval.py` is PostgreSQL FTS + Okapi BM25 (batched DF lookup, avg doc length aligned with `_tokenize`) → Chroma similarity → hybrid fusion (weighted α or RRF). Robertson–Sparck Jones IDF + RRF: do not change formulas without benchmarking.
- Active branch is `sebelum-fase-1`; Phase 0 (Konsuler & Kepercayaan) is masterplan priority before advanced RAG work.
- Agent uses Google ADK + LiteLLM with `ToolboxToolset` from `toolbox/config/tools.yaml`. Multi-agent layout: `agents/shared.py` (model/toolbox/RAG, thread-safe `_get_retriever` for `cari_dokumen_rag`), `identity_agent.py`, `router_agent.py`, `triage_agent.py`, `lookup_formatter_agent.py`; `agent.py` is root orchestrator — merged into `sebelum-fase-1`.
- Telegram `telegram_bot.py`: collect user-visible text from `Runner.run_async` using `event.is_final_response()` (not `event.author == root_agent.name`); sub-agents emit the replies. Aggregate all text parts; empty text after a run often means ADK ended with non-text finals (e.g. `function_call` only).
- `pengguna_id` from `simpan-identitas` is propagated via `[ID:<uuid>]` in `identity_agent` confirmation text; `lookup_formatter_agent` reads it back from conversation for `simpan-interaksi`. `CHANNEL` env selects analytics channel (`web` vs `telegram`).
- Telegram handoff: `handoff_queue` + `forward_user_message_to_staff`; needs `KJRI_STAFF_TELEGRAM_GROUP_ID`. `handoff.py` defines `CRISIS_KEYWORDS` (PMI/violence) merged into escalation regex; `HANDOFF_BOT_FAILURE_COOLDOWN_SEC` (default 300) dedupes rapid bot-failure handoffs per session.
- `pytest.ini` uses `asyncio_mode = auto` — async tests need no `@pytest.mark.asyncio` if `pytest-asyncio` is installed.
- Local RAG smoke: `requirements-rag.txt`, `scripts/upload_document.py`, `scripts/upload_test_doc.py`, `scripts/test_rag_retrieval.py` (Postgres + Chroma on localhost from compose).
