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


# -----------------------------------------------------------------------------
# Global singleton reset fixture
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function", autouse=True)
def reset_global_store_singleton(tmp_path):
    """
    Reset the global SessionStore singleton before each test.

    This fixture ensures that tests calling get_store() directly receive
    a fresh instance instead of sharing state with previous tests.

    The global _store singleton in src.session.store persists across tests,
    which violates test isolation when tests call get_store() instead of using
    the isolated fixtures (test_db_store, in_memory_db_store, etc.).

    This fixture is autouse=True so it runs automatically before every test,
    ensuring complete isolation even when tests bypass the explicit fixtures.

    It also sets ADC_DB_PATH to a unique test-specific database file, ensuring
    that even if tests call get_store(), they get an isolated database instead
    of the production data/session.db or a shared test database.

    Usage in tests:
        # No explicit usage needed - runs automatically
        async def test_something():
            store = get_store()  # Gets fresh instance with isolated database
            # Test with guaranteed fresh store and database
    """
    import os
    import uuid
    from src.session import store as store_module

    # Create a unique test-specific database path for this test
    test_db_path = tmp_path / f"singleton_test_db_{uuid.uuid4().hex}.db"

    # Store original values
    original_store = store_module._store
    original_env = os.environ.get("ADC_DB_PATH")

    # Set the environment variable to point to the test-specific database
    os.environ["ADC_DB_PATH"] = str(test_db_path)

    # Reset the global singleton to None
    store_module._store = None

    yield

    # Cleanup: restore original state
    store_module._store = original_store
    if original_env is not None:
        os.environ["ADC_DB_PATH"] = original_env
    else:
        os.environ.pop("ADC_DB_PATH", None)

    # Clean up test database file if it exists
    try:
        if test_db_path.exists():
            os.unlink(test_db_path)
        # Also clean up WAL files if they exist
        wal_path = str(test_db_path) + "-wal"
        shm_path = str(test_db_path) + "-shm"
        if os.path.exists(wal_path):
            os.unlink(wal_path)
        if os.path.exists(shm_path):
            os.unlink(shm_path)
    except Exception:
        pass  # Ignore cleanup errors


# -----------------------------------------------------------------------------
# SSE event capture fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def mock_sse_broadcaster():
    """
    Provide a mock SSE broadcaster that captures all broadcast events.

    This fixture creates a broadcaster mock that records all events sent via
    broadcast(), enabling tests to verify what events were broadcast without
    managing actual SSE connections.

    Usage in tests:
        async def test_something(mock_sse_broadcaster):
            broadcaster, events = mock_sse_broadcaster

            # Broadcast an event
            await broadcaster.broadcast(SSEEvent(event_type="result_created", data={...}))

            # Verify the event was captured
            assert len(events) == 1
            assert events[0].event_type == "result_created"

    Returns:
        Tuple of (broadcaster_instance, events_list)
    """
    from src.sse.broadcaster import SSEBroadcaster, SSEEvent
    from unittest.mock import AsyncMock, patch

    events = []

    async def mock_broadcast(event: SSEEvent) -> int:
        """Mock broadcast that captures events."""
        events.append(event)
        return 1  # Return fake sent count

    # Create a real broadcaster instance
    broadcaster = SSEBroadcaster()

    # Patch the broadcast method to capture events
    with patch.object(broadcaster, 'broadcast', side_effect=mock_broadcast):
        yield broadcaster, events


@pytest.fixture(scope="function")
async def mock_sse_connection():
    """
    Provide a mock SSE connection that can receive events.

    This fixture creates a connection-like object with a queue that can be
    used to test event delivery without managing real SSE connections.

    Usage in tests:
        async def test_something(mock_sse_connection):
            connection, queue = mock_sse_connection

            # Queue an event
            await queue.put(SSEEvent(event_type="result_created", data={...}))

            # Verify the event was received
            event = await queue.get()
            assert event.event_type == "result_created"

    Returns:
        Tuple of (connection_dict, event_queue)
    """
    import asyncio
    from uuid import uuid4

    queue = asyncio.Queue()
    connection = {
        "connection_id": str(uuid4()),
        "surface_id": str(uuid4()),
        "session_id": str(uuid4()),
        "surface_type": "canvas",
        "queue": queue,
    }

    return connection, queue


