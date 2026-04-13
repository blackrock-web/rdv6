"""
ROADAI Redis Client Config
==========================
Synchronous and Asynchronous Redis integration for Caching and PubSub.
"""

import os
import json
from typing import Optional, Any, cast
from backend.utils.logger import get_logger

logger = get_logger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class RedisCache:
    def __init__(self):
        self._redis: Any = None
        self._async_redis: Any = None
        self.enabled = False

    def get_client(self) -> Any:
        if self._redis is None:
            try:
                import redis
                client = redis.from_url(REDIS_URL, decode_responses=True)
                if client:
                    client.ping()
                    self._redis = client
                    self.enabled = True
                    logger.info(f"✅ Redis Connected (Sync): {REDIS_URL}")
            except Exception as e:
                logger.warning(f"⚠️ Redis connection failed: {e}. Caching disabled.")
                self.enabled = False
        return self._redis

    async def get_async_client(self) -> Any:
        if self._async_redis is None:
            try:
                import redis.asyncio as aioredis
                client = aioredis.from_url(REDIS_URL, decode_responses=True)
                if client:
                    await client.ping()
                    self._async_redis = client
                    self.enabled = True
                    logger.info(f"✅ Redis Connected (Async): {REDIS_URL}")
            except Exception as e:
                logger.warning(f"⚠️ Async Redis connection failed: {e}.")
                self.enabled = False
        return self._async_redis

    async def get(self, key: str) -> Optional[Any]:
        if not self.enabled: return None
        try:
            r = await self.get_async_client()
            if r is None: return None
            # Cast r to Any to satisfy Pyre's inference of it being a Coroutine
            val = await cast(Any, r).get(key)
            return json.loads(val) if val else None
        except Exception:
            return None

    async def set(self, key: str, value: Any, ex: int = 300):
        if not self.enabled: return
        try:
            r = await self.get_async_client()
            if r is not None:
                await cast(Any, r).set(key, json.dumps(value), ex=ex)
        except Exception:
            pass

redis_cache = RedisCache()
