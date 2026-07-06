# TTS/Narration Testing Documentation

## Overview

This test module provides automated testing for TTS (Text-to-Speech) output and narration functionality without requiring actual audio output or subjective "sounds acceptable" judgment. It captures narration events and TTS properties for programmatic verification.

## Architecture

### How TTS Works in ADC

The ADC (aide-de-camp) system uses the **OpenAI Realtime API** for voice mode:

1. **Client-side TTS**: Audio generation happens in the browser via WebRTC
2. **Server-side events**: The server sends `adc.narrate_results` events via WebSocket
3. **Urgency-based narration**: Results are narrated based on urgency levels:
   - **Critical**: Interrupts immediately
   - **High**: Waits for natural pause
   - **Normal**: Batched within ~5s window
   - **Low**: Only if conversation is idle

### Testing Approach

Since actual TTS happens client-side, this test module:
1. **Captures narration events** that would be sent to the client
2. **Verifies timing** matches expected batching windows
3. **Verifies urgency ordering** (critical before high before normal/low)
4. **Captures mock TTS output** with expected properties (duration, sample rate, file size)
5. **Provides programmatic verification** instead of subjective audio checks

## API Endpoints

### Session Management

#### Create Narration Session
```http
POST /api/v1/test/narration/session
Content-Type: application/json

{
  "session_id": "test-session-001",
  "voice": "alloy"
}

Response:
{
  "status": "created",
  "session_id": "test-session-001",
  "voice": "alloy",
  "created_at": 1625097600.0
}
```

#### Get Session Details
```http
GET /api/v1/test/narration/session/{session_id}

Response:
{
  "session_id": "test-session-001",
  "voice": "alloy",
  "created_at": 1625097600.0,
  "narration_summary": {
    "total_events": 3,
    "total_results": 5,
    "urgencies": ["critical", "high", "normal", "normal", "low"],
    "topics": ["alerts", "status", "logs"]
  },
  "tts_summary": {
    "total_captures": 5,
    "total_duration": 12.5,
    "average_duration": 2.5,
    "total_size": 300000,
    "voice": "alloy"
  },
  "events": [...],
  "tts_captures": [...]
}
```

#### Delete Session
```http
DELETE /api/v1/test/narration/session/{session_id}

Response:
{
  "status": "deleted",
  "session_id": "test-session-001"
}
```

### Event Injection

#### Inject Narration Event
```http
POST /api/v1/test/narration/inject
Content-Type: application/json

{
  "session_id": "test-session-001",
  "results": [
    {
      "intent_id": "intent-001",
      "topic_id": "topic-001",
      "summary": "Critical system alert",
      "urgency": "critical"
    }
  ],
  "grouped_by_topic": {
    "topic-001": ["Critical system alert"]
  }
}

Response:
{
  "status": "injected",
  "event_id": "event-uuid",
  "timestamp": 1625097605.0,
  "result_count": 1
}
```

#### Inject TTS Capture
```http
POST /api/v1/test/narration/tts
Content-Type: application/json

{
  "session_id": "test-session-001",
  "text": "The text that was spoken",
  "duration_seconds": 2.5,
  "sample_rate": 24000,
  "file_size": 60000
}

Response:
{
  "status": "captured",
  "utterance_id": "utterance-uuid",
  "timestamp": 1625097610.0,
  "text": "The text that was spoken",
  "duration_seconds": 2.5
}
```

### Verification

#### Verify Narration Properties
```http
POST /api/v1/test/narration/verify
Content-Type: application/json

{
  "session_id": "test-session-001",
  "expected_window_seconds": 5.0
}

Response:
{
  "session_id": "test-session-001",
  "timing_verified": {
    "verified": true,
    "expected_window_seconds": 5.0,
    "intervals": [1.0, 2.5, 1.5],
    "average_interval": 1.67,
    "max_interval": 2.5,
    "event_count": 4
  },
  "urgency_order_verified": {
    "verified": true,
    "urgency_sequence": ["critical", "high", "normal", "normal", "low"],
    "priority_sequence": [0, 1, 2, 2, 3],
    "total_checked": 5
  },
  "tts_properties_verified": {
    "verified": true,
    "total_captures": 5,
    "invalid_captures": []
  },
  "overall_verified": true
}
```

