from sqlalchemy import Column, Integer, String, TIMESTAMP, func, BIGINT 
from sqlalchemy.orm import relationship
from database import Base 

class User(Base):
    __tablename__ = 'users'

    userId = Column(Integer, primary_key=True, autoincrement=True)
    telegramId = Column(BIGINT, unique=True, nullable=False)
    telegramUsername = Column(String, nullable=False)
    accessToken = Column(String, nullable=True)
    refreshToken = Column(String, nullable=True)
    cloudId = Column(String, nullable=True) 
    expiredAt = Column(TIMESTAMP, nullable=True) 
    createdAt = Column(TIMESTAMP, server_default=func.now())
    updatedAt = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    messages = relationship("Message", back_populates="user")
