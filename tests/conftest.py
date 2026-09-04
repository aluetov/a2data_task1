from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("rate limiter")
    group.addoption(
        "--base-url",
        default=os.getenv("TEST_BASE_URL", "http://localhost"),
        help="Public URL of the running rate-limiter service",
    )
    group.addoption(
        "--rate-limit",
        type=int,
        default=int(os.getenv("TEST_RATE_LIMIT", "100")),
        help="Configured number of requests allowed per window",
    )
    group.addoption(
        "--window-seconds",
        type=int,
        default=int(os.getenv("TEST_WINDOW_SECONDS", "60")),
        help="Configured rate-limit window in seconds",
    )


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def base_url(pytestconfig: pytest.Config) -> str:
    return str(pytestconfig.getoption("--base-url")).rstrip("/")


@pytest.fixture(scope="session")
def rate_limit(pytestconfig: pytest.Config) -> int:
    return int(pytestconfig.getoption("--rate-limit"))


@pytest.fixture(scope="session")
def window_seconds(pytestconfig: pytest.Config) -> int:
    return int(pytestconfig.getoption("--window-seconds"))


@pytest.fixture
def client_id() -> str:
    return f"test_{uuid4().hex}"


@pytest.fixture
async def api_client(base_url: str) -> AsyncIterator[httpx.AsyncClient]:
    limits = httpx.Limits(
        max_connections=500,
        max_keepalive_connections=100,
    )
    timeout = httpx.Timeout(30.0, connect=5.0)

    async with httpx.AsyncClient(
        base_url=base_url,
        limits=limits,
        timeout=timeout,
    ) as client:
        for _ in range(60):
            try:
                response = await client.get("/health")
                if response.status_code == httpx.codes.OK:
                    break
            except httpx.HTTPError:
                pass

            await asyncio.sleep(0.25)
        else:
            pytest.fail(f"Service did not become healthy at {base_url}")

        yield client
