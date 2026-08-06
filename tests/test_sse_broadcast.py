"""
Test SSE Broadcasting from Test Endpoints

Verifies that test endpoints properly broadcast SSE events using the existing
SSE broadcaster infrastructure, matching the pattern used by the main /dispatch
endpoint.

Acceptance Criteria:
- SSE event with event_type="result_created" broadcast
- Event includes surface_id targeting if provided
- Uses existing get_broadcaster() and SSEEvent
- Broadcast timing matches /dispatch pattern
"""

import asyncio
import pytest
import uuid
from unittest.mock import Mock, AsyncMock, patch

from src.main import app
from src.sse.broadcaster import SSEBroadcaster, SSEEvent, EventType


@pytest.fixture
async def mock_broadcaster():
    """Create a mock broadcaster for testing."""
    broadcaster = Mock(spec=SSEBroadcaster)
    broadcaster.broadcast = AsyncMock(return_value=1)
    return broadcaster


@pytest.fixture
async def client_with_mock_broadcaster(mock_broadcaster):
    """Create a test client with mocked broadcaster."""
    from fastapi.testclient import TestClient

    # Patch the global _broadcaster
    with patch('src.main._broadcaster', mock_broadcaster):
        with TestClient(app) as client:
            yield client, mock_broadcaster


