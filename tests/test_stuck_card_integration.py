"""
End-to-end integration test for stuck card creation flow (bead adc-4pwlf).

Acceptance criteria:
- Test creates a fenced bead scenario
- Verifies stuck card is created
- Verifies card persists in session store
- Verifies refusal_reason is captured
- Verifies bead_id and reference are stored
- Test passes with full coverage

This test verifies the complete stuck card creation flow:
1. Create session, utterance, and intent with bead_ref
2. Create bead_watch row and fence the bead
3. Trigger intent router escalation with fenced bead detection
4. Verify stuck card is created with proper fields
5. Verify SSE task_stuck event is broadcast
6. Verify all data persists correctly in session store
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.intent.router import IntentRouter, RoutedIntent, IntentClassification, IntentType
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
async def test_stuck_card_complete_flow(store, broadcaster):
    """
    End-to-end test: fenced bead scenario creates stuck card.

    Verifies the complete stuck card creation flow:
    1. Create fenced bead scenario (session, utterance, intent, bead_watch)
    2. Trigger intent router escalation
    3. Router detects fenced bead in session
    4. Creates stuck card instead of escalating
    5. Broadcasts SSE task_stuck event
    6. All data persists correctly in session store
    """
    # Step 1: Create test data - session, utterance, topic, intent
    session_id = await store.create_session()
    surface_id = await store.register_surface(
        session_id=session_id,
        surface_type="canvas",
    )

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Implement feature X",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Implement feature X",
        session_id=session_id,
        topic_type="project",
        project_slugs=["adc"],
    )

    bead_ref = "adc-stuck-test-123"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    # Step 2: Create bead_watch and fence it (simulating circuit breaker)
    await store.create_bead_watch(
        bead_ref=bead_ref,
        sla_hours=24,
        intent_type="task-profile",
    )

    # Simulate refusals that triggered fencing
    refusal_reason = "Missing context: need clarification on feature X requirements"
    await store.update_bead_watch_refusal(
        bead_ref=bead_ref,
        refusal_reason=refusal_reason,
        comment_index=2,
        refusal_count_add=3,  # At circuit breaker threshold
    )

    # Fence the bead
    await store.fence_bead(bead_ref=bead_ref)

    # Verify bead is fenced
    fenced_beads = await store.get_fenced_beads_for_session(session_id)
    assert len(fenced_beads) == 1
    assert fenced_beads[0]["bead_ref"] == bead_ref
    assert fenced_beads[0]["fenced_at"] is not None

    # Step 3: Create intent router and trigger escalation
    router = IntentRouter(store=store)

    routed_intent = RoutedIntent(
        intent_id=intent_id,
        classification=IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="adc",
            confidence=0.9,
            utterance_fragment="Implement feature X",
        ),
        session_id=session_id,
        utterance="Implement feature X",
        router_ms=100,
    )

    # Register SSE connection
    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    # Step 4: Process intent - should detect fenced bead and create stuck card
    # Patch get_broadcaster to use our test broadcaster
    import src.intent.router
    with patch.object(src.intent.router, 'get_broadcaster', return_value=broadcaster):
        timings = MagicMock()
        result = await router._escalate_to_bead(routed_intent, timings)

    # Step 5: Verify stuck card was created
    assert result["status"] == "stuck"
    assert result["intent_type"] == "stuck"
    assert result["bead_id"] == bead_ref
    assert "stuck_reason" in result
    assert result["stuck_reason"] == refusal_reason
    assert "refusal_count" in result
    assert result["refusal_count"] == 3
    assert "topic_id" in result
    assert "result_id" in result

    # Step 6: Verify data persists in session store
    # Intent should have type='stuck' and status='stuck'
    intent = await store.get_intent(intent_id)
    assert intent["intent_type"] == "stuck"
    assert intent["status"] == "stuck"
    assert intent["bead_ref"] == bead_ref

    # Result should contain stuck card data
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1

    stuck_result = results[0]
    assert stuck_result["intent_id"] == intent_id
    assert stuck_result["topic_id"] == result["topic_id"]
    assert stuck_result["summary"] == "Task stuck — needs your input"
    assert stuck_result["urgency"] == "high"

    import json
    result_data = json.loads(stuck_result["data"])
    assert result_data["bead_id"] == bead_ref
    assert result_data["stuck_reason"] == refusal_reason
    assert result_data["refusal_count"] == 3
    assert "message" in result_data
    assert "action_hint" in result_data
    assert result_data["fence_detected_during"] == "intent_routing"

    # Step 7: Verify SSE task_stuck event was broadcast
    event = await conn.queue.get()
    assert event.event_type == "task_stuck"
    assert event.data["bead_id"] == bead_ref
    assert event.data["stuck_reason"] == refusal_reason
    assert event.data["refusal_count"] == 3
    assert event.data["intent_id"] == intent_id
    assert event.data["session_id"] == session_id
    assert event.data["topic_id"] == result["topic_id"]
    assert "timestamp" in event.data


@pytest.mark.asyncio
async def test_stuck_card_persists_refusal_reason(store, broadcaster):
    """
    Test that refusal_reason is captured and persisted correctly.

    Verifies:
    - Refusal reason is stored in bead_watch
    - Refusal reason is copied to stuck card result
    - Refusal reason is included in SSE event
    """
    session_id = await store.create_session()
    surface_id = await store.register_surface(session_id, "canvas")

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test task",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Test",
        session_id=session_id,
        topic_type="project",
    )

    bead_ref = "adc-refusal-test"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    # Create bead watch with specific refusal reason
    refusal_reason = "REFUSED: Missing user input for configuration"
    await store.create_bead_watch(bead_ref=bead_ref)
    await store.update_bead_watch_refusal(
        bead_ref=bead_ref,
        refusal_reason=refusal_reason,
        comment_index=0,
        refusal_count_add=1,
    )
    await store.fence_bead(bead_ref=bead_ref)

    # Verify refusal reason persists in bead_watch
    bead_watch = await store.get_bead_watch(bead_ref)
    assert bead_watch["last_refusal_reason"] == refusal_reason

    # Create router and process intent
    router = IntentRouter(store=store)
    routed_intent = RoutedIntent(
        intent_id=intent_id,
        classification=IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="adc",
        ),
        session_id=session_id,
        utterance="Test task",
    )

    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    import src.intent.router
    with patch.object(src.intent.router, 'get_broadcaster', return_value=broadcaster):
        result = await router._escalate_to_bead(routed_intent, MagicMock())

    # Verify refusal reason in result
    assert result["stuck_reason"] == refusal_reason

    # Verify refusal reason in persisted result
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1
    import json
    result_data = json.loads(results[0]["data"])
    assert result_data["stuck_reason"] == refusal_reason

    # Verify refusal reason in SSE event
    event = await conn.queue.get()
    assert event.data["stuck_reason"] == refusal_reason


@pytest.mark.asyncio
async def test_stuck_card_stores_bead_reference(store, broadcaster):
    """
    Test that bead_id and reference are stored correctly.

    Verifies:
    - bead_ref is stored in intent
    - bead_id is stored in result data
    - Bead reference is queryable via session API
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

    bead_ref = "adc-bead-ref-456"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    # Fence the bead
    await store.create_bead_watch(bead_ref=bead_ref)
    await store.fence_bead(bead_ref=bead_ref)

    # Process intent
    router = IntentRouter(store=store)
    routed_intent = RoutedIntent(
        intent_id=intent_id,
        classification=IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="adc",
        ),
        session_id=session_id,
        utterance="Test bead reference",
    )

    import src.intent.router
    with patch.object(src.intent.router, 'get_broadcaster', return_value=broadcaster):
        await router._escalate_to_bead(routed_intent, MagicMock())

    # Verify bead_ref stored in intent
    intent = await store.get_intent(intent_id)
    assert intent["bead_ref"] == bead_ref

    # Verify bead_id stored in result data
    results = await store.get_results_for_intent(intent_id)
    import json
    result_data = json.loads(results[0]["data"])
    assert result_data["bead_id"] == bead_ref

    # Verify bead is queryable via fenced beads API
    fenced_beads = await store.get_fenced_beads_for_session(session_id)
    assert len(fenced_beads) == 1
    assert fenced_beads[0]["bead_ref"] == bead_ref


