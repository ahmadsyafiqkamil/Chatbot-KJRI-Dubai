import os
import logging
import asyncio

import httpx
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from chatbot_kjri_dubai.agent import root_agent
from chatbot_kjri_dubai.markdown_converter import md_to_html
from chatbot_kjri_dubai.handoff import (
    can_create_bot_failure_handoff,
    check_and_resolve_timed_out_handoffs,
    detect_escalation_trigger,
    forward_user_message_to_staff,
    get_user_chat_id_by_session,
    handle_staff_reply,
    has_active_handoff,
    is_from_staff_group,
    resolve_handoff_by_session,
    save_handoff_to_db,
    send_staff_notification,
    set_handoff_in_progress_by_session,
    update_handoff_activity,
    USER_CONFIRMATION_MSG,
)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
NGROK_API = os.environ.get("NGROK_API", "http://ngrok:4040")
KJRI_STAFF_GROUP_ID = os.environ.get("KJRI_STAFF_TELEGRAM_GROUP_ID", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mask token in logs — show only first 10 chars so logs are safe to share.
_token_prefix = (TELEGRAM_BOT_TOKEN[:10] + "***") if len(TELEGRAM_BOT_TOKEN) > 10 else "***"
logger.info("Telegram bot initialising. Token prefix: %s", _token_prefix)

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="kjri_dubai_telegram",
    session_service=session_service,
)


async def send_message(chat_id: int, text: str) -> None:
    """Send a message to Telegram. Falls back to plain text if HTML parse fails."""
    async with httpx.AsyncClient(timeout=30) as client:
        html_text = md_to_html(text)
        chunks = [html_text[i : i + 4096] for i in range(0, len(html_text), 4096)]
        for chunk in chunks:
            resp = await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"},
            )
            if resp.status_code != 200 or not resp.json().get("ok"):
                # Fallback: send as plain text without formatting
                plain_chunks = [text[i : i + 4096] for i in range(0, len(text), 4096)]
                for plain_chunk in plain_chunks:
                    await client.post(
                        f"{TELEGRAM_API}/sendMessage",
                        json={"chat_id": chat_id, "text": plain_chunk},
                    )
                return


