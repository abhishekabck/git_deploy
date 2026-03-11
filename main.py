import api
import logging
from fastapi import FastAPI
from app.Errors.app_errors import AppBaseError
from app.Errors.exception_handler import app_error_handler
from app.database import engine, Base
from app.config import Config
app = FastAPI()
app.include_router(api.router, prefix="/api")
app.add_exception_handler(AppBaseError, app_error_handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

Base.metadata.create_all(bind=engine)
Config.BASE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
Config.BASE_APPS_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/")
def health():
    return {
        "status": "healthy"
    }