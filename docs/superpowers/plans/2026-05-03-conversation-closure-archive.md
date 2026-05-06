# Conversation Closure & Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect gratitude/farewell messages in Telegram conversations, buffer all turns per session, and archive the full transcript to PostgreSQL when the user closes the conversation.

**Architecture:** New module `conversation_archive.py` owns closure detection + DB persistence. A thread-safe transcript buffer (`dict[session_id, list[turn]]` + `threading.Lock`) lives in `telegram_bot.py` as module-level state. The closure guard is inserted in the webhook handler *after* the existing handoff/escalation guards and *before* the normal agent flow. One archive row is written per closure event; buffer is cleared afterwards.

**Tech Stack:** Python 3.11+, psycopg2, PostgreSQL (JSONB), threading.Lock, pytest + unittest.mock.

---

## Design Decisions (locked in)

| Decision | Choice | Rationale |
|---|---|---|
| Satu vs banyak arsip | One archive row per closure detection | Simplest; buffer is cleared after archiving |
| Buffer cleared after closure | Yes — buffer reset to `[]` | Fresh start for any follow-up messages |
| New module vs extend handoff.py | New `conversation_archive.py` | Single responsibility; handoff.py already handles escalation |
| `"on"` column meaning | Closure reason code (`"gratitude"`) | Queryable without JSONB parsing; must be quoted in SQL (reserved word) |
| Buffer location | Module-level dict+lock in `telegram_bot.py` | Bot state belongs in bot module, not archive module |
| Guard position in webhook | After active-handoff guard, after escalation, BEFORE agent | Matches required order: handoff → escalation → closure → agent |

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `migrations/008_conversation_archives.sql` | `conversation_archives` table DDL + indexes |
| Create | `chatbot_kjri_dubai/conversation_archive.py` | `detect_gratitude_closure()` + `save_conversation_archive()` |
| Create | `tests/test_conversation_archive.py` | Unit tests for detection + DB save |
| Modify | `chatbot_kjri_dubai/telegram_bot.py` | Add buffer dict+lock, append turns, add closure guard |
| Modify | `CLAUDE.md` | Document migration 008 apply instructions + `conversation_archives` table |

---

## Task 1: Database Migration

**Files:**
- Create: `migrations/008_conversation_archives.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- Migration 008: Conversation closure archives
-- Apply to existing DB:
--   docker exec -i kjri_postgres psql -U postgres -d rag_kjri < migrations/008_conversation_archives.sql

CREATE TABLE IF NOT EXISTS conversation_archives (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  VARCHAR     NOT NULL,
    channel     VARCHAR     NOT NULL,
    "on"        VARCHAR     NOT NULL,
    transcript  JSONB       NOT NULL,
    pengguna_id UUID        REFERENCES pengguna(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_archives_session_id  ON conversation_archives(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_archives_created_at  ON conversation_archives(created_at);
```

Save this to `migrations/008_conversation_archives.sql`.

- [ ] **Step 2: Commit**

```bash
git add migrations/008_conversation_archives.sql
git commit -m "feat(db): migration 008 — conversation_archives table"
```

---

## Task 2: `detect_gratitude_closure` (TDD)

**Files:**
- Create: `chatbot_kjri_dubai/conversation_archive.py`
- Create: `tests/test_conversation_archive.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_conversation_archive.py`:

