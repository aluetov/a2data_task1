from fastapi import Request
from redis.asyncio import Redis

from app.config import Settings


def create_redis(settings: Settings) -> Redis:
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )


def get_redis(request: Request) -> Redis:
    return request.app.state.redis
