from dotenv import load_dotenv
import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")

app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Bot webhook orqali ishlayapti 🚀")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    asyncio.create_task(application.process_update(update))
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "Bot ishlayapti 🚀", 200

async def set_webhook():
    webhook_url = f"{RAILWAY_URL}/{BOT_TOKEN}"
    await application.bot.set_webhook(webhook_url)
    print(f"Webhook o‘rnatildi: {webhook_url}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_webhook())
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
