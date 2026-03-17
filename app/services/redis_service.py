"""
Redis service — optional caching layer.
Uses a gitdeploy: namespace prefix so we don't clash with other apps on the same Redis.
If Redis is disabled or unreachable, all operations silently no-op.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

REDIS_PREFIX = "gitdeploy:"

_client: Optional["aioredis.Redis"] = None  # type: ignore


async def init_redis(url: str) -> None:
    global _client
    if not _REDIS_AVAILABLE:
        logger.warning("redis package not installed — Redis disabled.")
        return
    try:
        _client = aioredis.from_url(url, decode_responses=True)
        await _client.ping()
        logger.info("Redis connected: %s", url)
    except Exception as e:
        logger.warning("Redis unavailable (%s) — continuing without cache.", e)
        _client = None


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def redis_get(key: str) -> Optional[str]:
    if _client is None:
        return None
    try:
        return await _client.get(f"{REDIS_PREFIX}{key}")
    except Exception:
        return None


async def redis_set(key: str, value: str, ex: int = 60) -> None:
    if _client is None:
        return
    try:
        await _client.set(f"{REDIS_PREFIX}{key}", value, ex=ex)
    except Exception:
        pass


async def redis_delete(key: str) -> None:
    if _client is None:
        return
    try:
        await _client.delete(f"{REDIS_PREFIX}{key}")
    except Exception:
        pass


async def redis_incr(key: str, ex: int = 3600) -> int:
    """Increment a counter, initialising TTL on first call. Returns new value."""
    if _client is None:
        return 0
    try:
        pipe = _client.pipeline()
        full_key = f"{REDIS_PREFIX}{key}"
        await pipe.incr(full_key)
        await pipe.expire(full_key, ex)
        results = await pipe.execute()
        return results[0]
    except Exception:
        return 0
