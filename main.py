import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN") or "BOT_TOKENINGNI_BU_YERGA_QO'Y"
BASE_URL = "https://forex-production.up.railway.app"  # Railway URL

app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Webhook ishlayapti 🚀")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# === Webhook route ===
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.get_event_loop().create_task(application.process_update(update))
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "Bot ishga tushdi ✅", 200

# === Webhook o‘rnatish ===
async def set_webhook():
    url = f"{BASE_URL}/{TOKEN}"
    await application.bot.set_webhook(url)
    print(f"Webhook o‘rnatildi: {url}")

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(set_webhook())
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
