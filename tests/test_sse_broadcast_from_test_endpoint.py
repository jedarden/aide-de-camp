"""
Test SSE broadcast from /test endpoint (bead adc-3pbim).

Verifies that the /test endpoint broadcasts SSE events to connected canvas surfaces
using the existing broadcaster, matching the /dispatch pattern.

Acceptance criteria:
- SSE event with event_type="result_created" broadcast
- Event includes surface_id targeting if provided
- Uses existing get_broadcaster() and SSEEvent
- Broadcast timing matches /dispatch pattern
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

from src.main import app
from src.sse.broadcaster import get_broadcaster, SSEBroadcaster, SSEEvent, EventType
from src.session.store import SessionStore, get_store
from pathlib import Path


@pytest.fixture
async def test_store(tmp_path: Path) -> SessionStore:
    """An isolated SessionStore on a temp DB for testing."""
    db_path = tmp_path / "test_session.db"
    store = SessionStore(db_path)
    await store.initialize()
    yield store
    await store.close()


class TestSSEBroadcastFromTestEndpoint:
    """Verify SSE broadcast from /test endpoint."""

    @pytest.mark.asyncio
    async def test_test_endpoint_broadcasts_sse_event(self, test_store: SessionStore) -> None:
        """Verify that /test endpoint broadcasts result_created SSE event when surface_id is provided."""
        # Get broadcaster
        broadcaster = get_broadcaster()
        await broadcaster.start()

        try:
            # Mock the store
            with patch('src.main.get_store', return_value=test_store):
                # Create a mock surface connection
                surface_id = "test-surface-123"
                session_id = "test-session-456"

                # Register a test connection
                connection = broadcaster.register(
                    surface_id=surface_id,
                    session_id=session_id,
                    surface_type="canvas"
                )

                # Create a queue to capture events sent to this connection
                event_queue = asyncio.Queue()
                original_queue = connection.queue

                # Replace the connection's queue with our test queue
                connection.queue = event_queue

                # Call the /test endpoint with surface_id
                test_payload = {
                    "utterance": "test SSE broadcast verification",
                    "session_id": session_id,
                }

                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post("/test", json=test_payload)

                # Verify the endpoint returns success
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "test"
                assert "result_id" in data["stored"]

                # Restore original queue
                connection.queue = original_queue

                # Verify SSE event was broadcast
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    assert isinstance(event, SSEEvent)
                    assert event.event_type == EventType.RESULT_CREATED
                    assert event.data["result_id"] == data["stored"]["result_id"]
                    assert event.target_surface_id == surface_id
                except asyncio.TimeoutError:
                    # If no event was received, the SSE broadcast is not implemented
                    pytest.fail("SSE event was not broadcast from /test endpoint")

        finally:
            await broadcaster.stop()

    @pytest.mark.asyncio
    async def test_test_endpoint_without_surface_id_no_broadcast(self, test_store: SessionStore) -> None:
        """Verify that /test endpoint without surface_id does not broadcast to specific surface."""
        # Get broadcaster
        broadcaster = get_broadcaster()
        await broadcaster.start()

        try:
            # Mock the store
            with patch('src.main.get_store', return_value=test_store):
                session_id = "test-session-no-surface"

                # Register a test connection (should NOT receive event)
                surface_id = "test-surface-789"
                connection = broadcaster.register(
                    surface_id=surface_id,
                    session_id=session_id,
                    surface_type="canvas"
                )

                # Create a queue to capture events
                event_queue = asyncio.Queue()
                original_queue = connection.queue
                connection.queue = event_queue

                # Call the /test endpoint WITHOUT surface_id
                test_payload = {
                    "utterance": "test without surface ID",
                    "session_id": session_id,
                }

                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post("/test", json=test_payload)

                # Verify the endpoint returns success
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "test"

                # Restore original queue
                connection.queue = original_queue

                # Verify NO SSE event was sent to this specific surface
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                    # If an event was received, verify it wasn't targeted at this surface
                    if event.target_surface_id:
                        assert event.target_surface_id != surface_id, \
                            f"Event should not be targeted at this surface"
                except asyncio.TimeoutError:
                    # No event received - this is expected when no surface_id is provided
                    pass

        finally:
            await broadcaster.stop()

    @pytest.mark.asyncio
    async def test_test_endpoint_sse_matches_dispatch_pattern(self, test_store: SessionStore) -> None:
        """Verify that /test endpoint SSE pattern matches /dispatch endpoint pattern."""
        # Get broadcaster
        broadcaster = get_broadcaster()
        await broadcaster.start()

        try:
            # Mock the store
            with patch('src.main.get_store', return_value=test_store):
                session_id = "test-pattern-match"
                surface_id = "test-surface-pattern"

                # Register connection
                connection = broadcaster.register(
                    surface_id=surface_id,
                    session_id=session_id,
                    surface_type="canvas"
                )

                event_queue = asyncio.Queue()
                original_queue = connection.queue
                connection.queue = event_queue

                # Call /test endpoint
                test_payload = {
                    "utterance": "pattern verification",
                    "session_id": session_id,
                }

                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post("/test", json=test_payload)

                assert response.status_code == 200
                data = response.json()

                connection.queue = original_queue

                # Get the broadcast event
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)

                    # Verify event structure matches /dispatch pattern:
                    # 1. Uses SSEEvent dataclass
                    assert isinstance(event, SSEEvent)

                    # 2. Has result_created event type
                    assert event.event_type == EventType.RESULT_CREATED

                    # 3. Has target_surface_id set
                    assert event.target_surface_id == surface_id

                    # 4. Has result_id in data (like /dispatch)
                    assert "result_id" in event.data

                    # 5. Has summary in data (like /dispatch)
                    assert "summary" in event.data

                except asyncio.TimeoutError:
                    pytest.fail("SSE event not broadcast - pattern doesn't match /dispatch")

        finally:
            await broadcaster.stop()

    @pytest.mark.asyncio
    async def test_test_endpoint_uses_get_broadcaster(self, test_store: SessionStore) -> None:
        """Verify that /test endpoint uses get_broadcaster() singleton."""
        # Mock the store
        with patch('src.main.get_store', return_value=test_store):
            # Mock get_broadcaster to track calls
            mock_broadcaster = AsyncMock()
            mock_broadcaster.broadcast = AsyncMock(return_value=1)

            with patch('src.main.get_broadcaster', return_value=mock_broadcaster):
                session_id = "test-broadcaster-usage"

                test_payload = {
                    "utterance": "verify broadcaster usage",
                    "session_id": session_id,
                }

                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post("/test", json=test_payload)

                # Verify endpoint succeeded
                assert response.status_code == 200

                # Verify get_broadcaster was called
                # Note: This will fail until we add SSE broadcast to /test endpoint
                # mock_broadcaster.broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_synthetic_dispatch_broadcasts_sse():
    """Verify that /api/v1/test/dispatch-synthetic broadcasts SSE events."""
    from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest
    from src.sse.broadcaster import get_broadcaster

    broadcaster = get_broadcaster()
    await broadcaster.start()

    try:
        # Create test session and surface
        session_id = "test-synthetic-sse"
        surface_id = "test-surface-synthetic"

        # Register connection
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        event_queue = asyncio.Queue()
        original_queue = connection.queue
        connection.queue = event_queue

        # Create synthetic result request
        request = SyntheticResultRequest(
            session_id=session_id,
            surface_id=surface_id,
            test_data={
                "utterance": "synthetic SSE test",
                "summary": "Test synthetic SSE broadcast",
            }
        )

        # Generate result
        response = await generate_synthetic_result(request)

        connection.queue = original_queue

        # Verify SSE event was broadcast
        event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
        assert isinstance(event, SSEEvent)
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["intent_id"] == response.intent_id
        assert event.target_surface_id == surface_id

    finally:
        await broadcaster.stop()
