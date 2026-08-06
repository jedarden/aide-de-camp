"""
Comprehensive tests for /test/dispatch storage and SSE broadcast behavior (bead adc-3mc5).

This test suite verifies that results from the test endpoint are correctly:
1. Stored in the session database (matching /dispatch structure)
2. Broadcast via SSE to connected canvas surfaces
3. Broadcast at the correct timing (matching /dispatch)
4. Storage payload matches /dispatch payload

Acceptance criteria:
- Results persist to SQLite session store
- SSE events broadcast to correct surfaces
- Broadcast timing matches /dispatch
- Storage payload matches /dispatch payload
"""

import asyncio
import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import aiosqlite

from src.session.store import SessionStore
from src.sse.broadcaster import SSEBroadcaster, SSEEvent, get_broadcaster
from src.test.dispatch import (
    dispatch_test_utterance,
    generate_synthetic_result,
    TestDispatchRequest,
    SyntheticResultRequest,
)
from src.intent.router import get_router


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
async def isolated_store(tmp_path):
    """Isolated session store for each test."""
    db_path = tmp_path / "test-storage-sse.db"
    store = SessionStore(db_path)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
async def started_broadcaster():
    """Start SSE broadcaster for each test."""
    b = SSEBroadcaster()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def mock_surface_connection():
    """Mock SSE connection for testing."""
    conn = MagicMock()
    conn.connection_id = "test-conn-1"
    conn.surface_id = "test-surface-1"
    conn.session_id = "test-session-1"
    conn.surface_type = "canvas"
    conn.queue = asyncio.Queue()
    return conn


# --- Storage tests ------------------------------------------------------------


