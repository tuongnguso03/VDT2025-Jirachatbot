from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Feedback(Base):
    __tablename__ = 'feedback'

    feedbackId = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(Integer, ForeignKey('users.userId'), nullable=False)
    content = Column(Text)
    createdAt = Column(DateTime)

    user = relationship("User", back_populates="feedbacks")