from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime, timezone
from sidecar.database import Base


class SecretStore(Base):
    __tablename__ = "secret_store"

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_id = Column(Integer, nullable=False, index=True, unique=True)
    encrypted_secrets = Column(Text, nullable=False)   # JSON dict, encrypted
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
