from fastapi import APIRouter

from api.v1 import apps, auth, admin

router = APIRouter()
router.include_router(apps.router, prefix="/v1", tags=["apps"])
router.include_router(auth.router, prefix="/v1", tags=["auth"])
router.include_router(admin.router, prefix="/v1", tags=["admin"])
