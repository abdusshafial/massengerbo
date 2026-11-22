"""Telegram AI assistant with an optional Telegram Mini App."""
from __future__ import annotations

import html
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

import requests

from assistant_service import (
    BOT_NAME,
    MAX_INPUT,
    MODEL,
    OPENAI_API_KEY,
    ConversationChanged,
    ai_reply,
    api_request,
    reset_conversation,
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
MINIAPP_INLINE_CHAT = os.getenv("MINIAPP_INLINE_CHAT", "").strip() == "1"
TRANSCRIPTION_MODEL = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe").strip()
MAX_VOICE_BYTES = 20_000_000
MAX_MESSAGE = 3900
SHORTCUTS = {
    "write": (
        "পোস্ট লেখো",
        "পোস্টের বিষয় কী? চাইলে প্ল্যাটফর্ম বা টোনও বলুন।",
        "Write a ready-to-use social media post based on the user's brief.",
    ),
    "translate": (
        "অনুবাদ করো",
        "যে লেখাটি অনুবাদ করবেন, সেটি পাঠান। কোন ভাষায় চান সেটিও লিখতে পারেন।",
        "Translate the provided text. Default to Bengali for other languages and to "
        "English for Bengali unless the user specifies a target language.",
    ),
    "explain": (
        "সহজ করে বোঝাও",
        "যে বিষয়টি বুঝতে চান, সেটি পাঠান।",
        "Explain the provided topic in simple language with an example when helpful.",
    ),
}

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("epremium")


def telegram(method: str, payload: dict) -> dict:
    return api_request(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}", payload)




def keyboard(*, private: bool = False) -> dict:
    rows = [
        [{"text": "Chat with AI", "callback_data": "chat"}],
        [
            {"text": label, "callback_data": f"shortcut:{mode}"}
            for mode, (label, _, _) in SHORTCUTS.items()
        ],
        [
            {"text": "Premium", "callback_data": "premium"},
            {"text": "How it works", "callback_data": "help"},
        ],
    ]
    if private and MINIAPP_INLINE_CHAT and WEBAPP_URL:
        rows.insert(0, [{"text": "Open E Premium", "web_app": {"url": WEBAPP_URL}}])
    return {"inline_keyboard": rows}


def send_menu(chat_id: int, text: str, *, private: bool) -> None:
    if private and WEBAPP_URL and not MINIAPP_INLINE_CHAT:
        url = urlsplit(WEBAPP_URL)
        query = "&".join(filter(None, (url.query, "epremium_mode=telegram")))
        launch_url = url._replace(query=query).geturl()
        send(chat_id, text, markup={
            "keyboard": [
                [{"text": "Open E Premium", "web_app": {"url": launch_url}}],
                [{"text": "/new"}, {"text": "/help"}],
            ],
            "resize_keyboard": True,
            "is_persistent": True,
        })
        send(chat_id, "নিচের শর্টকাটগুলো থেকেও শুরু করতে পারেন।", markup=keyboard())
        return
    send(chat_id, text, markup=keyboard(private=private))


def send(
    chat_id: int, text: str, *, markup: dict | None = None, plain: bool = False
) -> None:
    chunks = [text[i:i + MAX_MESSAGE] for i in range(0, len(text), MAX_MESSAGE)] or [""]
    for index, chunk in enumerate(chunks):
        payload: dict = {"chat_id": chat_id, "text": chunk}
        if not plain:
            payload["parse_mode"] = "HTML"
        if markup and index == len(chunks) - 1:
            payload["reply_markup"] = markup
        telegram("sendMessage", payload)


def welcome(chat_id: int, first_name: str, *, private: bool) -> None:
    name = html.escape(first_name or "বন্ধু")
    send_menu(
        chat_id,
        f"<b>&#10022; {html.escape(BOT_NAME)}</b>\n\n"
        f"স্বাগতম, {name}! বাংলায় লিখে বা ভয়েস মেসেজ পাঠিয়ে প্রশ্ন করতে পারেন। "
        "পোস্ট, অনুবাদ বা সহজ ব্যাখ্যার জন্য নিচের শর্টকাটগুলো ব্যবহার করুন।",
        private=private,
    )


def transcribe_voice(file_id: str) -> str:
    file_path = telegram("getFile", {"file_id": file_id}).get("result", {}).get("file_path")
    if not file_path:
        raise RuntimeError("Telegram did not provide a file path")

    url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{quote(file_path, safe='/')}"
    with urllib.request.urlopen(url, timeout=30) as response:
        audio = response.read(MAX_VOICE_BYTES + 1)
    if len(audio) > MAX_VOICE_BYTES:
        raise ValueError("Voice message exceeds the download limit")

    suffix = PurePosixPath(file_path).suffix.lower()
    filename, media_type = {
        ".mp3": ("voice.mp3", "audio/mpeg"),
        ".m4a": ("voice.m4a", "audio/mp4"),
    }.get(suffix, ("voice.ogg", "audio/ogg"))
    response = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        data={"model": TRANSCRIPTION_MODEL},
        files={"file": (filename, audio, media_type)},
        timeout=(10, 70),
    )
    response.raise_for_status()
    return response.json().get("text", "").strip()


