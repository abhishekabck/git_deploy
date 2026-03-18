from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import Config


def _make_async_url(url: str) -> str:
    """Convert a plain DB URL to its async driver equivalent."""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("sqlite+aiosqlite"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


ASYNC_DATABASE_URL = _make_async_url(Config.DB_URL)

connect_args = {}
if "sqlite" in ASYNC_DATABASE_URL:
    connect_args["check_same_thread"] = False

_pool_kwargs = {}
if "sqlite" not in ASYNC_DATABASE_URL:
    _pool_kwargs = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

engine = create_async_engine(
    ASYNC_DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    **_pool_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass
