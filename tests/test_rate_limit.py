from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import pytest


def assert_check_response(response: httpx.Response) -> dict[str, Any]:
    assert response.status_code == httpx.codes.OK, response.text

    payload = response.json()
    assert set(payload) == {"allowed", "remaining", "reset_at"}
    assert type(payload["allowed"]) is bool
    assert type(payload["remaining"]) is int
    assert type(payload["reset_at"]) is int

    return payload


async def post_concurrently(
    client: httpx.AsyncClient,
    client_id: str,
    count: int,
) -> list[httpx.Response]:
    barrier = asyncio.Barrier(count + 1)

    async def send_request() -> httpx.Response:
        await barrier.wait()
        return await client.post("/check", json={"client_id": client_id})

    tasks = [asyncio.create_task(send_request()) for _ in range(count)]
    await barrier.wait()

    return await asyncio.gather(*tasks)


@pytest.mark.anyio
@pytest.mark.integration
async def test_500_parallel_requests_allow_exactly_100(
    api_client: httpx.AsyncClient,
    client_id: str,
    rate_limit: int,
) -> None:
    responses = await post_concurrently(api_client, client_id, count=500)
    payloads = [assert_check_response(response) for response in responses]

    allowed = sum(payload["allowed"] is True for payload in payloads)
    denied = sum(payload["allowed"] is False for payload in payloads)

    assert allowed == rate_limit
    assert denied == 500 - rate_limit
    assert all(payload["remaining"] >= 0 for payload in payloads)


@pytest.mark.anyio
@pytest.mark.integration
async def test_clients_do_not_share_counters(
    api_client: httpx.AsyncClient,
    rate_limit: int,
) -> None:
    first_client = f"client_a_{time.time_ns()}"
    second_client = f"client_b_{time.time_ns()}"

    first_response, second_response = await asyncio.gather(
        api_client.post("/check", json={"client_id": first_client}),
        api_client.post("/check", json={"client_id": second_client}),
    )
    first_payload = assert_check_response(first_response)
    second_payload = assert_check_response(second_response)

    assert first_payload["allowed"] is True
    assert second_payload["allowed"] is True
    assert first_payload["remaining"] == rate_limit - 1
    assert second_payload["remaining"] == rate_limit - 1

    first_client_responses = await post_concurrently(
        api_client,
        first_client,
        count=rate_limit,
    )
    first_client_payloads = [
        assert_check_response(response) for response in first_client_responses
    ]

    assert sum(payload["allowed"] is True for payload in first_client_payloads) == (
        rate_limit - 1
    )
    assert sum(payload["allowed"] is False for payload in first_client_payloads) == 1

    second_client_response = await api_client.post(
        "/check",
        json={"client_id": second_client},
    )
    second_client_payload = assert_check_response(second_client_response)

    assert second_client_payload["allowed"] is True
    assert second_client_payload["remaining"] == rate_limit - 2


@pytest.mark.anyio
@pytest.mark.integration
@pytest.mark.slow
async def test_limit_resets_after_window(
    api_client: httpx.AsyncClient,
    client_id: str,
    rate_limit: int,
    window_seconds: int,
) -> None:
    first_response = await api_client.post(
        "/check",
        json={"client_id": client_id},
    )
    first_payload = assert_check_response(first_response)

    wait_seconds = first_payload["reset_at"] - time.time() + 0.25
    assert 0 < wait_seconds <= window_seconds + 1.5
    await asyncio.sleep(wait_seconds)

    next_window_response = await api_client.post(
        "/check",
        json={"client_id": client_id},
    )
    next_window_payload = assert_check_response(next_window_response)

    assert next_window_payload["allowed"] is True
    assert next_window_payload["remaining"] == rate_limit - 1
    assert next_window_payload["reset_at"] > first_payload["reset_at"]
