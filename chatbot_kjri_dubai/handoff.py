"""Human Agent Handoff module for KJRI Dubai chatbot.

Detects escalation triggers, queues requests in PostgreSQL, and notifies
KJRI staff via a Telegram group. Staff can reply back to users via /reply.
"""

import logging
import os
import re
from typing import Optional

import httpx
import psycopg2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Escalation keyword detection
# ---------------------------------------------------------------------------

ESCALATION_KEYWORDS = [
    r"agen",
    r"manusia",
    r"petugas",
    r"bicara dengan",
    r"hubungi",
    r"tidak membantu",
    r"tidak ada jawaban",
    r"operator",
    r"berbicara dengan",
    r"minta tolong manusia",
]

_ESCALATION_PATTERN = re.compile(
    "|".join(ESCALATION_KEYWORDS),
    re.IGNORECASE,
)

USER_CONFIRMATION_MSG = (
    "Permintaan Anda telah diteruskan ke petugas KJRI. "
    "Mohon tunggu balasan dari staf kami."
)


def detect_escalation_trigger(text: str) -> bool:
    """Return True if text contains any escalation keyword."""
    return bool(_ESCALATION_PATTERN.search(text))


def is_from_staff_group(chat_id: str, staff_group_id: str) -> bool:
    """Return True only if chat_id matches the configured staff group and group is set."""
    if not staff_group_id:
        return False
    return str(chat_id) == str(staff_group_id)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

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


def save_handoff_to_db(
    session_id: str,
    user_chat_id: int,
    pengguna_id: Optional[str],
    nama_user: Optional[str],
    pertanyaan_terakhir: Optional[str],
    layanan_dicari: Optional[str] = None,
) -> str:
    """Insert handoff request into handoff_queue. Returns UUID handoff_id."""
    conn_string = _get_conn_string()
    with psycopg2.connect(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO handoff_queue
                    (session_id, user_chat_id, pengguna_id, nama_user,
                     pertanyaan_terakhir, layanan_dicari)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    session_id,
                    user_chat_id,
                    pengguna_id,
                    nama_user,
                    pertanyaan_terakhir,
                    layanan_dicari,
                ),
            )
            handoff_id = str(cur.fetchone()[0])
        conn.commit()
    return handoff_id


def get_user_chat_id_by_session(session_id: str) -> Optional[int]:
    """Return user_chat_id for the most recent handoff with this session_id, or None."""
    conn_string = _get_conn_string()
    with psycopg2.connect(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_chat_id FROM handoff_queue
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            )
            row = cur.fetchone()
    return int(row[0]) if row else None


def has_active_handoff(session_id: str) -> bool:
    """Return True if session has a pending or in_progress handoff."""
    conn_string = _get_conn_string()
    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM handoff_queue
                    WHERE session_id = %s
                      AND status IN ('pending', 'in_progress')
                    LIMIT 1
                    """,
                    (session_id,),
                )
                return cur.fetchone() is not None
    except Exception:
        logger.exception("Error checking active handoff for session=%s", session_id)
        return False


def update_handoff_status(handoff_id: str, status: str) -> None:
    """Update handoff status: 'pending' → 'in_progress' → 'resolved'."""
    conn_string = _get_conn_string()
    with psycopg2.connect(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE handoff_queue
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (status, handoff_id),
            )
        conn.commit()


def resolve_handoff_by_session(session_id: str) -> bool:
    """Set all active handoffs for session to 'resolved'. Returns True if any were updated."""
    conn_string = _get_conn_string()
    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE handoff_queue
                    SET status = 'resolved', updated_at = NOW()
                    WHERE session_id = %s AND status IN ('pending', 'in_progress')
                    """,
                    (session_id,),
                )
                updated = cur.rowcount
            conn.commit()
        return updated > 0
    except Exception:
        logger.exception("Error resolving handoff for session=%s", session_id)
        return False


def set_handoff_in_progress_by_session(session_id: str) -> None:
    """Move pending handoffs for session to in_progress when staff first replies."""
    conn_string = _get_conn_string()
    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE handoff_queue
                    SET status = 'in_progress', updated_at = NOW()
                    WHERE session_id = %s AND status = 'pending'
                    """,
                    (session_id,),
                )
            conn.commit()
    except Exception:
        logger.exception("Error setting in_progress for session=%s", session_id)


# ---------------------------------------------------------------------------
# Telegram notification helpers
# ---------------------------------------------------------------------------

def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def forward_user_message_to_staff(
    bot_token: str,
    staff_group_id: str,
    session_id: str,
    nama_user: str,
    pesan_user: str,
) -> None:
    """Forward a user's follow-up message to the staff group during active handoff."""
    text = (
        f"\U0001f4ac <b>Pesan lanjutan dari User</b>\n"
        f"\U0001f464 User: {_html_escape(nama_user)}\n"
        f"\U0001f4cb Session: <code>{_html_escape(session_id)}</code>\n\n"
        f"{_html_escape(pesan_user)}\n\n"
        f"Balas dengan:\n"
        f"<code>/reply {_html_escape(session_id)} &lt;pesan kamu&gt;</code>"
    )
    telegram_api = f"https://api.telegram.org/bot{bot_token}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{telegram_api}/sendMessage",
            json={"chat_id": staff_group_id, "text": text, "parse_mode": "HTML"},
        )
    if resp.status_code != 200 or not resp.json().get("ok"):
        logger.error(
            "Failed to forward user message to staff (session=%s): %s",
            session_id,
            resp.text,
        )


