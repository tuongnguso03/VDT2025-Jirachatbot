from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from models import User, Message
from database import SessionLocal
from modules.fastapi.config import get_jira_auth_url, BOT_TOKEN
import aiohttp

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
            msg_user = Message(userId=user.userId, role="user", message=user_text)
            session.add(msg_user)
            session.commit()

            gemini_reply = await call_gemini_api(user_text)

            msg_bot = Message(userId=user.userId, role="bot", message=gemini_reply)
            session.add(msg_bot)
            session.commit()

            await update.message.reply_text(gemini_reply)
        else:
            await update.message.reply_text("Bạn chưa đăng ký, vui lòng gửi /start để bắt đầu.")
    except Exception as e:
        print(f"Error in handle_message: {e}")
        await update.message.reply_text("Đã có lỗi xảy ra, vui lòng thử lại sau.")
    finally:
        session.close()


async def call_gemini_api(text: str) -> str:
    url = "https://api.gemini.example.com/chat"  # URL chưa có thật

    # Nếu URL chưa thay đổi, nghĩa là chưa có API thật thì trả về câu thông báo
    if url == "https://api.gemini.example.com/chat":
        return "API Gemini hiện chưa sẵn sàng, vui lòng thử lại sau."

    payload = {"message": text}
    headers = {
        "Authorization": "Bearer YOUR_GEMINI_API_KEY",  # Thay bằng key thật khi có
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("reply", "Không có câu trả lời.")
                else:
                    text_resp = await resp.text()
                    print(f"API trả về lỗi status {resp.status}: {text_resp}")
                    return "Xin lỗi, tôi không thể xử lý yêu cầu ngay bây giờ."
    except Exception as e:
        print(f"Lỗi gọi API Gemini: {e}")
        return "Xin lỗi, tôi không thể xử lý yêu cầu ngay bây giờ."