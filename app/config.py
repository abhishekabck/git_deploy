from dotenv import load_dotenv
import os
import secrets
from pathlib import Path

load_dotenv()


class Config:
    DB_URL = os.getenv("DB_URL")
    BASE_APPS_DIR = Path(os.getenv("BASE_APPS_DIR", "/opt/apps"))
    BASE_LOGS_DIR = Path(os.getenv("BASE_LOGS_DIR", "/opt/logs"))
    VALID_API_KEY = os.getenv("VALID_API_KEY", "")

    # JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", secrets.token_hex(32))
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))