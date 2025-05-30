from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from database import SessionLocal
from modules.jira.jira_task import get_today_issues
from modules.telegrambot.telegrambot import send_telegram_message 
from models import User

def check_jira_tasks():
    print(f"[{datetime.now()}] Running Jira task check...")

    db = SessionLocal()
    try:
        users = db.query(User).filter(
            User.accessToken.isnot(None),
            User.cloudId.isnot(None),
            User.telegramId.isnot(None)
        ).all()
        print(f"Đã lấy được {len(users)} user có accessToken, cloudId, telegramId")

        for user in users:
            access_token = user.accessToken
            cloud_id = user.cloudId
            telegram_id = user.telegramId

            try:
                issues = get_today_issues(access_token, cloud_id)
                if issues:
                    message = "📌 *Task hôm nay của bạn trên Jira:*\n"
                    for i, issue in enumerate(issues, 1):
                        message += f"{i}. `{issue['key']}` - {issue['summary']}\n"
                else:
                    message = "🎉 Bạn không có task đến hạn vào ngày hôm nay!"

                print(f"Gửi tin nhắn cho user {user.userId} với telegramId={telegram_id}")
                send_telegram_message(telegram_id, message)

            except Exception as e:
                print(f"Lỗi khi xử lý user {user.userId}: {str(e)}")

    finally:
        db.close()

def start_scheduler_8AM():
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.add_job(check_jira_tasks, 'cron', hour=12, minute=36)
    scheduler.start()
