"""Tests for Human Agent Handoff module (TDD — RED then GREEN)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_HANDOFF_ID = str(uuid.uuid4())
FAKE_SESSION_ID = "telegram_123456"
FAKE_CHAT_ID = 123456
FAKE_NAMA = "Budi Santoso"
FAKE_PERTANYAAN = "Paspor saya hilang, tidak bisa pulang"
BOT_TOKEN = "fakebottoken"
STAFF_GROUP_ID = "-1009999999999"


def _make_mock_db(return_handoff_id=FAKE_HANDOFF_ID, user_chat_id=FAKE_CHAT_ID):
    """Build a mock psycopg2 connection/cursor stack."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        (return_handoff_id,),  # first fetchone → INSERT RETURNING id
        (user_chat_id,),       # second fetchone → SELECT user_chat_id
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_connect = MagicMock()
    mock_connect.return_value.__enter__ = lambda s: mock_conn
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)
    return mock_connect, mock_conn, mock_cursor


def _make_mock_httpx(status_code=200, ok=True):
    """Build a mock httpx.AsyncClient that returns a successful response."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = {"ok": ok}
    mock_response.text = ""

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_cls, mock_client


# ---------------------------------------------------------------------------
# detect_escalation_trigger
# ---------------------------------------------------------------------------

class TestDetectEscalationTrigger:
    def test_keyword_agen(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Saya mau bicara dengan agen") is True

    def test_keyword_manusia(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Tolong sambungkan ke manusia") is True

    def test_keyword_petugas(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Ada petugas yang bisa bantu?") is True

    def test_keyword_bicara_dengan(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Saya ingin bicara dengan orang") is True

    def test_keyword_hubungi(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Bagaimana cara hubungi KJRI?") is True

    def test_keyword_tidak_membantu(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Bot ini tidak membantu sama sekali") is True

    def test_keyword_tidak_ada_jawaban(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("tidak ada jawaban yang sesuai") is True

    def test_keyword_operator(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Bisa minta operator?") is True

    def test_keyword_berbicara_dengan(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Ingin berbicara dengan staf") is True

    def test_case_insensitive_upper(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("AGEN saja yang bisa bantu") is True

    def test_case_insensitive_mixed(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Manusia dong, bukan bot") is True

    def test_case_insensitive_petugas_upper(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("PETUGAS please help me") is True

    def test_mixed_language(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("I need agen manusia sekarang") is True

    def test_mixed_language_english_trigger(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("please hubungi me with staff") is True

    def test_no_match_normal_message(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Paspor saya sudah expired") is False

    def test_no_match_service_question(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Berapa biaya perpanjang paspor?") is False

    def test_no_match_empty_string(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("") is False

    def test_no_match_greeting(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Assalamualaikum, nama saya Budi") is False


# ---------------------------------------------------------------------------
# save_handoff_to_db
# ---------------------------------------------------------------------------

class TestSaveHandoffToDb:
    def test_returns_handoff_id_string(self):
        from chatbot_kjri_dubai.handoff import save_handoff_to_db
        mock_connect, mock_conn, mock_cursor = _make_mock_db()
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            result = save_handoff_to_db(
                session_id=FAKE_SESSION_ID,
                user_chat_id=FAKE_CHAT_ID,
                pengguna_id=None,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )
        assert result == FAKE_HANDOFF_ID

    def test_inserts_into_handoff_queue(self):
        from chatbot_kjri_dubai.handoff import save_handoff_to_db
        mock_connect, mock_conn, mock_cursor = _make_mock_db()
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            save_handoff_to_db(
                session_id=FAKE_SESSION_ID,
                user_chat_id=FAKE_CHAT_ID,
                pengguna_id=None,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )
        all_calls = " ".join(str(c) for c in mock_cursor.execute.call_args_list)
        assert "handoff_queue" in all_calls

    def test_passes_all_fields_to_insert(self):
        from chatbot_kjri_dubai.handoff import save_handoff_to_db
        mock_connect, mock_conn, mock_cursor = _make_mock_db()
        pengguna_id = str(uuid.uuid4())
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            save_handoff_to_db(
                session_id=FAKE_SESSION_ID,
                user_chat_id=FAKE_CHAT_ID,
                pengguna_id=pengguna_id,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
                layanan_dicari="Paspor Hilang",
            )
        call_args = mock_cursor.execute.call_args_list[0]
        params = call_args[0][1]
        assert FAKE_SESSION_ID in params
        assert FAKE_CHAT_ID in params
        assert FAKE_NAMA in params
        assert FAKE_PERTANYAAN in params

    def test_commits_transaction(self):
        from chatbot_kjri_dubai.handoff import save_handoff_to_db
        mock_connect, mock_conn, mock_cursor = _make_mock_db()
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            save_handoff_to_db(
                session_id=FAKE_SESSION_ID,
                user_chat_id=FAKE_CHAT_ID,
                pengguna_id=None,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )
        mock_conn.commit.assert_called_once()

    def test_accepts_none_layanan_dicari(self):
        from chatbot_kjri_dubai.handoff import save_handoff_to_db
        mock_connect, mock_conn, mock_cursor = _make_mock_db()
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            result = save_handoff_to_db(
                session_id=FAKE_SESSION_ID,
                user_chat_id=FAKE_CHAT_ID,
                pengguna_id=None,
                nama_user=None,
                pertanyaan_terakhir=None,
            )
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# get_user_chat_id_by_session
# ---------------------------------------------------------------------------

class TestGetUserChatIdBySession:
    def test_returns_chat_id_when_found(self):
        from chatbot_kjri_dubai.handoff import get_user_chat_id_by_session
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (FAKE_CHAT_ID,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect = MagicMock()
        mock_connect.return_value.__enter__ = lambda s: mock_conn
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            result = get_user_chat_id_by_session(FAKE_SESSION_ID)
        assert result == FAKE_CHAT_ID

    def test_returns_none_when_not_found(self):
        from chatbot_kjri_dubai.handoff import get_user_chat_id_by_session
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect = MagicMock()
        mock_connect.return_value.__enter__ = lambda s: mock_conn
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            result = get_user_chat_id_by_session("unknown_session")
        assert result is None


# ---------------------------------------------------------------------------
# send_staff_notification
# ---------------------------------------------------------------------------

class TestSendStaffNotification:
    @pytest.mark.asyncio
    async def test_sends_to_staff_group(self):
        from chatbot_kjri_dubai.handoff import send_staff_notification
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_staff_notification(
                bot_token=BOT_TOKEN,
                staff_group_id=STAFF_GROUP_ID,
                handoff_id=FAKE_HANDOFF_ID,
                session_id=FAKE_SESSION_ID,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["chat_id"] == STAFF_GROUP_ID

    @pytest.mark.asyncio
    async def test_notification_contains_user_name(self):
        from chatbot_kjri_dubai.handoff import send_staff_notification
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_staff_notification(
                bot_token=BOT_TOKEN,
                staff_group_id=STAFF_GROUP_ID,
                handoff_id=FAKE_HANDOFF_ID,
                session_id=FAKE_SESSION_ID,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )
        text = mock_client.post.call_args[1]["json"]["text"]
        assert FAKE_NAMA in text

    @pytest.mark.asyncio
    async def test_notification_contains_question(self):
        from chatbot_kjri_dubai.handoff import send_staff_notification
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_staff_notification(
                bot_token=BOT_TOKEN,
                staff_group_id=STAFF_GROUP_ID,
                handoff_id=FAKE_HANDOFF_ID,
                session_id=FAKE_SESSION_ID,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )
        text = mock_client.post.call_args[1]["json"]["text"]
        assert FAKE_PERTANYAAN in text

    @pytest.mark.asyncio
    async def test_notification_contains_reply_instruction(self):
        from chatbot_kjri_dubai.handoff import send_staff_notification
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_staff_notification(
                bot_token=BOT_TOKEN,
                staff_group_id=STAFF_GROUP_ID,
                handoff_id=FAKE_HANDOFF_ID,
                session_id=FAKE_SESSION_ID,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )
        text = mock_client.post.call_args[1]["json"]["text"]
        assert "/reply" in text
        assert FAKE_SESSION_ID in text

    @pytest.mark.asyncio
    async def test_notification_contains_session_id(self):
        from chatbot_kjri_dubai.handoff import send_staff_notification
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_staff_notification(
                bot_token=BOT_TOKEN,
                staff_group_id=STAFF_GROUP_ID,
                handoff_id=FAKE_HANDOFF_ID,
                session_id=FAKE_SESSION_ID,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )
        text = mock_client.post.call_args[1]["json"]["text"]
        assert FAKE_SESSION_ID in text

    @pytest.mark.asyncio
    async def test_uses_correct_bot_token_in_url(self):
        from chatbot_kjri_dubai.handoff import send_staff_notification
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_staff_notification(
                bot_token=BOT_TOKEN,
                staff_group_id=STAFF_GROUP_ID,
                handoff_id=FAKE_HANDOFF_ID,
                session_id=FAKE_SESSION_ID,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )
        url = mock_client.post.call_args[0][0]
        assert BOT_TOKEN in url

    @pytest.mark.asyncio
    async def test_failed_response_does_not_raise(self):
        """Notification failure should log error, not raise exception."""
        from chatbot_kjri_dubai.handoff import send_staff_notification
        mock_cls, mock_client = _make_mock_httpx(status_code=500, ok=False)
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            # Should not raise
            await send_staff_notification(
                bot_token=BOT_TOKEN,
                staff_group_id=STAFF_GROUP_ID,
                handoff_id=FAKE_HANDOFF_ID,
                session_id=FAKE_SESSION_ID,
                nama_user=FAKE_NAMA,
                pertanyaan_terakhir=FAKE_PERTANYAAN,
            )


# ---------------------------------------------------------------------------
# handle_staff_reply
# ---------------------------------------------------------------------------

class TestHandleStaffReply:
    @pytest.mark.asyncio
    async def test_forwards_message_to_user(self):
        from chatbot_kjri_dubai.handoff import handle_staff_reply
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await handle_staff_reply(
                bot_token=BOT_TOKEN,
                user_chat_id=FAKE_CHAT_ID,
                pesan_staf="Silakan datang ke kantor besok jam 9.",
            )
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["chat_id"] == FAKE_CHAT_ID

    @pytest.mark.asyncio
    async def test_reply_contains_staff_message(self):
        from chatbot_kjri_dubai.handoff import handle_staff_reply
        mock_cls, mock_client = _make_mock_httpx()
        pesan = "Dokumen bisa diambil Senin ini."
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await handle_staff_reply(
                bot_token=BOT_TOKEN,
                user_chat_id=FAKE_CHAT_ID,
                pesan_staf=pesan,
            )
        text = mock_client.post.call_args[1]["json"]["text"]
        assert pesan in text

    @pytest.mark.asyncio
    async def test_reply_uses_correct_bot_token(self):
        from chatbot_kjri_dubai.handoff import handle_staff_reply
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await handle_staff_reply(
                bot_token=BOT_TOKEN,
                user_chat_id=FAKE_CHAT_ID,
                pesan_staf="Halo user.",
            )
        url = mock_client.post.call_args[0][0]
        assert BOT_TOKEN in url

    @pytest.mark.asyncio
    async def test_failed_reply_does_not_raise(self):
        from chatbot_kjri_dubai.handoff import handle_staff_reply
        mock_cls, mock_client = _make_mock_httpx(status_code=400, ok=False)
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await handle_staff_reply(
                bot_token=BOT_TOKEN,
                user_chat_id=FAKE_CHAT_ID,
                pesan_staf="Test gagal.",
            )


# ---------------------------------------------------------------------------
# update_handoff_status
# ---------------------------------------------------------------------------

class TestUpdateHandoffStatus:
    def test_updates_status_in_db(self):
        from chatbot_kjri_dubai.handoff import update_handoff_status
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect = MagicMock()
        mock_connect.return_value.__enter__ = lambda s: mock_conn
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            update_handoff_status(FAKE_HANDOFF_ID, "in_progress")

        all_calls = " ".join(str(c) for c in mock_cursor.execute.call_args_list)
        assert "UPDATE" in all_calls or "handoff_queue" in all_calls
        mock_conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Security: /reply only from staff group (logic test)
# ---------------------------------------------------------------------------

class TestReplySecurityLogic:
    def test_reply_command_is_rejected_from_wrong_group(self):
        """The is_from_staff_group helper should return False for non-staff chats."""
        from chatbot_kjri_dubai.handoff import is_from_staff_group
        assert is_from_staff_group(chat_id="-1001111111111", staff_group_id=STAFF_GROUP_ID) is False

    def test_reply_command_is_accepted_from_staff_group(self):
        from chatbot_kjri_dubai.handoff import is_from_staff_group
        assert is_from_staff_group(chat_id=STAFF_GROUP_ID, staff_group_id=STAFF_GROUP_ID) is True

    def test_reply_command_rejected_from_private_chat(self):
        from chatbot_kjri_dubai.handoff import is_from_staff_group
        assert is_from_staff_group(chat_id="123456", staff_group_id=STAFF_GROUP_ID) is False

    def test_staff_group_id_empty_always_false(self):
        """If KJRI_STAFF_TELEGRAM_GROUP_ID is not configured, reject all."""
        from chatbot_kjri_dubai.handoff import is_from_staff_group
        assert is_from_staff_group(chat_id=STAFF_GROUP_ID, staff_group_id="") is False


# ---------------------------------------------------------------------------
# Helpers for inactivity timeout tests
# ---------------------------------------------------------------------------

def _make_mock_db_fetchall(rows):
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect = MagicMock()
    mock_connect.return_value.__enter__ = lambda s: mock_conn
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)
    return mock_connect, mock_conn, mock_cursor


def _make_mock_db_simple():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect = MagicMock()
    mock_connect.return_value.__enter__ = lambda s: mock_conn
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)
    return mock_connect, mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# update_handoff_activity
# ---------------------------------------------------------------------------

class TestUpdateHandoffActivity:
    def test_executes_update_query(self):
        from chatbot_kjri_dubai.handoff import update_handoff_activity
        mock_connect, mock_conn, mock_cursor = _make_mock_db_simple()
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            update_handoff_activity(FAKE_SESSION_ID)
        sql = mock_cursor.execute.call_args[0][0]
        assert "UPDATE" in sql.upper()
        assert "handoff_queue" in sql

    def test_passes_session_id_as_parameter(self):
        from chatbot_kjri_dubai.handoff import update_handoff_activity
        mock_connect, mock_conn, mock_cursor = _make_mock_db_simple()
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            update_handoff_activity(FAKE_SESSION_ID)
        params = mock_cursor.execute.call_args[0][1]
        assert FAKE_SESSION_ID in params

    def test_commits_transaction(self):
        from chatbot_kjri_dubai.handoff import update_handoff_activity
        mock_connect, mock_conn, mock_cursor = _make_mock_db_simple()
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            update_handoff_activity(FAKE_SESSION_ID)
        mock_conn.commit.assert_called_once()

    def test_handles_db_exception_silently(self):
        from chatbot_kjri_dubai.handoff import update_handoff_activity
        mock_connect = MagicMock(side_effect=Exception("DB down"))
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            update_handoff_activity(FAKE_SESSION_ID)  # must not raise


# ---------------------------------------------------------------------------
# get_timed_out_handoffs
# ---------------------------------------------------------------------------

class TestGetTimedOutHandoffs:
    def test_returns_list_of_dicts_with_session_and_chat_id(self):
        from chatbot_kjri_dubai.handoff import get_timed_out_handoffs
        mock_connect, _, _ = _make_mock_db_fetchall([(FAKE_SESSION_ID, FAKE_CHAT_ID)])
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            result = get_timed_out_handoffs()
        assert result == [{"session_id": FAKE_SESSION_ID, "user_chat_id": FAKE_CHAT_ID}]

    def test_returns_empty_list_when_no_timed_out_handoffs(self):
        from chatbot_kjri_dubai.handoff import get_timed_out_handoffs
        mock_connect, _, _ = _make_mock_db_fetchall([])
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            result = get_timed_out_handoffs()
        assert result == []

    def test_query_filters_by_last_activity_at(self):
        from chatbot_kjri_dubai.handoff import get_timed_out_handoffs
        mock_connect, _, mock_cursor = _make_mock_db_fetchall([])
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            get_timed_out_handoffs(timeout_minutes=10)
        sql = mock_cursor.execute.call_args[0][0]
        assert "last_activity_at" in sql

    def test_query_filters_active_statuses_only(self):
        from chatbot_kjri_dubai.handoff import get_timed_out_handoffs
        mock_connect, _, mock_cursor = _make_mock_db_fetchall([])
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            get_timed_out_handoffs()
        sql = mock_cursor.execute.call_args[0][0]
        assert "pending" in sql
        assert "in_progress" in sql

    def test_returns_multiple_timed_out_handoffs(self):
        from chatbot_kjri_dubai.handoff import get_timed_out_handoffs
        rows = [("telegram_111", 111), ("telegram_222", 222)]
        mock_connect, _, _ = _make_mock_db_fetchall(rows)
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            result = get_timed_out_handoffs()
        assert len(result) == 2
        assert result[0]["session_id"] == "telegram_111"
        assert result[1]["user_chat_id"] == 222

    def test_returns_empty_list_on_db_exception(self):
        from chatbot_kjri_dubai.handoff import get_timed_out_handoffs
        mock_connect = MagicMock(side_effect=Exception("DB down"))
        with patch("chatbot_kjri_dubai.handoff.psycopg2.connect", mock_connect):
            result = get_timed_out_handoffs()
        assert result == []


# ---------------------------------------------------------------------------
# send_user_timeout_message
# ---------------------------------------------------------------------------

class TestSendUserTimeoutMessage:
    @pytest.mark.asyncio
    async def test_sends_message_to_correct_chat_id(self):
        from chatbot_kjri_dubai.handoff import send_user_timeout_message
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_user_timeout_message(BOT_TOKEN, FAKE_CHAT_ID)
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["chat_id"] == FAKE_CHAT_ID

    @pytest.mark.asyncio
    async def test_message_mentions_10_menit(self):
        from chatbot_kjri_dubai.handoff import send_user_timeout_message
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_user_timeout_message(BOT_TOKEN, FAKE_CHAT_ID)
        text = mock_client.post.call_args[1]["json"]["text"]
        assert "10 menit" in text

    @pytest.mark.asyncio
    async def test_message_says_returned_to_virtual_assistant(self):
        from chatbot_kjri_dubai.handoff import send_user_timeout_message
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_user_timeout_message(BOT_TOKEN, FAKE_CHAT_ID)
        text = mock_client.post.call_args[1]["json"]["text"]
        assert "asisten virtual" in text.lower()

    @pytest.mark.asyncio
    async def test_uses_correct_bot_token_in_url(self):
        from chatbot_kjri_dubai.handoff import send_user_timeout_message
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_user_timeout_message(BOT_TOKEN, FAKE_CHAT_ID)
        url = mock_client.post.call_args[0][0]
        assert BOT_TOKEN in url

    @pytest.mark.asyncio
    async def test_failed_response_does_not_raise(self):
        from chatbot_kjri_dubai.handoff import send_user_timeout_message
        mock_cls, mock_client = _make_mock_httpx(status_code=500, ok=False)
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_user_timeout_message(BOT_TOKEN, FAKE_CHAT_ID)


# ---------------------------------------------------------------------------
# send_handoff_timeout_to_staff
# ---------------------------------------------------------------------------

class TestSendHandoffTimeoutToStaff:
    @pytest.mark.asyncio
    async def test_sends_to_staff_group_id(self):
        from chatbot_kjri_dubai.handoff import send_handoff_timeout_to_staff
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_handoff_timeout_to_staff(BOT_TOKEN, STAFF_GROUP_ID, FAKE_SESSION_ID)
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["chat_id"] == STAFF_GROUP_ID

    @pytest.mark.asyncio
    async def test_message_contains_session_id(self):
        from chatbot_kjri_dubai.handoff import send_handoff_timeout_to_staff
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_handoff_timeout_to_staff(BOT_TOKEN, STAFF_GROUP_ID, FAKE_SESSION_ID)
        text = mock_client.post.call_args[1]["json"]["text"]
        assert FAKE_SESSION_ID in text

    @pytest.mark.asyncio
    async def test_message_indicates_auto_close(self):
        from chatbot_kjri_dubai.handoff import send_handoff_timeout_to_staff
        mock_cls, mock_client = _make_mock_httpx()
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_handoff_timeout_to_staff(BOT_TOKEN, STAFF_GROUP_ID, FAKE_SESSION_ID)
        text = mock_client.post.call_args[1]["json"]["text"].lower()
        assert "auto" in text or "timeout" in text or "tidak aktif" in text

    @pytest.mark.asyncio
    async def test_failed_response_does_not_raise(self):
        from chatbot_kjri_dubai.handoff import send_handoff_timeout_to_staff
        mock_cls, mock_client = _make_mock_httpx(status_code=500, ok=False)
        with patch("chatbot_kjri_dubai.handoff.httpx.AsyncClient", mock_cls):
            await send_handoff_timeout_to_staff(BOT_TOKEN, STAFF_GROUP_ID, FAKE_SESSION_ID)


# ---------------------------------------------------------------------------
# check_and_resolve_timed_out_handoffs
# ---------------------------------------------------------------------------

class TestCheckAndResolveTimedOutHandoffs:
    @pytest.mark.asyncio
    async def test_resolves_timed_out_handoff_in_db(self):
        from chatbot_kjri_dubai.handoff import check_and_resolve_timed_out_handoffs
        timed_out = [{"session_id": FAKE_SESSION_ID, "user_chat_id": FAKE_CHAT_ID}]
        with (
            patch("chatbot_kjri_dubai.handoff.get_timed_out_handoffs", return_value=timed_out),
            patch("chatbot_kjri_dubai.handoff.send_user_timeout_message", new_callable=AsyncMock),
            patch("chatbot_kjri_dubai.handoff.send_handoff_timeout_to_staff", new_callable=AsyncMock),
            patch("chatbot_kjri_dubai.handoff.resolve_handoff_by_session", return_value=True) as mock_resolve,
        ):
            count = await check_and_resolve_timed_out_handoffs(BOT_TOKEN, STAFF_GROUP_ID)
        mock_resolve.assert_called_once_with(FAKE_SESSION_ID)
        assert count == 1

    @pytest.mark.asyncio
    async def test_sends_timeout_message_to_user(self):
        from chatbot_kjri_dubai.handoff import check_and_resolve_timed_out_handoffs
        timed_out = [{"session_id": FAKE_SESSION_ID, "user_chat_id": FAKE_CHAT_ID}]
        with (
            patch("chatbot_kjri_dubai.handoff.get_timed_out_handoffs", return_value=timed_out),
            patch("chatbot_kjri_dubai.handoff.send_user_timeout_message", new_callable=AsyncMock) as mock_msg,
            patch("chatbot_kjri_dubai.handoff.send_handoff_timeout_to_staff", new_callable=AsyncMock),
            patch("chatbot_kjri_dubai.handoff.resolve_handoff_by_session", return_value=True),
        ):
            await check_and_resolve_timed_out_handoffs(BOT_TOKEN, STAFF_GROUP_ID)
        mock_msg.assert_called_once_with(BOT_TOKEN, FAKE_CHAT_ID)

    @pytest.mark.asyncio
    async def test_notifies_staff_when_group_id_set(self):
        from chatbot_kjri_dubai.handoff import check_and_resolve_timed_out_handoffs
        timed_out = [{"session_id": FAKE_SESSION_ID, "user_chat_id": FAKE_CHAT_ID}]
        with (
            patch("chatbot_kjri_dubai.handoff.get_timed_out_handoffs", return_value=timed_out),
            patch("chatbot_kjri_dubai.handoff.send_user_timeout_message", new_callable=AsyncMock),
            patch("chatbot_kjri_dubai.handoff.send_handoff_timeout_to_staff", new_callable=AsyncMock) as mock_staff,
            patch("chatbot_kjri_dubai.handoff.resolve_handoff_by_session", return_value=True),
        ):
            await check_and_resolve_timed_out_handoffs(BOT_TOKEN, STAFF_GROUP_ID)
        mock_staff.assert_called_once_with(BOT_TOKEN, STAFF_GROUP_ID, FAKE_SESSION_ID)

    @pytest.mark.asyncio
    async def test_skips_staff_notification_when_no_group_id(self):
        from chatbot_kjri_dubai.handoff import check_and_resolve_timed_out_handoffs
        timed_out = [{"session_id": FAKE_SESSION_ID, "user_chat_id": FAKE_CHAT_ID}]
        with (
            patch("chatbot_kjri_dubai.handoff.get_timed_out_handoffs", return_value=timed_out),
            patch("chatbot_kjri_dubai.handoff.send_user_timeout_message", new_callable=AsyncMock),
            patch("chatbot_kjri_dubai.handoff.send_handoff_timeout_to_staff", new_callable=AsyncMock) as mock_staff,
            patch("chatbot_kjri_dubai.handoff.resolve_handoff_by_session", return_value=True),
        ):
            await check_and_resolve_timed_out_handoffs(BOT_TOKEN, staff_group_id="")
        mock_staff.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_timed_out_handoffs(self):
        from chatbot_kjri_dubai.handoff import check_and_resolve_timed_out_handoffs
        with patch("chatbot_kjri_dubai.handoff.get_timed_out_handoffs", return_value=[]):
            count = await check_and_resolve_timed_out_handoffs(BOT_TOKEN, STAFF_GROUP_ID)
        assert count == 0

    @pytest.mark.asyncio
    async def test_handles_multiple_timed_out_handoffs(self):
        from chatbot_kjri_dubai.handoff import check_and_resolve_timed_out_handoffs
        timed_out = [
            {"session_id": "telegram_111", "user_chat_id": 111},
            {"session_id": "telegram_222", "user_chat_id": 222},
        ]
        with (
            patch("chatbot_kjri_dubai.handoff.get_timed_out_handoffs", return_value=timed_out),
            patch("chatbot_kjri_dubai.handoff.send_user_timeout_message", new_callable=AsyncMock),
            patch("chatbot_kjri_dubai.handoff.send_handoff_timeout_to_staff", new_callable=AsyncMock),
            patch("chatbot_kjri_dubai.handoff.resolve_handoff_by_session", return_value=True),
        ):
            count = await check_and_resolve_timed_out_handoffs(BOT_TOKEN, STAFF_GROUP_ID)
        assert count == 2

    @pytest.mark.asyncio
    async def test_continues_processing_after_single_handoff_error(self):
        from chatbot_kjri_dubai.handoff import check_and_resolve_timed_out_handoffs
        timed_out = [
            {"session_id": "telegram_111", "user_chat_id": 111},
            {"session_id": "telegram_222", "user_chat_id": 222},
        ]
        call_count = 0

        async def flaky_send(bot_token: str, chat_id: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Network error")

        with (
            patch("chatbot_kjri_dubai.handoff.get_timed_out_handoffs", return_value=timed_out),
            patch("chatbot_kjri_dubai.handoff.send_user_timeout_message", side_effect=flaky_send),
            patch("chatbot_kjri_dubai.handoff.send_handoff_timeout_to_staff", new_callable=AsyncMock),
            patch("chatbot_kjri_dubai.handoff.resolve_handoff_by_session", return_value=True) as mock_resolve,
        ):
            count = await check_and_resolve_timed_out_handoffs(BOT_TOKEN, STAFF_GROUP_ID)
        assert mock_resolve.call_count == 1
        assert count == 1


# ---------------------------------------------------------------------------
# CRISIS_KEYWORDS — PMI / violence scenarios
# ---------------------------------------------------------------------------

class TestCrisisKeywords:
    """Verify that PMI/violence crisis keywords trigger escalation.

    These tests cover the conservative keyword set; adjust alongside CRISIS_KEYWORDS
    in handoff.py when SOP changes.
    """

    def test_disiksa_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Saya disiksa oleh majikan saya") is True

    def test_dipukul_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Saya dipukul setiap hari") is True

    def test_dianiaya_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Saya dianiaya sejak bulan lalu") is True

    def test_penyiksaan_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Ada penyiksaan di tempat kerja") is True

    def test_disekap_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Saya disekap dan tidak boleh keluar") is True

    def test_paspor_ditahan_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Paspor ditahan oleh majikan") is True

    def test_dokumen_ditahan_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Semua dokumen ditahan, tidak bisa kemana-mana") is True

    def test_diancam_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Saya diancam jika lapor ke polisi") is True

    def test_tidak_dibayar_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Gaji saya tidak dibayar selama 3 bulan") is True

    def test_gaji_tidak_dibayar_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("gaji tidak dibayar sudah lama") is True

    def test_kekerasan_fisik_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Terjadi kekerasan fisik di rumah majikan") is True

    def test_terancam_triggers(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("Nyawa saya terancam") is True

    def test_case_insensitive_disiksa(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        assert detect_escalation_trigger("DISIKSA majikan jahat") is True

    def test_normal_passport_question_no_trigger(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        # General question should not trigger crisis path
        assert detect_escalation_trigger("Berapa biaya perpanjang paspor?") is False

    def test_normal_salary_question_no_trigger(self):
        from chatbot_kjri_dubai.handoff import detect_escalation_trigger
        # Discussing salary in neutral context should not trigger
        assert detect_escalation_trigger("Berapa gaji rata-rata TKI di Dubai?") is False


# ---------------------------------------------------------------------------
# can_create_bot_failure_handoff — cooldown / dedupe logic
# ---------------------------------------------------------------------------

class TestBotFailureCooldown:
    def setup_method(self):
        """Reset in-memory cooldown state before each test."""
        import chatbot_kjri_dubai.handoff as hm
        with hm._bot_failure_lock:
            hm._bot_failure_ts.clear()

    def test_first_call_returns_true(self):
        from chatbot_kjri_dubai.handoff import can_create_bot_failure_handoff
        assert can_create_bot_failure_handoff("session_abc") is True

    def test_second_immediate_call_returns_false(self):
        from chatbot_kjri_dubai.handoff import can_create_bot_failure_handoff
        can_create_bot_failure_handoff("session_abc")
        assert can_create_bot_failure_handoff("session_abc") is False

    def test_different_sessions_are_independent(self):
        from chatbot_kjri_dubai.handoff import can_create_bot_failure_handoff
        assert can_create_bot_failure_handoff("session_1") is True
        assert can_create_bot_failure_handoff("session_2") is True

    def test_cooldown_zero_allows_repeated_calls(self, monkeypatch):
        monkeypatch.setenv("HANDOFF_BOT_FAILURE_COOLDOWN_SEC", "0")
        from chatbot_kjri_dubai.handoff import can_create_bot_failure_handoff
        assert can_create_bot_failure_handoff("session_x") is True
        assert can_create_bot_failure_handoff("session_x") is True

    def test_records_timestamp_on_true(self):
        import chatbot_kjri_dubai.handoff as hm
        hm.can_create_bot_failure_handoff("session_ts")
        with hm._bot_failure_lock:
            assert "session_ts" in hm._bot_failure_ts
