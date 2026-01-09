from fastapi import FastAPI
from routes import apps
app = FastAPI()
app.include_router(apps.router)
from database import engine, Base
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

Base.metadata.create_all(bind=engine)
