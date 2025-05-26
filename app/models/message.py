from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, func, TEXT
from sqlalchemy.orm import relationship
from database import Base 

class Message(Base):
    __tablename__ = 'messages'

    messageId = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(Integer, ForeignKey('users.userId'), nullable=False)
    role = Column(String, nullable=False)  # 'user' hoặc 'bot'
    message = Column(TEXT, nullable=False)
    timestamp = Column(TIMESTAMP, server_default=func.now())

    user = relationship("User", backref="messages")
