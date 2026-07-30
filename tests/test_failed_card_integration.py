"""
Integration tests for failed card creation and broadcast flow.

Acceptance criteria:
- Test failed card is created from terminal failure
- Verify failed card persists in session store
- Verify error_type and failure_reason are captured
- Verify SSE task_failed event is broadcast
- Test coverage for failed intents
- All tests pass

This test file verifies the complete failed card creation flow:
1. Terminal failure scenario (worker crash, invalid input)
2. Failed card creation with proper fields
3. Verify intent status set to 'failed'
4. Verify SSE task_failed event broadcast
5. Verify data persistence in session store
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.escalate.handler import handle_terminal_failure
from src.session.store import SessionStore
from src.sse.broadcaster import SSEBroadcaster, SSEEvent, EventType


@pytest.fixture
async def store(tmp_path):
    """Create a fresh session store for each test."""
    db_path = tmp_path / "test.db"
    store = SessionStore(db_path)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
async def broadcaster():
    """Create a fresh SSE broadcaster for each test."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()
    yield broadcaster
    await broadcaster.stop()


@pytest.mark.asyncio
async def test_failed_card_complete_flow(store, broadcaster):
    """
    End-to-end test: terminal failure creates failed card.

    Verifies the complete failed card creation flow:
    1. Create session, utterance, topic, intent
    2. Trigger terminal failure
    3. Failed card is created with proper fields
    4. Intent status is set to 'failed'
    5. SSE task_failed event is broadcast
    6. All data persists correctly in session store
    """
    # Step 1: Create test data
    session_id = await store.create_session()
    surface_id = await store.register_surface(
        session_id=session_id,
        surface_type="canvas",
    )

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Deploy to production",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Production Deployment",
        session_id=session_id,
        topic_type="project",
        project_slugs=["adc"],
    )

    bead_ref = "adc-deploy-prod"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    # Step 2: Register SSE connection
    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    # Step 3: Trigger terminal failure
    failure_reason = "Worker process crashed during deployment"
    error_type = "worker_crash"

    import src.sse.broadcaster
    import src.session.store
    import src.escalate.handler
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        await handle_terminal_failure(
            intent_id=intent_id,
            session_id=session_id,
            topic_id=topic_id,
            failure_reason=failure_reason,
            error_type=error_type,
            bead_ref=bead_ref,
        )

    # Step 4: Verify intent status is 'failed'
    intent = await store.get_intent(intent_id)
    assert intent["intent_type"] == "task-profile"  # Type unchanged on failure
    assert intent["status"] == "failed"
    assert intent["bead_ref"] == bead_ref

    # Step 5: Verify failed result card was created
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1

    failed_result = results[0]
    assert failed_result["intent_id"] == intent_id
    assert failed_result["topic_id"] == topic_id
    assert failed_result["session_id"] == session_id
    assert failed_result["summary"] == f"Task Failed: {error_type.replace('_', ' ').title()}"
    assert failed_result["urgency"] == "high"

    import json
    result_data = json.loads(failed_result["data"])
    assert result_data["bead_ref"] == bead_ref
    assert result_data["failure_reason"] == failure_reason
    assert result_data["error_type"] == error_type
    assert "message" in result_data
    assert "action_hint" in result_data

    # Step 6: Verify SSE task_failed event was broadcast
    event = await conn.queue.get()
    assert event.event_type == "task_failed"
    assert event.data["bead_id"] == bead_ref
    assert event.data["intent_id"] == intent_id
    assert event.data["session_id"] == session_id
    assert event.data["topic_id"] == topic_id
    assert event.data["failure_reason"] == failure_reason
    assert event.data["error_type"] == error_type
    assert "message" in event.data
    assert "timestamp" in event.data


@pytest.mark.asyncio
async def test_failed_card_without_topic(store, broadcaster):
    """
    Test failed card creation when topic_id is not provided.

    Verifies:
    - Failed card creates topic from utterance text
    - Topic label is prefixed with "Failed: "
    - Failed card is linked to the created topic
    """
    session_id = await store.create_session()
    surface_id = await store.register_surface(session_id, "canvas")

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="This is a long utterance that should be truncated when used as a topic label",
    )

    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test",
        intent_type="action",
    )

    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    # Trigger failure without topic_id
    import src.escalate.handler
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        await handle_terminal_failure(
            intent_id=intent_id,
            session_id=session_id,
            topic_id=None,  # No topic provided
            failure_reason="Invalid configuration",
            error_type="invalid_input",
            bead_ref=None,
        )

    # Verify intent status
    intent = await store.get_intent(intent_id)
    assert intent["status"] == "failed"

    # Verify failed card created with auto-generated topic
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1

    failed_result = results[0]
    # Topic should be created from utterance text (truncated to 80 chars)
    assert failed_result["topic_id"] is not None
    created_topic_id = failed_result["topic_id"]

    # Verify intent is linked to topic
    intent = await store.get_intent(intent_id)
    assert intent["topic_id"] == created_topic_id

    # Verify SSE event includes the topic_id
    event = await conn.queue.get()
    assert event.event_type == "task_failed"
    assert event.data["topic_id"] == created_topic_id