class TestDispatchStorage:
    """Verify results are correctly stored in the session database."""

    @pytest.mark.asyncio
    async def test_synthetic_result_creates_database_records(self, isolated_store):
        """Synthetic result creates utterance, intent, topic, and result records."""
        # Generate synthetic result
        request = SyntheticResultRequest(
            session_id="test-session-1",
            surface_id="test-surface-1",
            test_data={
                "utterance": "test utterance for storage verification",
                "intent_type": "status",
                "topic_label": "Test Topic",
                "summary": "Test summary",
                "data": {"test_key": "test_value"},
            },
        )

        # Patch store to use isolated store
        import src.session.store as store_mod
        original_get_store = store_mod.get_store
        store_mod.get_store = lambda: isolated_store
        # Also patch the module's _store global
        store_mod._store = isolated_store

        try:
            response = await generate_synthetic_result(request)

            # Verify result was created
            assert response.result_id is not None
            assert response.intent_id is not None
            assert response.topic_id is not None
            assert response.utterance_id is not None

            # Verify records in database using direct SQL queries
            # 1. Check utterance record
            import aiosqlite
            async with aiosqlite.connect(isolated_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM utterances WHERE session_id = ?",
                    (response.session_id,)
                ) as cursor:
                    utterances = await cursor.fetchall()
                    assert len(utterances) >= 1
                    assert any(u["id"] == response.utterance_id for u in utterances)

            # 2. Check intent record
            async with aiosqlite.connect(isolated_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM intents WHERE utterance_id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    intents = await cursor.fetchall()
                    assert len(intents) >= 1
                    assert any(i["id"] == response.intent_id for i in intents)

            # 3. Check topic record
            topic = await isolated_store.get_topic(response.topic_id)
            assert topic is not None
            assert topic["label"] == "Test Topic"

            # 4. Check result record using direct SQL
            async with aiosqlite.connect(isolated_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM results WHERE intent_id = ?",
                    (response.intent_id,)
                ) as cursor:
                    results = await cursor.fetchall()
                    assert len(results) >= 1
                    result = next((r for r in results if r["id"] == response.result_id), None)
                    assert result is not None
                    assert result["summary"] == "Test summary"

                    # Verify data payload matches
                    result_data = json.loads(result["data"])
                    assert result_data["test_key"] == "test_value"

        finally:
            store_mod.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_storage_payload_matches_dispatch_structure(self, isolated_store):
        """Storage payload structure matches /dispatch payload."""
        request = SyntheticResultRequest(
            session_id="test-session-2",
            surface_id="test-surface-2",
            test_data={
                "summary": "Test payload structure",
                "data": {"field1": "value1", "field2": ["array", "values"]},
                "urgency": "high",
                "result_type": "status",
            },
        )

        # Patch store
        import src.session.store as store_mod
        original_get_store = store_mod.get_store
        store_mod.get_store = lambda: isolated_store
        store_mod._store = isolated_store

        try:
            response = await generate_synthetic_result(request)

            # Verify result structure matches /dispatch output using direct SQL
            async with aiosqlite.connect(isolated_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM results WHERE intent_id = ?",
                    (response.intent_id,)
                ) as cursor:
                    results = await cursor.fetchall()
                    assert len(results) >= 1
                    result = dict(results[0])

                    # Check required fields match /dispatch structure
                    assert result["summary"] == response.summary
                    assert result["urgency"] == response.urgency

                    # Check data structure is preserved
                    result_data = json.loads(result["data"])
                    assert result_data["field1"] == "value1"
                    assert result_data["field2"] == ["array", "values"]

        finally:
            store_mod.get_store = original_get_store


# --- SSE broadcast tests -----------------------------------------------------


class TestSSEBroadcast:
    """Verify SSE events are broadcast correctly to connected surfaces."""

    @pytest.mark.asyncio
    async def test_synthetic_result_broadcasts_sse_event(self, isolated_store, started_broadcaster):
        """Synthetic result broadcasts result_created SSE event."""
        # Register a test connection
        conn = started_broadcaster.register(
            surface_id="test-surface-1",
            session_id="test-session-1",
            surface_type="canvas",
        )

        # Patch store and broadcaster
        import src.session.store as store_mod
        import src.sse.broadcaster as bcast_mod
        original_get_store = store_mod.get_store
        original_get_broadcaster = bcast_mod.get_broadcaster
        store_mod.get_store = lambda: isolated_store
        bcast_mod.get_broadcaster = lambda: started_broadcaster

        try:
            request = SyntheticResultRequest(
                session_id="test-session-1",
                surface_id="test-surface-1",
                test_data={"summary": "SSE test", "data": {"sse": "test"}},
            )

            await generate_synthetic_result(request)

            # Verify SSE event was queued (with timeout)
            try:
                event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
                assert isinstance(event, SSEEvent)
                assert event.event_type == "result_created"
                assert event.target_surface_id == "test-surface-1"
                assert event.data["summary"] == "SSE test"
            except asyncio.TimeoutError:
                pytest.fail("SSE event was not broadcast within timeout")

        finally:
            started_broadcaster.unregister(conn.connection_id)
            store_mod.get_store = original_get_store
            bcast_mod.get_broadcaster = original_get_broadcaster

    @pytest.mark.asyncio
    async def test_sse_event_targets_correct_surface(self, isolated_store, started_broadcaster):
        """SSE event is only sent to the targeted surface_id."""
        # Register two connections for different surfaces
        conn1 = started_broadcaster.register(
            surface_id="surface-1",
            session_id="test-session-1",
            surface_type="canvas",
        )
        conn2 = started_broadcaster.register(
            surface_id="surface-2",
            session_id="test-session-1",
            surface_type="canvas",
        )

        # Patch store and broadcaster
        import src.session.store as store_mod
        import src.sse.broadcaster as bcast_mod
        original_get_store = store_mod.get_store
        original_get_broadcaster = bcast_mod.get_broadcaster
        store_mod.get_store = lambda: isolated_store
        bcast_mod.get_broadcaster = lambda: started_broadcaster

        try:
            # Generate result targeting only surface-1
            request = SyntheticResultRequest(
                session_id="test-session-1",
                surface_id="surface-1",
                test_data={"summary": "Targeted test"},
            )

            await generate_synthetic_result(request)

            # Verify surface-1 received the event
            try:
                event1 = await asyncio.wait_for(conn1.queue.get(), timeout=1.0)
                assert event1.event_type == "result_created"
            except asyncio.TimeoutError:
                pytest.fail("surface-1 did not receive SSE event")

            # Verify surface-2 did NOT receive the event (queue should be empty)
            try:
                event2 = await asyncio.wait_for(conn2.queue.get(), timeout=0.2)
                pytest.fail(f"surface-2 unexpectedly received event: {event2}")
            except asyncio.TimeoutError:
                # Expected - surface-2 should not receive the event
                pass

        finally:
            started_broadcaster.unregister(conn1.connection_id)
            started_broadcaster.unregister(conn2.connection_id)
            store_mod.get_store = original_get_store
            bcast_mod.get_broadcaster = original_get_broadcaster


# --- Broadcast timing tests ---------------------------------------------------


class TestBroadcastTiming:
    """Verify SSE broadcast timing matches /dispatch behavior."""

    @pytest.mark.asyncio
    async def test_broadcast_occurs_after_storage(self, isolated_store, started_broadcaster):
        """SSE broadcast occurs after result is stored in database."""
        conn = started_broadcaster.register(
            surface_id="test-surface-1",
            session_id="test-session-1",
            surface_type="canvas",
        )

        # Patch store and broadcaster
        import src.session.store as store_mod
        import src.sse.broadcaster as bcast_mod
        original_get_store = store_mod.get_store
        original_get_broadcaster = bcast_mod.get_broadcaster
        store_mod.get_store = lambda: isolated_store
        bcast_mod.get_broadcaster = lambda: started_broadcaster

        try:
            storage_order = []

            # Wrap create_result to track when storage happens
            original_create_result = isolated_store.create_result
            async def tracked_create_result(*args, **kwargs):
                storage_order.append("storage")
                return await original_create_result(*args, **kwargs)

            # Wrap broadcast to track when SSE happens
            original_broadcast = started_broadcaster.broadcast
            async def tracked_broadcast(event: SSEEvent):
                storage_order.append("sse_broadcast")
                return await original_broadcast(event)

            isolated_store.create_result = tracked_create_result
            started_broadcaster.broadcast = tracked_broadcast

            request = SyntheticResultRequest(
                session_id="test-session-1",
                surface_id="test-surface-1",
                test_data={"summary": "Timing test"},
            )

            await generate_synthetic_result(request)

            # Verify storage happened before SSE broadcast
            assert storage_order == ["storage", "sse_broadcast"], \
                f"Storage and SSE order incorrect: {storage_order}"

        finally:
            started_broadcaster.unregister(conn.connection_id)
            isolated_store.create_result = original_create_result
            started_broadcaster.broadcast = original_broadcast
            store_mod.get_store = original_get_store
            bcast_mod.get_broadcaster = original_get_broadcaster

    @pytest.mark.asyncio
    async def test_sse_includes_all_result_fields(self, isolated_store, started_broadcaster):
        """SSE event payload includes all necessary fields for canvas rendering."""
        conn = started_broadcaster.register(
            surface_id="test-surface-1",
            session_id="test-session-1",
            surface_type="canvas",
        )

        # Patch store and broadcaster
        import src.session.store as store_mod
        import src.sse.broadcaster as bcast_mod
        original_get_store = store_mod.get_store
        original_get_broadcaster = bcast_mod.get_broadcaster
        store_mod.get_store = lambda: isolated_store
        bcast_mod.get_broadcaster = lambda: started_broadcaster

        try:
            request = SyntheticResultRequest(
                session_id="test-session-1",
                surface_id="test-surface-1",
                test_data={
                    "summary": "Complete fields test",
                    "data": {"test": "data"},
                    "urgency": "high",
                },
            )

            await generate_synthetic_result(request)

            # Get SSE event
            event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)

            # Verify event has all required fields for canvas
            assert "intent_id" in event.data
            assert "topic_id" in event.data
            assert "summary" in event.data
            assert "urgency" in event.data

            # Verify values match the request
            assert event.data["summary"] == "Complete fields test"
            assert event.data["urgency"] == "high"

        finally:
            started_broadcaster.unregister(conn.connection_id)
            store_mod.get_store = original_get_store
            bcast_mod.get_broadcaster = original_get_broadcaster


