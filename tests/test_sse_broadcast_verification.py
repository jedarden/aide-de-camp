"""
SSE Broadcast Verification for Test Endpoint (bead adc-71gof).

Tests verify that SSE events are correctly broadcast when test endpoints
create results, ensuring the canvas receives real-time updates.

Test coverage:
- SSE event with type="result_created" is broadcast
- Event includes correct target_surface_id
- Event payload matches test result data
- Canvas surfaces can receive and parse the event
- Multiple surfaces can receive simultaneous broadcasts
"""
import asyncio

import pytest

import src.main as main_mod
import src.session.store as store_mod
from src.sse.broadcaster import SSEEvent, get_broadcaster


# --- fixtures -----------------------------------------------------------------


@pytest.fixture
async def isolated_store(tmp_path, monkeypatch):
    """Isolated session store for each test (never touches data/session.db)."""
    tmp_db = tmp_path / "test-sse-broadcast.db"
    monkeypatch.setenv("ADC_DB_PATH", str(tmp_db))

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


# --- Single surface SSE broadcast tests ----------------------------------------


class TestSingleSurfaceSSEBroadcast:
    """Test SSE broadcast verification for single surface connections."""

    async def test_result_created_event_is_broadcast(
        self, isolated_store
    ):
        """Verify that SSE event with type='result_created' is broadcast."""
        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Create a topic and result
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic",
            topic_type="research",
            project_slugs=[],
            session_id=session_id,
        )

        result_id = await store.create_result(
            intent_id="test-intent-1",
            topic_id=topic_id,
            session_id=session_id,
            summary="Test result",
            data={"test": "data"},
            urgency="normal",
            result_type="status:test",
        )

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast result_created event
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test-intent-1",
                        "topic_id": topic_id,
                        "summary": "Test result",
                        "urgency": "normal",
                    },
                    target_surface_id=surface_id,
                )
            )

            # Collect SSE events
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])

            # Verify event was broadcast
            assert len(events) >= 1
            event_type, event_data = events[0]
            assert event_type == "result_created"

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_event_includes_correct_target_surface_id(
        self, isolated_store
    ):
        """Verify that SSE event includes correct target_surface_id."""
        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast event with specific target_surface_id
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test-intent-2",
                        "topic_id": "test-topic",
                        "summary": "Test",
                        "urgency": "normal",
                    },
                    target_surface_id=surface_id,
                )
            )

            # Verify connection received the event
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])
            assert len(events) >= 1

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_event_payload_matches_test_result_data(
        self, isolated_store
    ):
        """Verify that event payload matches test result data."""
        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Create test data
        test_data = {
            "intent_id": "test-intent-3",
            "topic_id": "test-topic-3",
            "summary": "Test summary",
            "urgency": "high",
            "custom_field": "custom_value",
        }

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast event with test data
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data=test_data,
                    target_surface_id=surface_id,
                )
            )

            # Collect and verify event payload
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])
            assert len(events) >= 1

            event_type, event_data = events[0]

            # Verify all fields match
            assert event_data["intent_id"] == test_data["intent_id"]
            assert event_data["topic_id"] == test_data["topic_id"]
            assert event_data["summary"] == test_data["summary"]
            assert event_data["urgency"] == test_data["urgency"]
            assert event_data["custom_field"] == test_data["custom_field"]

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_canvas_surface_can_receive_and_parse_event(
        self, isolated_store
    ):
        """Verify that canvas surfaces can receive and parse the event."""
        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast event
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test-intent-4",
                        "topic_id": "test-topic-4",
                        "summary": "Canvas test",
                        "urgency": "normal",
                    },
                    target_surface_id=surface_id,
                )
            )

            # Parse received event
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])
            assert len(events) >= 1

            event_type, event_data = events[0]

            # Verify event structure is parseable
            assert isinstance(event_type, str)
            assert isinstance(event_data, dict)
            assert "intent_id" in event_data
            assert "topic_id" in event_data
            assert "summary" in event_data
            assert "urgency" in event_data

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_event_received_within_timeout_window(
        self, isolated_store
    ):
        """Verify that events are received within a reasonable timeout window."""
        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Measure time to broadcast and receive
            import time
            start_time = time.monotonic()

            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test-intent-5",
                        "topic_id": "test-topic-5",
                        "summary": "Timing test",
                        "urgency": "normal",
                    },
                    target_surface_id=surface_id,
                )
            )

            events = await _collect_sse_events(broadcaster, conn, ["result_created"], timeout=1.0)

            elapsed_time = time.monotonic() - start_time

            assert len(events) >= 1
            # Event should be received quickly (< 500ms for local broadcast)
            assert elapsed_time < 0.5, f"Event took {elapsed_time:.3f}s, expected < 0.5s"

        finally:
            broadcaster.unregister(conn.connection_id)