async def set_webhook(url: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": url})
        data = resp.json()
        if data.get("ok"):
            logger.info("Webhook set: %s", url)
        else:
            logger.error("Failed to set webhook: %s", data)


async def get_ngrok_url() -> str | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{NGROK_API}/api/tunnels")
            for tunnel in resp.json().get("tunnels", []):
                public_url = tunnel.get("public_url", "")
                if public_url.startswith("https://"):
                    return public_url
    except Exception:
        return None
    return None


async def _handoff_timeout_loop() -> None:
    """Background task: check and resolve timed-out handoff sessions every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        try:
            resolved = await check_and_resolve_timed_out_handoffs(
                bot_token=TELEGRAM_BOT_TOKEN,
                staff_group_id=KJRI_STAFF_GROUP_ID,
            )
            if resolved:
                logger.info("Auto-resolved %d timed-out handoff(s)", resolved)
        except Exception:
            logger.exception("Error in handoff timeout loop")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Set webhook on startup
    webhook_base = WEBHOOK_BASE_URL
    if not webhook_base:
        for _ in range(10):
            webhook_base = await get_ngrok_url()
            if webhook_base:
                break
            logger.info("Waiting for ngrok...")
            await asyncio.sleep(3)

    if webhook_base:
        await set_webhook(f"{webhook_base}/webhook")
    else:
        logger.warning(
            "No webhook URL available. Set WEBHOOK_BASE_URL env var or ensure ngrok is running."
        )

    timeout_task = asyncio.create_task(_handoff_timeout_loop())
    try:
        yield
    finally:
        timeout_task.cancel()
        try:
            await timeout_task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _trigger_bot_failure_handoff(
    chat_id: int,
    session_id: str,
    user_text: str,
) -> None:
    """Escalate to human staff when the bot fails to produce a response.

    Deduplication strategy:
    - If session already has an active handoff: send a short "already queued" message, no new ticket.
    - If cooldown (HANDOFF_BOT_FAILURE_COOLDOWN_SEC) has not expired: same short message, no new ticket.
    - Otherwise: create a new handoff ticket, notify staff (if group ID configured), confirm to user.
    """
    if has_active_handoff(session_id):
        logger.info(
            "Bot-failure handoff skipped (active handoff exists) for session=%s", session_id
        )
        await send_message(
            chat_id,
            "Permintaan Anda sedang dalam antrean petugas. Mohon tunggu balasan staf kami.",
        )
        return

    if not can_create_bot_failure_handoff(session_id):
        logger.info(
            "Bot-failure handoff skipped (cooldown active) for session=%s", session_id
        )
        await send_message(
            chat_id,
            "Maaf, sistem sedang mengalami kendala. Permintaan Anda sudah dalam antrean petugas.",
        )
        return

    try:
        handoff_id = save_handoff_to_db(
            session_id=session_id,
            user_chat_id=chat_id,
            pengguna_id=None,
            nama_user=None,
            pertanyaan_terakhir=user_text,
            layanan_dicari=None,
        )
        logger.info(
            "Bot-failure handoff created id=%s for session=%s", handoff_id, session_id
        )
        if KJRI_STAFF_GROUP_ID:
            await send_staff_notification(
                bot_token=TELEGRAM_BOT_TOKEN,
                staff_group_id=KJRI_STAFF_GROUP_ID,
                handoff_id=handoff_id,
                session_id=session_id,
                nama_user=str(chat_id),
                pertanyaan_terakhir=f"[BOT FAILURE] {user_text}",
            )
        else:
            logger.warning(
                "KJRI_STAFF_TELEGRAM_GROUP_ID not set; skipping staff notification for bot failure"
            )
    except Exception:
        logger.exception(
            "Bot-failure handoff save/notify failed for chat_id=%s session=%s",
            chat_id, session_id,
        )
    await send_message(chat_id, USER_CONFIRMATION_MSG)


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logger.info("Webhook received: update_id=%s", data.get("update_id"))

    message = data.get("message")
    if not message:
        logger.info("Webhook: no 'message' field in update, skipping")
        return {"ok": True}

    if not message.get("text"):
        logger.info(
            "Webhook: message from chat_id=%s has no text (type=%s), skipping",
            message.get("chat", {}).get("id"),
            list(message.keys()),
        )
        return {"ok": True}

    chat_id = message["chat"]["id"]
    user_text = message["text"]
    user_id = str(chat_id)
    session_id = f"telegram_{chat_id}"

    logger.info(
        "Webhook: chat_id=%s session_id=%s text=%r",
        chat_id, session_id, user_text[:80],
    )

    # ---------------------------------------------------------------------------
    # Staff commands — only accepted from KJRI_STAFF_GROUP_ID
    # ---------------------------------------------------------------------------
    if user_text.startswith("/reply ") or user_text.startswith("/resolve "):
        logger.info("Webhook: detected staff command from chat_id=%s", chat_id)
        if not is_from_staff_group(str(chat_id), KJRI_STAFF_GROUP_ID):
            logger.warning("Webhook: staff command from non-staff chat_id=%s, ignoring", chat_id)
            return {"ok": True}

        if user_text.startswith("/reply "):
            parts = user_text[len("/reply "):].split(" ", 1)
            if len(parts) < 2:
                await send_message(chat_id, "Format: /reply &lt;session_id&gt; &lt;pesan&gt;")
                return {"ok": True}
            target_session_id, pesan_staf = parts[0], parts[1]
            target_chat_id = get_user_chat_id_by_session(target_session_id)
            if target_chat_id is None:
                await send_message(chat_id, f"Session <code>{target_session_id}</code> tidak ditemukan.")
                return {"ok": True}
            set_handoff_in_progress_by_session(target_session_id)
            logger.info("Webhook: /reply to session=%s chat_id=%s", target_session_id, target_chat_id)
            try:
                await handle_staff_reply(
                    bot_token=TELEGRAM_BOT_TOKEN,
                    user_chat_id=target_chat_id,
                    pesan_staf=pesan_staf,
                )
            except Exception:
                logger.exception("Failed to forward staff reply for session=%s", target_session_id)

        elif user_text.startswith("/resolve "):
            target_session_id = user_text[len("/resolve "):].strip()
            target_chat_id = get_user_chat_id_by_session(target_session_id)
            logger.info("Webhook: /resolve session=%s", target_session_id)
            resolved = resolve_handoff_by_session(target_session_id)
            if resolved:
                logger.info("Webhook: handoff resolved for session=%s", target_session_id)
                if target_chat_id:
                    try:
                        await handle_staff_reply(
                            bot_token=TELEGRAM_BOT_TOKEN,
                            user_chat_id=target_chat_id,
                            pesan_staf="Sesi Anda dengan petugas KJRI telah selesai. Anda dapat melanjutkan percakapan dengan bot kami.",
                        )
                    except Exception:
                        logger.exception("Failed to notify user on resolve for session=%s", target_session_id)
                await send_message(chat_id, f"Sesi <code>{target_session_id}</code> berhasil di-resolve. Bot aktif kembali untuk user.")
            else:
                logger.warning("Webhook: no active handoff found for session=%s", target_session_id)
                await send_message(chat_id, f"Tidak ada handoff aktif untuk sesi <code>{target_session_id}</code>.")

        return {"ok": True}

    # ---------------------------------------------------------------------------
    # Handle /start command
    # ---------------------------------------------------------------------------
    if user_text.strip() == "/start":
        user_text = "Halo"

    # ---------------------------------------------------------------------------
    # Guard: session already in handoff queue — forward ke staf, bot diam
    # ---------------------------------------------------------------------------
    active_handoff = has_active_handoff(session_id)
    logger.info("Webhook: has_active_handoff(%s) = %s", session_id, active_handoff)

    if active_handoff:
        update_handoff_activity(session_id)
        logger.info("Webhook: forwarding user message to staff for session=%s", session_id)
        if KJRI_STAFF_GROUP_ID:
            try:
                await forward_user_message_to_staff(
                    bot_token=TELEGRAM_BOT_TOKEN,
                    staff_group_id=KJRI_STAFF_GROUP_ID,
                    session_id=session_id,
                    nama_user=str(chat_id),
                    pesan_user=user_text,
                )
            except Exception:
                logger.exception("Failed to forward user message to staff for session=%s", session_id)
        return {"ok": True}

    # ---------------------------------------------------------------------------
    # Escalation trigger detection — intercept before agent
    # ---------------------------------------------------------------------------
    escalation = detect_escalation_trigger(user_text)
    logger.info("Webhook: detect_escalation_trigger = %s for session=%s", escalation, session_id)

    if escalation:
        try:
            handoff_id = save_handoff_to_db(
                session_id=session_id,
                user_chat_id=chat_id,
                pengguna_id=None,
                nama_user=None,
                pertanyaan_terakhir=user_text,
                layanan_dicari=None,
            )
            logger.info("Webhook: handoff created id=%s for session=%s", handoff_id, session_id)
            if KJRI_STAFF_GROUP_ID:
                await send_staff_notification(
                    bot_token=TELEGRAM_BOT_TOKEN,
                    staff_group_id=KJRI_STAFF_GROUP_ID,
                    handoff_id=handoff_id,
                    session_id=session_id,
                    nama_user=str(chat_id),
                    pertanyaan_terakhir=user_text,
                )
            else:
                logger.warning("KJRI_STAFF_TELEGRAM_GROUP_ID not set; skipping staff notification")
        except Exception:
            logger.exception("Handoff save/notify failed for chat_id=%s", chat_id)
        await send_message(chat_id, USER_CONFIRMATION_MSG)
        return {"ok": True}

    # ---------------------------------------------------------------------------
    # Normal agent flow (TAHAP 1–4)
    # ---------------------------------------------------------------------------
    logger.info("Webhook: running agent for session=%s text=%r", session_id, user_text[:80])

    # Get or create session
    session = await session_service.get_session(
        app_name="kjri_dubai_telegram",
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        logger.info("Webhook: creating new session for session_id=%s", session_id)
        session = await session_service.create_session(
            app_name="kjri_dubai_telegram",
            user_id=user_id,
            session_id=session_id,
        )
    else:
        logger.info("Webhook: existing session found for session_id=%s", session_id)

    # Run agent and collect final response
    content = types.Content(parts=[types.Part(text=user_text)], role="user")
    response_parts: list[str] = []

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content,
        ):
            author = getattr(event, "author", "?")
            is_final = event.is_final_response()
            logger.debug(
                "Webhook: event author=%s is_final=%s has_content=%s",
                author,
                is_final,
                bool(event.content),
            )
            if is_final:
                if not event.content or not event.content.parts:
                    logger.warning(
                        "Webhook: final_response has no content/parts — "
                        "author=%s session=%s",
                        author, session_id,
                    )
                else:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            logger.info(
                                "Webhook: final response part from author=%s text=%r",
                                author,
                                part.text[:100],
                            )
                            response_parts.append(part.text)
                        else:
                            part_type = type(part).__name__
                            logger.warning(
                                "Webhook: final_response part has no text — "
                                "author=%s part_type=%s session=%s",
                                author, part_type, session_id,
                            )
    except Exception:
        logger.exception("Error running agent for chat_id=%s session=%s", chat_id, session_id)
        await _trigger_bot_failure_handoff(chat_id, session_id, user_text)
        return {"ok": True}

    response_text = "\n".join(response_parts).strip()
    logger.info(
        "Webhook: agent done for session=%s, response_text length=%d",
        session_id, len(response_text),
    )

    if response_text:
        await send_message(chat_id, response_text)
    else:
        logger.warning(
            "Webhook: agent produced no text response for session=%s text=%r — "
            "triggering bot-failure handoff",
            session_id, user_text[:80],
        )
        await _trigger_bot_failure_handoff(chat_id, session_id, user_text)

    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