```python
"""Tests for conversation_archive module."""
import pytest
from chatbot_kjri_dubai.conversation_archive import detect_gratitude_closure


# ---------------------------------------------------------------------------
# Positive cases — should return "gratitude"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "terima kasih",
    "Terima Kasih banyak",
    "makasih ya!",
    "Thanks!",
    "thank you so much",
    "bye",
    "Bye!",
    "sampai jumpa",
    "selamat tinggal",
    "ok makasih, sudah cukup",
    "sudah selesai, terima kasih",
    "oke bye",
    "thanks, goodbye",
    "dadah",
    "terima kasih banyak, sudah sangat membantu",
])
def test_detect_gratitude_closure_positive(text):
    result = detect_gratitude_closure(text)
    assert result == "gratitude", f"Expected 'gratitude' for: {text!r}"


# ---------------------------------------------------------------------------
# Negative cases — should return None
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "halo, saya ingin tanya",
    "paspor saya hilang",
    "bagaimana cara memperbarui paspor?",
    "mantap",
    "oke",
    "baik",
    "ya",
])
def test_detect_gratitude_closure_negative(text):
    result = detect_gratitude_closure(text)
    assert result is None, f"Expected None for: {text!r}"


# ---------------------------------------------------------------------------
# Anti-false-positive: "terima kasih tapi ..." — continuation signals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "terima kasih tapi saya mau tanya satu lagi",
    "makasih, tapi gimana kalau dokumen saya berbeda?",
    "ok makasih, ada yang perlu saya siapkan?",
    "terima kasih, bagaimana jika paspor saya sudah expired?",
    "thanks, tapi namun saya masih bingung",
    "terima kasih! satu lagi pertanyaan: apakah perlu membawa foto?",
    "makasih, mau tanya soal biaya juga dong",
    "terima kasih, apakah prosesnya bisa dipercepat?",
])
def test_detect_gratitude_closure_continuation(text):
    result = detect_gratitude_closure(text)
    assert result is None, f"Expected None (continuation signal) for: {text!r}"


# ---------------------------------------------------------------------------
# Anti-false-positive: message with '?' should not trigger closure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "terima kasih, ada informasi lain?",
    "makasih, berapa harganya?",
    "thanks, bisa tolong jelaskan lagi?",
])
def test_detect_gratitude_closure_question_mark(text):
    result = detect_gratitude_closure(text)
    assert result is None, f"Expected None (has '?') for: {text!r}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/ahmadsyafiqkamil/Documents/Project/SYAMIL/Kumpulan Aplikasi/chatbotkjri2/Chatbot-KJRI-Dubai"
python -m pytest tests/test_conversation_archive.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'chatbot_kjri_dubai.conversation_archive'`

- [ ] **Step 3: Implement `detect_gratitude_closure`**

Create `chatbot_kjri_dubai/conversation_archive.py`:

```python
"""Conversation closure detection and transcript archiving for KJRI Dubai chatbot."""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Closure detection
# ---------------------------------------------------------------------------

_GRATITUDE_PATTERNS = re.compile(
    r"terima\s*kasih|makasih|thank\s*you|thanks|"
    r"sampai\s*jumpa|selamat\s*tinggal|bye|goodbye|dadah|"
    r"sudah\s*(?:cukup|selesai)",
    re.IGNORECASE,
)

# If any of these signals are present alongside a gratitude keyword,
# treat the message as a continuation rather than a closure.
_CONTINUATION_SIGNALS = re.compile(
    r"\?|tapi|tetapi|namun|satu\s*lagi|mau\s*tanya|ada\s*lagi|"
    r"bagaimana|gimana|berapa|apakah|bisa\s*tolong",
    re.IGNORECASE,
)


def detect_gratitude_closure(text: str) -> Optional[str]:
    """Return 'gratitude' if text is a clean farewell/thank-you, else None.

    Anti-false-positive heuristic: if continuation signals (question mark,
    'tapi', 'mau tanya', interrogative words) are present alongside a
    gratitude keyword, return None (user is continuing the conversation).
    """
    if not _GRATITUDE_PATTERNS.search(text):
        return None
    if _CONTINUATION_SIGNALS.search(text):
        return None
    return "gratitude"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_conversation_archive.py -v
```

Expected: All tests PASS. If any parametrize case fails, adjust `_CONTINUATION_SIGNALS` or `_GRATITUDE_PATTERNS` accordingly (do NOT change the tests unless the test itself is wrong).

- [ ] **Step 5: Commit**

```bash
git add chatbot_kjri_dubai/conversation_archive.py tests/test_conversation_archive.py
git commit -m "feat(archive): detect_gratitude_closure with anti-false-positive heuristic"
```