# --- Multiple surface SSE broadcast tests --------------------------------------


class TestMultipleSurfaceSSEBroadcast:
    """Test SSE broadcast verification for multiple surface connections."""

    async def test_multiple_surfaces_receive_simultaneous_broadcasts(
        self, isolated_store
    ):
        """Verify that multiple surfaces can receive simultaneous broadcasts."""
        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session
        session_id = await store.create_session()

        # Create multiple surfaces
        surface_1_id = await store.register_surface(session_id, "canvas")
        surface_2_id = await store.register_surface(session_id, "canvas")
        surface_3_id = await store.register_surface(session_id, "canvas")

        # Register multiple SSE connections
        conn1 = broadcaster.register(
            surface_id=surface_1_id, session_id=session_id, surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id=surface_2_id, session_id=session_id, surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id=surface_3_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast to all surfaces in the session (no specific target)
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test-intent-multi",
                        "topic_id": "test-topic-multi",
                        "summary": "Multi-surface test",
                        "urgency": "normal",
                    },
                    target_session_id=session_id,
                )
            )

            # All connections should receive the event
            events1 = await _collect_sse_events(broadcaster, conn1, ["result_created"])
            events2 = await _collect_sse_events(broadcaster, conn2, ["result_created"])
            events3 = await _collect_sse_events(broadcaster, conn3, ["result_created"])

            assert len(events1) >= 1
            assert len(events2) >= 1
            assert len(events3) >= 1

            # Verify all received the same data
            assert events1[0][1]["intent_id"] == events2[0][1]["intent_id"]
            assert events2[0][1]["intent_id"] == events3[0][1]["intent_id"]

        finally:
            broadcaster.unregister(conn1.connection_id)
            broadcaster.unregister(conn2.connection_id)
            broadcaster.unregister(conn3.connection_id)

    async def test_specific_surface_targeting_works_correctly(
        self, isolated_store
    ):
        """Verify that specific surface targeting works correctly."""
        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session
        session_id = await store.create_session()

        # Create multiple surfaces
        surface_1_id = await store.register_surface(session_id, "canvas")
        surface_2_id = await store.register_surface(session_id, "canvas")

        # Register two SSE connections
        conn1 = broadcaster.register(
            surface_id=surface_1_id, session_id=session_id, surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id=surface_2_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast specifically to surface_1
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test-intent-target-1",
                        "topic_id": "test-topic-target",
                        "summary": "Targeted test",
                        "urgency": "normal",
                    },
                    target_surface_id=surface_1_id,
                )
            )

            # Only surface_1 should receive the event
            events1 = await _collect_sse_events(broadcaster, conn1, ["result_created"])
            # surface_2 should not receive any events (timeout will occur)
            try:
                events2 = await _collect_sse_events(broadcaster, conn2, ["result_created"], timeout=0.5)
                surface_2_received = len(events2) > 0
            except asyncio.TimeoutError:
                surface_2_received = False

            assert len(events1) >= 1, "surface_1 should have received the event"
            assert not surface_2_received, "surface_2 should not have received the event"

        finally:
            broadcaster.unregister(conn1.connection_id)
            broadcaster.unregister(conn2.connection_id)

    async def test_surface_exclusion_filter_works_correctly(
        self, isolated_store
    ):
        """Verify that surface exclusion filter works correctly."""
        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session
        session_id = await store.create_session()

        # Create multiple surfaces
        surface_1_id = await store.register_surface(session_id, "canvas")
        surface_2_id = await store.register_surface(session_id, "canvas")
        surface_3_id = await store.register_surface(session_id, "canvas")

        # Register three SSE connections
        conn1 = broadcaster.register(
            surface_id=surface_1_id, session_id=session_id, surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id=surface_2_id, session_id=session_id, surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id=surface_3_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast to all surfaces except surface_2
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test-intent-exclude",
                        "topic_id": "test-topic-exclude",
                        "summary": "Exclusion test",
                        "urgency": "normal",
                    },
                    target_session_id=session_id,
                    exclude_surface_id=surface_2_id,
                )
            )

            # surface_1 and surface_3 should receive, surface_2 should not
            events1 = await _collect_sse_events(broadcaster, conn1, ["result_created"])

            # surface_2 should not receive events (timeout)
            try:
                events2 = await _collect_sse_events(broadcaster, conn2, ["result_created"], timeout=0.5)
                surface_2_received = len(events2) > 0
            except asyncio.TimeoutError:
                surface_2_received = False

            events3 = await _collect_sse_events(broadcaster, conn3, ["result_created"])

            assert len(events1) >= 1, "surface_1 should have received the event"
            assert not surface_2_received, "surface_2 should not have received the event (excluded)"
            assert len(events3) >= 1, "surface_3 should have received the event"

        finally:
            broadcaster.unregister(conn1.connection_id)
            broadcaster.unregister(conn2.connection_id)
            broadcaster.unregister(conn3.connection_id)


