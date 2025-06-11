from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pytz
from database import SessionLocal
from modules.jira.jira_task import get_today_issues, get_worklogs, get_current_user, get_jira_client, get_today_logs
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
                    message = "📌  *TASK HÔM NAY CỦA BẠN TRÊN JIRA:*\n\n"
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

def check_jira_worklogs():
    print(f"[{datetime.now()}] Running Jira worklog reminder...")

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
                today_issues = get_today_logs(access_token, cloud_id)
                if not today_issues:
                    continue

                jira = get_jira_client(access_token, cloud_id)
                account_id = get_current_user(jira)["accountId"]

                tz = pytz.timezone("Asia/Ho_Chi_Minh")
                today_start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start + timedelta(days=1)

                issues_not_logged = []
                for issue in today_issues:
                    worklogs = get_worklogs(access_token, cloud_id, issue['key'])

                    has_logged_today = any(
                        w.get("started") and 
                        account_id in w.get("author", "") and 
                        today_start <= datetime.strptime(w["started"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=tz) < today_end
                        for w in worklogs
                    )

                    if not has_logged_today:
                        issues_not_logged.append(issue)

                if issues_not_logged:
                    message = "⏰  *NHẮC NHỞ LOG WORK JIRA HÔM NAY:*\n\nBạn chưa log work cho các task sau:\n"
                    for i, issue in enumerate(issues_not_logged, 1):
                        message += f"{i}. `{issue['key']}` - {issue['summary']}\n"
                    message += "Hãy đảm bảo bạn đã log work đầy đủ nhé! 💪"

                    print(f"Nhắc user {user.userId} log work - telegramId={telegram_id}")
                    send_telegram_message(telegram_id, message)

            except Exception as e:
                print(f"Lỗi khi xử lý user {user.userId}: {str(e)}")

    finally:
        db.close()

def start_scheduler_everyday():
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.add_job(check_jira_tasks, 'cron', hour=8, minute=0)
    scheduler.add_job(check_jira_worklogs, 'cron', hour=17, minute=0)
    scheduler.start()