async def send_staff_notification(
    bot_token: str,
    staff_group_id: str,
    handoff_id: str,
    session_id: str,
    nama_user: str,
    pertanyaan_terakhir: str,
) -> None:
    """Send escalation notification to KJRI staff Telegram group."""
    text = (
        f"\U0001f514 <b>Eskalasi ke Agen Manusia</b>\n"
        f"\U0001f464 User: {_html_escape(nama_user)}\n"
        f"\U0001f4ac Pertanyaan: {_html_escape(pertanyaan_terakhir)}\n"
        f"\U0001f4cb Session: <code>{_html_escape(session_id)}</code>\n\n"
        f"Balas dengan:\n"
        f"<code>/reply {_html_escape(session_id)} &lt;pesan kamu&gt;</code>"
    )
    telegram_api = f"https://api.telegram.org/bot{bot_token}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{telegram_api}/sendMessage",
            json={
                "chat_id": staff_group_id,
                "text": text,
                "parse_mode": "HTML",
            },
        )
    if resp.status_code != 200 or not resp.json().get("ok"):
        logger.error(
            "Failed to send staff notification (handoff_id=%s): %s",
            handoff_id,
            resp.text,
        )


async def handle_staff_reply(
    bot_token: str,
    user_chat_id: int,
    pesan_staf: str,
) -> None:
    """Forward a staff reply to the user via Telegram."""
    reply_text = f"\U0001f4e9 <b>Balasan dari Petugas KJRI:</b>\n\n{_html_escape(pesan_staf)}"
    telegram_api = f"https://api.telegram.org/bot{bot_token}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{telegram_api}/sendMessage",
            json={
                "chat_id": user_chat_id,
                "text": reply_text,
                "parse_mode": "HTML",
            },
        )
    if resp.status_code != 200 or not resp.json().get("ok"):
        logger.error(
            "Failed to forward staff reply to user_chat_id=%s: %s",
            user_chat_id,
            resp.text,
        )


# ---------------------------------------------------------------------------
# Inactivity timeout helpers
# ---------------------------------------------------------------------------

def update_handoff_activity(session_id: str) -> None:
    """Refresh last_activity_at for active handoffs belonging to session_id."""
    conn_string = _get_conn_string()
    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE handoff_queue
                    SET last_activity_at = NOW()
                    WHERE session_id = %s
                      AND status IN ('pending', 'in_progress')
                    """,
                    (session_id,),
                )
            conn.commit()
    except Exception:
        logger.exception("Error updating handoff activity for session=%s", session_id)


def get_timed_out_handoffs(timeout_minutes: int = 10) -> list[dict]:
    """Return active handoffs where last_activity_at is older than timeout_minutes."""
    conn_string = _get_conn_string()
    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT session_id, user_chat_id
                    FROM handoff_queue
                    WHERE status IN ('pending', 'in_progress')
                      AND last_activity_at < NOW() - (%s * INTERVAL '1 minute')
                    """,
                    (timeout_minutes,),
                )
                rows = cur.fetchall()
        return [{"session_id": row[0], "user_chat_id": row[1]} for row in rows]
    except Exception:
        logger.exception("Error fetching timed-out handoffs")
        return []


async def send_user_timeout_message(bot_token: str, user_chat_id: int) -> None:
    """Notify user that their handoff session expired due to inactivity."""
    text = (
        "⏰ <b>Sesi dengan petugas KJRI telah berakhir</b> karena tidak ada "
        "aktivitas selama 10 menit.\n\n"
        "Anda kembali dilayani oleh asisten virtual. "
        "Silakan kirim pesan jika masih butuh bantuan."
    )
    telegram_api = f"https://api.telegram.org/bot{bot_token}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{telegram_api}/sendMessage",
            json={"chat_id": user_chat_id, "text": text, "parse_mode": "HTML"},
        )
    if resp.status_code != 200 or not resp.json().get("ok"):
        logger.error(
            "Failed to send timeout message to user_chat_id=%s: %s",
            user_chat_id,
            resp.text,
        )


async def send_handoff_timeout_to_staff(
    bot_token: str,
    staff_group_id: str,
    session_id: str,
) -> None:
    """Notify staff group that a handoff session was auto-closed due to user inactivity."""
    text = (
        f"⏰ <b>Handoff auto-closed</b>\n"
        f"\U0001f4cb Session: <code>{_html_escape(session_id)}</code>\n"
        f"User tidak aktif selama 10 menit — sesi otomatis ditutup."
    )
    telegram_api = f"https://api.telegram.org/bot{bot_token}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{telegram_api}/sendMessage",
            json={"chat_id": staff_group_id, "text": text, "parse_mode": "HTML"},
        )
    if resp.status_code != 200 or not resp.json().get("ok"):
        logger.error(
            "Failed to send timeout notification to staff (session=%s): %s",
            session_id,
            resp.text,
        )


async def check_and_resolve_timed_out_handoffs(
    bot_token: str,
    staff_group_id: str,
    timeout_minutes: int = 10,
) -> int:
    """Resolve all handoffs that exceeded inactivity timeout. Returns count resolved."""
    timed_out = get_timed_out_handoffs(timeout_minutes)
    resolved = 0
    for handoff in timed_out:
        session_id = handoff["session_id"]
        user_chat_id = handoff["user_chat_id"]
        try:
            await send_user_timeout_message(bot_token, user_chat_id)
            if staff_group_id:
                await send_handoff_timeout_to_staff(bot_token, staff_group_id, session_id)
            resolve_handoff_by_session(session_id)
            resolved += 1
        except Exception:
            logger.exception("Error resolving timed-out handoff for session=%s", session_id)
    return resolved
