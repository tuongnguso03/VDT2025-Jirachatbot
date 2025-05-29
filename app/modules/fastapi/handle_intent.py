from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv
from database import SessionLocal
from models import User

load_dotenv()
router = APIRouter()

class IntentRequest(BaseModel):
    user_id: int
    intent: str
    data: dict

@router.post("/handle_intent")
async def handle_intent(payload: IntentRequest):
    user_id = payload.user_id
    intent = payload.intent
    data = payload.data

    try:
        access_token = get_access_token(user_id)
    except Exception:
        return {
            "success": False,
            "message": "Bạn chưa kết nối với Jira hoặc Confluence. Vui lòng đăng nhập để tiếp tục."
        }

    try:
        if intent == "log_work":
            result = log_work_to_jira(user_id, data)
        elif intent == "search_confluence":
            result = search_confluence(user_id, data)
        else:
            return {
                "success": False,
                "message": "Tôi chưa hiểu ý định của bạn. Vui lòng thử lại với yêu cầu rõ hơn."
            }
        return {
            "success": True,
            "message": result
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Đã xảy ra lỗi trong quá trình xử lý: {str(e)}"
        }

def get_access_token(user_id: int) -> str:
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(userId=user_id).first()
        if not user:
            raise Exception(f"User {user_id} not found")
        if not user.accessToken:
            raise Exception("User has no access token stored")
        return user.accessToken
    finally:
        session.close()

def get_cloud_id(user_id: int) -> str:
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(userId=user_id).first()
        if not user:
            raise Exception(f"User {user_id} not found")
        if not user.cloudId:
            raise Exception("User has no cloud ID stored")
        return user.cloudId
    finally:
        session.close()

def get_domain(user_id: int) -> str:
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(userId=user_id).first()
        if not user:
            raise Exception(f"User {user_id} not found")
        if not user.domain:
            raise Exception("User has no domain stored")
        return user.domain
    finally:
        session.close()