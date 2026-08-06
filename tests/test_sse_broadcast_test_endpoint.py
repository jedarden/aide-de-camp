"""
Test SSE broadcast behavior for /api/v1/test/create-topic endpoint (bead adc-10kok).

Verifies that the test endpoint broadcasts SSE events correctly, confirming:
- event_type="result_created" is broadcast
- surface_id targeting works when provided
- broadcast timing matches /dispatch pattern
- Tests can be run via pytest
- All tests pass
"""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from src.sse.broadcaster import SSEEvent, get_broadcaster, EventType
from src.session.store import SessionStore, get_store
from src.main import app


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
async def isolated_store(tmp_path: Path, monkeypatch) -> SessionStore:
    """Isolated session store for each test (never touches data/session.db)."""
    tmp_db = tmp_path / "test-sse-test-endpoint.db"
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


class TestSSEBroadcastFromCreateTopicEndpoint:
    """Verify SSE broadcast from POST /api/v1/test/create-topic endpoint."""

    async def test_create_topic_broadcasts_result_created_event(
        self, isolated_store: SessionStore
    ):
        """Verify that event_type='result_created' is broadcast when topic is created."""
        broadcaster = await _started_broadcaster()
        session_id = "test-sse-broadcast-session"
        surface_id = "test-sse-broadcast-surface"

        # Create session
        await isolated_store.create_session(session_id)

        # Register SSE connection BEFORE creating the topic
        conn = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Create topic via test endpoint (should broadcast SSE event)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/create-topic",
                    json={
                        "session_id": session_id,
                        "label": "SSE Broadcast Test Topic",
                        "type": "research",
                        "summary": "Testing SSE broadcast from create-topic endpoint",
                        "urgency": "normal",
                    }
                )

            # Verify endpoint returns success
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "created"
            assert "topic_id" in data
            assert "result_id" in data

            # Collect SSE events
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])

            # Verify result_created event was broadcast
            assert len(events) >= 1, "No SSE events were broadcast"
            event_type, event_data = events[0]
            assert event_type == "result_created", f"Expected 'result_created', got '{event_type}'"

            # Verify event payload contains expected data
            assert "topic_id" in event_data
            assert "result_id" in event_data
            assert event_data["topic_id"] == data["topic_id"]
            assert event_data["result_id"] == data["result_id"]
            assert event_data["summary"] == "Testing SSE broadcast from create-topic endpoint"

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_broadcast_targets_session_correctly(
        self, isolated_store: SessionStore
    ):
        """Verify that broadcast targets the correct session_id."""
        broadcaster = await _started_broadcaster()

        # Create two different sessions
        session_a = "test-session-a"
        session_b = "test-session-b"
        surface_a = "test-surface-a"
        surface_b = "test-surface-b"

        await isolated_store.create_session(session_a)
        await isolated_store.create_session(session_b)

        # Register SSE connections for both sessions
        conn_a = broadcaster.register(
            surface_id=surface_a,
            session_id=session_a,
            surface_type="canvas"
        )
        conn_b = broadcaster.register(
            surface_id=surface_b,
            session_id=session_b,
            surface_type="canvas"
        )

        try:
            # Create topic in session A
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/create-topic",
                    json={
                        "session_id": session_a,
                        "label": "Session A Topic",
                        "type": "project",
                        "summary": "Session A result",
                    }
                )

            assert response.status_code == 200

            # Session A should receive the event
            events_a = await _collect_sse_events(broadcaster, conn_a, ["result_created"])
            assert len(events_a) >= 1, "Session A should have received the event"

            # Session B should NOT receive the event (timeout expected)
            try:
                events_b = await _collect_sse_events(
                    broadcaster, conn_b, ["result_created"], timeout=0.5
                )
                session_b_received = len(events_b) > 0
            except asyncio.TimeoutError:
                session_b_received = False

            assert not session_b_received, "Session B should not have received event for session A"

        finally:
            broadcaster.unregister(conn_a.connection_id)
            broadcaster.unregister(conn_b.connection_id)

    async def test_broadcast_timing_matches_dispatch_pattern(
        self, isolated_store: SessionStore
    ):
        """Verify that broadcast timing matches /dispatch pattern (synchronous completion)."""
        broadcaster = await _started_broadcaster()
        session_id = "test-timing-session"
        surface_id = "test-timing-surface"

        await isolated_store.create_session(session_id)

        conn = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            import time
            start_time = time.monotonic()

            # Create topic - SSE broadcast should happen synchronously within the request
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/create-topic",
                    json={
                        "session_id": session_id,
                        "label": "Timing Test Topic",
                        "type": "research",
                        "summary": "Testing broadcast timing",
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

    async def test_multiple_surfaces_in_session_receive_broadcast(
        self, isolated_store: SessionStore
    ):
        """Verify that multiple surfaces in the same session all receive the broadcast."""
        broadcaster = await _started_broadcaster()
        session_id = "test-multi-surface-session"

        await isolated_store.create_session(session_id)

        # Register multiple surfaces for the same session
        surface_1 = "test-surface-1"
        surface_2 = "test-surface-2"
        surface_3 = "test-surface-3"

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
        conn3 = broadcaster.register(
            surface_id=surface_3,
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Create topic
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/create-topic",
                    json={
                        "session_id": session_id,
                        "label": "Multi-Surface Topic",
                        "type": "project",
                        "summary": "Testing broadcast to multiple surfaces",
                    }
                )

            assert response.status_code == 200
            data = response.json()

            # All three surfaces should receive the event
            events1 = await _collect_sse_events(broadcaster, conn1, ["result_created"])
            events2 = await _collect_sse_events(broadcaster, conn2, ["result_created"])
            events3 = await _collect_sse_events(broadcaster, conn3, ["result_created"])

            assert len(events1) >= 1, "Surface 1 should receive event"
            assert len(events2) >= 1, "Surface 2 should receive event"
            assert len(events3) >= 1, "Surface 3 should receive event"

            # All should have the same topic_id
            topic_id = data["topic_id"]
            assert events1[0][1]["topic_id"] == topic_id
            assert events2[0][1]["topic_id"] == topic_id
            assert events3[0][1]["topic_id"] == topic_id

        finally:
            broadcaster.unregister(conn1.connection_id)
            broadcaster.unregister(conn2.connection_id)
            broadcaster.unregister(conn3.connection_id)

    async def test_event_payload_structure_matches_dispatch(
        self, isolated_store: SessionStore
    ):
        """Verify that event payload structure matches /dispatch endpoint pattern."""
        broadcaster = await _started_broadcaster()
        session_id = "test-payload-structure-session"

        await isolated_store.create_session(session_id)

        conn = broadcaster.register(
            surface_id="test-payload-surface",
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Create topic with all fields
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/create-topic",
                    json={
                        "session_id": session_id,
                        "label": "Payload Structure Test",
                        "type": "exception",
                        "summary": "Testing payload structure",
                        "urgency": "high",
                    }
                )

            assert response.status_code == 200
            data = response.json()

            # Collect event
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])
            assert len(events) >= 1

            event_type, event_data = events[0]

            # Verify event structure matches /dispatch pattern:
            # Should have topic_id, result_id, summary, urgency
            assert "topic_id" in event_data
            assert "result_id" in event_data
            assert "summary" in event_data
            assert "urgency" in event_data

            # Verify values match response
            assert event_data["topic_id"] == data["topic_id"]
            assert event_data["result_id"] == data["result_id"]
            assert event_data["summary"] == "Testing payload structure"
            assert event_data["urgency"] == "high"

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_backdated_topic_broadcasts_correctly(
        self, isolated_store: SessionStore
    ):
        """Verify that backdated topics (staleness_seconds > 0) broadcast correctly."""
        broadcaster = await _started_broadcaster()
        session_id = "test-backdated-session"

        await isolated_store.create_session(session_id)

        conn = broadcaster.register(
            surface_id="test-backdated-surface",
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Create backdated topic
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/test/create-topic",
                    json={
                        "session_id": session_id,
                        "label": "Backdated Topic",
                        "type": "research",
                        "summary": "Testing backdated topic broadcast",
                        "urgency": "normal",
                        "staleness_seconds": 3600,  # 1 hour old
                    }
                )

            assert response.status_code == 200

            # Should still broadcast SSE event
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])
            assert len(events) >= 1, "Backdated topic should still broadcast SSE event"

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_no_connected_surface_still_succeeds(
        self, isolated_store: SessionStore
    ):
        """Verify that endpoint succeeds even when no SSE surface is connected."""
        session_id = "test-no-surface-session"

        await isolated_store.create_session(session_id)

        # Do NOT register any SSE connection

        # Create topic - should succeed even with no connected surfaces
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/test/create-topic",
                json={
                    "session_id": session_id,
                    "label": "No Surface Topic",
                    "type": "project",
                    "summary": "Testing with no connected surface",
                }
            )

        # Should succeed - broadcast to zero connections is valid
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"

    async def test_consecutive_topic_creates_broadcast_independently(
        self, isolated_store: SessionStore
    ):
        """Verify that consecutive topic creations each broadcast independently."""
        broadcaster = await _started_broadcaster()
        session_id = "test-consecutive-session"

        await isolated_store.create_session(session_id)

        conn = broadcaster.register(
            surface_id="test-consecutive-surface",
            session_id=session_id,
            surface_type="canvas"
        )

        try:
            # Collect multiple events
            collected_events = []

            async def collect_multiple():
                try:
                    async for wire in broadcaster.event_generator(conn):
                        lines = wire.strip().split("\n")
                        current_event_type = None
                        current_data = None

                        for line in lines:
                            if line.startswith("event: "):
                                current_event_type = line[7:].strip()
                            elif line.startswith("data: "):
                                import json
                                current_data = json.loads(line[6:].strip())
                                if current_event_type and current_data:
                                    if current_event_type == "result_created":
                                        collected_events.append((current_event_type, current_data))
                                        if len(collected_events) >= 3:
                                            return
                except Exception:
                    pass

            # Start collection
            collect_task = asyncio.create_task(collect_multiple())

            # Create 3 topics consecutively
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                for i in range(3):
                    await client.post(
                        "/api/v1/test/create-topic",
                        json={
                            "session_id": session_id,
                            "label": f"Consecutive Topic {i}",
                            "type": "research",
                            "summary": f"Consecutive result {i}",
                        }
                    )
                    await asyncio.sleep(0.1)  # Small delay

            # Wait for collection
            try:
                await asyncio.wait_for(collect_task, timeout=3.0)
            except asyncio.TimeoutError:
                collect_task.cancel()
                try:
                    await collect_task
                except asyncio.CancelledError:
                    pass

            # Should have collected 3 separate events
            assert len(collected_events) >= 3, f"Expected 3 events, got {len(collected_events)}"

            # Each event should have unique data
            summaries = [e[1]["summary"] for e in collected_events]
            assert "Consecutive result 0" in summaries
            assert "Consecutive result 1" in summaries
            assert "Consecutive result 2" in summaries

        finally:
            broadcaster.unregister(conn.connection_id)


# --- run tests directly -------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
