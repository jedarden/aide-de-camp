"""
Pytest fixtures for unit testing FastAPI endpoints.
"""

import asyncio
from typing import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI


@pytest.fixture(scope="function")
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an HTTPX async client for testing FastAPI endpoints.

    This client connects to a running server at localhost:8000.
    For tests that require the server to be running, use this fixture.
    """
    client = httpx.AsyncClient(
        base_url="http://localhost:8000",
        timeout=10.0
    )
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture(scope="function")
async def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
