from dotenv import load_dotenv
import os
import secrets
from pathlib import Path

load_dotenv()


class Config:
    DB_URL: str = os.getenv("DB_URL", "sqlite+aiosqlite:///./gitdeploy.db")
    BASE_APPS_DIR: Path = Path(os.getenv("BASE_APPS_DIR", "/opt/apps"))
    BASE_LOGS_DIR: Path = Path(os.getenv("BASE_LOGS_DIR", "/opt/logs"))
    VALID_API_KEY: str = os.getenv("VALID_API_KEY", "")

    # JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", secrets.token_hex(32))
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # Redis — optional, gracefully skipped if not set
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "false").lower() == "true"

    # Domain — used to build public app URLs (e.g. app-1.yourdomain.com)
    APP_DOMAIN: str = os.getenv("APP_DOMAIN", "localhost")

    # Secret Sidecar
    SIDECAR_URL: str = os.getenv("SIDECAR_URL", "http://localhost:8001")
    SIDECAR_API_KEY: str = os.getenv("SIDECAR_API_KEY", secrets.token_hex(32))

    # Nginx — automatic config management
    NGINX_ENABLED: bool = os.getenv("NGINX_ENABLED", "false").lower() == "true"
    NGINX_CONF_DIR: str = os.getenv("NGINX_CONF_DIR", "/etc/nginx/gitdeploy.d")
    NGINX_AUTO_RELOAD: bool = os.getenv("NGINX_AUTO_RELOAD", "false").lower() == "true"
    NGINX_LISTEN_PORT: int = int(os.getenv("NGINX_LISTEN_PORT", "80"))

    # CORS origins (comma-separated)
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5500"
        ).split(",")
        if o.strip()
    ]
