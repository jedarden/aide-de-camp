"""
Integration test for bead watcher close->result path (bead adc-12ar).

Tests the full chain:
1. Create intent with bead_ref pointing at test bead
2. Close bead via bf CLI (simulated via CLI output mocking)
3. Assert results row written, intent resolved, SSE event fires within one poll interval

This test uses a scratch .beads workspace and never touches the real production workspace.
"""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.session.store import SessionStore
from src.sse.broadcaster import SSEBroadcaster, SSEEvent
from src.surface.router import SurfaceRouter
from src.watcher.daemon import BeadWatcher


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """An isolated SessionStore on a tmp DB."""
    db_path = tmp_path / "session.db"
    s = SessionStore(db_path)
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def broadcaster() -> SSEBroadcaster:
    """A fresh SSEBroadcaster per test."""
    b = SSEBroadcaster()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def router(store: SessionStore) -> SurfaceRouter:
    """A SurfaceRouter for testing."""
    return SurfaceRouter(store)


@pytest.fixture
def scratch_beads_workspace(tmp_path: Path) -> Path:
    """A scratch .beads workspace for testing."""
    workspace = tmp_path / ".beads"
    workspace.mkdir()
    return workspace


@pytest.mark.asyncio
async def test_bead_close_creates_result_and_sse(
    store: SessionStore,
    broadcaster: SSEBroadcaster,
    router: SurfaceRouter,
    scratch_beads_workspace: Path,
):
    """
    Integration test: closing a bead writes a result, resolves intent, and fires SSE.

    This test verifies the complete close->result path:
    1. Create an intent with bead_ref pointing at a test bead
    2. Simulate bf CLI returning the closed bead
    3. Run one watcher tick
    4. Assert:
       - Results row written to DB
       - Intent status updated to resolved
       - SSE result_created event fired on active surface
    """
    # Step 1: Set up session, surface, utterance, topic, and intent
    session_id = await store.create_session()
    surface_id = await store.register_surface(session_id, "canvas")
    utterance_id = await store.create_utterance(session_id, "test escalation")
    topic_id = await store.create_topic(
        label="Test Bead",
        topic_type="project",
        project_slugs=["test"],
        scope="session",
        session_id=session_id,
    )

    # Create intent with bead_ref pointing at our test bead
    bead_id = "test-bead-123"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test",
        intent_type="escalate",
        bead_ref=bead_id,
        topic_id=topic_id,
    )

    # Register SSE connection for the active surface
    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    # Step 2: Create a BeadWatcher with short poll interval
    watcher = BeadWatcher(
        store=store,
        router=router,
        bf_bin="bf",  # Will be mocked
        bf_workspace=str(scratch_beads_workspace.parent),  # Parent dir contains .beads
        check_interval_seconds=1.0,  # Short interval for testing
    )

    # Set the high-water mark to a past timestamp so the first poll emits events
    # (otherwise the watcher treats it as a baseline run and emits nothing)
    watcher._close_highwater = 0.0

    # Step 3: Mock the bf CLI to return a closed bead
    closed_at = datetime.now().isoformat() + "Z"
    mock_bead_record = {
        "id": bead_id,
        "title": "Test Bead",
        "description": "Test result",
        "status": "closed",
        "closed_at": closed_at,
        "labels": ["urgency=normal"],
    }

    async def mock_run_bf_list_closed():
        """Mock bf list --status closed --json to return our test bead."""
        return [mock_bead_record]

    # Patch the _run_bf_list_closed method
    watcher._run_bf_list_closed = mock_run_bf_list_closed

    # Patch the global broadcaster to use our test broadcaster
    # The watcher uses broadcast_result() which calls get_broadcaster()
    import src.sse.broadcaster
    with patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster):

        # Step 4: Run one tick of the watcher
        await watcher._check_for_events()

        # Step 5: Assert results row was written
        results = await store.get_results_for_intent(intent_id)
        assert len(results) == 1
        result = results[0]
        assert result["intent_id"] == intent_id
        assert result["topic_id"] == topic_id
        assert result["session_id"] == session_id
        assert "Test result" in result["summary"]
        assert json.loads(result["data"])["bead_id"] == bead_id

        # Step 6: Assert intent was resolved
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "resolved"

        # Step 7: Assert SSE event was fired on the active surface
        # The event should be in the connection's queue
        event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert event.event_type == "result_created"
        assert event.data["result_id"] == result["id"]
        assert event.data["session_id"] == session_id


