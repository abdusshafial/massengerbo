# MessengerBo and E Premium

This repository contains a Telegram AI bot (`bot.py`) and a separate Flask demo/Messenger webhook (`app.py`). They use different credentials.

## Telegram AI bot

Requires Python 3.10 or newer, a Telegram bot token, and an OpenAI API key. The bot answers Telegram messages using the OpenAI Responses API and keeps a short in-memory conversation history per chat.

1. Copy `.env.example` to `.env`.
2. Set `TELEGRAM_BOT_TOKEN` and `OPENAI_API_KEY` in `.env`. Get a Telegram token from [@BotFather](https://t.me/BotFather). If a token was shared, revoke it and use a replacement. Create an OpenAI API key in the [API Platform](https://platform.openai.com/api-keys).
3. Start the bot:

```powershell
python bot.py
```

The bot supports `/start`, `/help`, `/menu`, and `/new`. OpenAI API usage may incur charges.

### Telegram Mini App

`webapp/index.html` is the dark-purple Mini App and `webapp/logo.svg` is its matching vector mark. Host the `webapp` folder on a public HTTPS site, then set `WEBAPP_URL` in `.env` to the hosted page URL. After that, `/start` shows an **Open E Premium** keyboard button. Messages sent from the Mini App are answered in the Telegram chat. Telegram requires a Mini App URL to use HTTPS, and keyboard-launched Mini Apps can send data back to the bot with `sendData`.

For a local preview, run `python app.py` and open `http://127.0.0.1:5000/miniapp`. The preview posts to the local `/message` demo endpoint, which echoes the text. Inside Telegram, the Mini App sends the text to `bot.py`, which generates the AI reply. A local HTTP URL is only for preview; Telegram needs the hosted HTTPS URL in `WEBAPP_URL`.

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
