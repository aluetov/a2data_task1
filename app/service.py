from redis.asyncio import Redis
from app.config import get_settings

settings = get_settings()


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

    result = await redis.eval(
        RATE_LIMIT_SCRIPT,
        1,
        key,
        settings.rate_limit,
        settings.rate_limit_window_seconds,
    )

    allowed, remaining, reset_at = result

    return bool(allowed), remaining, reset_at