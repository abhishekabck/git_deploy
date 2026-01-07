from fastapi import FastAPI
from routes import apps
app = FastAPI()
app.include_router(apps.router)
from database import engine, Base

Base.metadata.create_all(bind=engine)