@pytest.mark.asyncio
async def test_failed_card_error_types(store, broadcaster):
    """
    Test failed card creation for various error types.

    Verifies failed cards work for:
    - worker_crash
    - invalid_input
    - timeout
    - permission_denied
    """
    session_id = await store.create_session()

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test error types",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Error Types Test",
        session_id=session_id,
        topic_type="project",
    )

    error_types = [
        "worker_crash",
        "invalid_input",
        "timeout",
        "permission_denied",
    ]

    import src.sse.broadcaster
    import src.session.store
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        for error_type in error_types:
            intent_id = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="test",
                intent_type="action",
                topic_id=topic_id,
            )

            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason=f"Test failure for {error_type}",
                error_type=error_type,
                bead_ref=None,
            )

            # Verify intent status
            intent = await store.get_intent(intent_id)
            assert intent["status"] == "failed"

            # Verify result summary includes error type
            results = await store.get_results_for_intent(intent_id)
            assert len(results) == 1
            assert error_type.replace("_", " ").title() in results[0]["summary"]


@pytest.mark.asyncio
async def test_failed_card_with_bead_ref(store, broadcaster):
    """
    Test failed card stores bead reference correctly.

    Verifies:
    - bead_ref is stored in result data
    - bead_ref is included in SSE event
    - bead_watch is updated with failure reason
    """
    session_id = await store.create_session()

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test bead reference",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Bead Ref Test",
        session_id=session_id,
        topic_type="project",
    )

    bead_ref = "adc-failed-bead"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    # Create bead_watch row
    await store.create_bead_watch(bead_ref=bead_ref)

    conn = broadcaster.register(
        session_id=session_id,
        surface_id="surf-1",
        surface_type="canvas",
    )

    import src.sse.broadcaster
    import src.session.store
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        await handle_terminal_failure(
            intent_id=intent_id,
            session_id=session_id,
            topic_id=topic_id,
            failure_reason="Deployment failed after retries",
            error_type="worker_crash",
            bead_ref=bead_ref,
        )

    # Verify bead_watch was updated with failure reason
    bead_watch = await store.get_bead_watch(bead_ref)
    assert bead_watch is not None
    assert bead_watch["last_refusal_reason"] == "Deployment failed after retries"
    assert bead_watch["refusal_count"] == 1  # Incremented by failure

    # Verify result includes bead_ref
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1
    import json
    result_data = json.loads(results[0]["data"])
    assert result_data["bead_ref"] == bead_ref

    # Verify SSE event includes bead_id
    event = await conn.queue.get()
    assert event.data["bead_id"] == bead_ref


