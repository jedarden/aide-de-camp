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


# -----------------------------------------------------------------------------
# Test database isolation fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def test_db_path(tmp_path):
    """
    Provide a fresh temporary database file path for testing.

    This fixture creates a unique temporary database file for each test,
    ensuring complete isolation from production data and between tests.

    Usage in tests:
        async def test_something(test_db_path):
            store = SessionStore(test_db_path)
            await store.initialize()
            # Test with isolated database
    """
    import tempfile
    import os

    # Create a unique temporary database file for this test
    db_path = tmp_path / f"test_db_{os.urandom(8).hex()}.db"
    yield db_path

    # Cleanup: delete the temporary database file
    try:
        if db_path.exists():
            os.unlink(db_path)
        # Also clean up WAL files if they exist
        wal_path = str(db_path) + "-wal"
        shm_path = str(db_path) + "-shm"
        if os.path.exists(wal_path):
            os.unlink(wal_path)
        if os.path.exists(shm_path):
            os.unlink(shm_path)
    except Exception:
        pass  # Ignore cleanup errors


@pytest.fixture(scope="function")
async def test_db_store(test_db_path):
    """
    Provide a fresh SessionStore with an isolated database.

    This fixture creates a completely isolated test database using a temporary
    file, ensuring that each test gets a fresh database instance that is
    completely isolated from the production session.db.

    The database is automatically initialized with the full schema including
    all migrations, and is automatically cleaned up after the test completes.

    Usage in tests:
        async def test_something(test_db_store):
            session_id = await test_db_store.create_session()
            # Test with isolated database
            # Database is automatically cleaned up after test

    Benefits:
        - Complete isolation from production data
        - Each test gets a fresh database (no state leakage between tests)
        - Full schema: includes all tables and migrations like production
        - WAL mode enabled for concurrent access like production
        - Automatic cleanup: database file is deleted after test
    """
    from src.session.store import SessionStore

    store = SessionStore(test_db_path)
    await store.initialize()

    yield store

    # Cleanup: close the store and let the test_db_path fixture handle file deletion
    await store.close()


@pytest.fixture(scope="function")
async def test_session_id(test_db_store):
    """
    Create a test session and return its ID.

    This fixture provides a convenient way to get a fresh session ID for testing
    without manually calling create_session().

    Usage in tests:
        async def test_something(test_db_store, test_session_id):
            # test_session_id is a fresh session ID ready to use
            pass
    """
    return await test_db_store.create_session()


@pytest.fixture(scope="function")
async def test_db_connection(test_db_path):
    """
    Provide a direct aiosqlite connection to an isolated database.

    This fixture gives tests direct database access for low-level testing
    without going through the SessionStore API. The database is initialized
    with the full schema.

    Usage in tests:
        async def test_raw_sql(test_db_connection):
            async with test_db_connection.execute("SELECT * FROM sessions") as cur:
                rows = await cur.fetchall()
                # Test with direct SQL access
    """
    import aiosqlite
    from src.session.store import SCHEMA_SQL

    # Create database connection
    db = await aiosqlite.connect(test_db_path)

    # Enable WAL mode for consistency with production
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")

    # Initialize schema
    await db.executescript(SCHEMA_SQL)
    await db.commit()

    yield db

    # Cleanup: close the connection
    await db.close()


@pytest.fixture(scope="function")
async def in_memory_db_store():
    """
    Provide a fresh SessionStore with a completely isolated in-memory database.

    This fixture creates a completely isolated test database using SQLite's
    shared cache in-memory mode, ensuring that each test gets a fresh database
    instance that is completely isolated from the production session.db and
    from other tests.

    The database is automatically initialized with the full schema including
    all migrations, and is automatically destroyed after the test completes.

    Usage in tests:
        async def test_something(in_memory_db_store):
            session_id = await in_memory_db_store.create_session()
            # Test with isolated database
            # Database is automatically destroyed after test

    Benefits:
        - Complete isolation from production data
        - Each test gets a fresh database (no state leakage between tests)
        - Full schema: includes all tables and migrations like production
        - Automatic cleanup: database is destroyed when connection closes
        - Faster I/O: in-memory database has no disk access overhead
        - Guaranteed isolation: in-memory databases cannot accidentally interfere

    Technical Note:
        Uses SQLite's shared cache mode (file:in_memory_db?mode=memory&cache=shared)
        instead of :memory: to ensure all connections within the process access
        the same in-memory database. Each test gets a unique cache name to ensure
        complete isolation between tests.
    """
    import aiosqlite
    import uuid
    from src.session.store import SessionStore, SCHEMA_SQL

    # Use shared cache mode with unique cache name per test for isolation
    # This ensures all connections within this test share the same database
    cache_name = f"in_memory_db_{uuid.uuid4().hex}"
    db_path = f"file:{cache_name}?mode=memory&cache=shared"

    # Initialize in-memory database with full schema
    async with aiosqlite.connect(db_path) as db:
        # Enable WAL mode for concurrent access
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")

        # Create schema with all migrations
        await db.executescript(SCHEMA_SQL)
        await db.commit()

        # Run all migrations to ensure full schema compatibility
        await SessionStore._migrate_additive_columns(db)

    # Create SessionStore with in-memory database
    store = SessionStore(db_path)

    yield store

    # Cleanup: close the store (in-memory database is automatically destroyed)
    await store.close()


@pytest.fixture(scope="function")
async def in_memory_db_session_id(in_memory_db_store):
    """
    Create a test session in the in-memory database and return its ID.

    This fixture provides a convenient way to get a fresh session ID for testing
    with the in-memory database without manually calling create_session().

    Usage in tests:
        async def test_something(in_memory_db_store, in_memory_db_session_id):
            # in_memory_db_session_id is a fresh session ID ready to use
            pass
    """
    return await in_memory_db_store.create_session()


@pytest.fixture(scope="function")
async def in_memory_db_connection():
    """
    Provide a direct aiosqlite connection to an isolated in-memory database.

    This fixture gives tests direct database access for low-level testing
    without going through the SessionStore API. The database is initialized
    with the full schema including all migrations.

    The in-memory database is completely isolated and automatically destroyed
    when the test completes.

    Usage in tests:
        async def test_raw_sql(in_memory_db_connection):
            async with in_memory_db_connection.execute("SELECT * FROM sessions") as cur:
                rows = await cur.fetchall()
                # Test with direct SQL access to in-memory database
    """
    import aiosqlite
    import uuid
    from src.session.store import SessionStore, SCHEMA_SQL

    # Use shared cache mode with unique cache name per test for isolation
    cache_name = f"in_memory_conn_{uuid.uuid4().hex}"
    db_path = f"file:{cache_name}?mode=memory&cache=shared"

    # Create in-memory database connection
    db = await aiosqlite.connect(db_path)

    # Enable WAL mode for consistency with production
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")

    # Initialize schema with all migrations
    await db.executescript(SCHEMA_SQL)
    await SessionStore._migrate_additive_columns(db)
    await db.commit()

    yield db

    # Cleanup: close the connection (in-memory database is automatically destroyed)
    await db.close()