---

## Task 3: `save_conversation_archive` (TDD)

**Files:**
- Modify: `chatbot_kjri_dubai/conversation_archive.py`
- Modify: `tests/test_conversation_archive.py`

- [ ] **Step 1: Add failing tests for `save_conversation_archive`**

Append to `tests/test_conversation_archive.py`:

```python
import uuid
from unittest.mock import MagicMock, patch


FAKE_ARCHIVE_ID = str(uuid.uuid4())
FAKE_SESSION_ID = "telegram_999"
FAKE_PENGGUNA_ID = str(uuid.uuid4())

SAMPLE_MESSAGES = [
    {"role": "user", "text": "Halo, paspor saya hilang", "at": "2026-05-03T10:00:00+00:00"},
    {"role": "assistant", "text": "Baik, saya bantu. ...", "at": "2026-05-03T10:00:05+00:00"},
    {"role": "user", "text": "terima kasih", "at": "2026-05-03T10:01:00+00:00"},
]


def _make_mock_db_for_archive(archive_id=FAKE_ARCHIVE_ID):
    """Build psycopg2 mock stack returning archive UUID."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (archive_id,)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect = MagicMock()
    mock_connect.return_value.__enter__ = lambda s: mock_conn
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)
    return mock_connect, mock_conn, mock_cursor


def test_save_conversation_archive_returns_uuid():
    """save_conversation_archive returns archive UUID on success."""
    from chatbot_kjri_dubai.conversation_archive import save_conversation_archive

    mock_connect, mock_conn, mock_cursor = _make_mock_db_for_archive()
    with patch("chatbot_kjri_dubai.conversation_archive.psycopg2.connect", mock_connect):
        result = save_conversation_archive(
            session_id=FAKE_SESSION_ID,
            channel="telegram",
            on="gratitude",
            transcript_messages=SAMPLE_MESSAGES,
            pengguna_id=FAKE_PENGGUNA_ID,
        )
    assert result == FAKE_ARCHIVE_ID


def test_save_conversation_archive_inserts_correct_json():
    """save_conversation_archive inserts JSONB with schema_version and messages."""
    from chatbot_kjri_dubai.conversation_archive import save_conversation_archive

    mock_connect, mock_conn, mock_cursor = _make_mock_db_for_archive()
    with patch("chatbot_kjri_dubai.conversation_archive.psycopg2.connect", mock_connect):
        save_conversation_archive(
            session_id=FAKE_SESSION_ID,
            channel="telegram",
            on="gratitude",
            transcript_messages=SAMPLE_MESSAGES,
        )

    call_args = mock_cursor.execute.call_args
    sql, params = call_args[0]
    assert "conversation_archives" in sql
    assert "INSERT" in sql.upper()

    # params: (session_id, channel, on, transcript_json, pengguna_id)
    transcript_json = params[3]
    transcript = json.loads(transcript_json)
    assert transcript["schema_version"] == "1"
    assert transcript["closure_reason"] == "gratitude"
    assert len(transcript["messages"]) == 3
    assert transcript["messages"][0]["role"] == "user"


def test_save_conversation_archive_without_pengguna_id():
    """save_conversation_archive works without pengguna_id (NULL FK)."""
    from chatbot_kjri_dubai.conversation_archive import save_conversation_archive

    mock_connect, mock_conn, mock_cursor = _make_mock_db_for_archive()
    with patch("chatbot_kjri_dubai.conversation_archive.psycopg2.connect", mock_connect):
        result = save_conversation_archive(
            session_id=FAKE_SESSION_ID,
            channel="telegram",
            on="gratitude",
            transcript_messages=SAMPLE_MESSAGES,
            pengguna_id=None,
        )
    assert result == FAKE_ARCHIVE_ID


def test_save_conversation_archive_returns_none_on_db_error():
    """save_conversation_archive returns None (does not raise) on DB error."""
    from chatbot_kjri_dubai.conversation_archive import save_conversation_archive

    with patch(
        "chatbot_kjri_dubai.conversation_archive.psycopg2.connect",
        side_effect=Exception("DB down"),
    ):
        result = save_conversation_archive(
            session_id=FAKE_SESSION_ID,
            channel="telegram",
            on="gratitude",
            transcript_messages=SAMPLE_MESSAGES,
        )
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_conversation_archive.py::test_save_conversation_archive_returns_uuid -v
```