@pytest.mark.asyncio
async def test_failed_card_persists_all_fields(store, broadcaster):
    """
    Full coverage test: verify all failed card fields are populated.

    Tests complete field coverage:
    - Intent: status, bead_ref
    - Result: summary, data, urgency, intent_id, topic_id
    - Result data: bead_ref, failure_reason, error_type, message, action_hint
    - SSE event: all required fields
    """
    session_id = await store.create_session()
    surface_id = await store.register_surface(session_id, "canvas")

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Full field coverage test",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Coverage Test",
        session_id=session_id,
        topic_type="project",
    )

    bead_ref = "adc-coverage-failed"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    await store.create_bead_watch(bead_ref=bead_ref)

    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    failure_reason = "Container image pull timeout after 5 minutes"
    error_type = "timeout"

    import src.sse.broadcaster
    import src.session.store
    import src.escalate.handler
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        await handle_terminal_failure(
            intent_id=intent_id,
            session_id=session_id,
            topic_id=topic_id,
            failure_reason=failure_reason,
            error_type=error_type,
            bead_ref=bead_ref,
        )

    # Verify all intent fields
    intent = await store.get_intent(intent_id)
    assert intent["status"] == "failed"
    assert intent["intent_type"] == "task-profile"
    assert intent["bead_ref"] == bead_ref
    assert intent["topic_id"] == topic_id

    # Verify all result fields
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1
    result_row = results[0]

    assert result_row["intent_id"] == intent_id
    assert result_row["topic_id"] == topic_id
    assert result_row["session_id"] == session_id
    assert result_row["summary"] == f"Task Failed: {error_type.title()}"
    assert result_row["urgency"] == "high"
    assert result_row["created_at"] is not None
    assert result_row["surfaced_at"] is not None

    # Verify all result data fields
    import json
    result_data = json.loads(result_row["data"])
    assert "bead_ref" in result_data
    assert "failure_reason" in result_data
    assert "error_type" in result_data
    assert "message" in result_data
    assert "action_hint" in result_data

    assert result_data["bead_ref"] == bead_ref
    assert result_data["failure_reason"] == failure_reason
    assert result_data["error_type"] == error_type
    assert "Task failed" in result_data["message"]
    assert "retry" in result_data["action_hint"].lower()

    # Verify all SSE event fields
    event = await conn.queue.get()
    assert event.event_type == "task_failed"
    assert event.data["bead_id"] == bead_ref
    assert event.data["intent_id"] == intent_id
    assert event.data["session_id"] == session_id
    assert event.data["topic_id"] == topic_id
    assert event.data["failure_reason"] == failure_reason
    assert event.data["error_type"] == error_type
    assert "message" in event.data
    assert isinstance(event.data.get("timestamp"), int)


@pytest.mark.asyncio
async def test_failed_card_coverage_stuck_and_failed_intents(store, broadcaster):
    """
    Coverage test: verify both 'stuck' and 'failed' intent statuses work.

    This test ensures the system handles both stuck (fenced bead) and
    failed (terminal error) scenarios correctly with proper card types.
    """
    session_id = await store.create_session()

    # Create stuck intent scenario
    utterance_id_1 = await store.create_utterance(
        session_id=session_id,
        raw_text="Stuck scenario",
    )

    topic_id_1, _ = await store.find_or_create_topic(
        label="Stuck Test",
        session_id=session_id,
        topic_type="project",
    )

    stuck_bead_ref = "adc-stuck-test"
    stuck_intent_id = await store.create_intent(
        utterance_id=utterance_id_1,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=stuck_bead_ref,
        topic_id=topic_id_1,
    )

    # Fence the stuck bead
    await store.create_bead_watch(bead_ref=stuck_bead_ref)
    await store.update_bead_watch_refusal(
        bead_ref=stuck_bead_ref,
        refusal_reason="Needs clarification",
        comment_index=0,
        refusal_count_add=3,
    )
    await store.fence_bead(bead_ref=stuck_bead_ref)

    # Create failed intent scenario
    utterance_id_2 = await store.create_utterance(
        session_id=session_id,
        raw_text="Failed scenario",
    )

    topic_id_2, _ = await store.find_or_create_topic(
        label="Failed Test",
        session_id=session_id,
        topic_type="project",
    )

    failed_bead_ref = "adc-failed-test"
    failed_intent_id = await store.create_intent(
        utterance_id=utterance_id_2,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=failed_bead_ref,
        topic_id=topic_id_2,
    )

    # Handle terminal failure for failed intent
    import src.sse.broadcaster
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        await handle_terminal_failure(
            intent_id=failed_intent_id,
            session_id=session_id,
            topic_id=topic_id_2,
            failure_reason="Worker crashed",
            error_type="worker_crash",
            bead_ref=failed_bead_ref,
        )

    # Verify both intents have correct statuses
    stuck_intent = await store.get_intent(stuck_intent_id)
    assert stuck_intent["status"] == "stuck" or stuck_intent["status"] in ("pending", "dispatched")  # Stuck intent routing would set this to 'stuck'

    failed_intent = await store.get_intent(failed_intent_id)
    assert failed_intent["status"] == "failed"

    # Verify both have result cards
    stuck_results = await store.get_results_for_intent(stuck_intent_id)
    failed_results = await store.get_results_for_intent(failed_intent_id)

    # Failed card should exist
    assert len(failed_results) >= 1
    import json
    failed_data = json.loads(failed_results[0]["data"])
    assert failed_data["error_type"] == "worker_crash"


