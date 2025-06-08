from telegram.ext import ApplicationBuilder
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from modules.telegrambot.telegrambot import start, handle_message, handle_file, help_command, feedback_command
from modules.fastapi.config import BOT_TOKEN
import asyncio

# def run_bot():
#     print("Bot is running with webhook...")
#     application = ApplicationBuilder().token(BOT_TOKEN).build()
#     application.add_handler(CommandHandler("start", start))
#     application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
#     application.add_handler(MessageHandler(
#         filters.Document.ALL | filters.PHOTO,
#         handle_file
#     ))
#     application.add_handler(CommandHandler("help", help_command))

#     application.run_webhook(
#         listen="0.0.0.0",
#         port=8000, 
#         url_path=BOT_TOKEN,
#         webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
#     )

def run_bot():
    print("Bot is running...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO,
        handle_file
    ))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.run_polling()

if __name__ == "__main__":
    asyncio.run(run_bot())