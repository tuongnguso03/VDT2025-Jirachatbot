from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import telegram.helpers
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

bot = Bot(token=BOT_TOKEN)

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
            feedback = Feedback(
                userId=user.userId,
                content=user_text,
                createdAt=datetime.now()
            )
            session.add(feedback)

            user.awaitingFeedback = False
            session.commit()

            await update.message.reply_text("✅  Cảm ơn bạn đã góp ý!")
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

            # formatted_conversation = ""

            loop = asyncio.get_event_loop()
            response, chat_history = await loop.run_in_executor(
                None, lambda: agent.chat_function(user_text, chat_history=formatted_conversation)
            )

            if not response.candidates[0].content.parts:
                print("BUG:", response)
            
            reply_text = ("\n".join([part.text for part in response.candidates[0].content.parts]))[:4095]

            attachments_urls = []
            match = re.search(r'Attachments:\s*(\[[\s\S]*?\])', reply_text)
            if match:
                try:
                    attachments_urls = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            def remove_attachments_section(text: str) -> str:
                return re.sub(r'\n?-?- Attachments:\s*\[.*?\]', '', text, flags=re.DOTALL)

            reply_text = remove_attachments_section(reply_text)

            msg_user = Message(userId=user.userId, role="user", message=user_text)
            msg_bot = Message(userId=user.userId, role="bot", message=reply_text)
            session.add_all([msg_user, msg_bot])
            session.commit()
            
            # safe_text = telegram.helpers.escape_markdown(reply_text, version=2)
            # await update.message.reply_text(safe_text, parse_mode="MarkdownV2")
            
            def escape_markdown(text):
                markdown_special_chars = r"\`*_{}[]()#+-.!|>"
                for char in markdown_special_chars:
                    text = text.replace(char, f"\\{char}")
                return text

            def format_markdown_text(text):
                code_blocks = []
                def replace_code_block(match):
                    code_blocks.append(match.group(0))
                    return f"[[CODE_BLOCK_{len(code_blocks)-1}]]"

                text_wo_code = re.sub(r"```.*?```", replace_code_block, text, flags=re.DOTALL)

                escaped_text = escape_markdown(text_wo_code)

                for i, block in enumerate(code_blocks):
                    escaped_text = escaped_text.replace(f"\\[\\[CODE\\_BLOCK\\_{i}\\]\\]", block)  

                return escaped_text
        
            formatted = format_markdown_text(reply_text)

            def reply_text_contains_markdown(text):
                markdown_special_chars = r"```\\"
                return any(char in text for char in markdown_special_chars)

            if reply_text_contains_markdown(reply_text):
                await update.message.reply_text(formatted, parse_mode="MarkdownV2")
            else:
                await update.message.reply_text(reply_text)

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
        "- `Lấy thông tin chi tiết task <Issue Key>`\n"
        "- `Lấy ra danh sách worklog task <Issue Key>`\n"
        "- `Log work cho tôi task <Issue Key> bắt đầu từ <HH:MM> hôm nay, làm trong <MM> phút và nội dung là <Content>`\n"
        "- `Tạo mới task với project key: <Project Key>, summary: <Summary>, description: <Description>, issue type: <Issue Type>, Deadline: <DD/mm/YYYY>, giao cho <Name> đảm nhiệm, priority: <Priority>`\n"
        "- `Giao task <Issue Key> cho <Name> đảm nhiệm`\n"
        "- `Chuyển trạng thái task <Issue Key> sang <Transition Name>`\n"
        "- `Lấy danh sách các bình luận của task <Issue Key>`\n"
        "- `Tạo bình luận mới cho task <Issue Key> với nội dung <Content>`\n"
        "- `Chỉnh sửa bình luận ID 10001 của task <Issue Key> nội dung <Content>`\n"
        "- `Đính kèm file vào task <Issue Key>`\n"
        "- `Lấy ra ID và tên của các page chứa nội dung tài liệu có thể truy cập được trong Confluence của task <Issue Key>`\n"
        "- `Lấy ra thông tin chi tiết của <Document> <Document ID>`\n\n"
        "*Lệnh hỗ trợ:*\n"
        "/start - Đăng nhập Jira\n"
        "/help - Hướng dẫn sử dụng\n"
        "/feedback - Hòm thư góp ý"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_telegram_id = update.effective_user.id
    try:
        await bot.send_message(
            chat_id=user_telegram_id,
            text="📣  KHẢO SÁT ĐỊNH KỲ\n\nBạn đánh giá trải nghiệm sử dụng chatbot như thế nào?\nBạn có góp ý gì cho hệ thống không?\nVui lòng trả lời tin nhắn này để chúng tôi cải thiện dịch vụ. 🥰"
        )
        db = SessionLocal()
        user = db.query(User).filter(User.telegramId == user_telegram_id).first()
        if user:
            user.awaitingFeedback = True
            db.commit()
        db.close()
    except Exception as e:
        logger.exception(f"Error sending feedback prompt to user {user_telegram_id}")
