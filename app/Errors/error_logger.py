import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.error_log import ErrorLog
from app.Errors.app_errors import AppBaseError

logger = logging.getLogger(__name__)


async def log_error(db: AsyncSession, error: AppBaseError, app_id: int | None = None) -> None:
    try:
        entry = ErrorLog(
            error_code=str(error.error_code),
            status_code=error.status_code,
            app_id=app_id,
            context=error.context,
        )
        db.add(entry)
        await db.commit()
    except Exception as exc:
        logger.error("Failed to persist error log: %s", exc)
