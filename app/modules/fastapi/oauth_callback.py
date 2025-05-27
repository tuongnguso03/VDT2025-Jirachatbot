from fastapi import FastAPI, Request, APIRouter
import requests
import datetime
from database import SessionLocal
from models import User
from modules.fastapi.config import JIRA_CLIENT_ID, JIRA_CLIENT_SECRET, REDIRECT_URI, BOT_TOKEN
from fastapi.responses import HTMLResponse 

app = FastAPI()
router = APIRouter()

@router.get("/oauth/callback")
def oauth_callback(code: str, state: str):
    telegram_id = int(state)

    token_url = "https://auth.atlassian.com/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": JIRA_CLIENT_ID,
        "client_secret": JIRA_CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI
    }

    response = requests.post(token_url, data=payload)
    data = response.json()

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expired_in = data.get("expires_in")

    if not access_token:
        return {"error": "Không lấy được token", "details": data}
    
    cloud_url = "https://api.atlassian.com/oauth/token/accessible-resources"
    headers = {"Authorization": f"Bearer {access_token}"}
    cloud_response = requests.get(cloud_url, headers=headers)
    cloud_data = cloud_response.json()

    cloud_id = cloud_data[0]["id"]

    session = SessionLocal()
    user = session.query(User).filter_by(telegramId=telegram_id).first()
    if user:
        user.accessToken = access_token
        user.refreshToken = refresh_token
        user.expiredAt = datetime.datetime.now() + datetime.timedelta(seconds=expired_in) if expired_in else None
        user.cloudId = cloud_id
        session.commit()
    session.close()

    notify_user(telegram_id, "🎉 Bạn đã liên kết thành công với Jira!")
    
    html_content = """
    <html>
    <head>
    <title>Đăng nhập thành công</title>
    <style>
    body { font-family: Arial, sans-serif; background-color: #f4f4f4; text-align: center; padding-top: 50px; }
    .container { background: white; padding: 20px; margin: auto; width: 50%; border-radius: 8px; box-shadow: 0 0 10px #ccc; }
    button { padding: 10px 20px; background-color: #0088cc; color: white; border: none; border-radius: 4px; cursor: pointer; }
    button:hover { background-color: #006699; }
    </style>
    </head>
    <body>
    <div class="container">
    <h1>Đăng nhập thành công!</h1>
    <p>Bạn đã liên kết thành công với Jira!</p>
    <a href="https://web.telegram.org/a"><button>Back to Telegram</button></a>
    </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

def notify_user(telegram_id, message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": message
    }
    requests.post(url, json=payload)
