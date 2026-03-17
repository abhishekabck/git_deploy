from typing import AsyncGenerator
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sidecar.database import AsyncSessionLocal
from sidecar.config import SidecarConfig


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def verify_api_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != SidecarConfig.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
