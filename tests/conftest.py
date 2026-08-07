"""
Pytest fixtures for unit testing FastAPI endpoints.
"""

import asyncio
import os
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

# Import hot-reload test infrastructure
from tests.helpers.hot_reload_test_infrastructure import (
    HotReloadTestBase,
    EdgeCaseScenario,
    MockFileSystem,
    create_test_registry,
    create_test_prompt_file,
    create_test_config_file,
    ConcurrentAccessTracker,
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


# -----------------------------------------------------------------------------
# Hot-reload test infrastructure fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function")
def hot_reload_test_base():
    """
    Provide a HotReloadTestBase instance for edge case testing.

    This fixture gives tests a pre-configured test base with automatic
    setup/teardown for temporary files and permissions.

    Usage in tests:
        def test_permission_error(hot_reload_test_base):
            with hot_reload_test_base.temp_file_context() as temp_file:
                hot_reload_test_base.reload_mgr.register_prompt('test', str(temp_file))
                hot_reload_test_base.set_readonly(temp_file)
                # Test permission error handling
    """
    test_base = HotReloadTestBase()
    test_base.setup_method()
    yield test_base
    test_base.teardown_method()


@pytest.fixture(scope="function")
def mock_file_system():
    """
    Provide a MockFileSystem for testing file operations without actual I/O.

    This fixture allows tests to simulate file system errors and conditions
    without creating real files or modifying the file system.

    Usage in tests:
        def test_with_mock_fs(mock_file_system):
            mock_fs.add_file('/test/file.md', 'content')
            mock_fs.set_permission_error('/test/file.md')
            # Test behavior with mocked file system
    """
    return MockFileSystem()


@pytest.fixture(scope="function")
def concurrent_access_tracker():
    """
    Provide a ConcurrentAccessTracker for testing concurrent access patterns.

    This fixture helps identify race conditions and concurrency issues by
    tracking all access attempts with timing and success/failure status.

    Usage in tests:
        def test_concurrent_access(concurrent_access_tracker):
            with concurrent_access_tracker.track_access('read', 'router'):
                content = reload_mgr.get_prompt('router')
            stats = concurrent_access_tracker.get_statistics()
    """
    return ConcurrentAccessTracker()


@pytest.fixture(scope="function")
def test_prompt_file():
    """
    Create a temporary test prompt file that is automatically cleaned up.

    This fixture creates a test prompt file with default content and
    ensures it's cleaned up after the test.

    Usage in tests:
        def test_with_prompt(test_prompt_file):
            reload_mgr.register_prompt('test', str(test_prompt_file))
            content = reload_mgr.get_prompt('test')
            # File is automatically cleaned up
    """
    temp_path = create_test_prompt_file('test')
    yield temp_path
    # Cleanup
    try:
        if temp_path.exists():
            os.chmod(temp_path, 0o644)
            temp_path.unlink()
    except Exception:
        pass


@pytest.fixture(scope="function")
def test_config_file():
    """
    Create a temporary test config file that is automatically cleaned up.

    This fixture creates a test YAML config file with default content and
    ensures it's cleaned up after the test.

    Usage in tests:
        def test_with_config(test_config_file):
            reload_mgr.register_config('test', str(test_config_file))
            config = reload_mgr.get_config('test')
            # File is automatically cleaned up
    """
    temp_path = create_test_config_file('test')
    yield temp_path
    # Cleanup
    try:
        if temp_path.exists():
            os.chmod(temp_path, 0o644)
            temp_path.unlink()
    except Exception:
        pass


@pytest.fixture(scope="function")
def test_registry_file():
    """
    Create a temporary test registry file that is automatically cleaned up.

    This fixture creates a test registry.yaml file with default content and
    ensures it's cleaned up after the test.

    Usage in tests:
        def test_with_registry(test_registry_file):
            reload_mgr.register_config('registry', str(test_registry_file))
            registry = reload_mgr.get_config('registry')
            # File is automatically cleaned up
    """
    temp_path = create_test_registry()
    yield temp_path
    # Cleanup
    try:
        if temp_path.exists():
            os.chmod(temp_path, 0o644)
            temp_path.unlink()
    except Exception:
        pass


@pytest.fixture(scope="function")
def permission_error_scenario():
    """
    Provide an EdgeCaseScenario for testing permission errors.

    This fixture gives tests a pre-configured scenario that simulates
    file permission errors.

    Usage in tests:
        def test_permission_error(permission_error_scenario):
            with permission_error_scenario.apply(reload_mgr):
                # Test behavior when file has permission errors
                pass
    """
    return EdgeCaseScenario.permission_error()


@pytest.fixture(scope="function")
def missing_file_scenario():
    """
    Provide an EdgeCaseScenario for testing missing file errors.

    This fixture gives tests a pre-configured scenario that simulates
    a missing file.

    Usage in tests:
        def test_missing_file(missing_file_scenario):
            with missing_file_scenario.apply(reload_mgr):
                # Test behavior when file doesn't exist
                pass
    """
    return EdgeCaseScenario.missing_file()


@pytest.fixture(scope="function")
def malformed_yaml_scenario():
    """
    Provide an EdgeCaseScenario for testing malformed YAML errors.

    This fixture gives tests a pre-configured scenario that simulates
    malformed YAML content.

    Usage in tests:
        def test_malformed_yaml(malformed_yaml_scenario):
            with malformed_yaml_scenario.apply(reload_mgr):
                # Test behavior when YAML is malformed
                pass
    """
    return EdgeCaseScenario.malformed_yaml()


@pytest.fixture(scope="function")
def empty_file_scenario():
    """
    Provide an EdgeCaseScenario for testing empty file handling.

    This fixture gives tests a pre-configured scenario that simulates
    an empty file.

    Usage in tests:
        def test_empty_file(empty_file_scenario):
            with empty_file_scenario.apply(reload_mgr):
                # Test behavior when file is empty
                pass
    """
    return EdgeCaseScenario.empty_file()