Expected: `ImportError` or `AttributeError` — `save_conversation_archive` not yet defined.

- [ ] **Step 3: Implement `save_conversation_archive`**

Add to `chatbot_kjri_dubai/conversation_archive.py` (below existing functions):

```python
def _get_conn_string() -> str:
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return db_url
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "rag_kjri")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def save_conversation_archive(
    session_id: str,
    channel: str,
    on: str,
    transcript_messages: list[dict],
    pengguna_id: Optional[str] = None,
) -> Optional[str]:
    """Insert a conversation archive row. Returns archive UUID or None on error.

    transcript_messages: list of {"role": str, "text": str, "at": str (ISO 8601)}
    on: closure reason code (e.g. "gratitude")
    Error handling: logs exception and returns None — never raises, so UX is not broken.
    """
    transcript = json.dumps(
        {
            "schema_version": "1",
            "closure_reason": on,
            "messages": transcript_messages,
        },
        ensure_ascii=False,
    )
    conn_string = _get_conn_string()
    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO conversation_archives
                        (session_id, channel, "on", transcript, pengguna_id)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    RETURNING id
                    """,
                    (session_id, channel, on, transcript, pengguna_id),
                )
                archive_id = str(cur.fetchone()[0])
            conn.commit()
        logger.info(
            "Conversation archive saved: id=%s session=%s on=%s messages=%d",
            archive_id, session_id, on, len(transcript_messages),
        )
        return archive_id
    except Exception:
        logger.exception(
            "Failed to save conversation archive for session=%s", session_id
        )
        return None
```

- [ ] **Step 4: Run all archive tests**

```bash
python -m pytest tests/test_conversation_archive.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chatbot_kjri_dubai/conversation_archive.py tests/test_conversation_archive.py
git commit -m "feat(archive): save_conversation_archive — DB insert with JSONB transcript"
```

---

## Task 4: Transcript Buffer in `telegram_bot.py`

**Files:**
- Modify: `chatbot_kjri_dubai/telegram_bot.py`

The buffer is a module-level `dict[str, list[dict]]` protected by a `threading.Lock`. Each turn is `{"role": "user"|"assistant", "text": str, "at": str}` where `at` is UTC ISO 8601.

- [ ] **Step 1: Add imports and buffer state at module level**

In `telegram_bot.py`, after the existing imports block (around line 12, after the `from chatbot_kjri_dubai.handoff import (...)` block), add:

```python
import threading
from datetime import datetime, timezone

from chatbot_kjri_dubai.conversation_archive import (
    detect_gratitude_closure,
    save_conversation_archive,
)

# ---------------------------------------------------------------------------
# Per-session transcript buffer (for conversation archives)
# ---------------------------------------------------------------------------
_transcript_buffers: dict[str, list[dict]] = {}
_transcript_lock = threading.Lock()

_CLOSURE_REPLY = (
    "Sama-sama, semoga informasi ini membantu! "
    "Jika ada pertanyaan lain di lain waktu, jangan ragu menghubungi kami kembali."
)


def _append_turn(session_id: str, role: str, text: str) -> None:
    """Append one turn to the session transcript buffer (thread-safe)."""
    turn = {
        "role": role,
        "text": text,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    with _transcript_lock:
        if session_id not in _transcript_buffers:
            _transcript_buffers[session_id] = []
        _transcript_buffers[session_id].append(turn)


def _get_and_clear_buffer(session_id: str) -> list[dict]:
    """Return current buffer for session_id and clear it (thread-safe)."""
    with _transcript_lock:
        turns = list(_transcript_buffers.pop(session_id, []))
    return turns
```

