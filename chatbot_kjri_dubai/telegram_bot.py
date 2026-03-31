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

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
NGROK_API = os.environ.get("NGROK_API", "http://ngrok:4040")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message")
    if not message or not message.get("text"):
        return {"ok": True}

    chat_id = message["chat"]["id"]
    user_text = message["text"]
    user_id = str(chat_id)
    session_id = f"telegram_{chat_id}"

    # Handle /start command
    if user_text.strip() == "/start":
        user_text = "Halo"

    # Get or create session
    session = await session_service.get_session(
        app_name="kjri_dubai_telegram",
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        session = await session_service.create_session(
            app_name="kjri_dubai_telegram",
            user_id=user_id,
            session_id=session_id,
        )

    # Run agent and collect final response
    content = types.Content(parts=[types.Part(text=user_text)], role="user")
    response_text = ""

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content,
        ):
            if (
                event.content
                and event.content.parts
                and event.author == root_agent.name
            ):
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_text = part.text
    except Exception:
        logger.exception("Error running agent for chat_id=%s", chat_id)
        response_text = (
            "Maaf, terjadi kesalahan pada sistem. Silakan coba lagi nanti."
        )

    if response_text:
        await send_message(chat_id, response_text)

    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
