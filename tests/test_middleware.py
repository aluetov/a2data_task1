from __future__ import annotations

import httpx
import pytest


REQUIRED_RATE_LIMIT_HEADERS = {
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
    "Retry-After",
}


@pytest.mark.anyio
@pytest.mark.integration
async def test_demo_requires_client_id_header(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/demo")

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {"detail": "X-Client-ID header is required"}


@pytest.mark.anyio
@pytest.mark.integration
async def test_demo_returns_429_and_rate_limit_headers(
    api_client: httpx.AsyncClient,
    client_id: str,
    rate_limit: int,
) -> None:
    headers = {"X-Client-ID": client_id}

    for expected_remaining in range(rate_limit - 1, -1, -1):
        response = await api_client.get("/demo", headers=headers)

        assert response.status_code == httpx.codes.OK, response.text
        assert int(response.headers["X-RateLimit-Limit"]) == rate_limit
        assert int(response.headers["X-RateLimit-Remaining"]) == expected_remaining
        assert int(response.headers["X-RateLimit-Reset"]) > 0

    rejected_response = await api_client.get("/demo", headers=headers)

    assert rejected_response.status_code == httpx.codes.TOO_MANY_REQUESTS
    assert rejected_response.json() == {"detail": "Rate limit exceeded"}
    assert all(
        header in rejected_response.headers for header in REQUIRED_RATE_LIMIT_HEADERS
    )
    assert int(rejected_response.headers["X-RateLimit-Limit"]) == rate_limit
    assert int(rejected_response.headers["X-RateLimit-Remaining"]) == 0
    assert int(rejected_response.headers["X-RateLimit-Reset"]) > 0
    assert int(rejected_response.headers["Retry-After"]) >= 0
