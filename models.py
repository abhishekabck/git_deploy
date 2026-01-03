import enum
from sqlalchemy import Column, Integer, String, Enum, Text, DateTime
from database import Base
from datetime import datetime


class AppStatus(enum.Enum):
    CREATED = "created"
    RUNNING = "running"
    ERROR = "error"
    PREPARED = "prepared"

class AppModel(Base):
    __tablename__ = "apps"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    subdomain = Column(Text, unique=True, index=True)
    repo_url = Column(String, nullable=False)
    internal_port = Column(Integer, unique=True)
    status = Column(Enum(AppStatus), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
