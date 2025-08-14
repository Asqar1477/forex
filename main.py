import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Token environment variabledan olinadi
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Flask app yaratamiz
app = Flask(__name__)

# Bot application
application = Application.builder().token(BOT_TOKEN).build()

# Oddiy /start komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Bot ishga tushdi 🚀")

# Oddiy echo handler
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

# Handlerlarni qo'shamiz
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
    # Railway URL'ni o'zingizga moslang
    application.bot.set_webhook(f"https://{os.environ.get('RAILWAY_URL')}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=port)
