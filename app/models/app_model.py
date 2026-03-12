from app.database import Base
from sqlalchemy import Column, Integer, String, Text, Enum, CheckConstraint, JSON, ForeignKey
from app.models.timestatus_mixin import TimeStatusMixin
from app.constants import AppStatus

class AppModel(Base, TimeStatusMixin):
    __tablename__ = "apps"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    subdomain = Column(Text, unique=True, index=True)
    repo_url = Column(String, nullable=False)
    internal_port = Column(Integer, unique=True)
    branch = Column(String, nullable=False, default="main")       # used for checking out code form branch
    build_path = Column(String, nullable=False, default=".")       # Build Path - relative to repo root
    dockerfile_path = Column(String, nullable=False, default="Dockerfile")  # Dockerfile path -- Custom Path possible
    container_port = Column(Integer, unique=False, nullable=False)
    status = Column(Enum(AppStatus), nullable=False, default=AppStatus.CREATED)
    env = Column(JSON, nullable=False, default=dict)
    user_id = Column(ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint('container_port >= 1024 AND container_port <= 65535', name='valid_port_range'),
    )
