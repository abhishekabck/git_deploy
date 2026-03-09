
"""
Utility to persist error occurrences into the ErrorLog table.
"""

from __future__ import annotations
import logging
from sqlalchemy.orm import Session
from app.models import ErrorLog
from app.Errors.app_errors import AppBaseError

logger = logging.getLogger(__name__)

def log_error(db: Session, error: AppBaseError, app_id: int | None = None) -> ErrorLog:
    """
    Persist an AppBaseError instance to the error_logs table.

    Args:
        db: Active SQLAlchemy session.
        error: The custom error instance.
        app_id: Optional related application ID.

    Returns:
        The Created ErrorLog record.
    """
    entry = ErrorLog(
        error_code=str(error.error_code),
        status_code=error.status_code,
        app_id=app_id,
        context=error.context,
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)
    logger.info(
        "ErrorLog #%s recorded - code=%s status=%s app_id=%s",
        entry.id,
        entry.error_code,
        entry.status_code,
        app_id,
    )
    return entry