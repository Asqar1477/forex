import os
from flask import Flask, request
import requests

# === Config ===
TOKEN = os.getenv("BOT_TOKEN", "8471322511:AAHPf0BkWLVZ8g7Y2Mh4BHHc2sQuENViG0c")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

app = Flask(__name__)

# === Webhook route ===
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    print(update)  # Debug uchun

    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        if text == "/start":
            send_message(chat_id, "Salom! Webhook ishlayapti 🚀")
        else:
            send_message(chat_id, f"Siz yubordingiz: {text}")

    return "ok"

# === Home route ===
@app.route("/", methods=["GET"])
def home():
    return "Bot ishga tushdi ✅", 200

# === Helper function ===
def send_message(chat_id, text):
    requests.post(f"{BASE_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

# === Webhook o‘rnatish ===
def set_webhook():
    webhook_url = f"https://forex-production.up.railway.app/{TOKEN}"
    r = requests.get(f"{BASE_URL}/setWebhook", params={"url": webhook_url})
    print(r.json())

if __name__ == "__main__":
    set_webhook()  # faqat bir marta ishga tushganda o‘rnatadi
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
