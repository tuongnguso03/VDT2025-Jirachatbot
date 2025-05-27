from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from models import User, Message
from database import SessionLocal
from modules.fastapi.config import get_jira_auth_url, BOT_TOKEN
import json
import requests
import asyncio
from modules.chatbot.chatbot import chat_function, confluence_function

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_chat.id
    session = SessionLocal()
    user = session.query(User).filter_by(telegramId=telegram_id).first()
    if not user:
        user = User(
            telegramId=telegram_id,
            telegramUsername=update.effective_user.username
        )
        session.add(user)
        session.commit()

    jira_link = get_jira_auth_url(telegram_id)
    welcome_msg = (
        f"👋 Chào bạn {update.effective_user.first_name}!\n\n"
        f"Để bắt đầu, hãy đăng nhập Jira tại link sau:\n"
        f"[Nhấn để đăng nhập Jira]({jira_link})"
    )

    await update.message.reply_text(welcome_msg, parse_mode='Markdown', disable_web_page_preview=True)

    session.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_chat.id
    user_text = update.message.text
    session = SessionLocal()

    try:
        user = session.query(User).filter_by(telegramId=telegram_id).first()
        if user:
            msg_user = Message(userId=user.userId, role="user", message=user_text)
            session.add(msg_user)
            session.commit()

            recent_messages = (
                session.query(Message)
                .filter_by(userId=user.userId)
                .order_by(Message.timestamp.desc()) 
                .limit(10)
                .all()
            )

            recent_messages.reverse()

            formatted_conversation = [
                {"role": msg.role, "message": msg.message} for msg in recent_messages
            ]

            pretty_json = json.dumps(formatted_conversation, ensure_ascii=False)

            loop = asyncio.get_event_loop()
            response, updated_history = await loop.run_in_executor(
                None, lambda: chat_function(user_text, chat_history=pretty_json, functions=[confluence_function])
            )

            msg_bot = Message(userId=user.userId, role="bot", message=response)
            session.add(msg_bot)
            session.commit()

            await update.message.reply_text(response)
    except Exception as e:
        print(f"Error in handle_message: {e}")
        await update.message.reply_text("Đã có lỗi xảy ra, vui lòng thử lại sau.")
    finally:
        session.close()