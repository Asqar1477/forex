from dotenv import load_dotenv
import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# .env fayldan yuklaymiz
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN bo'sh! .env yoki Railway Variables'ni tekshir!")

# Flask app
app = Flask(__name__)

# Telegram bot application
application = Application.builder().token(BOT_TOKEN).build()

# /start komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Bot ishga tushdi 🚀")

# Echo handler
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

# Handlerlar
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# Webhook endpoint
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "Bot ishlayapti 🚀", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8443))
    railway_url = os.environ.get("RAILWAY_URL")
    if not railway_url:
        raise ValueError("RAILWAY_URL bo'sh! Railway environment variables'ga qo'shing.")
    application.bot.set_webhook(f"https://{railway_url}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=port)
