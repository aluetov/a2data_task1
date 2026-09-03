from typing import Annotated
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from app.config import get_settings
from app.redis import create_redis, get_redis
from app.schema import RateLimitRequest, RateLimitResponse
from redis.asyncio import Redis
from app.service import check_limit
from app.middleware import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    app.state.settings = settings
    app.state.redis = create_redis(settings)

    try:
        yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)


@app.get("/")
async def read_root():
    return {"message": "Hello, World!"}


@app.post("/check", response_model=RateLimitResponse)
async def check_rate_limit(
    data: RateLimitRequest,
    redis: Annotated[Redis, Depends(get_redis)],
) -> RateLimitResponse:
    allowed, remaining, reset_at = await check_limit(
        redis=redis,
        client_id=data.client_id,
    )

    return RateLimitResponse(
        allowed=allowed,
        remaining=remaining,
        reset_at=reset_at,
    )


@app.get("/demo")
async def demo_endpoint() -> dict[str, str]:
    return {"message": "Request allowed"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}