def shortcut_task(message: dict) -> str:
    replied_to = message.get("reply_to_message", {})
    bot_id = TELEGRAM_TOKEN.partition(":")[0]
    if str(replied_to.get("from", {}).get("id", "")) == bot_id:
        for _, prompt, task in SHORTCUTS.values():
            if replied_to.get("text") == prompt:
                return task
    return ""


def answer_user(
    chat_id: int, text: str, *, task: str = "", voice: dict | None = None
) -> None:
    try:
        telegram("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        if voice is not None:
            if (voice.get("file_size") or 0) > MAX_VOICE_BYTES:
                send(chat_id, "ভয়েস মেসেজটি বড় হয়ে গেছে। ছোট করে আবার পাঠান।")
                return
            text = transcribe_voice(voice["file_id"])
            if not text:
                send(chat_id, "ভয়েস মেসেজে কথা বোঝা যায়নি। আবার রেকর্ড করুন বা লিখে পাঠান।")
                return
        if len(text) > MAX_INPUT:
            send(chat_id, f"মেসেজটি {MAX_INPUT} অক্ষরের মধ্যে রেখে আবার পাঠান।")
            return
        answer = ai_reply(chat_id, text, task=task)
        send(chat_id, answer, markup=keyboard(), plain=True)
    except ConversationChanged:
        send(chat_id, "চ্যাটে আরেকটি পরিবর্তন হয়েছে। আবার পাঠান।")
    except (
        urllib.error.URLError, requests.RequestException, TimeoutError,
        RuntimeError, ValueError, sqlite3.Error,
    ) as exc:
        log.warning("Could not answer Telegram message: %s", type(exc).__name__)
        send(chat_id, "এখন উত্তর পাওয়া যাচ্ছে না। একটু পরে আবার চেষ্টা করুন।")


def handle_message(message: dict) -> None:
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    private = chat.get("type") == "private"
    if chat_id is None:
        return
    web_app_data = message.get("web_app_data", {}).get("data")
    if web_app_data:
        try:
            data = json.loads(web_app_data)
            if isinstance(data, dict) and data.get("type") == "message":
                text = data.get("text")
                if isinstance(text, str) and text.strip():
                    answer_user(chat_id, text.strip())
        except (json.JSONDecodeError, TypeError):
            log.warning("Ignoring malformed Mini App data")
        return

    task = shortcut_task(message)
    voice = message.get("voice")
    if isinstance(voice, dict) and isinstance(voice.get("file_id"), str):
        answer_user(chat_id, "", task=task, voice=voice)
        return

    text = (message.get("text") or "").strip()
    if not text:
        send(chat_id, "প্রশ্ন লিখে পাঠান অথবা একটি ভয়েস মেসেজ দিন।")
        return
    command = text.split()[0].split("@")[0].lower()
    if command == "/start":
        welcome(chat_id, message.get("from", {}).get("first_name", ""), private=private)
    elif command in ("/help", "/menu"):
        send_menu(
            chat_id,
            "<b>কীভাবে সাহায্য করতে পারি?</b>\n\n"
            "লিখে বা ভয়েসে প্রশ্ন করুন। আগের কথার প্রসঙ্গ মুছে নতুন করে শুরু করতে /new দিন।",
            private=private,
        )
    elif command == "/new":
        try:
            reset_conversation(chat_id)
        except sqlite3.Error as exc:
            log.warning("Could not reset conversation: %s", type(exc).__name__)
            send(chat_id, "চ্যাটের প্রসঙ্গ মুছতে সমস্যা হয়েছে। আবার চেষ্টা করুন।")
            return
        send(chat_id, "নতুন চ্যাট শুরু হলো। কী নিয়ে কথা বলবেন?", markup=keyboard(private=private))
    elif text.startswith("/"):
        send(chat_id, "কমান্ডটি চেনা যায়নি। /help দিন অথবা প্রশ্ন লিখুন।")
    else:
        answer_user(chat_id, text, task=task)


def handle_callback(callback: dict) -> None:
    callback_id = callback.get("id")
    chat_id = callback.get("message", {}).get("chat", {}).get("id")
    data = callback.get("data", "")
    if callback_id:
        telegram("answerCallbackQuery", {"callback_query_id": callback_id})
    if chat_id is None:
        return
    shortcut = SHORTCUTS.get(data.removeprefix("shortcut:")) if data.startswith("shortcut:") else None
    if shortcut:
        message_id = callback.get("message", {}).get("message_id")
        payload = {
            "chat_id": chat_id,
            "text": shortcut[1],
            "reply_markup": {"force_reply": True},
        }
        if message_id is not None:
            payload["reply_parameters"] = {"message_id": message_id}
        telegram("sendMessage", payload)
    elif data == "chat":
        send(chat_id, "আপনার প্রশ্ন লিখুন অথবা ভয়েস মেসেজ পাঠান।")
    elif data == "premium":
        send(chat_id, "<b>&#10022; Premium</b>\n\nSubscription plans and payments have not been configured yet. You can chat with the AI assistant here.", markup=keyboard())
    elif data == "help":
        send(chat_id, "লিখে বা ভয়েসে প্রশ্ন করুন। আগের চ্যাটের প্রসঙ্গ মুছতে /new দিন।", markup=keyboard())


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
