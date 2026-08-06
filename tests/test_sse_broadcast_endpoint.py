"""
Test SSE broadcast functionality from /api/v1/test/sse-broadcast endpoint (bead adc-3pbim).

Verifies that the test endpoint broadcasts SSE events correctly:
- SSE event with event_type="result_created" is broadcast
- Event includes surface_id targeting when provided
- Uses existing get_broadcaster() and SSEEvent
- Broadcast timing matches /dispatch pattern
"""
import asyncio
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from src.sse.broadcaster import SSEEvent, get_broadcaster
from src.session.store import SessionStore, get_store
from src.main import app


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
async def isolated_store(tmp_path: Path, monkeypatch) -> SessionStore:
    """Isolated session store for each test (never touches data/session.db)."""
    tmp_db = tmp_path / "test-sse-broadcast-endpoint.db"
    monkeypatch.setenv("ADC_DB_PATH", str(tmp_db))

    import src.session.store as store_mod
    import src.main as main_mod

    saved_store = store_mod._store
    saved_main_store = main_mod._store

    store_mod._store = None
    main_mod._store = None

    store = store_mod.get_store()
    await store.initialize()

    yield store

    main_mod._store = saved_main_store
    store_mod._store = saved_store


async def _started_broadcaster():
    """Start the process-wide SSE broadcaster singleton if not already running."""
    b = get_broadcaster()
    if not getattr(b, "_running", False):
        await b.start()
    return b


async def _collect_sse_events(broadcaster, conn, wanted_types, *, timeout=2.0):
    """Collect SSE events until all wanted types arrive (excluding 'connected')."""
    wanted = set(wanted_types)
    collected = []

    async def drain():
        async for wire in broadcaster.event_generator(conn):
            # Parse SSE wire format
            lines = wire.strip().split("\n")
            current_event_type = None
            current_data = None

            for line in lines:
                if line.startswith("event: "):
                    current_event_type = line[7:].strip()
                elif line.startswith("data: "):
                    import json
                    current_data = json.loads(line[6:].strip())
                    # Emit event when we have both type and data
                    if current_event_type and current_data:
                        if current_event_type != "connected":  # Skip connection events
                            collected.append((current_event_type, current_data))
                        if wanted <= {e for e, _ in collected}:
                            return

    task = asyncio.create_task(drain())
    try:
        await asyncio.wait_for(task, timeout=timeout)
    except asyncio.TimeoutError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise
    return collected


# --- test classes -------------------------------------------------------------