@pytest.mark.asyncio
async def test_bead_close_with_no_intent_is_skipped(
    store: SessionStore,
    router: SurfaceRouter,
    scratch_beads_workspace: Path,
):
    """
    Test that closing a bead with no matching intent is skipped gracefully.

    Most bf beads are not escalate-tracked, so the watcher should skip them
    without error.
    """
    # Create a watcher
    watcher = BeadWatcher(
        store=store,
        router=router,
        bf_bin="bf",
        bf_workspace=str(scratch_beads_workspace.parent),
        check_interval_seconds=1.0,
    )

    # Mock bf to return a bead with no matching intent
    bead_id = "untracked-bead-456"
    closed_at = datetime.now().isoformat() + "Z"
    mock_bead_record = {
        "id": bead_id,
        "title": "Untracked Bead",
        "status": "closed",
        "closed_at": closed_at,
        "labels": [],
    }

    async def mock_run_bf_list_closed():
        return [mock_bead_record]

    watcher._run_bf_list_closed = mock_run_bf_list_closed

    # Run one tick - should not raise any error
    await watcher._check_for_events()

    # No results should exist
    all_results = await store.get_all_results()
    assert len(all_results) == 0


@pytest.mark.asyncio
async def test_bead_close_with_missing_topic_id_is_skipped(
    store: SessionStore,
    router: SurfaceRouter,
    scratch_beads_workspace: Path,
):
    """
    Test that closing a bead whose intent has no topic_id is skipped.

    This handles edge cases where intent state is incomplete.
    """
    session_id = await store.create_session()
    utterance_id = await store.create_utterance(session_id, "test")

    # Create intent with bead_ref but no topic_id
    bead_id = "orphan-bead-789"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test",
        intent_type="escalate",
        bead_ref=bead_id,
    )

    watcher = BeadWatcher(
        store=store,
        router=router,
        bf_bin="bf",
        bf_workspace=str(scratch_beads_workspace.parent),
        check_interval_seconds=1.0,
    )

    # Mock bf to return the closed bead
    closed_at = datetime.now().isoformat() + "Z"
    mock_bead_record = {
        "id": bead_id,
        "title": "Orphan Bead",
        "description": "No topic",
        "status": "closed",
        "closed_at": closed_at,
        "labels": [],
    }

    async def mock_run_bf_list_closed():
        return [mock_bead_record]

    watcher._run_bf_list_closed = mock_run_bf_list_closed

    # Run one tick - should log warning but not crash
    await watcher._check_for_events()

    # Intent should still be pending (not resolved)
    intent = await store.get_intent(intent_id)
    assert intent["status"] == "pending"

    # No result should exist
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_highwater_mark_prevents_duplicate_delivery(
    store: SessionStore,
    broadcaster: SSEBroadcaster,
    router: SurfaceRouter,
    scratch_beads_workspace: Path,
):
    """
    Test that the close-timestamp high-water mark prevents re-delivery of
    already-closed beads on restart.

    First tick after start should baseline the mark and emit nothing.
    Only beads closed AFTER the mark should be delivered.
    """
    session_id = await store.create_session()
    surface_id = await store.register_surface(session_id, "canvas")
    utterance_id = await store.create_utterance(session_id, "test")
    topic_id = await store.create_topic(
        label="Test Topic",
        topic_type="project",
        project_slugs=["test"],
        scope="session",
        session_id=session_id,
    )

    bead_id = "baseline-bead-999"
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test",
        intent_type="escalate",
        bead_ref=bead_id,
    )

    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )

    watcher = BeadWatcher(
        store=store,
        router=router,
        bf_bin="bf",
        bf_workspace=str(scratch_beads_workspace.parent),
        check_interval_seconds=1.0,
    )

    # First tick: return existing closed bead
    # Should baseline the mark and emit nothing
    closed_at = datetime.now().isoformat() + "Z"
    mock_existing_bead = {
        "id": bead_id,
        "title": "Existing Closed Bead",
        "description": "Already closed",
        "status": "closed",
        "closed_at": closed_at,
        "labels": ["urgency=normal"],
    }

    async def mock_run_bf_list_closed():
        return [mock_existing_bead]

    watcher._run_bf_list_closed = mock_run_bf_list_closed

    # First tick - should baseline and emit nothing
    await watcher._check_for_events()

    # No result should exist (bead was already closed)
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 0

    # Intent should still be pending
    intent = await store.get_intent(intent_id)
    assert intent["status"] == "pending"

    # No SSE event should have been fired
    assert conn.queue.empty()

    # Second tick: same bead (still closed)
    # Should still emit nothing (already processed)
    await watcher._check_for_events()

    # Still no result
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 0
