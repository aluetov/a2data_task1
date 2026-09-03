from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from app.config import get_settings
import logging
import time

settings = get_settings()

logger = logging.getLogger(__name__)


RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])

local counter = redis.call("INCR", key)

if counter == 1 then
    redis.call("EXPIRE", key, window_seconds)
end

local ttl_ms = redis.call("PTTL", key)
local current_time = redis.call("TIME")
local reset_at = tonumber(current_time[1]) + math.ceil(ttl_ms / 1000)

local allowed = 0

if counter <= limit then
    allowed = 1
end

local remaining = math.max(limit - counter, 0)

return {allowed, remaining, reset_at}
"""

async def check_limit(
    redis: Redis,
    client_id: str,
) -> tuple[bool, int, int]:
    key = f"rate_limit:{client_id}"
    limit = settings.rate_limit
    window_seconds = settings.rate_limit_window_seconds

    try:
        result = await redis.eval(
            RATE_LIMIT_SCRIPT,
            1,
            key,
            limit,
            window_seconds,
        )
    except (RedisConnectionError, RedisTimeoutError):
        logger.warning(
            "Redis unavailable; rate limiter is failing open",
            exc_info=True,
        )

        return (
            True,
            limit,
            int(time.time()) + window_seconds,
        )

    allowed, remaining, reset_at = result

    return bool(allowed), remaining, reset_at