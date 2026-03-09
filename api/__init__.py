from fastapi import APIRouter

from api.v1 import apps

router = APIRouter()
router.include_router(apps.router, prefix="/v1", tags=['/api/v1'])