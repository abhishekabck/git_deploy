import api
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.Errors.app_errors import AppBaseError
from app.Errors.exception_handler import app_error_handler
from app.database import engine, Base
from app.config import Config
from app.services.redis_service import init_redis, close_redis
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Config.BASE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    Config.BASE_APPS_DIR.mkdir(parents=True, exist_ok=True)
    if Config.REDIS_ENABLED:
        await init_redis(Config.REDIS_URL)
    yield
    # Shutdown
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="gitDeploy",
    description="Self-hosted PaaS — deploy GitHub repos as Docker containers.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router, prefix="/api")
app.add_exception_handler(AppBaseError, app_error_handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


@app.get("/", tags=["health"])
async def health():
    return {"status": "healthy", "version": "2.0.0"}
