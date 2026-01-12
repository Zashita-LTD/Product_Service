"""
Redis Cache implementation.

Implements Cache-Aside pattern with jitter for TTL.
"""
import random
from typing import Optional

import msgpack
import redis.asyncio as aioredis
from redis.asyncio import Redis

from pkg.logger.logger import get_logger


logger = get_logger(__name__)


# Default TTL in seconds (10 minutes)
DEFAULT_TTL = 600
# Maximum jitter in seconds (2 minutes)
MAX_JITTER = 120


class RedisCache:
    """
    Redis cache implementation with Cache-Aside pattern.

    Uses msgpack for efficient serialization and jitter for TTL
    to prevent cache stampede.
    """

    def __init__(
        self,
        redis_url: str,
        default_ttl: int = DEFAULT_TTL,
        max_jitter: int = MAX_JITTER,
    ) -> None:
        """
        Initialize the Redis cache.

        Args:
            redis_url: Redis connection URL.
            default_ttl: Default TTL in seconds.
            max_jitter: Maximum jitter to add to TTL.
        """
        self._redis_url = redis_url
        self._default_ttl = default_ttl
        self._max_jitter = max_jitter
        self._redis: Optional[Redis] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        self._redis = await aioredis.from_url(
            self._redis_url,
            encoding=None,  # We use binary for msgpack
            decode_responses=False,
        )
        logger.info("Connected to Redis", url=self._redis_url)

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.aclose()
            logger.info("Disconnected from Redis")

    async def close(self) -> None:
        """Alias for disconnect."""
        await self.disconnect()

    def _get_ttl_with_jitter(self, ttl: Optional[int] = None) -> int:
        """
        Calculate TTL with random jitter.

        Jitter helps prevent cache stampede when multiple keys
        expire at the same time.

        Args:
            ttl: Base TTL in seconds. Uses default if not provided.

        Returns:
            TTL with random jitter added.
        """
        base_ttl = ttl or self._default_ttl
        jitter = random.randint(0, self._max_jitter)
        return base_ttl + jitter

    async def get(self, key: str) -> Optional[dict]:
        """
        Get a value from cache.

        Args:
            key: Cache key.

        Returns:
            Cached value as dict, or None if not found.
        """
        if not self._redis:
            logger.warning("Redis not connected, cache miss")
            return None

        try:
            data = await self._redis.get(key)
            if data is None:
                logger.debug("Cache miss", key=key)
                return None

            value = msgpack.unpackb(data, raw=False)
            logger.debug("Cache hit", key=key)
            return value
        except Exception as e:
            logger.error("Cache get error", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: dict,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set a value in cache with TTL.

        Args:
            key: Cache key.
            value: Value to cache (must be dict).
            ttl: TTL in seconds. Uses default with jitter if not provided.

        Returns:
            True if successful, False otherwise.
        """
        if not self._redis:
            logger.warning("Redis not connected, skipping cache set")
            return False

        try:
            # Use default=str to handle UUID, Decimal, datetime etc.
            data = msgpack.packb(value, use_bin_type=True, default=str)
            ttl_with_jitter = self._get_ttl_with_jitter(ttl)
            await self._redis.setex(key, ttl_with_jitter, data)
            logger.debug("Cache set", key=key, ttl=ttl_with_jitter)
            return True
        except Exception as e:
            logger.error("Cache set error", key=key, error=str(e))
            return False

    async def invalidate(self, key: str) -> bool:
        """
        Invalidate a cache key.

        Args:
            key: Cache key to invalidate.

        Returns:
            True if key was deleted, False otherwise.
        """
        if not self._redis:
            return False

        try:
            deleted = await self._redis.delete(key)
            logger.debug("Cache invalidated", key=key, deleted=deleted)
            return deleted > 0
        except Exception as e:
            logger.error("Cache invalidate error", key=key, error=str(e))
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.

        Args:
            pattern: Redis key pattern (e.g., "product:*").

        Returns:
            Number of keys deleted.
        """
        if not self._redis:
            return 0

        try:
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await self._redis.delete(*keys)
                logger.info(
                    "Cache pattern invalidated",
                    pattern=pattern,
                    deleted=deleted,
                )
                return deleted
            return 0
        except Exception as e:
            logger.error(
                "Cache pattern invalidate error",
                pattern=pattern,
                error=str(e),
            )
            return 0


class ProductCacheService:
    """
    Product-specific cache service.

    Provides high-level caching operations for product entities.
    """

    def __init__(self, cache: RedisCache) -> None:
        """
        Initialize the product cache service.

        Args:
            cache: RedisCache instance.
        """
        self._cache = cache

    def _product_key(self, uuid: str) -> str:
        """Generate cache key for a product."""
        return f"product:fam:{uuid}:full"

    def _category_list_key(self, category_id: int) -> str:
        """Generate cache key for a category product list."""
        return f"product:category:{category_id}:list"

    async def get_product(self, uuid: str) -> Optional[dict]:
        """
        Get a product from cache.

        Args:
            uuid: Product UUID.

        Returns:
            Product data as dict, or None if not cached.
        """
        return await self._cache.get(self._product_key(uuid))

    async def set_product(self, uuid: str, product_data: dict) -> bool:
        """
        Cache a product.

        Args:
            uuid: Product UUID.
            product_data: Product data to cache.

        Returns:
            True if successful.
        """
        return await self._cache.set(self._product_key(uuid), product_data)

    async def invalidate_product(self, uuid: str) -> bool:
        """
        Invalidate a product cache.

        Args:
            uuid: Product UUID.

        Returns:
            True if key was deleted.
        """
        return await self._cache.invalidate(self._product_key(uuid))

    async def invalidate_category(self, category_id: int) -> int:
        """
        Invalidate all cached products in a category.

        Args:
            category_id: Category ID.

        Returns:
            Number of keys deleted.
        """
        return await self._cache.invalidate_pattern(
            f"product:category:{category_id}:*"
        )
