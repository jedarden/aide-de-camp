"""
End-to-End Narration Test

Tests TTS/narration functionality using the test endpoints:
1. Create a narration session
2. Inject test narration events with various urgency levels
3. Verify timing and urgency ordering
4. Capture mock TTS output
5. Verify TTS properties
"""
import asyncio
import time
import httpx
import pytest


# Test server base URL
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1/test/narration"


class TestNarrationE2E:
    """End-to-end tests for narration functionality."""

    @pytest.mark.asyncio
    async def test_narration_session_lifecycle(self):
        """Test creating and managing a narration session."""
        session_id = "test-session-e2e-001"

        async with httpx.AsyncClient() as client:
            # Create session
            response = await client.post(
                f"{API_BASE}/session",
                json={"session_id": session_id, "voice": "alloy"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "created"
            assert data["session_id"] == session_id
            assert data["voice"] == "alloy"

            # Get session details
            response = await client.get(f"{API_BASE}/session/{session_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == session_id
            assert data["narration_summary"]["total_events"] == 0

            # Delete session
            response = await client.delete(f"{API_BASE}/session/{session_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_narration_event_injection(self):
        """Test injecting and capturing narration events."""
        session_id = "test-session-e2e-002"

        async with httpx.AsyncClient() as client:
            # Create session
            await client.post(
                f"{API_BASE}/session",
                json={"session_id": session_id}
            )

            # Inject critical urgency event
            response = await client.post(
                f"{API_BASE}/inject",
                json={
                    "session_id": session_id,
                    "results": [
                        {
                            "intent_id": "intent-001",
                            "topic_id": "topic-001",
                            "summary": "Critical system alert",
                            "urgency": "critical"
                        }
                    ]
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "injected"
            assert data["result_count"] == 1

            # Inject normal urgency event
            await asyncio.sleep(1)  # Simulate time passing
            response = await client.post(
                f"{API_BASE}/inject",
                json={
                    "session_id": session_id,
                    "results": [
                        {
                            "intent_id": "intent-002",
                            "topic_id": "topic-002",
                            "summary": "Normal status update",
                            "urgency": "normal"
                        }
                    ]
                }
            )
            assert response.status_code == 200

            # Get session and verify events
            response = await client.get(f"{API_BASE}/session/{session_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["narration_summary"]["total_events"] == 2
            assert data["narration_summary"]["total_results"] == 2
            assert "critical" in data["narration_summary"]["urgencies"]
            assert "normal" in data["narration_summary"]["urgencies"]

            # Cleanup
            await client.delete(f"{API_BASE}/session/{session_id}")

    @pytest.mark.asyncio
    async def test_urgency_ordering_verification(self):
        """Test that urgency ordering is correctly verified."""
        session_id = "test-session-e2e-003"

        async with httpx.AsyncClient() as client:
            # Create session
            await client.post(
                f"{API_BASE}/session",
                json={"session_id": session_id}
            )

            # Inject events in correct urgency order: critical -> high -> normal -> low
            events = [
                {"urgency": "critical", "summary": "Critical alert"},
                {"urgency": "high", "summary": "High priority update"},
                {"urgency": "normal", "summary": "Normal update"},
                {"urgency": "low", "summary": "Low priority notification"},
            ]

            for event in events:
                await client.post(
                    f"{API_BASE}/inject",
                    json={
                        "session_id": session_id,
                        "results": [
                            {
                                "intent_id": f"intent-{event['urgency']}",
                                "topic_id": "topic-001",
                                "summary": event["summary"],
                                "urgency": event["urgency"]
                            }
                        ]
                    }
                )

            # Verify ordering
            response = await client.post(
                f"{API_BASE}/verify",
                json={"session_id": session_id}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["urgency_order_verified"]["verified"] == True
            assert data["urgency_order_verified"]["urgency_sequence"] == [
                "critical", "high", "normal", "low"
            ]

            # Cleanup
            await client.delete(f"{API_BASE}/session/{session_id}")

    @pytest.mark.asyncio
    async def test_timing_verification(self):
        """Test narration timing within batching window."""
        session_id = "test-session-e2e-004"

        async with httpx.AsyncClient() as client:
            # Create session
            await client.post(
                f"{API_BASE}/session",
                json={"session_id": session_id}
            )

            # Inject events with 1-second intervals
            for i in range(3):
                await client.post(
                    f"{API_BASE}/inject",
                    json={
                        "session_id": session_id,
                        "results": [
                            {
                                "intent_id": f"intent-{i:03d}",
                                "topic_id": "topic-001",
                                "summary": f"Event {i}",
                                "urgency": "normal"
                            }
                        ]
                    }
                )
                await asyncio.sleep(1)

            # Verify timing with 5-second window
            response = await client.post(
                f"{API_BASE}/verify",
                json={"session_id": session_id, "expected_window_seconds": 5.0}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["timing_verified"]["verified"] == True
            assert data["timing_verified"]["expected_window_seconds"] == 5.0
            assert all(
                interval <= 5.0 for interval in data["timing_verified"]["intervals"]
            )

            # Cleanup
            await client.delete(f"{API_BASE}/session/{session_id}")

    @pytest.mark.asyncio
    async def test_tts_capture_and_verification(self):
        """Test TTS output capture and property verification."""
        session_id = "test-session-e2e-005"

        async with httpx.AsyncClient() as client:
            # Create session
            await client.post(
                f"{API_BASE}/session",
                json={"session_id": session_id}
            )

            # Inject TTS captures
            response = await client.post(
                f"{API_BASE}/tts",
                json={
                    "session_id": session_id,
                    "text": "Hello, this is a test narration.",
                    "duration_seconds": 2.5,
                    "sample_rate": 24000,
                    "file_size": 60000,
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "captured"
            assert data["duration_seconds"] == 2.5

            # Inject another capture
            response = await client.post(
                f"{API_BASE}/tts",
                json={
                    "session_id": session_id,
                    "text": "This is a second narration.",
                    "duration_seconds": 1.8,
                    "sample_rate": 24000,
                    "file_size": 43200,
                }
            )
            assert response.status_code == 200

            # Get session and verify TTS summary
            response = await client.get(f"{API_BASE}/session/{session_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["tts_summary"]["total_captures"] == 2
            assert data["tts_summary"]["total_duration"] == 4.3
            assert data["tts_summary"]["average_duration"] == 2.15

            # Verify TTS properties
            response = await client.post(
                f"{API_BASE}/verify",
                json={"session_id": session_id}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["tts_properties_verified"]["verified"] == True
            assert data["tts_properties_verified"]["total_captures"] == 2

            # Cleanup
            await client.delete(f"{API_BASE}/session/{session_id}")

    @pytest.mark.asyncio
    async def test_complex_narration_scenario(self):
        """Test a complex scenario with mixed urgency and timing."""
        session_id = "test-session-e2e-006"

        async with httpx.AsyncClient() as client:
            # Create session
            await client.post(
                f"{API_BASE}/session",
                json={"session_id": session_id}
            )

            # Simulate realistic scenario:
            # 1. Critical alert arrives immediately
            await client.post(
                f"{API_BASE}/inject",
                json={
                    "session_id": session_id,
                    "results": [
                        {
                            "intent_id": "intent-critical",
                            "topic_id": "alerts",
                            "summary": "System overload detected",
                            "urgency": "critical"
                        }
                    ]
                }
            )

            # 2. User speaks (simulated by delay)
            await asyncio.sleep(2)

            # 3. High priority result arrives
            await client.post(
                f"{API_BASE}/inject",
                json={
                    "session_id": session_id,
                    "results": [
                        {
                            "intent_id": "intent-high",
                            "topic_id": "status",
                            "summary": "Pod status updated",
                            "urgency": "high"
                        }
                    ]
                }
            )

            # 4. Normal batched results arrive
            await asyncio.sleep(1)
            await client.post(
                f"{API_BASE}/inject",
                json={
                    "session_id": session_id,
                    "results": [
                        {
                            "intent_id": "intent-normal-1",
                            "topic_id": "logs",
                            "summary": "Log entries collected",
                            "urgency": "normal"
                        },
                        {
                            "intent_id": "intent-normal-2",
                            "topic_id": "metrics",
                            "summary": "Metrics updated",
                            "urgency": "normal"
                        }
                    ]
                }
            )

            # 5. Low priority result arrives later
            await asyncio.sleep(6)  # Beyond batching window
            await client.post(
                f"{API_BASE}/inject",
                json={
                    "session_id": session_id,
                    "results": [
                        {
                            "intent_id": "intent-low",
                            "topic_id": "background",
                            "summary": "Background task completed",
                            "urgency": "low"
                        }
                    ]
                }
            )

            # Verify overall properties
            response = await client.post(
                f"{API_BASE}/verify",
                json={"session_id": session_id, "expected_window_seconds": 10.0}
            )
            assert response.status_code == 200
            data = response.json()

            # Should pass timing verification (within 10s window)
            assert data["timing_verified"]["verified"] == True

            # Should pass urgency ordering
            assert data["urgency_order_verified"]["verified"] == True

            # Get detailed session info
            response = await client.get(f"{API_BASE}/session/{session_id}")
            data = response.json()

            # Verify event counts
            assert data["narration_summary"]["total_events"] == 4
            assert data["narration_summary"]["total_results"] == 5
            assert len(data["narration_summary"]["topics"]) >= 3

            # Verify urgency distribution
            urgencies = data["narration_summary"]["urgencies"]
            assert urgencies.count("critical") == 1
            assert urgencies.count("high") == 1
            assert urgencies.count("normal") == 2
            assert urgencies.count("low") == 1

            # Cleanup
            await client.delete(f"{API_BASE}/session/{session_id}")

    @pytest.mark.asyncio
    async def test_session_list_and_cleanup(self):
        """Test session listing and bulk cleanup."""
        async with httpx.AsyncClient() as client:
            # Clean up any existing sessions first
            await client.post(f"{API_BASE}/cleanup")

            # Create multiple sessions
            session_ids = [f"test-session-bulk-{i:03d}" for i in range(5)]
            for session_id in session_ids:
                await client.post(
                    f"{API_BASE}/session",
                    json={"session_id": session_id}
                )

            # List sessions
            response = await client.get(f"{API_BASE}/sessions")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 5
            assert set(data["sessions"]) >= set(session_ids)

            # Bulk cleanup
            response = await client.post(f"{API_BASE}/cleanup")
            assert response.status_code == 200
            data = response.json()
            assert data["deleted_count"] >= 5

            # Verify cleanup
            response = await client.get(f"{API_BASE}/sessions")
            data = response.json()
            assert data["total"] == 0


# Standalone test runner (can be executed without pytest)
async def run_tests():
    """Run all tests manually without pytest."""
    test = TestNarrationE2E()

    tests = [
        ("Session Lifecycle", test.test_narration_session_lifecycle),
        ("Event Injection", test.test_narration_event_injection),
        ("Urgency Ordering", test.test_urgency_ordering_verification),
        ("Timing Verification", test.test_timing_verification),
        ("TTS Capture", test.test_tts_capture_and_verification),
        ("Complex Scenario", test.test_complex_narration_scenario),
        ("Session Management", test.test_session_list_and_cleanup),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            await test_func()
            print(f"✓ {name}")
            passed += 1
        except Exception as e:
            print(f"✗ {name}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    # Check if server is running
    import sys
    try:
        response = httpx.get(f"{BASE_URL}/health", timeout=2.0)
        if response.status_code != 200:
            print(f"Server health check failed: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"Cannot connect to server at {BASE_URL}: {e}")
        print("Make sure the ADC server is running with: python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)

    # Run tests
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
