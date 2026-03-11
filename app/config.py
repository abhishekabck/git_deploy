from dotenv import load_dotenv
import os
from pathlib import Path
load_dotenv()

class Config:
    DB_URL = os.getenv("DB_URL")
    BASE_APPS_DIR = Path(os.getenv("BASE_APPS_DIR", "/opt/apps"))
    BASE_LOGS_DIR = Path(os.getenv("BASE_LOGS_DIR", "/opt/logs"))