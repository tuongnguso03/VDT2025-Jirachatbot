from fastapi import FastAPI
from database import Base, engine

app = FastAPI()

print(Base.metadata.tables.keys())

@app.on_event("startup")
def on_startup():
    print("Creating database tables if they do not exist...")
    from models.user import User
    from models.message import Message

    Base.metadata.create_all(bind=engine)
    print("Database tables created (if not existed)")

@app.get("/")
async def root():
    return {"message": "Hello, FastAPI is running!"}
