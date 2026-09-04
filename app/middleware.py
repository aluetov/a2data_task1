import time

from fastapi import Request, status
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.service import check_limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.url.path != "/demo":
            return await call_next(request)

        client_id = request.headers.get("X-Client-ID")

        if client_id is None:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "X-Client-ID header is required"},
            )

        redis: Redis = request.app.state.redis

        allowed, remaining, reset_at = await check_limit(
            redis=redis,
            client_id=client_id,
        )

        limit = request.app.state.settings.rate_limit
        rate_limit_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }

        if not allowed:
            retry_after = max(reset_at - int(time.time()), 0)

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded"},
                headers={
                    **rate_limit_headers,
                    "Retry-After": str(retry_after),
                },
            )

        response = await call_next(request)
        response.headers.update(rate_limit_headers)

        return response