- [ ] **Step 2: Append user turn in the normal-agent section of the webhook**

In the webhook handler, find the comment `# Normal agent flow (TAHAP 1–4)` (around line 459). Immediately after the `logger.info("Webhook: running agent ...")` line and before the `session = await session_service.get_session(...)` call, add:

```python
    # Append user message to transcript buffer
    _append_turn(session_id, "user", user_text)
```

- [ ] **Step 3: Append assistant turn after `send_message`**

Find the `if response_text:` block near the end of the webhook handler (around line 508). Change it from:

```python
    if response_text:
        await send_message(chat_id, response_text)
    else:
        ...
```

To:

```python
    if response_text:
        await send_message(chat_id, response_text)
        # Append assistant turn to transcript buffer
        _append_turn(session_id, "assistant", response_text)
    else:
        ...
```

- [ ] **Step 4: Run existing tests to confirm no regression**

```bash
python -m pytest tests/test_handoff.py tests/test_agents_structure.py -v
```

Expected: All previously passing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add chatbot_kjri_dubai/telegram_bot.py
git commit -m "feat(telegram): transcript buffer — append user/assistant turns per session"
```

---

## Task 5: Closure Guard in Webhook Handler

**Files:**
- Modify: `chatbot_kjri_dubai/telegram_bot.py`

The closure guard is inserted **after** the escalation block and **before** the normal agent flow block. Guard order becomes: active-handoff → escalation → **closure** → agent.

- [ ] **Step 1: Insert closure guard block in the webhook handler**

In `telegram_bot.py`, find the comment `# Normal agent flow (TAHAP 1–4)` (currently around line 459). Insert the following block **immediately before** that comment:

```python
    # ---------------------------------------------------------------------------
    # Closure detection — archive transcript if user says goodbye/thank you
    # ---------------------------------------------------------------------------
    closure_reason = detect_gratitude_closure(user_text)
    logger.info(
        "Webhook: detect_gratitude_closure = %s for session=%s",
        closure_reason, session_id,
    )

    if closure_reason:
        # Append the farewell message to buffer before archiving
        _append_turn(session_id, "user", user_text)
        turns = _get_and_clear_buffer(session_id)

        pengguna_id, _ = get_latest_pengguna_for_session(session_id)
        save_conversation_archive(
            session_id=session_id,
            channel="telegram",
            on=closure_reason,
            transcript_messages=turns,
            pengguna_id=pengguna_id,
        )
        await send_message(chat_id, _CLOSURE_REPLY)
        return {"ok": True}
```

Note: `get_latest_pengguna_for_session` is already imported from `handoff` at the top of the file.

- [ ] **Step 2: Remove duplicate user-turn append from the normal-agent section**

In Task 4 Step 2, we added `_append_turn(session_id, "user", user_text)` before the session creation. Now that the closure branch also appends the user turn before returning, we need to confirm the normal-agent path still appends — it should, because the closure branch returns early and never reaches the normal-agent section. The `_append_turn` call added in Task 4 Step 2 remains correct for non-closure messages. **No change needed here** — just verify the flow is correct by reading the surrounding code.

- [ ] **Step 3: Run all tests**

```bash
python -m pytest tests/ -v --ignore=tests/rag
```

Expected: All tests PASS with no regression.

- [ ] **Step 4: Verify guard order by reading the final webhook handler**

Read `chatbot_kjri_dubai/telegram_bot.py` lines 395–470 and confirm:
1. `has_active_handoff` check comes first (returns early)
2. `detect_escalation_trigger` check comes second (returns early)
3. `detect_gratitude_closure` check comes third (returns early with closure reply)
4. Normal agent flow starts after all three guards

- [ ] **Step 5: Commit**

```bash
git add chatbot_kjri_dubai/telegram_bot.py
git commit -m "feat(telegram): closure guard — detect farewell, archive transcript, send reply"
```

---

## Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add migration 008 to the Migrations section**

In `CLAUDE.md`, find the `### Migrations` section. Add migration 008 to the numbered list:

```markdown
- `008_conversation_archives.sql` — Conversation closure archives: `conversation_archives` table (session_id, channel, "on" closure reason, transcript JSONB, pengguna_id FK)
```

Add the manual apply command alongside migrations 006–007:

```bash
docker exec -i kjri_postgres psql -U postgres -d rag_kjri < migrations/008_conversation_archives.sql
```

- [ ] **Step 2: Add `conversation_archives` to the Database Schema section**

After the `handoff_queue` table description in `CLAUDE.md`, add:

```markdown
**`conversation_archives`** (conversation closure transcripts)
- Columns: `id` (UUID PK), `session_id` (VARCHAR), `channel` (VARCHAR, e.g. "telegram"), `"on"` (VARCHAR, closure reason code e.g. "gratitude"), `transcript` (JSONB: `{schema_version, closure_reason, messages[{role, text, at}]}`), `pengguna_id` (UUID NULL FK → pengguna), `created_at` TIMESTAMPTZ
- Indexes: `session_id`, `created_at`
- Used by: `conversation_archive.py` (INSERT on closure detection)
- Note: `"on"` is a PostgreSQL reserved word — must be double-quoted in all SQL statements
```

- [ ] **Step 3: Add `conversation_archive.py` to the Code Organization section**

In the `## Code Organization` section, add:

```markdown
- **`chatbot_kjri_dubai/conversation_archive.py`** — Gratitude/farewell closure detection (`detect_gratitude_closure`) + transcript archive DB insert (`save_conversation_archive`)
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document migration 008 and conversation_archive module"
```

---

## Task 7: Final Integration Verification

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -v --ignore=tests/rag
```

Expected: All tests PASS (includes `test_handoff.py`, `test_agents_structure.py`, `test_conversation_archive.py`).

- [ ] **Step 2: Run RAG tests for regression check**

```bash
python -m pytest tests/rag/ -q
```

Expected: All 51 RAG tests still PASS (no imports changed in RAG module).

- [ ] **Step 3: Smoke-check module imports**

```bash
python -c "
from chatbot_kjri_dubai.conversation_archive import detect_gratitude_closure, save_conversation_archive
print('detect:', detect_gratitude_closure('terima kasih'))
print('no-close:', detect_gratitude_closure('terima kasih tapi ada pertanyaan?'))
print('imports OK')
"
```

Expected output:
```
detect: gratitude
no-close: None
imports OK
```

- [ ] **Step 4: Final commit tag**

```bash
git log --oneline -6
```

Verify the 6 commits from Tasks 1–6 are present and clean.

---

## Self-Review Checklist

**Spec coverage:**
- [x] Migration `008_conversation_archives.sql` — Task 1
- [x] `detect_gratitude_closure` with anti-false-positive — Task 2
- [x] `save_conversation_archive` with psycopg2, error handling — Task 3
- [x] Thread-safe buffer in `telegram_bot.py` — Task 4
- [x] Guard order: handoff → escalation → closure → agent — Task 5
- [x] JSONB structure: `schema_version`, `messages[{role, text, at}]`, `closure_reason` — Task 3
- [x] `pengguna_id` optional FK from `get_latest_pengguna_for_session` — Task 5
- [x] Closure reply sent to user — Task 5
- [x] Buffer cleared after closure — Task 5 (`_get_and_clear_buffer`)
- [x] CLAUDE.md updated with migration and table docs — Task 6
- [x] No secrets/tokens written to archives or AGENTS.md — ensured by not logging transcript content

**Type consistency check:**
- `detect_gratitude_closure(text: str) -> Optional[str]` — returns `"gratitude"` or `None` — consistent across Tasks 2 and 5
- `save_conversation_archive(session_id, channel, on, transcript_messages, pengguna_id)` — signature matches test mocks and webhook call in Task 5
- `_append_turn(session_id, role, text)` / `_get_and_clear_buffer(session_id)` — used consistently in Tasks 4 and 5
- `turns` (list[dict]) passed to `save_conversation_archive` as `transcript_messages` — consistent