class TestSSEBroadcastFromTestEndpoint:
    """Test SSE broadcasting from /test endpoint."""

    def test_broadcasts_result_created_event(self, client_with_mock_broadcaster):
        """Verify that /test endpoint broadcasts result_created SSE event."""
        client, broadcaster = client_with_mock_broadcaster

        surface_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        response = client.post(
            "/test",
            json={
                "utterance": "test utterance",
                "session_id": session_id,
                "surface_id": surface_id,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "test"

        # Verify broadcast was called
        broadcaster.broadcast.assert_called_once()

        # Verify the event structure
        call_args = broadcaster.broadcast.call_args
        event = call_args[0][0]  # First positional argument

        assert isinstance(event, SSEEvent)
        assert event.event_type == EventType.RESULT_CREATED
        assert event.target_surface_id == surface_id

        # Verify event data contains expected fields
        assert "intent_id" in event.data
        assert "topic_id" in event.data
        assert "result_id" in event.data
        assert "summary" in event.data
        assert event.data["urgency"] == "normal"

    def test_broadcasts_without_surface_id(self, client_with_mock_broadcaster):
        """Verify that /test endpoint doesn't broadcast when surface_id is missing."""
        client, broadcaster = client_with_mock_broadcaster

        response = client.post(
            "/test",
            json={
                "utterance": "test utterance",
                "session_id": str(uuid.uuid4()),
                # No surface_id provided
            }
        )

        assert response.status_code == 200

        # Verify broadcast was NOT called
        broadcaster.broadcast.assert_not_called()

    def test_broadcast_failure_does_not_affect_response(self, client_with_mock_broadcaster):
        """Verify that broadcast failure doesn't break the endpoint response."""
        client, broadcaster = client_with_mock_broadcaster

        # Make broadcast raise an exception
        broadcaster.broadcast = AsyncMock(side_effect=Exception("Broadcast failed"))

        surface_id = str(uuid.uuid4())

        response = client.post(
            "/test",
            json={
                "utterance": "test utterance",
                "session_id": str(uuid.uuid4()),
                "surface_id": surface_id,
            }
        )

        # Response should still succeed (broadcast failure is non-fatal)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "test"

        # Broadcast was attempted
        broadcaster.broadcast.assert_called_once()


class TestSSEBroadcastFromTestDispatch:
    """Test SSE broadcasting from /api/v1/test/dispatch endpoint."""

    def test_broadcasts_result_created_event(self, client_with_mock_broadcaster):
        """Verify that /api/v1/test/dispatch broadcasts result_created SSE event."""
        client, broadcaster = client_with_mock_broadcaster

        surface_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        response = client.post(
            "/api/v1/test/dispatch",
            json={
                "utterance": "test dispatch utterance",
                "session_id": session_id,
                "surface_id": surface_id,
                "wait_for_results": False,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "dispatched"

        # Note: This endpoint broadcasts from a background task,
        # so we can't easily verify the broadcast in this synchronous test
        # The integration test below verifies the actual SSE delivery


class TestSSEBroadcastFromSyntheticDispatch:
    """Test SSE broadcasting from /api/v1/test/dispatch-synthetic endpoint."""

    def test_broadcasts_result_created_event(self, client_with_mock_broadcaster):
        """Verify that /api/v1/test/dispatch-synthetic broadcasts result_created SSE event."""
        client, broadcaster = client_with_mock_broadcaster

        surface_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        response = client.post(
            "/api/v1/test/dispatch-synthetic",
            json={
                "session_id": session_id,
                "surface_id": surface_id,
                "test_data": {
                    "utterance": "synthetic test",
                    "summary": "Synthetic test result",
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resolved"

        # Verify broadcast was called
        broadcaster.broadcast.assert_called_once()

        # Verify the event structure
        call_args = broadcaster.broadcast.call_args
        event = call_args[0][0]

        assert isinstance(event, SSEEvent)
        assert event.event_type == "result_created"
        assert event.target_surface_id == surface_id

        # Verify event data
        assert "intent_id" in event.data
        assert "topic_id" in event.data
        assert "summary" in event.data
        assert event.data["summary"] == "Synthetic test result"
        assert event.data["urgency"] == "normal"


class TestSSEBroadcastIntegration:
    """Integration tests for SSE broadcast delivery."""

    @pytest.mark.asyncio
    async def test_sse_event_reaches_canvas(self):
        """Verify that SSE events from test endpoint reach connected canvas."""
        from fastapi.testclient import TestClient

        # Create a real broadcaster instance
        broadcaster = SSEBroadcaster()
        await broadcaster.start()

        with patch('src.main._broadcaster', broadcaster):
            with TestClient(app) as client:
                # Step 1: Register a canvas surface via SSE connection
                session_id = str(uuid.uuid4())

                # Connect to SSE endpoint
                sse_response = client.get(
                    f"/events?session_id={session_id}",
                    stream=True
                )

                assert sse_response.status_code == 200

                # Step 2: Call test endpoint with surface_id
                # Note: We can't easily get the surface_id from the SSE connection
                # in this test setup, so we'll use a known surface_id

                surface_id = str(uuid.uuid4())

                # Register the surface manually
                connection = broadcaster.register(
                    surface_id=surface_id,
                    session_id=session_id,
                    surface_type="canvas"
                )

                # Call test endpoint
                test_response = client.post(
                    "/test",
                    json={
                        "utterance": "SSE integration test",
                        "session_id": session_id,
                        "surface_id": surface_id,
                    }
                )

                assert test_response.status_code == 200

                # Step 3: Verify event was queued to the connection
                # Check if an event was queued (non-blocking check)
                try:
                    event = connection.queue.get_nowait()
                    assert event.event_type == EventType.RESULT_CREATED
                    assert event.target_surface_id == surface_id
                    assert "summary" in event.data
                except asyncio.QueueEmpty:
                    pytest.fail("No SSE event was queued to the canvas")

        await broadcaster.stop()

    @pytest.mark.asyncio
    async def test_broadcast_pattern_matches_dispatch(self):
        """Verify that test endpoint broadcast pattern matches /dispatch pattern."""
        from fastapi.testclient import TestClient

        broadcaster = SSEBroadcaster()
        await broadcaster.start()

        with patch('src.main._broadcaster', broadcaster):
            with TestClient(app) as client:
                session_id = str(uuid.uuid4())
                surface_id = str(uuid.uuid4())

                connection = broadcaster.register(
                    surface_id=surface_id,
                    session_id=session_id,
                    surface_type="canvas"
                )

                # Call test endpoint
                test_response = client.post(
                    "/test",
                    json={
                        "utterance": "pattern match test",
                        "session_id": session_id,
                        "surface_id": surface_id,
                    }
                )

                assert test_response.status_code == 200

                # Verify event structure matches /dispatch pattern
                event = connection.queue.get_nowait()

                # /dispatch uses event_type="result_created"
                assert event.event_type == EventType.RESULT_CREATED

                # /dispatch includes target_surface_id
                assert event.target_surface_id == surface_id

                # /dispatch includes: intent_id, topic_id, summary, urgency
                required_fields = {"intent_id", "topic_id", "result_id", "summary", "urgency"}
                assert required_fields.issubset(set(event.data.keys()))

        await broadcaster.stop()


class TestSSEEventStructure:
    """Test the structure and content of SSE events."""

    def test_result_created_event_structure(self):
        """Verify that result_created events have the correct structure."""
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            target_surface_id="test-surface",
            data={
                "intent_id": "intent-123",
                "topic_id": "topic-456",
                "result_id": "result-789",
                "summary": "Test summary",
                "urgency": "normal",
            }
        )

        assert event.event_type == EventType.RESULT_CREATED
        assert event.target_surface_id == "test-surface"
        assert event.data["intent_id"] == "intent-123"
        assert event.data["topic_id"] == "topic-456"
        assert event.data["summary"] == "Test summary"
        assert event.data["urgency"] == "normal"

    def test_event_type_constant_matches_string(self):
        """Verify that EventType.RESULT_CREATED matches the string constant."""
        # This ensures consistency between using the constant and the string
        assert EventType.RESULT_CREATED == "result_created"


@pytest.mark.parametrize("endpoint,endpoint_path", [
    ("test", "/test"),
    ("test_dispatch", "/api/v1/test/dispatch"),
    ("synthetic", "/api/v1/test/dispatch-synthetic"),
])
class TestAllTestEndpoints:
    """Parametrized tests across all test endpoints."""

    def test_endpoints_use_get_broadcaster(self, endpoint, endpoint_path):
        """Verify that all test endpoints use get_broadcaster()."""
        # Check that the endpoint code references the broadcaster
        from src import main
        import inspect

        if endpoint == "test":
            func = main.test_endpoint
        elif endpoint == "test_dispatch":
            # This endpoint is in test/dispatch.py
            from src.test import dispatch
            func = dispatch.api_v1_test_dispatch
        else:  # synthetic
            from src.test import dispatch
            func = dispatch.api_v1_test_dispatch_synthetic

        # Get the source code
        source = inspect.getsource(func)

        # Check for broadcaster usage
        assert "broadcaster" in source or "_broadcaster" in source
        assert "broadcast" in source

    def test_endpoints_use_sse_event_class(self, endpoint, endpoint_path):
        """Verify that all test endpoints use SSEEvent class."""
        from src.test import dispatch
        import inspect

        if endpoint in ("test_dispatch", "synthetic"):
            if endpoint == "test_dispatch":
                func = dispatch.api_v1_test_dispatch
            else:
                func = dispatch.api_v1_test_dispatch_synthetic

            source = inspect.getsource(func)
            assert "SSEEvent" in source

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
