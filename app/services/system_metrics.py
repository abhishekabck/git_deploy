"""System health metrics using psutil."""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

_start_time = datetime.now(timezone.utc)


def _collect_metrics() -> dict:
    if not _PSUTIL_AVAILABLE:
        return {"error": "psutil not installed"}

    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    uptime_seconds = (datetime.now(timezone.utc) - _start_time).total_seconds()

    return {
        "cpu": {
            "percent": cpu,
            "count": psutil.cpu_count(),
        },
        "memory": {
            "total_mb": round(mem.total / 1024 / 1024, 1),
            "available_mb": round(mem.available / 1024 / 1024, 1),
            "used_mb": round(mem.used / 1024 / 1024, 1),
            "percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
            "free_gb": round(disk.free / 1024 / 1024 / 1024, 2),
            "used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent_mb": round(net.bytes_sent / 1024 / 1024, 2),
            "bytes_recv_mb": round(net.bytes_recv / 1024 / 1024, 2),
        },
        "uptime_seconds": round(uptime_seconds),
    }


async def get_system_metrics() -> dict:
    return await asyncio.to_thread(_collect_metrics)
