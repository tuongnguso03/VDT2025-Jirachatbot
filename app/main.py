from fastapi import FastAPI
from modules.fastapi.oauth_callback import router as oauth_router
from database import Base, engine
from models.user import User
from models.message import Message

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI application!"}

@app.on_event("startup")
def on_startup():
    print("Database tables created (if not existed)")

    Base.metadata.create_all(bind=engine)

app.include_router(oauth_router)
