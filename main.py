from dotenv import load_dotenv
import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

# .env yuklash
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")

# Flask app
app = Flask(__name__)

# Telegram bot
application = Application.builder().token(BOT_TOKEN).build()

# /start komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Bot ishga tushdi 🚀")

# Echo handler
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

# Handlerlarni qo‘shish
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# Webhook endpoint
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
async def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    await application.process_update(update)  # shu update’ni ishlatadi
    return "OK", 200

# Home route
@app.route("/", methods=["GET"])
def home():
    return "Bot ishlayapti 🚀", 200

async def main():
    # Webhook o‘rnatish
    await application.bot.set_webhook(f"{RAILWAY_URL}/{BOT_TOKEN}")

if __name__ == "__main__":
    asyncio.run(main())
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
