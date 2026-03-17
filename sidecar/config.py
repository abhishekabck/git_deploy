import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class SidecarConfig:
    API_KEY: str = os.getenv("SIDECAR_API_KEY", secrets.token_hex(32))
    ENCRYPTION_KEY: str = os.getenv("SIDECAR_ENCRYPTION_KEY", "")  # Must be set in production
    DB_PATH: str = os.getenv("SIDECAR_DB_PATH", "/opt/secrets/secrets.db")
    HOST: str = os.getenv("SIDECAR_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("SIDECAR_PORT", "8001"))
    ALLOWED_ORIGINS: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
