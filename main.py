from fastapi import FastAPI
from routes import apps
from Errors.app_errors import AppBaseError
from Errors.exception_handler import app_error_handler
app = FastAPI()
app.include_router(apps.router)
app.add_exception_handler(AppBaseError, app_error_handler)
from database import engine, Base
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

Base.metadata.create_all(bind=engine)

@app.get("/")
def health():
    return {
        "status": "healthy"
    }