### Bulk Operations

#### List All Sessions
```http
GET /api/v1/test/narration/sessions

Response:
{
  "sessions": ["session-001", "session-002", "session-003"],
  "total": 3
}
```

#### Clean Up All Sessions
```http
POST /api/v1/test/narration/cleanup

Response:
{
  "status": "cleaned",
  "deleted_count": 3
}
```

## Verification Criteria

### 1. Timing Verification

Narration events should be batched within the expected window:

- **Default window**: 5.0 seconds
- **Critical results**: Should interrupt immediately
- **High urgency**: Should wait for pause
- **Normal/Low**: Should be batched

**Success criteria**: All intervals between events are within the expected window.

### 2. Urgency Ordering Verification

Results should be narrated in correct urgency order:

**Priority order** (highest to lowest):
1. Critical (priority 0)
2. High (priority 1)
3. Normal (priority 2)
4. Low (priority 3)

**Success criteria**: Priority sequence is non-decreasing.

### 3. TTS Properties Verification

TTS output should have valid properties:

**Required properties**:
- `duration_seconds > 0`: Audio has positive duration
- `sample_rate > 0`: Valid audio sample rate (typically 24000 Hz)
- `file_size > 0`: Non-zero file size
- `len(text) > 0`: Non-empty text

**Success criteria**: All captures have valid properties.

## Usage Examples

### Example 1: Basic Narration Test

```python
import httpx
import asyncio

async def test_basic_narration():
    async with httpx.AsyncClient() as client:
        # Create session
        await client.post(
            "http://localhost:8000/api/v1/test/narration/session",
            json={"session_id": "test-001", "voice": "alloy"}
        )

        # Inject narration event
        await client.post(
            "http://localhost:8000/api/v1/test/narration/inject",
            json={
                "session_id": "test-001",
                "results": [
                    {
                        "intent_id": "intent-001",
                        "topic_id": "alerts",
                        "summary": "System alert",
                        "urgency": "critical"
                    }
                ]
            }
        )

        # Get session details
        response = await client.get(
            "http://localhost:8000/api/v1/test/narration/session/test-001"
        )
        data = response.json()
        print(f"Total events: {data['narration_summary']['total_events']}")

        # Cleanup
        await client.delete(
            "http://localhost:8000/api/v1/test/narration/session/test-001"
        )

asyncio.run(test_basic_narration())
```

### Example 2: Urgency Ordering Test

```python
async def test_urgency_ordering():
    async with httpx.AsyncClient() as client:
        session_id = "test-002"

        # Create session
        await client.post(
            "http://localhost:8000/api/v1/test/narration/session",
            json={"session_id": session_id}
        )

        # Inject events in correct urgency order
        for urgency in ["critical", "high", "normal", "low"]:
            await client.post(
                "http://localhost:8000/api/v1/test/narration/inject",
                json={
                    "session_id": session_id,
                    "results": [{
                        "intent_id": f"intent-{urgency}",
                        "topic_id": "general",
                        "summary": f"{urgency.capitalize()} message",
                        "urgency": urgency
                    }]
                }
            )

        # Verify ordering
        response = await client.post(
            "http://localhost:8000/api/v1/test/narration/verify",
            json={"session_id": session_id}
        )
        data = response.json()
        assert data["urgency_order_verified"]["verified"] == True

        print(f"✓ Urgency ordering verified: {data['urgency_order_verified']['urgency_sequence']}")

        # Cleanup
        await client.delete(f"http://localhost:8000/api/v1/test/narration/session/{session_id}")

asyncio.run(test_urgency_ordering())
```

### Example 3: Complete Workflow

