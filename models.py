import enum
from sqlalchemy import Column, Integer, String, Enum, Text, DateTime, CheckConstraint
from database import Base
from datetime import datetime
from datetime import timezone


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
    container_port = Column(Integer, unique=False, nullable=False)
    status = Column(Enum(AppStatus), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint('container_port >= 1024 AND container_port <= 65535', name='valid_port_range'),
    )
