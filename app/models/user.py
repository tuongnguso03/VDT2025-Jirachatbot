from sqlalchemy import Column, Integer, String, TIMESTAMP, func
from sqlalchemy.orm import relationship
from database import Base 

class User(Base):
    __tablename__ = 'users'

    userId = Column(Integer, primary_key=True, autoincrement=True)
    telegramId = Column(Integer, unique=True, nullable=False)
    accessToken = Column(String, nullable=True)
    refreshToken = Column(String, nullable=True)
    createdAt = Column(TIMESTAMP, server_default=func.now())

    messages = relationship("Message", back_populates="user")