```python
async def test_complete_workflow():
    async with httpx.AsyncClient() as client:
        session_id = "test-complete-001"

        # 1. Create session
        await client.post(
            "http://localhost:8000/api/v1/test/narration/session",
            json={"session_id": session_id, "voice": "shimmer"}
        )

        # 2. Simulate realistic narration flow
        scenarios = [
            ("System overload detected", "critical"),
            ("Pod status updated", "high"),
            ("Log analysis complete", "normal"),
            ("Background sync finished", "low"),
        ]

        for text, urgency in scenarios:
            await client.post(
                "http://localhost:8000/api/v1/test/narration/inject",
                json={
                    "session_id": session_id,
                    "results": [{
                        "intent_id": f"intent-{urgency}",
                        "topic_id": "general",
                        "summary": text,
                        "urgency": urgency
                    }]
                }
            )

            # Simulate TTS output
            await client.post(
                "http://localhost:8000/api/v1/test/narration/tts",
                json={
                    "session_id": session_id,
                    "text": text,
                    "duration_seconds": len(text) / 10.0,  # Approximate
                    "sample_rate": 24000,
                    "file_size": len(text) * 100,
                }
            )

            await asyncio.sleep(0.5)  # Simulate passage of time

        # 3. Verify all properties
        response = await client.post(
            "http://localhost:8000/api/v1/test/narration/verify",
            json={"session_id": session_id, "expected_window_seconds": 10.0}
        )
        data = response.json()

        print(f"Timing verified: {data['timing_verified']['verified']}")
        print(f"Urgency ordering verified: {data['urgency_order_verified']['verified']}")
        print(f"TTS properties verified: {data['tts_properties_verified']['verified']}")
        print(f"Overall verified: {data['overall_verified']}")

        # 4. Get detailed summary
        response = await client.get(
            f"http://localhost:8000/api/v1/test/narration/session/{session_id}"
        )
        data = response.json()

        print(f"\nSession Summary:")
        print(f"  Total events: {data['narration_summary']['total_events']}")
        print(f"  Total results: {data['narration_summary']['total_results']}")
        print(f"  Topics: {data['narration_summary']['topics']}")
        print(f"  Urgencies: {data['narration_summary']['urgencies']}")
        print(f"\nTTS Summary:")
        print(f"  Total captures: {data['tts_summary']['total_captures']}")
        print(f"  Total duration: {data['tts_summary']['total_duration']:.2f}s")
        print(f"  Average duration: {data['tts_summary']['average_duration']:.2f}s")

        # 5. Cleanup
        await client.delete(f"http://localhost:8000/api/v1/test/narration/session/{session_id}")
        print("\n✓ Test completed successfully")

asyncio.run(test_complete_workflow())
```

## Running Tests

### With pytest

```bash
# Run all narration tests
pytest tests/e2e/test_narration.py -v

# Run specific test
pytest tests/e2e/test_narration.py::TestNarrationE2E::test_urgency_ordering_verification -v

# Run with coverage
pytest tests/e2e/test_narration.py --cov=src.test.narration -v
```

### Standalone (without pytest)

```bash
# Make sure server is running
python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# Run tests
python3 tests/e2e/test_narration.py
```

## Integration with Real Voice Sessions

To test narration with actual voice sessions:

1. **Start a voice session** via the `/voice` WebSocket endpoint
2. **Dispatch intents** using `POST /dispatch` or `POST /api/v1/test/dispatch`
3. **Wait for results** to arrive via the result listener
4. **Verify narration** using the test endpoints

The narration events sent to the client (`adc.narrate_results`) can be captured and verified using the same structure as the test injections.

## Troubleshooting

### Common Issues

1. **Server not running**: Make sure ADC server is running at `http://localhost:8000`
2. **Session not found**: Ensure you create a session before injecting events
3. **Verification failures**: Check urgency ordering and timing intervals
4. **TTS property failures**: Ensure duration, sample rate, and file_size are positive

### Debug Mode

Enable debug logging to see detailed test execution:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Related Files

- **Test module**: `src/test/narration.py`
- **E2E tests**: `tests/e2e/test_narration.py`
- **Realtime session**: `src/realtime/session.py`
- **Voice prompt**: `prompts/voice.md`

## Summary

This test module provides:
- ✓ Automated narration testing without audio output
- ✓ Timing verification for batching windows
- ✓ Urgency ordering verification
- ✓ TTS property verification
- ✓ Programmatic assertions instead of subjective checks
- ✓ Integration with existing test infrastructure

Use these endpoints to verify narration behavior in CI/CD pipelines and local development without requiring manual audio inspection.
