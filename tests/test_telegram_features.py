import hmac
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlencode

import app as web
import assistant_service as assistant
import bot

TOKEN = "123:mock-bot-token"


def telegram_headers(user_id: int, *, auth_date: int | None = None) -> dict[str, str]:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "fake-query",
        "user": json.dumps({"id": user_id}),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.digest(b"WebAppData", TOKEN.encode(), "sha256")
    fields["hash"] = hmac.digest(secret, check_string.encode(), "sha256").hex()
    return {"Authorization": "tma " + urlencode(fields)}


def ai_response(text: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


class MiniAppChatTests(unittest.TestCase):
    def setUp(self):
        database_dir = tempfile.TemporaryDirectory()
        self.addCleanup(database_dir.cleanup)
        database = patch.object(assistant, "CHAT_DB_PATH", Path(database_dir.name) / "chat.db")
        credentials = patch.multiple(web, TELEGRAM_TOKEN=TOKEN, OPENAI_API_KEY="fake-key")
        for replacement in (database, credentials):
            replacement.start()
            self.addCleanup(replacement.stop)
        self.client = web.app.test_client()
        self.path = "/miniapp/chat"
        self.headers = telegram_headers(42)

    def test_rejects_tampered_and_expired_sessions(self):
        tampered = self.headers["Authorization"].replace("%3A+42%7D", "%3A+43%7D")
        self.assertNotEqual(tampered, self.headers["Authorization"])
        expired = telegram_headers(42, auth_date=int(time.time()) - 86401)
        with patch.object(web, "ai_reply") as reply:
            for headers in ({"Authorization": tampered}, expired, {}):
                response = self.client.post(self.path, headers=headers, json={"text": "hello"})
                self.assertEqual(response.status_code, 401)
            reply.assert_not_called()

    def test_saves_context_and_scopes_it_to_the_signed_user(self):
        ai_inputs = []

        def append_input(_url, payload, _headers):
            ai_inputs.append([message["content"] for message in payload["input"]])
            return ai_response("reply")

        with patch.object(assistant, "api_request", side_effect=append_input):
            response = self.client.post(self.path, headers=self.headers, json={"text": "first"})
            self.assertEqual(response.get_json(), {"reply": "reply"})
            response = self.client.post(self.path, headers=self.headers, json={"text": "second"})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(ai_inputs, [["first"], ["first", "reply", "second"]])

        history = self.client.get(self.path, headers=self.headers)
        self.assertEqual(history.headers["Cache-Control"], "no-store")
        self.assertEqual(len(history.get_json()["messages"]), 4)
        other = self.client.get(self.path, headers=telegram_headers(43))
        self.assertEqual(other.get_json(), {"messages": []})

        self.assertEqual(self.client.delete(self.path, headers=self.headers).status_code, 204)
        self.assertEqual(assistant.read_conversation(42)[1], [])

    def test_reset_during_an_answer_keeps_the_chat_empty(self):
        def reset_then_answer(*_args):
            assistant.reset_conversation(42)
            return ai_response("stale reply")

        with patch.object(assistant, "api_request", side_effect=reset_then_answer):
            response = self.client.post(self.path, headers=self.headers, json={"text": "first"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(assistant.read_conversation(42)[1], [])


class TelegramFeatureTests(unittest.TestCase):
    def test_shortcut_uses_force_reply_and_passes_the_task_to_ai(self):
        _, prompt, task = bot.SHORTCUTS["translate"]
        callback = {
            "id": "callback",
            "data": "shortcut:translate",
            "message": {"message_id": 11, "chat": {"id": 42}},
        }
        with patch.object(bot, "telegram") as telegram:
            bot.handle_callback(callback)
        self.assertEqual(telegram.call_args.args[0], "sendMessage")
        self.assertEqual(telegram.call_args.args[1]["reply_markup"], {"force_reply": True})

        message = {
            "chat": {"id": 42, "type": "private"},
            "text": "Translate this",
            "reply_to_message": {"from": {"id": 123}, "text": prompt},
        }
        with patch.object(bot, "TELEGRAM_TOKEN", TOKEN), patch.object(bot, "answer_user") as answer:
            bot.handle_message(message)
        answer.assert_called_once_with(42, "Translate this", task=task)

    def test_voice_download_and_transcription_feed_the_assistant(self):
        transcription = Mock()
        transcription.json.return_value = {"text": "ভয়েস থেকে লেখা"}
        voice = {"file_id": "voice-id", "file_size": 5}
        file_info = {"result": {"file_path": "voice/file.oga"}}
        with (
            patch.object(bot, "telegram", side_effect=[{}, file_info]) as telegram,
            patch.object(bot.urllib.request, "urlopen", return_value=io.BytesIO(b"audio")),
            patch.object(bot.requests, "post", return_value=transcription) as post,
            patch.object(bot, "ai_reply", return_value="উত্তর") as reply,
            patch.object(bot, "send") as send,
        ):
            bot.handle_message({"chat": {"id": 42}, "voice": voice})

        telegram.assert_any_call("getFile", {"file_id": "voice-id"})
        self.assertEqual(post.call_args.kwargs["files"]["file"], ("voice.ogg", b"audio", "audio/ogg"))
        reply.assert_called_once_with(42, "ভয়েস থেকে লেখা", task="")
        self.assertEqual(send.call_args.args, (42, "উত্তর"))
        self.assertTrue(send.call_args.kwargs["plain"])