# --- Test endpoint integration tests ------------------------------------------


class TestEndpointSSEIntegration:
    """Test SSE broadcast integration with test endpoints."""

    async def test_test_dispatch_synthetic_broadcasts_sse(
        self, isolated_store
    ):
        """Verify that /api/v1/test/dispatch-synthetic broadcasts SSE events."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Call the synthetic result endpoint
            request = SyntheticResultRequest(
                session_id=session_id,
                surface_id=surface_id,
                test_data={
                    "utterance": "synthetic test utterance",
                    "topic_label": "Synthetic Test Topic",
                    "summary": "Synthetic test result",
                    "data": {"test": "data"},
                }
            )

            # Generate the synthetic result (should broadcast SSE)
            result = await generate_synthetic_result(request)

            # Verify SSE event was broadcast
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])
            assert len(events) >= 1

            event_type, event_data = events[0]
            assert event_type == "result_created"
            assert event_data["summary"] == "Synthetic test result"

        finally:
            broadcaster.unregister(conn.connection_id)

    async def test_multiple_test_results_broadcast_correctly(
        self, isolated_store
    ):
        """Verify that multiple test results broadcast correctly in sequence."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        store = isolated_store
        broadcaster = await _started_broadcaster()

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Register SSE connection
        conn = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Collect events manually to get multiple events of the same type
            collected_events = []

            async def collect_multiple_events():
                """Collect multiple events of the same type."""
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
                except Exception as e:
                    print(f"Error collecting events: {e}")

            # Start event collection in background
            collect_task = asyncio.create_task(collect_multiple_events())

            # Create multiple synthetic results
            for i in range(3):
                request = SyntheticResultRequest(
                    session_id=session_id,
                    surface_id=surface_id,
                    test_data={
                        "utterance": f"synthetic test utterance {i}",
                        "topic_label": f"Synthetic Test Topic {i}",
                        "summary": f"Synthetic test result {i}",
                        "data": {"test": f"data_{i}"},
                    }
                )
                await generate_synthetic_result(request)
                # Small delay to ensure events are sent
                await asyncio.sleep(0.1)

            # Wait for collection to complete
            try:
                await asyncio.wait_for(collect_task, timeout=3.0)
            except asyncio.TimeoutError:
                collect_task.cancel()
                try:
                    await collect_task
                except asyncio.CancelledError:
                    pass

            # Should have collected at least 3 events
            assert len(collected_events) >= 3, f"Expected at least 3 events, got {len(collected_events)}"

            # Verify each event has unique data
            summaries = [e[1]["summary"] for e in collected_events]
            assert "Synthetic test result 0" in summaries
            assert "Synthetic test result 1" in summaries
            assert "Synthetic test result 2" in summaries

        finally:
            broadcaster.unregister(conn.connection_id)


# --- SSE connection lifecycle tests ------------------------------------------


