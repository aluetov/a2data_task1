from __future__ import annotations

import os

import httpx
import pytest


@pytest.mark.anyio
@pytest.mark.integration
@pytest.mark.redis_outage
async def test_expected_redis_state(
    api_client: httpx.AsyncClient,
    client_id: str,
    rate_limit: int,
) -> None:
    expected_state = os.getenv("EXPECTED_REDIS_STATE")
    if expected_state not in {"unavailable", "available"}:
        pytest.skip("The integration test runner controls Redis state")

    response = await api_client.post(
        "/check",
        json={"client_id": client_id},
    )

    assert response.status_code == httpx.codes.OK, response.text
    payload = response.json()
    assert payload["allowed"] is True

    if expected_state == "unavailable":
        assert payload["remaining"] == rate_limit
    else:
        assert payload["remaining"] == rate_limit - 1
