import socket
import logging
from sqlalchemy.orm import Session
from app.models import AppModel
from app.Errors import NoAvailablePortError

logger = logging.getLogger(__name__)

PORT_RANGE_START = 10000
PORT_RANGE_END = 65535


def is_port_free(port: int) -> bool:
    """Check if a port is free on the host OS by attempting to bind to it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def allocate_free_port(db: Session) -> int:
    """
    Find and return the lowest available port in the configured range that is:
      1. Not currently assigned to any app in the database
      2. Not bound by any process on the host OS

    This allows ports to be reused after an app is deleted or re-deployed,
    unlike a static formula (e.g. 10000 + id) which permanently consumes
    a port slot for every app ever created.

    Raises NoAvailablePortError if the entire range is exhausted.
    """
    # Snapshot of all ports currently held by apps in the DB
    used_ports = {
        row[0] for row in
        db.query(AppModel.internal_port)
        .filter(AppModel.internal_port.isnot(None))
        .all()
    }
    logger.debug("Ports currently assigned in DB: %s", used_ports)

    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        if port in used_ports:
            continue
        if is_port_free(port):
            logger.info("Allocated free port: %d", port)
            return port

    logger.error(
        "No available port found in range %d-%d",
        PORT_RANGE_START, PORT_RANGE_END
    )
    raise NoAvailablePortError()