# --- Integration test ---------------------------------------------------------


class TestDispatchIntegration:
    """Integration tests for complete /test/dispatch flow."""

    @pytest.mark.asyncio
    async def test_complete_flow_storage_then_sse(self, isolated_store, started_broadcaster):
        """Complete flow: result stored then SSE broadcast with matching payload."""
        conn = started_broadcaster.register(
            surface_id="test-surface-1",
            session_id="test-session-1",
            surface_type="canvas",
        )

        # Patch store and broadcaster
        import src.session.store as store_mod
        import src.sse.broadcaster as bcast_mod
        original_get_store = store_mod.get_store
        original_get_broadcaster = bcast_mod.get_broadcaster
        store_mod.get_store = lambda: isolated_store
        bcast_mod.get_broadcaster = lambda: started_broadcaster

        try:
            request = SyntheticResultRequest(
                session_id="test-session-1",
                surface_id="test-surface-1",
                test_data={
                    "utterance": "integration test utterance",
                    "summary": "Integration test summary",
                    "data": {"integration": "test", "value": 42},
                    "urgency": "normal",
                },
            )

            response = await generate_synthetic_result(request)

            # 1. Verify storage using direct SQL
            async with aiosqlite.connect(isolated_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM results WHERE intent_id = ?",
                    (response.intent_id,)
                ) as cursor:
                    results = await cursor.fetchall()
                    assert len(results) >= 1
                    stored_result = dict(results[0])

            # 2. Verify SSE event
            event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)

            # 3. Verify SSE payload matches stored payload
            assert stored_result["summary"] == event.data["summary"]
            assert stored_result["urgency"] == event.data["urgency"]
            assert event.data["intent_id"] == response.intent_id
            assert event.data["topic_id"] == response.topic_id

            # 4. Verify result is linked to topic
            topic = await isolated_store.get_topic(response.topic_id)
            assert topic is not None

            # 5. Verify utterance is linked to intent using direct SQL
            async with aiosqlite.connect(isolated_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM intents WHERE utterance_id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    intents = await cursor.fetchall()
                    assert any(i["id"] == response.intent_id for i in intents)

        finally:
            started_broadcaster.unregister(conn.connection_id)
            store_mod.get_store = original_get_store
            bcast_mod.get_broadcaster = original_get_broadcaster
