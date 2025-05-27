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
    # cloud_url = "https://api.atlassian.com/oauth/token/accessible-resources"
    # headers = {"Authorization": f"Bearer {access_token}"}
    # cloud_response = requests.get(cloud_url, headers=headers)
    # cloud_data = cloud_response.json()

    # if not cloud_data:
    #     return {"error": "Không truy cập được Jira site nào", "details": cloud_response.text}

    # cloud_id = cloud_data[0]["id"]
    # jira_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/search?jql=assignee=currentuser()"

    expires_in = data.get("expires_in")

    if not access_token:
        return {"error": "Không lấy được token", "details": data}

    session = SessionLocal()
    user = session.query(User).filter_by(telegramId=telegram_id).first()
    if user:
        user.accessToken = access_token
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

@router.post("/oauth/refresh")
def oauth_refresh(telegram_id: int):
    session = SessionLocal()
    user = session.query(User).filter_by(telegramId=telegram_id).first()
    if not user or not user.refreshToken:
        session.close()
        raise HTTPException(status_code=400, detail="Người dùng không tồn tại hoặc chưa có refresh token")

    refresh_token = user.refreshToken
    token_url = "https://auth.atlassian.com/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": JIRA_CLIENT_ID,
        "client_secret": JIRA_CLIENT_SECRET,
        "refresh_token": refresh_token
    }

    response = requests.post(token_url, data=payload)
    data = response.json()

    new_access_token = data.get("access_token")
    new_refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    if not new_access_token:
        session.close()
        raise HTTPException(status_code=400, detail={"error": "Không lấy được token mới", "details": data})

    user.accessToken = new_access_token
    if new_refresh_token:
        user.refreshToken = new_refresh_token  # Atlassian có thể trả refresh token mới
    session.commit()
    session.close()

    return {
        "message": "Làm mới token thành công",
        "access_token": new_access_token,
        "expires_in": expires_in
    }


def notify_user(telegram_id, message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": message
    }
    requests.post(url, json=payload)
