from contextlib import asynccontextmanager
from functools import lru_cache
from time import time
import random
from typing import Annotated
from redis.asyncio import Redis
from fastapi import Body, Depends, FastAPI, HTTPException, status, Request


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
        key = f"rate_limiter{endpoint}:{ip_address}"

        current_ms = time()*1000
        window_start = current_ms - window_seconds * 1000

        current_request = f"{time()*1000}-{random.randint(0, 100_000)}"

        async with self._redis.pipeline() as pipe:
            await pipe.zremrangebyscore(name=key, min=0, max=window_start)

            await pipe.zcard(key)

            await pipe.zadd(key, {current_request: current_ms})

            await pipe.expire(key, window_seconds)

            res = await pipe.execute()
        _, current_count, _, _ = res
        return current_count >= max_requests
         

@lru_cache
def get_rate_limiter() -> RateLimiter:
    return RateLimiter(get_redis())

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = get_redis()
    await redis.ping()
    print("Redis is working")
    yield
    await redis.aclose()
    print("Redis connection was cut")

app = FastAPI(lifespan=lifespan)

def rate_limiter_factory(
    endpoint: str,
    max_requests: int,
    window_seconds: int,
):
    async def dependency(
            request: Request,
            rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    ):
        ip_address = request.client.host

        limited = await rate_limiter.is_limited(
            ip_address,
            endpoint,
            max_requests,
            window_seconds,
        )

        if limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Requests limit exeeded. Try a few seconds later"
            )

    return dependency

rate_limiter_sql = rate_limiter_factory(
    endpoint="sql_code",
    max_requests=5,
    window_seconds=3
)

rate_limiter_python = rate_limiter_factory(
    endpoint="python_code",
    max_requests=3,
    window_seconds=5
)

@app.post("/sql_code", dependencies=[Depends(rate_limiter_sql)])
async def send_sql_code(
    code: str = Body(embed=True)
):
    ...
    return {"ok": True}

@app.post("/python_code", dependencies=[Depends(rate_limiter_python)])
async def send_python_code(
    code: str = Body(embed=True)
):
    ...
    return {"ok": True}

