from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import asyncio
import logging
from telegram import Bot
from database import SessionLocal
from models import User
from modules.fastapi.config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_feedback_prompt():
    logger.info(f"[{datetime.now()}] Sending feedback prompts...")

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.telegramId.isnot(None)).all()
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user.telegramId,
                    text="📣  KHẢO SÁT ĐỊNH KỲ\n\nBạn đánh giá trải nghiệm sử dụng chatbot như thế nào?\nBạn có góp ý gì cho hệ thống không?\nVui lòng trả lời tin nhắn này để chúng tôi cải thiện dịch vụ. 🥰"
                )
                user.awaitingFeedback = True
                db.commit()
            except Exception as e:
                logger.exception(f"Error sending feedback prompt to user {user.userId}")
    finally:
        db.close()

def start_feedback_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.add_job(lambda: asyncio.run(send_feedback_prompt()), 'cron', day=1, hour=9, minute=0)
    scheduler.start()
    logger.info("Feedback scheduler started")