class TestSSEBroadcastEndpoint:
    """Verify SSE broadcast functionality from POST /api/v1/test/sse-broadcast endpoint."""

    async def test_broadcast_with_result_created_event_type(
        self, isolated_store: SessionStore
    ):
        """Verify that SSE event with event_type='result_created' is broadcast."""
        broadcaster = await _started_broadcaster()
        session_id = "test-broadcast-session"
        surface_id = "test-broadcast-surface"

        # Create session
        await isolated_store.create_session(session_id)

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Call the sse-broadcast endpoint with result_created event
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/sse-broadcast",
                    json={
                        "surface_id": surface_id,
                        "event_type": "result_created",
                        "test_data": {
                            "topic_id": "test-topic-1",
                            "result_id": "test-result-1",
                            "summary": "Test broadcast",
                        }
                    }
                )

            # Verify endpoint returns success
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "broadcasted"
            assert data["event_type"] == "result_created"
            assert data["surface_id"] == surface_id
            assert data["connections_notified"] == 1

            # Collect SSE events
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])

            # Verify result_created event was broadcast
            assert len(events) >= 1, "No SSE events were broadcast"
            event_type, event_data = events[0]
            assert event_type == "result_created", f"Expected 'result_created', got '{event_type}'"

            # Verify event payload contains expected data
            assert event_data["topic_id"] == "test-topic-1"
            assert event_data["result_id"] == "test-result-1"
            assert event_data["summary"] == "Test broadcast"
            assert event_data["test_broadcast"] is True

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_broadcast_with_surface_id_targeting(
        self, isolated_store: SessionStore
    ):
        """Verify that broadcast includes surface_id targeting when provided."""
        broadcaster = await _started_broadcaster()
        session_id = "test-targeting-session"

        # Create session
        await isolated_store.create_session(session_id)

        # Create multiple surfaces
        surface_1 = "test-target-surface-1"
        surface_2 = "test-target-surface-2"

        # Register SSE connections for both surfaces
        conn1 = broadcaster.register(
            surface_id=surface_1,
            session_id=session_id,
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id=surface_2,
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Broadcast specifically to surface_1
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/sse-broadcast",
                    json={
                        "surface_id": surface_1,
                        "event_type": "result_created",
                        "test_data": {"targeted": True}
                    }
                )

            assert response.status_code == 200
            data = response.json()
            assert data["connections_notified"] == 1

            # surface_1 should receive the event
            events1 = await _collect_sse_events(broadcaster, conn1, ["result_created"])
            assert len(events1) >= 1, "surface_1 should have received the event"

            # surface_2 should NOT receive the event (timeout expected)
            try:
                events2 = await _collect_sse_events(
                    broadcaster, conn2, ["result_created"], timeout=0.5
                )
                surface_2_received = len(events2) > 0
            except asyncio.TimeoutError:
                surface_2_received = False

            assert not surface_2_received, "surface_2 should not have received event targeted at surface_1"

        finally:
            broadcaster.unregister(conn1.connection_id)
            broadcaster.unregister(conn2.connection_id)

    async def test_broadcast_uses_existing_broadcaster_and_sse_event(
        self, isolated_store: SessionStore
    ):
        """Verify that endpoint uses existing get_broadcaster() and SSEEvent."""
        broadcaster = await _started_broadcaster()
        session_id = "test-existing-broadcaster-session"
        surface_id = "test-existing-broadcaster-surface"

        # Create session
        await isolated_store.create_session(session_id)

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Call the sse-broadcast endpoint
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/sse-broadcast",
                    json={
                        "surface_id": surface_id,
                        "event_type": "test_event",
                        "test_data": {"message": "Testing existing broadcaster"}
                    }
                )

            assert response.status_code == 200

            # Verify the event was broadcast using the existing broadcaster
            # by checking that it appears in the event stream
            events = await _collect_sse_events(broadcaster, conn, ["test_event"])
            assert len(events) >= 1, "Event should be broadcast using existing broadcaster"

            event_type, event_data = events[0]
            assert event_type == "test_event"
            assert event_data["message"] == "Testing existing broadcaster"

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_broadcast_timing_matches_dispatch_pattern(
        self, isolated_store: SessionStore
    ):
        """Verify that broadcast timing matches /dispatch pattern (synchronous completion)."""
        broadcaster = await _started_broadcaster()
        session_id = "test-timing-session"
        surface_id = "test-timing-surface"

        # Create session
        await isolated_store.create_session(session_id)

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            import time
            start_time = time.monotonic()

            # Call sse-broadcast endpoint - should complete synchronously
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/sse-broadcast",
                    json={
                        "surface_id": surface_id,
                        "event_type": "result_created",
                        "test_data": {"timing": "test"}
                    }
                )

            request_duration = time.monotonic() - start_time

            # Verify endpoint returns success quickly (broadcast is inline, not async)
            assert response.status_code == 200
            assert request_duration < 1.0, f"Request took {request_duration:.3f}s, expected < 1.0s"

            # Event should be immediately available (broadcast happens before response returns)
            events = await _collect_sse_events(broadcaster, conn, ["result_created"], timeout=0.5)
            assert len(events) >= 1, "Event should be immediately available"

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_broadcast_without_surface_id(
        self, isolated_store: SessionStore
    ):
        """Verify that broadcast works when surface_id is not provided (broadcasts to all)."""
        broadcaster = await _started_broadcaster()
        session_id = "test-no-surface-id-session"
        surface_id = "test-no-surface-id-target"

        # Create session
        await isolated_store.create_session(session_id)

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Broadcast without surface_id (should broadcast to ALL connected surfaces)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/sse-broadcast",
                    json={
                        "surface_id": None,
                        "event_type": "result_created",
                        "test_data": {"no_surface": True}
                    }
                )

            assert response.status_code == 200
            data = response.json()
            # When surface_id is None, broadcast goes to all connections (not 0)
            assert data["connections_notified"] == 1

            # Verify the event was actually received
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])
            assert len(events) >= 1, "Event should be broadcast when surface_id is None"

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_custom_event_type_broadcast(
        self, isolated_store: SessionStore
    ):
        """Verify that custom event types are broadcast correctly."""
        broadcaster = await _started_broadcaster()
        session_id = "test-custom-event-session"
        surface_id = "test-custom-event-surface"

        # Create session
        await isolated_store.create_session(session_id)

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Broadcast with custom event type
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/sse-broadcast",
                    json={
                        "surface_id": surface_id,
                        "event_type": "custom_event",
                        "test_data": {"custom": "data"}
                    }
                )

            assert response.status_code == 200
            data = response.json()
            assert data["event_type"] == "custom_event"

            # Verify custom event type was broadcast
            events = await _collect_sse_events(broadcaster, conn, ["custom_event"])
            assert len(events) >= 1, "Custom event should be broadcast"

            event_type, event_data = events[0]
            assert event_type == "custom_event"
            assert event_data["custom"] == "data"

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_no_connected_surfaces_still_succeeds(
        self, isolated_store: SessionStore
    ):
        """Verify that endpoint succeeds even when no SSE surface is connected."""
        # Do NOT register any SSE connection

        # Broadcast without any connected surfaces
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/test/sse-broadcast",
                json={
                    "surface_id": "non-existent-surface",
                    "event_type": "result_created",
                    "test_data": {"test": True}
                }
            )

        # Should succeed - broadcast to zero connections is valid
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "broadcasted"
        assert data["connections_notified"] == 0


# --- run tests directly -------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