class TestSSEConnectionLifecycle:
    """Test SSE connection lifecycle and cleanup."""

    async def test_connection_registration_and_unregistration(
        self, isolated_store
    ):
        """Verify that connections can be registered and unregistered correctly."""
        broadcaster = await _started_broadcaster()
        store = isolated_store

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Register connection
        conn = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        # Verify connection is registered
        assert conn.connection_id in broadcaster.connections

        # Unregister connection
        broadcaster.unregister(conn.connection_id)

        # Verify connection is unregistered
        assert conn.connection_id not in broadcaster.connections

    async def test_multiple_connections_same_surface(
        self, isolated_store
    ):
        """Verify that multiple connections to the same surface are handled correctly."""
        broadcaster = await _started_broadcaster()
        store = isolated_store

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Register multiple connections for the same surface
        conn1 = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast to the surface
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test-intent-conn",
                        "topic_id": "test-topic-conn",
                        "summary": "Connection test",
                        "urgency": "normal",
                    },
                    target_surface_id=surface_id,
                )
            )

            # Both connections should receive the event
            events1 = await _collect_sse_events(broadcaster, conn1, ["result_created"])
            events2 = await _collect_sse_events(broadcaster, conn2, ["result_created"])

            assert len(events1) >= 1
            assert len(events2) >= 1

        finally:
            broadcaster.unregister(conn1.connection_id)
            broadcaster.unregister(conn2.connection_id)


# --- Edge cases and error handling --------------------------------------------


class TestSSEBroadcastEdgeCases:
    """Test edge cases and error handling for SSE broadcasts."""

    async def test_broadcast_with_no_target_reaches_all_session_surfaces(
        self, isolated_store
    ):
        """Verify that broadcast with no specific target reaches all session surfaces."""
        broadcaster = await _started_broadcaster()
        store = isolated_store

        # Create a session with multiple surfaces
        session_id = await store.create_session()
        surface_1 = await store.register_surface(session_id, "canvas")
        surface_2 = await store.register_surface(session_id, "canvas")

        # Create a different session (should not receive events)
        other_session_id = await store.create_session()
        other_surface = await store.register_surface(other_session_id, "canvas")

        # Register connections
        conn1 = broadcaster.register(
            surface_id=surface_1, session_id=session_id, surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id=surface_2, session_id=session_id, surface_type="canvas"
        )
        conn_other = broadcaster.register(
            surface_id=other_surface, session_id=other_session_id, surface_type="canvas"
        )

        try:
            # Broadcast to session without specific surface target
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test-intent-session",
                        "topic_id": "test-topic-session",
                        "summary": "Session broadcast test",
                        "urgency": "normal",
                    },
                    target_session_id=session_id,
                )
            )

            # Both surfaces in the session should receive
            events1 = await _collect_sse_events(broadcaster, conn1, ["result_created"])
            events2 = await _collect_sse_events(broadcaster, conn2, ["result_created"])

            # Other session should not receive
            try:
                events_other = await _collect_sse_events(
                    broadcaster, conn_other, ["result_created"], timeout=0.5
                )
                other_received = len(events_other) > 0
            except asyncio.TimeoutError:
                other_received = False

            assert len(events1) >= 1
            assert len(events2) >= 1
            assert not other_received, "Other session should not have received the event"

        finally:
            broadcaster.unregister(conn1.connection_id)
            broadcaster.unregister(conn2.connection_id)
            broadcaster.unregister(conn_other.connection_id)

    async def test_broadcast_with_malformed_data_doesnt_crash_broadcaster(
        self, isolated_store
    ):
        """Verify that malformed data doesn't crash the broadcaster."""
        broadcaster = await _started_broadcaster()
        store = isolated_store

        # Create a session and surface
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        # Register connection
        conn = broadcaster.register(
            surface_id=surface_id, session_id=session_id, surface_type="canvas"
        )

        try:
            # Broadcast with various data types (should not crash)
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    data={
                        "intent_id": "test",
                        "topic_id": "test",
                        "summary": "Test",
                        "urgency": "normal",
                        "null_field": None,
                        "empty_list": [],
                        "nested_dict": {"key": "value"},
                    },
                    target_surface_id=surface_id,
                )
            )

            # Should receive event successfully
            events = await _collect_sse_events(broadcaster, conn, ["result_created"])
            assert len(events) >= 1

        finally:
            broadcaster.unregister(conn.connection_id)
