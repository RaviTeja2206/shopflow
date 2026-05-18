import json

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


class Cache:
    """
    Simple cache-aside helper.
    Pattern: check cache first, if miss hit DB, store result in cache.
    """
    PREFIX = "shopflow:products"
    TTL = 300  # 5 minutes

    @staticmethod
    async def get(key: str) -> dict | list | None:
        redis = await get_redis()
        value = await redis.get(f"{Cache.PREFIX}:{key}")
        if value:
            logger.info("cache_hit", key=key)
            return json.loads(value)
        logger.info("cache_miss", key=key)
        return None

    @staticmethod
    async def set(key: str, value: dict | list, ttl: int = TTL) -> None:
        redis = await get_redis()
        await redis.setex(
            f"{Cache.PREFIX}:{key}",
            ttl,
            json.dumps(value, default=str),  # default=str handles UUID, Decimal
        )

    @staticmethod
    async def delete(key: str) -> None:
        redis = await get_redis()
        await redis.delete(f"{Cache.PREFIX}:{key}")

    @staticmethod
    async def delete_pattern(pattern: str) -> None:
        """Delete all keys matching a pattern — used for cache invalidation."""
        redis = await get_redis()
        keys = await redis.keys(f"{Cache.PREFIX}:{pattern}")
        if keys:
            await redis.delete(*keys)
            logger.info("cache_invalidated", pattern=pattern, count=len(keys))
