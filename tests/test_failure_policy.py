from __future__ import annotations

import time

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.service import check_limit, settings


class UnavailableRedis:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def eval(self, *_args: object, **_kwargs: object) -> None:
        raise self.error


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [RedisConnectionError("offline"), RedisTimeoutError("timed out")],
)
async def test_redis_errors_fail_open(error: Exception) -> None:
    before = int(time.time())

    allowed, remaining, reset_at = await check_limit(
        redis=UnavailableRedis(error),  # type: ignore[arg-type]
        client_id="unavailable_redis",
    )

    after = int(time.time())
    assert allowed is True
    assert remaining == settings.rate_limit
    assert before + settings.rate_limit_window_seconds <= reset_at
    assert reset_at <= after + settings.rate_limit_window_seconds