@pytest.mark.asyncio
async def test_stuck_card_coverage_all_fields(store, broadcaster):
    """
    Full coverage test: verify all stuck card fields are populated.

    Tests complete field coverage:
    - Intent: type, status, bead_ref
    - Result: summary, data, urgency
    - Result data: bead_id, stuck_reason, refusal_count, message, action_hint
    - SSE event: all required fields
    """
    session_id = await store.create_session()
    surface_id = await store.register_surface(session_id, "canvas")

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Full coverage test",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Coverage Test",
        session_id=session_id,
        topic_type="project",
    )

    bead_ref = "adc-coverage-test"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref,
        topic_id=topic_id,
    )

    await store.create_bead_watch(bead_ref=bead_ref)
    await store.update_bead_watch_refusal(
        bead_ref=bead_ref,
        refusal_reason="Coverage test refusal",
        comment_index=0,
        refusal_count_add=3,
    )
    await store.fence_bead(bead_ref=bead_ref)

    router = IntentRouter(store=store)
    routed_intent = RoutedIntent(
        intent_id=intent_id,
        classification=IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="adc",
        ),
        session_id=session_id,
        utterance="Full coverage test",
    )

    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    import src.intent.router
    with patch.object(src.intent.router, 'get_broadcaster', return_value=broadcaster):
        result = await router._escalate_to_bead(routed_intent, MagicMock())

    # Verify all intent fields
    intent = await store.get_intent(intent_id)
    assert intent["intent_type"] == "stuck"
    assert intent["status"] == "stuck"
    assert intent["bead_ref"] == bead_ref
    assert intent["session_id"] == session_id
    assert intent["project_slug"] == "adc"

    # Verify all result fields
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 1
    result_row = results[0]

    assert result_row["intent_id"] == intent_id
    # Note: stuck card creates a new topic with "Fenced:" prefix
    stuck_topic_id = result["topic_id"]
    assert result_row["topic_id"] == stuck_topic_id
    assert result_row["session_id"] == session_id
    assert result_row["summary"] == "Task stuck — needs your input"
    assert result_row["urgency"] == "high"
    assert result_row["created_at"] is not None
    assert result_row["surfaced_at"] is not None

    # Verify all result data fields
    import json
    result_data = json.loads(result_row["data"])
    assert "bead_id" in result_data
    assert "stuck_reason" in result_data
    assert "refusal_count" in result_data
    assert "message" in result_data
    assert "action_hint" in result_data
    assert "fence_detected_during" in result_data

    assert result_data["bead_id"] == bead_ref
    assert result_data["stuck_reason"] == "Coverage test refusal"
    assert result_data["refusal_count"] == 3
    assert result_data["fence_detected_during"] == "intent_routing"

    # Verify all SSE event fields
    event = await conn.queue.get()
    assert event.event_type == "task_stuck"
    assert event.data["bead_id"] == bead_ref
    assert event.data["stuck_reason"] == "Coverage test refusal"
    assert event.data["refusal_count"] == 3
    assert event.data["intent_id"] == intent_id
    assert event.data["session_id"] == session_id
    # Note: SSE event contains the stuck topic ID (not the original topic)
    assert event.data["topic_id"] == stuck_topic_id
    assert "timestamp" in event.data
    assert isinstance(event.data["timestamp"], int)