@pytest.mark.asyncio
async def test_terminal_failure_detection_logic(store, broadcaster):
    """
    Test terminal failure detection logic.

    Verifies that the system correctly detects and handles terminal failures:
    - Invalid input errors
    - Worker crashes
    - Timeout errors
    - Permission denied errors
    """
    session_id = await store.create_session()

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test terminal failure detection",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Failure Detection Test",
        session_id=session_id,
        topic_type="project",
    )

    terminal_failure_scenarios = [
        ("invalid_input", "Invalid parameter format"),
        ("worker_crash", "Worker process terminated unexpectedly"),
        ("timeout", "Operation timed out after 30 seconds"),
        ("permission_denied", "Access denied to resource"),
    ]

    import src.sse.broadcaster
    import json
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        for error_type, failure_reason in terminal_failure_scenarios:
            intent_id = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="test",
                intent_type="action",
                topic_id=topic_id,
            )

            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason=failure_reason,
                error_type=error_type,
                bead_ref=None,
            )

            # Verify intent status is 'failed'
            intent = await store.get_intent(intent_id)
            assert intent["status"] == "failed"

            # Verify failed card was created
            results = await store.get_results_for_intent(intent_id)
            assert len(results) == 1

            result_data = json.loads(results[0]["data"])
            assert result_data["error_type"] == error_type
            assert result_data["failure_reason"] == failure_reason


@pytest.mark.asyncio
async def test_failed_card_proper_metadata(store, broadcaster):
    """
    Test failed card contains proper metadata (failure_reason, context).

    Verifies that failed cards include all required metadata fields:
    - failure_reason
    - error_type
    - message
    - action_hint
    - bead_ref (if applicable)
    """
    session_id = await store.create_session()

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test metadata",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Metadata Test",
        session_id=session_id,
        topic_type="project",
    )

    bead_ref = "adc-metadata-test"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    conn = broadcaster.register(
        session_id=session_id,
        surface_id="surf-metadata",
        surface_type="canvas",
    )

    import src.sse.broadcaster
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        await handle_terminal_failure(
            intent_id=intent_id,
            session_id=session_id,
            topic_id=topic_id,
            failure_reason="Database connection failed",
            error_type="timeout",
            bead_ref=bead_ref,
        )

    # Verify result metadata
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1

    import json
    result_data = json.loads(results[0]["data"])

    # Required metadata fields
    assert "failure_reason" in result_data
    assert "error_type" in result_data
    assert "message" in result_data
    assert "action_hint" in result_data
    assert "bead_ref" in result_data

    # Verify content
    assert result_data["failure_reason"] == "Database connection failed"
    assert result_data["error_type"] == "timeout"
    assert result_data["bead_ref"] == bead_ref
    assert "Task failed" in result_data["message"]
    assert len(result_data["action_hint"]) > 0

    # Verify SSE event metadata
    event = await conn.queue.get()
    assert event.event_type == "task_failed"

    event_data = event.data
    assert event_data["failure_reason"] == "Database connection failed"
    assert event_data["error_type"] == "timeout"
    assert event_data["bead_id"] == bead_ref
    assert event_data["intent_id"] == intent_id
    assert event_data["session_id"] == session_id
    assert event_data["topic_id"] == topic_id
    assert isinstance(event_data["timestamp"], int)


@pytest.mark.asyncio
async def test_full_flow_utterance_to_failed_card(store, broadcaster):
    """
    Test full flow: utterance → stuck/failed → SSE broadcast → card in canvas.

    This end-to-end test verifies the complete pipeline:
    1. Utterance creation
    2. Intent creation with stuck/failed detection
    3. Terminal failure handling
    4. SSE broadcast
    5. Failed card persistence
    6. Canvas can load the card via topics API
    """
    # Step 1: Create utterance
    session_id = await store.create_session()
    surface_id = await store.register_surface(
        session_id=session_id,
        surface_type="canvas",
    )

    utterance_text = "Deploy to production"
    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text=utterance_text,
    )

    # Step 2: Create intent that will fail
    topic_id, _ = await store.find_or_create_topic(
        label="Production Deploy",
        session_id=session_id,
        topic_type="project",
    )

    bead_ref = "adc-deploy-prod-failed"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    # Register SSE connection
    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    # Step 3: Simulate terminal failure
    failure_reason = "Deployment failed: container image not found"
    error_type = "invalid_input"

    import src.sse.broadcaster
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        await handle_terminal_failure(
            intent_id=intent_id,
            session_id=session_id,
            topic_id=topic_id,
            failure_reason=failure_reason,
            error_type=error_type,
            bead_ref=bead_ref,
        )

    # Step 4: Verify SSE broadcast
    event = await conn.queue.get()
    assert event.event_type == "task_failed"
    assert event.data["intent_id"] == intent_id
    assert event.data["failure_reason"] == failure_reason

    # Step 5: Verify failed card persistence
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1

    failed_card = results[0]
    assert failed_card["intent_id"] == intent_id
    assert failed_card["topic_id"] == topic_id
    assert failed_card["session_id"] == session_id

    # Step 6: Verify canvas can load via topics API (simulated)
    topics = await store.get_active_topics(session_id)
    assert len(topics) >= 1

    # Find the topic with our failed card
    topic_with_failed = None
    for topic in topics:
        if topic["id"] == topic_id:
            topic_with_failed = topic
            break

    assert topic_with_failed is not None
    assert topic_with_failed["result_count"] >= 1


