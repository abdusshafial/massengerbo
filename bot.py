"""Telegram AI assistant with an optional Telegram Mini App."""
from __future__ import annotations

import html
import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
BOT_NAME = os.getenv("BOT_NAME", "E Premium").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
MAX_HISTORY = 12
MAX_MESSAGE = 3900

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("epremium")
history: dict[int, deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=MAX_HISTORY))


def api_request(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=70) as response:
        return json.loads(response.read().decode("utf-8"))


def telegram(method: str, payload: dict) -> dict:
    return api_request(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}", payload)


def keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Chat with AI", "callback_data": "chat"}],
            [
                {"text": "Premium", "callback_data": "premium"},
                {"text": "How it works", "callback_data": "help"},
            ],
        ]
    }


def launch_keyboard() -> dict:
    if not WEBAPP_URL:
        return keyboard()
    return {
        "keyboard": [
            [{"text": "Open E Premium", "web_app": {"url": WEBAPP_URL}}],
            [{"text": "/new"}, {"text": "/help"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def send(chat_id: int, text: str, *, markup: dict | None = None) -> None:
    chunks = [text[i:i + MAX_MESSAGE] for i in range(0, len(text), MAX_MESSAGE)] or [""]
    for index, chunk in enumerate(chunks):
        payload: dict = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}
        if markup and index == len(chunks) - 1:
            payload["reply_markup"] = markup
        telegram("sendMessage", payload)


def welcome(chat_id: int, first_name: str) -> None:
    name = html.escape(first_name or "there")
    send(
        chat_id,
        f"<b>&#10022; {html.escape(BOT_NAME)}</b>\n"
        "<i>Your personal AI space.</i>\n\n"
        f"Hi {name}! Send me a message and I will give you a thoughtful, useful reply. "
        "Ask a question, get ideas, or let me help write something.\n\n"
        "<b>Choose a shortcut below, or just start chatting.</b>",
        markup=launch_keyboard(),
    )


def ai_reply(chat_id: int, message: str) -> str:
    messages = list(history[chat_id])
    messages.append({"role": "user", "content": message})
    response = api_request(
        "https://api.openai.com/v1/responses",
        {
            "model": MODEL,
            "instructions": (
                f"You are {BOT_NAME}, a warm, capable Telegram assistant. "
                "Answer the user's actual question clearly and helpfully. Use concise "
                "formatting that reads well in chat. Ask one focused follow-up only "
                "when essential. Never claim a paid subscription or feature is active "
                "unless the user has configured it."
            ),
            "input": messages,
            "max_output_tokens": 700,
        },
        {"Authorization": f"Bearer {OPENAI_API_KEY}"},
    )
    answer = "".join(
        part.get("text", "")
        for item in response.get("output", []) if item.get("type") == "message"
        for part in item.get("content", []) if part.get("type") == "output_text"
    ).strip()
    if not answer:
        raise RuntimeError("The AI service returned an empty answer")
    history[chat_id].append({"role": "user", "content": message})
    history[chat_id].append({"role": "assistant", "content": answer})
    return answer


def answer_user(chat_id: int, text: str) -> None:
    try:
        telegram("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        send(chat_id, html.escape(ai_reply(chat_id, text)), markup=keyboard())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        log.error("API returned HTTP %s: %s", exc.code, detail)
        send(chat_id, "I hit a temporary service issue. Please try again in a moment.")
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
        log.exception("Could not answer message: %s", exc)
        send(chat_id, "I could not reach my AI service just now. Please try again shortly.")


def handle_message(message: dict) -> None:
    chat_id = message.get("chat", {}).get("id")
    if chat_id is None:
        return
    web_app_data = message.get("web_app_data", {}).get("data")
    if web_app_data:
        try:
            data = json.loads(web_app_data)
            if data.get("type") == "message":
                text = str(data.get("text", "")).strip()[:4000]
                if text:
                    answer_user(chat_id, text)
        except (json.JSONDecodeError, TypeError):
            log.warning("Ignoring malformed Mini App data")
        return

    text = (message.get("text") or "").strip()
    if not text:
        send(chat_id, "I can help with text messages for now. Send me a question or idea.")
        return
    command = text.split()[0].split("@")[0].lower()
    if command == "/start":
        welcome(chat_id, message.get("from", {}).get("first_name", "there"))
    elif command in ("/help", "/menu"):
        send(chat_id, "<b>How can I help?</b>\n\nSend a question or message and I will reply. Use /new to start fresh.", markup=launch_keyboard())
    elif command == "/new":
        history.pop(chat_id, None)
        send(chat_id, "<b>Fresh conversation &#10022;</b>\nWhat would you like to talk about?", markup=launch_keyboard())
    elif text.startswith("/"):
        send(chat_id, "I do not recognize that command. Try /help or send me a message.")
    else:
        answer_user(chat_id, text)


def handle_callback(callback: dict) -> None:
    callback_id = callback.get("id")
    chat_id = callback.get("message", {}).get("chat", {}).get("id")
    data = callback.get("data", "")
    if callback_id:
        telegram("answerCallbackQuery", {"callback_query_id": callback_id})
    if chat_id is None:
        return
    if data == "chat":
        send(chat_id, "<b>I am here.</b>\nSend your question or tell me what you need help with.")
    elif data == "premium":
        send(chat_id, "<b>&#10022; Premium</b>\n\nSubscription plans and payments have not been configured yet. You can chat with the AI assistant here.", markup=keyboard())
    elif data == "help":
        send(chat_id, "<b>Simple to use</b>\n\n1. Send any question or message.\n2. Get a helpful reply.\n3. Use /new to clear the chat context.", markup=keyboard())


def main() -> None:
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and OPENAI_API_KEY first. See .env.example and README.md.")
    log.info("Starting %s with model %s", BOT_NAME, MODEL)
    offset: int | None = None
    while True:
        try:
            payload: dict = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
            if offset is not None:
                payload["offset"] = offset
            updates = telegram("getUpdates", payload).get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                if "message" in update:
                    handle_message(update["message"])
                elif "callback_query" in update:
                    handle_callback(update["callback_query"])
        except urllib.error.HTTPError as exc:
            log.error("Telegram returned HTTP %s", exc.code)
            time.sleep(3)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            log.error("Polling error: %s", exc)
            time.sleep(3)


if __name__ == "__main__":
    main()
