import json
import os
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "demo_verify_token")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
PORT = int(os.getenv("PORT", "5000"))


def normalize_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def send_messenger_reply(recipient_id: str, message_text: str) -> bool:
    if not PAGE_ACCESS_TOKEN:
        return False

    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
    }

    response = requests.post(
        f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}",
        json=payload,
        timeout=10,
    )

    if response.status_code >= 400:
        app.logger.warning("Messenger reply failed: %s %s", response.status_code, response.text)
        return False

    return True


def handle_incoming_message(event: Dict[str, Any]) -> str:
    sender_id = event.get("sender", {}).get("id")
    message = event.get("message", {})
    text = normalize_text(message.get("text"))

    if not sender_id:
        return ""

    if not text:
        return ""

    reply = f"Echo: {text}"
    send_messenger_reply(sender_id, reply)
    return reply


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/miniapp")
def miniapp():
    return redirect("/miniapp/")


@app.get("/miniapp/")
def miniapp_index():
    return send_from_directory(os.path.join(app.root_path, "webapp"), "index.html")


@app.get("/miniapp/<path:filename>")
def miniapp_asset(filename: str):
    return send_from_directory(os.path.join(app.root_path, "webapp"), filename)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "name": "MessengerBo"})


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200

        return "Forbidden", 403

    data = request.get_json(silent=True) or {}
    entries = data.get("entry", [])

    for entry in entries:
        messaging_events = entry.get("messaging", [])
        for event in messaging_events:
            if "message" in event and event.get("message", {}).get("text"):
                handle_incoming_message(event)

    return "OK", 200


@app.post("/message")
def local_message():
    payload = request.get_json(silent=True) or {}
    text = normalize_text(payload.get("text"))

    if not text:
        return jsonify({"reply": "Please send a text message."}), 400

    return jsonify({"reply": f"Echo: {text}"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
