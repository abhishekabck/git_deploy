"""
Secret Manager Sidecar — gitDeploy companion service.

Runs on port 8001 by default. Provides encrypted storage of per-app
environment variable secrets using AES encryption (Fernet).

Authentication: X-Api-Key header (shared secret with main app).

Endpoints:
  GET  /health                    - health check
  POST /secrets/{app_id}          - store / update secrets for an app
  GET  /secrets/{app_id}          - retrieve decrypted secrets for an app
  DELETE /secrets/{app_id}        - delete secrets for an app
  GET  /secrets                   - list all app IDs that have secrets stored
  POST /admin/rotate-key          - re-encrypt all secrets with a new key
"""
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Depends, HTTPException
from fastapi import Path as ApiPath
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from sidecar.config import SidecarConfig
from sidecar.database import engine, Base, AsyncSessionLocal
from sidecar.models import SecretStore
from sidecar.crypto import encrypt, decrypt, generate_key
from sidecar.dependencies import get_db, verify_api_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Secret Manager sidecar started on port %s", SidecarConfig.PORT)
    if not SidecarConfig.ENCRYPTION_KEY:
        new_key = generate_key()
        logger.warning(
            "SIDECAR_ENCRYPTION_KEY not set! Generated ephemeral key (secrets lost on restart):\n%s",
            new_key,
        )
        SidecarConfig.ENCRYPTION_KEY = new_key
    yield
    await engine.dispose()


app = FastAPI(
    title="gitDeploy Secret Manager",
    description="Sidecar service for encrypted per-app secret storage.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class SecretsPayload(BaseModel):
    secrets: dict[str, str]


class RotateKeyPayload(BaseModel):
    new_key: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "secret-manager-sidecar"}


@app.post("/secrets/{app_id}", dependencies=[Depends(verify_api_key)])
async def store_secrets(
    payload: SecretsPayload,
    db: AsyncSession = Depends(get_db),
    app_id: int = ApiPath(gt=0),
):
    encrypted = encrypt(json.dumps(payload.secrets), SidecarConfig.ENCRYPTION_KEY)

    result = await db.execute(select(SecretStore).where(SecretStore.app_id == app_id))
    existing = result.scalar_one_or_none()

    if existing:
        existing.encrypted_secrets = encrypted
    else:
        db.add(SecretStore(app_id=app_id, encrypted_secrets=encrypted))

    await db.commit()
    logger.info("Secrets stored for app_id=%s (%d keys)", app_id, len(payload.secrets))
    return {"app_id": app_id, "keys_stored": len(payload.secrets)}


@app.get("/secrets/{app_id}", dependencies=[Depends(verify_api_key)])
async def get_secrets(
    db: AsyncSession = Depends(get_db),
    app_id: int = ApiPath(gt=0),
):
    result = await db.execute(select(SecretStore).where(SecretStore.app_id == app_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No secrets found for this app")

    try:
        decrypted = decrypt(record.encrypted_secrets, SidecarConfig.ENCRYPTION_KEY)
        secrets = json.loads(decrypted)
    except Exception as e:
        logger.error("Decryption failed for app_id=%s: %s", app_id, e)
        raise HTTPException(status_code=500, detail="Failed to decrypt secrets")

    return {"app_id": app_id, "secrets": secrets}


@app.delete("/secrets/{app_id}", dependencies=[Depends(verify_api_key)])
async def delete_secrets(
    db: AsyncSession = Depends(get_db),
    app_id: int = ApiPath(gt=0),
):
    result = await db.execute(select(SecretStore).where(SecretStore.app_id == app_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No secrets found for this app")

    await db.delete(record)
    await db.commit()
    logger.info("Secrets deleted for app_id=%s", app_id)
    return {"message": f"Secrets for app {app_id} deleted"}


@app.get("/secrets", dependencies=[Depends(verify_api_key)])
async def list_secret_app_ids(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SecretStore.app_id))
    app_ids = [row[0] for row in result.all()]
    return {"app_ids": app_ids, "count": len(app_ids)}


@app.post("/admin/rotate-key", dependencies=[Depends(verify_api_key)])
async def rotate_encryption_key(
    payload: RotateKeyPayload,
    db: AsyncSession = Depends(get_db),
):
    """Re-encrypt all stored secrets with a new encryption key."""
    result = await db.execute(select(SecretStore))
    records = result.scalars().all()

    rotated = 0
    for record in records:
        try:
            plain = decrypt(record.encrypted_secrets, SidecarConfig.ENCRYPTION_KEY)
            record.encrypted_secrets = encrypt(plain, payload.new_key)
            rotated += 1
        except Exception as e:
            logger.error("Key rotation failed for app_id=%s: %s", record.app_id, e)

    SidecarConfig.ENCRYPTION_KEY = payload.new_key
    await db.commit()
    logger.info("Key rotation complete. %d records re-encrypted.", rotated)
    return {"rotated": rotated}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "sidecar.main:app",
        host=SidecarConfig.HOST,
        port=SidecarConfig.PORT,
        reload=False,
    )
