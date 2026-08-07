"""
Pytest fixtures for unit testing FastAPI endpoints.
"""

import asyncio
from pathlib import Path
from typing import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEConnection,
)

# Import registry test helpers
from tests.helpers.registry_test_helpers import (
    backup_registry,
    cleanup_backup,
    restore_registry,
    RegistryModificationContext,
)


# -----------------------------------------------------------------------------
# Registry hot-reload fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function")
def registry_backup_path() -> Path:
    """
    Create a backup of config/registry.yaml before a test.

    This fixture automatically backs up the registry before each test
    and restores it after the test completes, even if the test fails.

    Usage in tests:
        def test_something(registry_backup_path):
            # Modify registry.yaml
            # Registry is automatically restored after test
            pass
    """
    backup_path = backup_registry()
    yield backup_path
    # Teardown: restore and cleanup
    try:
        restore_registry(backup_path)
    finally:
        cleanup_backup(backup_path)


@pytest.fixture(scope="function")
def registry_context():
    """
    Provide a RegistryModificationContext for safe registry modification.

    This fixture gives tests a context manager for safe registry modifications
    with automatic restoration.

    Usage in tests:
        def test_something(registry_context):
            with registry_context as ctx:
                ctx.add_alias("pbx-web", "test-alias")
                # Registry is automatically restored on exit
    """
    with RegistryModificationContext(auto_cleanup=False) as ctx:
        yield ctx


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


# -----------------------------------------------------------------------------
# SSE Broadcaster fixtures (from test_sse_broadcaster.py)
# -----------------------------------------------------------------------------


@pytest.fixture
async def broadcaster():
    """
    Provide a fresh SSE broadcaster instance for each test.

    This fixture creates an isolated broadcaster that doesn't interact
    with the global singleton, ensuring test independence.
    """
    b = SSEBroadcaster()
    yield b
    # Cleanup: stop the broadcaster if it was started
    if b._running:
        await b.stop()


@pytest.fixture
async def started_broadcaster(broadcaster):
    """
    Provide a started broadcaster instance.

    This fixture ensures the broadcaster's cleanup loop is running,
    which is necessary for timeout and keepalive tests.
    """
    await broadcaster.start()
    yield broadcaster
    await broadcaster.stop()


@pytest.fixture
def sample_session(broadcaster):
    """
    Create and register a sample test session.

    Returns a tuple of (session_id, surface_id, connection) for use in tests.
    """
    session_id = str(uuid4())
    surface_id = str(uuid4())
    connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )
    return session_id, surface_id, connection
