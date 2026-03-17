"""
Admin-only endpoints.
All routes require the current user to have role=ADMIN.
"""
import logging
import asyncio
import shutil
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as ApiPath
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from typing import Annotated, List, Optional
from pathlib import Path
from pydantic import BaseModel

from app.dependencies import get_db
from app.models import AppModel, Users, ErrorLog
from app.constants import AppStatus, UserRoles, BillingType
from app.services.auth import get_admin_user
from app.services.system_metrics import get_system_metrics
from app.services.docker import docker_container_exists, docker_remove_container, docker_remove_image
from app.services.nginx_manager import remove_app_conf
from app.config import Config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

db_dep = Annotated[AsyncSession, Depends(get_db)]
admin_dep = Annotated[Users, Depends(get_admin_user)]

BASE_APPS_DIR = Path(Config.BASE_APPS_DIR)


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", status_code=status.HTTP_200_OK)
async def admin_health(db: db_dep, _: admin_dep):
    metrics = await get_system_metrics()

    # App stats from DB
    result = await db.execute(select(func.count()).select_from(AppModel))
    total_apps = result.scalar() or 0

    result = await db.execute(
        select(func.count()).select_from(AppModel).where(AppModel.status == AppStatus.RUNNING)
    )
    running_apps = result.scalar() or 0

    result = await db.execute(
        select(func.count()).select_from(AppModel).where(AppModel.status == AppStatus.ERROR)
    )
    error_apps = result.scalar() or 0

    result = await db.execute(select(func.count()).select_from(Users))
    total_users = result.scalar() or 0

    return {
        **metrics,
        "apps": {
            "total": total_apps,
            "running": running_apps,
            "error": error_apps,
        },
        "users": {"total": total_users},
    }


# ── Apps ──────────────────────────────────────────────────────────────────────

@router.get("/apps", status_code=status.HTTP_200_OK)
async def admin_list_apps(
    db: db_dep,
    _: admin_dep,
    filter_status: Optional[str] = None,
    page: int = 1,
    size: int = 50,
):
    query = select(AppModel)
    if filter_status and filter_status in [s.value for s in AppStatus]:
        query = query.where(AppModel.status == filter_status)
    query = query.order_by(AppModel.id.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    apps = result.scalars().all()

    count_result = await db.execute(select(func.count()).select_from(AppModel))
    total = count_result.scalar() or 0

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                "id": app.id,
                "name": app.name,
                "subdomain": app.subdomain,
                "repo_url": app.repo_url,
                "branch": app.branch,
                "status": app.status.value,
                "internal_port": app.internal_port,
                "container_port": app.container_port,
                "user_id": app.user_id,
                "created_at": app.created_at.isoformat() if app.created_at else None,
            }
            for app in apps
        ],
    }


class AdminAppUpdate(BaseModel):
    status: Optional[str] = None
    branch: Optional[str] = None


@router.patch("/apps/{app_id}", status_code=status.HTTP_200_OK)
async def admin_update_app(
    data: AdminAppUpdate,
    db: db_dep,
    _: admin_dep,
    app_id: int = ApiPath(gt=0),
):
    result = await db.execute(select(AppModel).where(AppModel.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    if data.status and data.status in [s.value for s in AppStatus]:
        app.status = AppStatus(data.status)
    if data.branch:
        app.branch = data.branch

    await db.commit()
    return {"id": app.id, "status": app.status.value, "branch": app.branch}


@router.delete("/apps/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_app(
    db: db_dep,
    _: admin_dep,
    app_id: int = ApiPath(gt=0),
):
    result = await db.execute(select(AppModel).where(AppModel.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    image_name = f"app_{app_id}_image"
    container_name = f"app_{app_id}_container"

    container_id = await asyncio.to_thread(docker_container_exists, container_name)
    if container_id:
        await asyncio.to_thread(docker_remove_container, container_name, container_id)

    await asyncio.to_thread(docker_remove_image, image_name)
    await remove_app_conf(app_id)

    app_dir = BASE_APPS_DIR / f"app-{app_id}"
    log_dir = Config.BASE_LOGS_DIR / f"app-{app_id}"
    if app_dir.exists():
        await asyncio.to_thread(shutil.rmtree, app_dir)
    if log_dir.exists():
        await asyncio.to_thread(shutil.rmtree, log_dir)

    await db.delete(app)
    await db.commit()


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", status_code=status.HTTP_200_OK)
async def admin_list_users(
    db: db_dep,
    _: admin_dep,
    page: int = 1,
    size: int = 50,
):
    query = select(Users).order_by(Users.id.asc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    users = result.scalars().all()

    count_result = await db.execute(select(func.count()).select_from(Users))
    total = count_result.scalar() or 0

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role.value,
                "billing_type": u.billing_type.value,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    }


class AdminUserUpdate(BaseModel):
    role: Optional[str] = None
    billing_type: Optional[str] = None


@router.patch("/users/{user_id}", status_code=status.HTTP_200_OK)
async def admin_update_user(
    data: AdminUserUpdate,
    db: db_dep,
    _: admin_dep,
    user_id: int = ApiPath(gt=0),
):
    result = await db.execute(select(Users).where(Users.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.role and data.role in [r.value for r in UserRoles]:
        user.role = UserRoles(data.role)
    if data.billing_type and data.billing_type in [b.value for b in BillingType]:
        user.billing_type = BillingType(data.billing_type)

    await db.commit()
    return {"id": user.id, "role": user.role.value, "billing_type": user.billing_type.value}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    db: db_dep,
    _: admin_dep,
    user_id: int = ApiPath(gt=0),
):
    # First delete all apps belonging to this user
    app_result = await db.execute(select(AppModel).where(AppModel.user_id == user_id))
    apps = app_result.scalars().all()
    for app in apps:
        image_name = f"app_{app.id}_image"
        container_name = f"app_{app.id}_container"
        container_id = await asyncio.to_thread(docker_container_exists, container_name)
        if container_id:
            await asyncio.to_thread(docker_remove_container, container_name, container_id)
        await asyncio.to_thread(docker_remove_image, image_name)
        await remove_app_conf(app.id)
        app_dir = BASE_APPS_DIR / f"app-{app.id}"
        if app_dir.exists():
            await asyncio.to_thread(shutil.rmtree, app_dir)
        await db.delete(app)

    result = await db.execute(select(Users).where(Users.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()


# ── Error logs ────────────────────────────────────────────────────────────────

@router.get("/errors", status_code=status.HTTP_200_OK)
async def admin_error_logs(
    db: db_dep,
    _: admin_dep,
    page: int = 1,
    size: int = 50,
):
    query = select(ErrorLog).order_by(ErrorLog.id.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    logs = result.scalars().all()

    count_result = await db.execute(select(func.count()).select_from(ErrorLog))
    total = count_result.scalar() or 0

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                "id": log.id,
                "error_code": log.error_code,
                "status_code": log.status_code,
                "app_id": log.app_id,
                "context": log.context,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }
