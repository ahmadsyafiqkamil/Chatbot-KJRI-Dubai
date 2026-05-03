"""Tests for conversation_archive module."""
import json
import uuid
from unittest.mock import MagicMock, patch

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
