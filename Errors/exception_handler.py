"""
FastAPI global exception handler for AppBaseError.
"""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from Errors.app_errors import AppBaseError
from Errors.error_logger import log_error
from database import SessionLocal

logger = logging.getLogger(__name__)

async def app_error_handler(request: Request, exc: AppBaseError) -> JSONResponse:
    """
    Catches any AppBaseError raised anywhere in the app,
    logs it to the DB, and returns a structured JSON response.
    """
    # Attempt to extract app_id from path params(e.g. /apps/{app_id}/deploy)
    app_id = request.path_params.get("app_id")

    db = SessionLocal()
    try:
        log_error(db, exc, app_id=int(app_id) if app_id else None)
    except Exception as log_exc:
        logger.error("Failed to persist error log: %s", str(log_exc))
    finally:
        db.close()


    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.detail,
        },
    )