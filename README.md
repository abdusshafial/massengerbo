# MessengerBo and E Premium

This repository contains a Telegram AI bot (`bot.py`) and a separate Flask demo/Messenger webhook (`app.py`). They use different credentials.

## Telegram AI bot

Requires Python 3.10 or newer, a Telegram bot token, and an OpenAI API key. The bot accepts text and voice messages and supports Bengali shortcuts for writing posts, translating, and explaining topics. It stores the latest 12 messages per conversation in a local SQLite database.

1. Copy `.env.example` to `.env`.
2. Set `TELEGRAM_BOT_TOKEN` and `OPENAI_API_KEY` in `.env`. Get a Telegram token from [@BotFather](https://t.me/BotFather). If a token was shared, revoke it and use a replacement. Create an OpenAI API key in the [API Platform](https://platform.openai.com/api-keys).
3. Install the dependencies and start the bot.

```powershell
python -m pip install -r requirements.txt
python bot.py
```

The bot supports `/start`, `/help`, `/menu`, and `/new`. Reply to a shortcut’s prompt with text or a voice message. Voice messages are transcribed with the model in `OPENAI_TRANSCRIPTION_MODEL` and answered in text. `/new` clears the saved conversation context. The database defaults to `chats.sqlite3` beside `bot.py`. Use `CHAT_DB_PATH` to point to a persistent disk when deploying. OpenAI API usage may incur charges.

### Ask questions about a PDF

Send a PDF file of up to 20 MB in Telegram. Leave the caption blank for a Bengali summary, or add a question such as “এই নোট থেকে পাঁচটি কুইজ প্রশ্ন বানাও” in the caption. Reply directly to the original PDF message with a new question to consult the file again.

The bot sends the PDF to OpenAI for analysis. SQLite keeps the questions and answers as text. If you override `OPENAI_MODEL`, use a model that supports PDF inputs.

### Ask questions about a photo

Send a photo in Telegram from the attachment menu. Leave the caption blank for a Bengali description and readable text, or ask a question in the caption. For example, “এই অঙ্কটা ধাপে ধাপে বুঝিয়ে দাও।” Reply directly to the original photo to ask another question.

For small print or handwriting, send the original JPG, PNG, or WebP as a file to avoid Telegram's photo compression. The image limit is 15 MB. The bot sends the image to OpenAI for analysis and keeps the questions and answers as text in SQLite.

### Telegram Mini App

For replies inside the Mini App, serve Flask's `app:app` through a production WSGI server on a public HTTPS domain. In `.env`, set `WEBAPP_URL=https://your-domain.example/miniapp/` and `MINIAPP_INLINE_CHAT=1`. The Flask server and Telegram bot need the same bot token and access to the same SQLite database file on a persistent local disk. Restart both processes and open **Open E Premium** from the bot’s new `/menu` message in a private chat. The Mini App shows the recent saved messages and provides controls to copy replies and reset the conversation.

For static hosting, publish the `webapp` folder over HTTPS, point `WEBAPP_URL` at it, and leave `MINIAPP_INLINE_CHAT=0`. Messages sent with the keyboard button are answered in Telegram chat.

For a local browser preview, run `python app.py` and open `http://127.0.0.1:5000/miniapp/`. The preview uses the local `/message` echo endpoint.

## Local dashboard and Messenger webhook

Install the Python packages and start the Flask app:

```powershell
python -m pip install -r requirements.txt
python app.py
```

The local dashboard is at `http://127.0.0.1:5000` when run with Flask's CLI; `app.py` itself binds to all interfaces on port 5000. Its `/message` endpoint is a local echo demo.

The optional Facebook Messenger webhook in `app.py` uses `PAGE_ACCESS_TOKEN` and `VERIFY_TOKEN`; it is separate from the Telegram bot. Configure the Page token and webhook in Meta for Developers, and expose a public HTTPS webhook URL for Meta to reach it. Meta may require app review and the appropriate Page permissions for production messaging.

## Secrets

Keep `.env` private. It is ignored by Git. Never commit or paste bot tokens or API keys into source files or public repositories.
