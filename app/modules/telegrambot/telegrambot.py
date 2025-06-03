from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from models import User, Message, Feedback
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
import aiohttp
import re
from datetime import datetime

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

    keyboard = [['Lấy ra danh sách các tasks!', 'Lấy ra danh sách tasks hôm nay!']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(welcome_msg, parse_mode='Markdown', disable_web_page_preview=True, reply_markup=reply_markup)

    session.close()


async def download_and_send_jira_image(update, jira_url, headers=None):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(jira_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                        tmp_file.write(data)
                        tmp_file_path = tmp_file.name

                    with open(tmp_file_path, "rb") as photo_file:
                        await update.message.reply_photo(photo=photo_file, caption="Ảnh từ Jira")

                    os.remove(tmp_file_path)
                else:
                    await update.message.reply_text(f"Không tải được ảnh từ Jira, status {resp.status}")
    except Exception as e:
        await update.message.reply_text(f"Lỗi khi tải ảnh từ Jira: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_chat.id
    user_text = update.message.text
    session = SessionLocal()

    try:
        user = session.query(User).filter_by(telegramId=telegram_id).first()

        if user.awaitingFeedback:
            # Lưu feedback, gửi cảm ơn
            feedback = Feedback(
                userId=user.userId,
                content=user_text,
                createdAt=datetime.now()
            )
            session.add(feedback)

            # Reset trạng thái chờ feedback
            user.awaitingFeedback = False
            session.commit()

            await update.message.reply_text("✅ Cảm ơn bạn đã góp ý!")
            return

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
                None, lambda: agent.chat_function(user_text, chat_history=formatted_conversation)
            )

            reply_text = response.candidates[0].content.parts[0].text

            msg_user = Message(userId=user.userId, role="user", message=user_text)
            msg_bot = Message(userId=user.userId, role="bot", message=reply_text)
            session.add_all([msg_user, msg_bot])
            session.commit()

            await update.message.reply_text(reply_text)

            attachments_urls = []
            match = re.search(r'Attachments:\s*(\[[\s\S]*?\])', reply_text)
            if match:
                try:
                    attachments_urls = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            for url in attachments_urls:
                headers = {"Authorization": f"Bearer {user.accessToken}"} 
                await download_and_send_jira_image(update, url, headers=headers)

    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text("Chat bot hiện không khả dụng, vui lòng thử lại sau ít phút!")
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
            file_name = getattr(file, 'file_name', 'attachment.png')

        agent = ChatAgent(
            user_id=user.userId,
            access_token=user.accessToken,
            cloud_id=user.cloudId,
            domain=user.domain
        )

        agent.file_path = file_path
        agent.file_name = file_name

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

        msg_user = Message(
            userId=user.userId,
            role="user",
            message=caption if caption else f"File gửi: {file_name}"
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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📘 *Hướng dẫn sử dụng Bot Jira*\n\n"
        "*Một số prompt bạn có thể thử:*\n"
        "- `Lấy ra danh sách các tasks`\n"
        "- `Lấy ra danh sách tasks hôm nay`\n"
        "- `Lấy thông tin chi tiết task VDT-1`\n"
        "- `Lấy ra danh sách worklog task VDT-1`\n"
        "- `Log work cho tôi task VDT-1 bắt đầu từ 10:00 hôm nay, làm trong 30 phút và nội dung là Hoàn thành`\n"
        "- `Tạo mới task với project_key: VDT, summary: Task mới, description: Nội dung task mới, issue_type: Task, deadline: 08/06/2025, giao cho Nguyễn Ngọc Hà đảm nhiệm`\n"
        "- `Giao task VDT-1 cho Nguyễn Ngọc Hà đảm nhiệm`\n"
        "- `Chuyển trạng thái task VDT-1 sang Done`\n"
        "- `Lấy danh sách các bình luận của task VDT-1`\n"
        "- `Tạo bình luận mới cho task VDT-1 với nội dung Hoàn thành`\n"
        "- `Chỉnh sửa bình luận ID 10001 của task VDT-1 nội dung Đã fix bug`\n"
        "- `Đính kèm file vào task VDT-1`\n"
        "- `Lấy ra ID và tên của các page chứa nội dung tài liệu có thể truy cập được trong Confluence của task VDT-8`\n"
        "- `Lấy ra thông tin chi tiết của John Lennon documentation ID 65849`\n\n"
        "*Lệnh hỗ trợ:*\n"
        "/start - Đăng nhập Jira\n"
        "/help - Hướng dẫn sử dụng"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
