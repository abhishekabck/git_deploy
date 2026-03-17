import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from app.Errors.app_errors import AppBaseError

logger = logging.getLogger(__name__)


async def app_error_handler(request: Request, exc: AppBaseError) -> JSONResponse:
    logger.error(
        "AppError [%s] status=%s detail=%s context=%s",
        exc.error_code,
        exc.status_code,
        exc.detail,
        exc.context,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )
