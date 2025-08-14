from dotenv import load_dotenv
import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

# .env dan ma'lumotlarni yuklaymiz
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Flask va Telegram Application
app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()

# /start komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Bot webhook orqali ishlayapti 🚀")

# Oddiy echo handler
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

# Handlerlarni qo'shamiz
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# Webhook endpoint (token URLga qo‘shilmaydi!)
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    asyncio.create_task(application.process_update(update))
    return "OK", 200

# Tekshirish uchun home page
@app.route("/", methods=["GET"])
def home():
    return "Bot ishlayapti 🚀", 200

# Webhook o‘rnatish funksiyasi
async def set_webhook():
    BASE_URL = "https://forex-production.up.railway.app"
    webhook_url = f"{BASE_URL}/webhook"
    await application.bot.set_webhook(webhook_url)
    print(f"Webhook o‘rnatildi: {webhook_url}")

# Asosiy ishga tushirish qismi
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_webhook())
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
