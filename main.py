from fastapi import FastAPI
import api
from app.Errors.app_errors import AppBaseError
from app.Errors.exception_handler import app_error_handler
app = FastAPI()
app.include_router(api.router, prefix="/api")
app.add_exception_handler(AppBaseError, app_error_handler)
from app.database import engine, Base
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