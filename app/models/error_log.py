from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database import Base
from datetime import datetime, timezone


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    error_code = Column(String, nullable=False, index=True)
    status_code = Column(Integer, nullable=False)
    app_id = Column(Integer, nullable=True, index=True)
    context = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