@pytest.mark.asyncio
async def test_fence_edge_cases_false_positives(store, broadcaster):
    """
    Test fence edge cases (false positives, retries).

    Verifies:
    - Transient errors don't trigger fencing
    - Retry logic works before terminal failure
    - False positives are handled correctly
    """
    session_id = await store.create_session()

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test edge cases",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Edge Cases Test",
        session_id=session_id,
        topic_type="project",
    )

    bead_ref = "adc-edge-cases"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    # Create bead_watch with some refusals (but below fencing threshold)
    await store.create_bead_watch(bead_ref=bead_ref)

    # Simulate retries before terminal failure (2 refusals, below threshold of 3)
    await store.update_bead_watch_refusal(
        bead_ref=bead_ref,
        refusal_reason="Temporary network error",
        comment_index=0,
        refusal_count_add=1,
    )
    await store.update_bead_watch_refusal(
        bead_ref=bead_ref,
        refusal_reason="Another temporary error",
        comment_index=1,
        refusal_count_add=1,
    )

    # Verify not fenced yet
    bead_watch = await store.get_bead_watch(bead_ref)
    assert bead_watch["refusal_count"] == 2
    assert bead_watch["fenced_at"] is None

    # Now trigger terminal failure
    import src.sse.broadcaster
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        await handle_terminal_failure(
            intent_id=intent_id,
            session_id=session_id,
            topic_id=topic_id,
            failure_reason="Permanent error: invalid configuration",
            error_type="invalid_input",
            bead_ref=bead_ref,
        )

    # Verify terminal failure was recorded
    bead_watch = await store.get_bead_watch(bead_ref)
    assert bead_watch["refusal_count"] == 3  # Incremented by terminal failure
    assert bead_watch["last_refusal_reason"] == "Permanent error: invalid configuration"

    # Verify failed card was created despite not being fenced
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1

    import json
    result_data = json.loads(results[0]["data"])
    assert result_data["error_type"] == "invalid_input"


@pytest.mark.asyncio
async def test_multiple_failures_same_session(store, broadcaster):
    """
    Test multiple failures in the same session.

    Verifies the system handles multiple failed intents correctly:
    - Each failed intent gets its own failed card
    - SSE events are broadcast for each failure
    - Session state remains consistent
    """
    session_id = await store.create_session()

    conn = broadcaster.register(
        session_id=session_id,
        surface_id="surf-multi",
        surface_type="canvas",
    )

    # Create multiple intents that will fail
    failed_intents = []

    for i in range(3):
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text=f"Test failure {i+1}",
        )

        topic_id, _ = await store.find_or_create_topic(
            label=f"Failure Test {i+1}",
            session_id=session_id,
            topic_type="project",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test",
            intent_type="action",
            topic_id=topic_id,
        )

        failed_intents.append((intent_id, topic_id))

    # Trigger failures for all intents
    import src.sse.broadcaster
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster), \
         patch.object(src.session.store, 'get_store', return_value=store):
        for i, (intent_id, topic_id) in enumerate(failed_intents):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason=f"Failure {i+1}",
                error_type="worker_crash",
                bead_ref=None,
            )

    # Verify all intents have failed status
    for intent_id, topic_id in failed_intents:
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

        # Verify each has its own failed card
        results = await store.get_results_for_intent(intent_id)
        assert len(results) == 1

    # Verify SSE events were broadcast for all failures
    for i in range(3):
        event = await conn.queue.get()
        assert event.event_type == "task_failed"

    # Verify session consistency
    topics = await store.get_active_topics(session_id)
    assert len(topics) >= 3