@pytest.mark.asyncio
async def test_multiple_fenced_beads_selects_most_recent(store, broadcaster):
    """
    Test that when multiple fenced beads exist, the most recent is selected.

    Verifies:
    - get_fenced_beads_for_session returns beads ordered by fenced_at DESC
    - Router selects the most recently fenced bead
    - Stuck card is created for the correct bead
    """
    session_id = await store.create_session()

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="Test multiple fenced",
    )

    topic_id, _ = await store.find_or_create_topic(
        label="Multiple Fenced",
        session_id=session_id,
        topic_type="project",
    )

    # Create two beads with different refs
    bead_ref_1 = "adc-fenced-1"
    bead_ref_2 = "adc-fenced-2"

    # Create intents for both beads (so they're tracked in the session)
    intent_id_1 = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref_1,
        topic_id=topic_id,
    )

    # Create a second intent for the second bead
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref=bead_ref_2,
        topic_id=topic_id,
    )

    # Create and fence both beads
    await store.create_bead_watch(bead_ref=bead_ref_1)
    await store.update_bead_watch_refusal(
        bead_ref=bead_ref_1,
        refusal_reason="First refusal",
        comment_index=0,
        refusal_count_add=3,
    )
    await store.fence_bead(bead_ref=bead_ref_1)

    # Add a delay to ensure different fenced_at timestamps (fenced_at is seconds precision)
    import asyncio
    await asyncio.sleep(1.1)

    # Second bead (more recent)
    await store.create_bead_watch(bead_ref=bead_ref_2)
    await store.update_bead_watch_refusal(
        bead_ref=bead_ref_2,
        refusal_reason="Second refusal",
        comment_index=0,
        refusal_count_add=3,
    )
    await store.fence_bead(bead_ref=bead_ref_2)

    # Verify both are fenced
    fenced_beads = await store.get_fenced_beads_for_session(session_id)
    assert len(fenced_beads) == 2

    # Most recently fenced should be first
    assert fenced_beads[0]["bead_ref"] == bead_ref_2
    assert fenced_beads[1]["bead_ref"] == bead_ref_1

    # Process intent - should create stuck card for most recent
    router = IntentRouter(store=store)
    routed_intent = RoutedIntent(
        intent_id=intent_id,
        classification=IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="adc",
        ),
        session_id=session_id,
        utterance="Test multiple fenced",
    )

    import src.intent.router
    with patch.object(src.intent.router, 'get_broadcaster', return_value=broadcaster):
        result = await router._escalate_to_bead(routed_intent, MagicMock())

    # Should use most recent fenced bead
    assert result["bead_id"] == bead_ref_2
    assert result["stuck_reason"] == "Second refusal"
