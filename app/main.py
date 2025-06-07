from fastapi import FastAPI
from modules.fastapi.oauth_callback import router as oauth_router
from modules.vector_db.document_change import doc_router
from modules.fastapi.refresh_token import start_scheduler
from modules.fastapi.jira_scheduler import start_scheduler_everyday
from modules.fastapi.feedback import start_feedback_scheduler
from database import Base, engine
from models.user import User
from models.message import Message

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "from Tường with love"}

@app.on_event("startup")
def on_startup():
    print("Database tables created (if not existed)")
    
    Base.metadata.create_all(bind=engine)

app.include_router(oauth_router)
app.include_router(doc_router)
start_scheduler()
start_scheduler_everyday()
start_feedback_scheduler()
