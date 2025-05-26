from telegram.ext import ApplicationBuilder

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from modules.telegrambot.telegrambot import start, handle_message
from modules.fastapi.config import BOT_TOKEN

def run_bot():
    print("Bot is running...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == "__main__":
    run_bot()