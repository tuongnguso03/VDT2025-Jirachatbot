from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from models import User, Message
from database import SessionLocal
from modules.fastapi.config import get_jira_auth_url, BOT_TOKEN
import json
import asyncio
from modules.chatbot.chatbot import ChatAgent
import logging
import traceback
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            recent_messages = (
                session.query(Message)
                .filter_by(userId=user.userId)
                .order_by(Message.timestamp.desc(), Message.messageId.desc())
                .limit(10)
                .all()
            )
            logger.info(f"[TelegramBot] Recent messages for user {user.userId}: {[{'role': m.role, 'message': m.message} for m in recent_messages]}")

            recent_messages.reverse()

            formatted_conversation = [
                {"role": msg.role, "message": msg.message} for msg in recent_messages
            ]

            agent = ChatAgent(
                user_id=user.userId,
                access_token=user.accessToken,
                cloud_id=user.cloudId,
                domain=user.domain
            )

            loop = asyncio.get_event_loop()
            response, chat_history = await loop.run_in_executor(
                None, lambda: agent.chat_function(
                    user_text,
                    chat_history=formatted_conversation,
                    functions=[
                        agent.get_jira_issues,
                        agent.get_jira_issues_today,
                        agent.get_jira_issue_detail,
                        agent.get_confluence_page_info
                    ]
                )
            )

            reply_text = response.candidates[0].content.parts[0].text

            msg_user = Message(userId=user.userId, role="user", message=user_text)
            msg_bot = Message(userId=user.userId, role="bot", message=reply_text)
            session.add_all([msg_user, msg_bot])
            session.commit()

            await update.message.reply_text(reply_text)

    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text("Đã có lỗi xảy ra, vui lòng thử lại sau.")
    finally:
        session.close()


def send_telegram_message(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)

    if not response.ok:
        print(f"Telegram error: {response.text}")
        return

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegramId=chat_id).first()
        if user:
            msg_user = Message(userId=user.userId, role="user", message="Nhắc việc từ hệ thống")
            msg_bot = Message(userId=user.userId, role="bot", message=text)
            session.add_all([msg_user, msg_bot])
            session.commit()
    except Exception as e:
        logger.error(f"Error saving bot message: {e}")
    finally:
        session.close()
