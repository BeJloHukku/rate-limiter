from functools import lru_cache

from redis.asyncio import Redis


@lru_cache
def get_redis() -> Redis:
    return Redis(host="localhost", port="6379")


class RateLimiter:
    def __init__(self, redis: Redis):
        self._redis = redis

    async def is_limited(
            self,
            ip_address: str,
            endpoint: str,
            max_requests: int,
            window_seconds: int  
) -> bool:
        
