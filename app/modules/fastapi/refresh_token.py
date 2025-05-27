from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import requests
from database import SessionLocal
from models import User
from modules.fastapi.config import JIRA_CLIENT_ID, JIRA_CLIENT_SECRET
import atexit

app = FastAPI()

def refresh_expiring_tokens():
    session = SessionLocal()
    now = datetime.datetime.now()
    threshold = now + datetime.timedelta(minutes=5)
    users = session.query(User).filter(
        User.accessToken.isnot(None),
        User.expiredAt.isnot(None),
        User.expiredAt <= threshold
    ).all()

    for user in users:
        print(f"Refreshing token for user {user.telegramId}")
        refresh_token = user.refreshToken
        if not refresh_token:
            continue
        
        token_url = "https://auth.atlassian.com/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": JIRA_CLIENT_ID,
            "client_secret": JIRA_CLIENT_SECRET,
            "refresh_token": refresh_token
        }
        try:
            response = requests.post(token_url, data=payload)
            data = response.json()

            new_access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token")
            expires_in = data.get("expires_in")

            if new_access_token:
                user.accessToken = new_access_token
                if new_refresh_token:
                    user.refreshToken = new_refresh_token
                if expires_in:
                    user.expiredAt = now + datetime.timedelta(seconds=expires_in)
                session.commit()
                print(f"Refreshed token for user {user.telegramId}")
            else:
                print(f"Failed to refresh token for user {user.telegramId}: {data}")

        except Exception as e:
            print(f"Exception when refreshing token for user {user.telegramId}: {e}")

    session.close()

def start_scheduler():
    print(f"Starting token refresh scheduler")
    scheduler = BackgroundScheduler()
    scheduler.add_job(refresh_expiring_tokens, 'interval', minutes=5)
    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())