# -----------------------------------------------------------------------------
# Test data builder fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def test_topic_builder(in_memory_db_store):
    """
    Provide a helper function to create test topics.

    This fixture provides a convenient builder function for creating test topics
    with default values, reducing boilerplate in tests.

    Usage in tests:
        async def test_something(test_topic_builder):
            # Create a simple topic
            topic_id = await test_topic_builder(label="Test Topic")

            # Create a topic with specific parameters
            topic_id = await test_topic_builder(
                label="Project Topic",
                topic_type="project",
                project_slugs=["my-project"],
                scope="session"
            )

    Returns:
        Async function that creates a topic and returns its ID.
    """
    async def build_topic(
        label: str = "Test Topic",
        topic_type: str = "adhoc",
        project_slugs: list[str] | None = None,
        scope: str = "session",
        session_id: str | None = None,
    ) -> str:
        """Create a test topic with the given parameters."""
        return await in_memory_db_store.create_topic(
            label=label,
            topic_type=topic_type,
            project_slugs=project_slugs,
            scope=scope,
            session_id=session_id,
        )

    return build_topic


@pytest.fixture(scope="function")
async def test_topic_with_session(in_memory_db_store, test_topic_builder):
    """
    Provide a pre-built test topic and session ID.

    This fixture creates both a session and a topic for that session, returning
    both IDs for use in tests.

    Usage in tests:
        async def test_something(test_topic_with_session):
            session_id, topic_id = test_topic_with_session

            # Both are ready to use
            result = await store.create_result(
                intent_id=None,
                topic_id=topic_id,
                session_id=session_id,
                summary="Test result",
                data={"test": "data"}
            )

    Returns:
        Tuple of (session_id, topic_id)
    """
    session_id = await in_memory_db_store.create_session()
    topic_id = await test_topic_builder(
        label="Test Topic",
        session_id=session_id,
    )
    return session_id, topic_id


@pytest.fixture(scope="function")
async def test_utterance_builder(in_memory_db_store):
    """
    Provide a helper function to create test utterances.

    This fixture provides a convenient builder function for creating test utterances
    with default values, reducing boilerplate in tests.

    Usage in tests:
        async def test_something(test_utterance_builder, test_session_id):
            # Create a simple utterance
            utterance_id = await test_utterance_builder(
                session_id=test_session_id,
                raw_text="Test utterance"
            )

    Returns:
        Async function that creates an utterance and returns its ID.
    """
    async def build_utterance(
        session_id: str,
        raw_text: str = "Test utterance",
        utterance_id: str | None = None,
    ) -> str:
        """Create a test utterance with the given parameters."""
        return await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text=raw_text,
            utterance_id=utterance_id,
        )

    return build_utterance


@pytest.fixture(scope="function")
async def test_intent_builder(in_memory_db_store):
    """
    Provide a helper function to create test intents.

    This fixture provides a convenient builder function for creating test intents
    with default values, reducing boilerplate in tests.

    Usage in tests:
        async def test_something(test_intent_builder, test_session_id, test_utterance_id):
            # Create a simple intent
            intent_id = await test_intent_builder(
                utterance_id=test_utterance_id,
                session_id=test_session_id,
                intent_type="status",
                project_slug="my-project"
            )

    Returns:
        Async function that creates an intent and returns its ID.
    """
    async def build_intent(
        utterance_id: str,
        session_id: str,
        intent_type: str = "status",
        project_slug: str | None = None,
        bead_ref: str | None = None,
        lookup_kind: str | None = None,
        topic_id: str | None = None,
    ) -> str:
        """Create a test intent with the given parameters."""
        return await in_memory_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug=project_slug,
            intent_type=intent_type,
            bead_ref=bead_ref,
            lookup_kind=lookup_kind,
            topic_id=topic_id,
        )

    return build_intent


@pytest.fixture(scope="function")
async def test_result_builder(in_memory_db_store):
    """
    Provide a helper function to create test results.

    This fixture provides a convenient builder function for creating test results
    with default values, reducing boilerplate in tests.

    Usage in tests:
        async def test_something(test_result_builder, test_session_id, test_topic_id):
            # Create a simple result
            result_id = await test_result_builder(
                topic_id=test_topic_id,
                session_id=test_session_id,
                summary="Test result",
                data={"test": "data"}
            )

    Returns:
        Async function that creates a result and returns its ID.
    """
    async def build_result(
        topic_id: str,
        session_id: str,
        summary: str = "Test result",
        data: dict | None = None,
        intent_id: str | None = None,
        urgency: str = "normal",
        result_type: str | None = None,
    ) -> str:
        """Create a test result with the given parameters."""
        return await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=summary,
            data=data or {},
            urgency=urgency,
            result_type=result_type,
        )

    return build_result
