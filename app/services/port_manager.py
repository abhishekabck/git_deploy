import asyncio
import socket
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AppModel
from app.Errors import NoAvailablePortError

logger = logging.getLogger(__name__)

PORT_RANGE_START = 10000
PORT_RANGE_END = 65535


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


async def allocate_free_port(db: AsyncSession) -> int:
    result = await db.execute(
        select(AppModel.internal_port).where(AppModel.internal_port.isnot(None))
    )
    used_ports = {row[0] for row in result.all()}
    logger.debug("Ports currently assigned in DB: %s", used_ports)

    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        if port in used_ports:
            continue
        free = await asyncio.to_thread(_is_port_free, port)
        if free:
            logger.info("Allocated free port: %d", port)
            return port

    logger.error("No available port found in range %d-%d", PORT_RANGE_START, PORT_RANGE_END)
    raise NoAvailablePortError()
