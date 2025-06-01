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
import os
import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_chat.id
    session = SessionLocal()
    user = session.query(User).filter_by(telegramId=telegram_id).first()
    if not user:
        user = User(telegramId=telegram_id)
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

            formatted_conversation = ""

            loop = asyncio.get_event_loop()
            response, chat_history = await loop.run_in_executor(
                None, lambda: agent.chat_function(
                    user_text,
                    chat_history=formatted_conversation,
                    functions=[
                        agent.get_jira_issues,
                        agent.get_jira_issues_today,
                        agent.get_jira_issue_detail,
                        agent.get_jira_log_works,
                        agent.create_jira_log_work,
                        agent.create_jira_issue,
                        agent.assign_jira_issue,
                        agent.transition_jira_issue,
                        agent.get_jira_comments,
                        agent.create_jira_comment,
                        agent.edit_jira_comment,
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

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_chat.id
    session = SessionLocal()

    try:
        user = session.query(User).filter_by(telegramId=telegram_id).first()
        if not user or not user.accessToken or not user.cloudId:
            await update.message.reply_text("❗️Bạn chưa kết nối với Jira. Gõ /start để kết nối.")
            return

        caption = update.message.caption or ""

        previous_msg = (
            session.query(Message)
            .filter_by(userId=user.userId, role="user")
            .order_by(Message.timestamp.desc(), Message.messageId.desc())
            .first()
        )
        if not caption and not previous_msg:
            await update.message.reply_text("⚠️ Không tìm thấy ngữ cảnh để xử lý file.")
            return

        file = update.message.document or update.message.photo[-1]
        telegram_file = await context.bot.get_file(file.file_id)

        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            await telegram_file.download_to_drive(temp_file.name)
            file_path = temp_file.name
            filename = getattr(file, 'file_name', 'attachment.png')

        agent = ChatAgent(
            user_id=user.userId,
            access_token=user.accessToken,
            cloud_id=user.cloudId,
            domain=user.domain
        )

        agent.file_path = file_path
        agent.filename = filename

        message_to_process = caption if caption else previous_msg.message

        loop = asyncio.get_event_loop()
        response, _ = await loop.run_in_executor(
            None, lambda: agent.chat_function(
                message_to_process,
                chat_history=[],
                functions=[agent.attach_file_to_jira_issue],
            )
        )

        reply_text = response.candidates[0].content.parts[0].text

        # Lưu tin nhắn caption hoặc mô tả gửi file
        msg_user = Message(
            userId=user.userId,
            role="user",
            message=caption if caption else f"File gửi: {filename}"
        )
        msg_bot = Message(userId=user.userId, role="bot", message=reply_text)
        session.add_all([msg_user, msg_bot])
        session.commit()

        await update.message.reply_text(reply_text)

    except Exception as e:
        logger.error(f"Lỗi xử lý file Gemini: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text("⚠️ Có lỗi xảy ra khi xử lý file.")
    finally:
        session.close()
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
