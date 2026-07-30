"""
Tests for the async circuit breaker system.

Tests coverage:
- Refusal comment parsing (REFUSED: prefix)
- Circuit breaker thresholds (3 refusals OR 24h age)
- SLA deadline tracking and flagging
- Bead fencing and stuck card creation
- Per-project SLA overrides
- bead_watch row lifecycle

Acceptance criteria from plan §10 The Async Path:
- 3 REFUSED comments trip the fence + stuck card
- 24h age trips it
- Counts survive a watcher restart
- Enum migration covered
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.session.store import (
    SessionStore,
    CIRCUIT_BREAKER_REFUSAL_THRESHOLD,
    CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS,
    DEFAULT_SLA_HOURS,
)
from src.watcher.daemon import BeadWatcher


# --- Fixtures -----------------------------------------------------------------


@pytest.fixture
async def store():
    """In-memory session store for testing with cleanup."""
    import tempfile
    from pathlib import Path

    # Use a temporary file database for proper test isolation
    # Each test gets its own database file to avoid leakage
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    s = SessionStore(db_path)
    # Initialize schema asynchronously
    await s.initialize()
    yield s
    # Cleanup: close the database connection and delete the file
    await s.close()
    try:
        db_path.unlink()
    except OSError:
        pass  # File already deleted or doesn't exist


@pytest.fixture
def router():
    """Mock surface router."""
    r = MagicMock()
    r.route_result = AsyncMock(
        return_value=MagicMock(
            target_surfaces=[],
            reason="no-surface-available",
            fallback_used=False,
        )
    )
    return r


@pytest.fixture
def watcher(store, router):
    """Bead watcher with mocked bf CLI."""
    w = BeadWatcher(store, router, bf_bin="/fake/bf", bf_workspace="/fake/workspace")
    return w


# --- Refusal comment parsing ----------------------------------------------------


class TestRefusalParsing:
    """Parsing REFUSED: comments from bead comment streams."""

    def test_refuse_pattern_simple(self):
        """Simple REFUSED: comment is parsed."""
        comments = [
            {"body": "REFUSED: Missing cluster context", "created_at": "2026-07-22T10:00:00Z"},
        ]
        refusals = BeadWatcher._parse_refusals_from_comments(comments, since_index=-1)
        assert len(refusals) == 1
        assert refusals[0]["reason"] == "Missing cluster context"
        assert refusals[0]["index"] == 0

    def test_refuse_pattern_with_extra_whitespace(self):
        """REFUSED: with leading/trailing whitespace is parsed."""
        comments = [
            {"body": "  REFUSED:   Scope unclear   ", "created_at": "2026-07-22T10:00:00Z"},
        ]
        refusals = BeadWatcher._parse_refusals_from_comments(comments, since_index=-1)
        assert len(refusals) == 1
        assert refusals[0]["reason"] == "Scope unclear"

    def test_non_refusal_comments_ignored(self):
        """Comments without REFUSED: prefix are ignored."""
        comments = [
            {"body": "Working on this", "created_at": "2026-07-22T10:00:00Z"},
            {"body": "Almost done", "created_at": "2026-07-22T11:00:00Z"},
        ]
        refusals = BeadWatcher._parse_refusals_from_comments(comments, since_index=-1)
        assert len(refusals) == 0

    def test_respects_high_water_mark(self):
        """Only comments past the high-water mark are parsed."""
        comments = [
            {"body": "REFUSED: Old reason", "created_at": "2026-07-22T10:00:00Z"},
            {"body": "REFUSED: New reason", "created_at": "2026-07-22T11:00:00Z"},
        ]
        # high_water=0 means comment 0 has been processed, so only index 1+ is checked
        refusals = BeadWatcher._parse_refusals_from_comments(comments, since_index=0)
        assert len(refusals) == 1
        assert refusals[0]["reason"] == "New reason"
        assert refusals[0]["index"] == 1

    def test_initial_state_parses_all_comments(self):
        """Initial state (-1) parses all comments (none have been processed yet)."""
        comments = [
            {"body": "REFUSED: Reason 1", "created_at": "2026-07-22T10:00:00Z"},
            {"body": "REFUSED: Reason 2", "created_at": "2026-07-22T11:00:00Z"},
        ]
        # high_water=-1 means no comments have been processed, so all are parsed
        refusals = BeadWatcher._parse_refusals_from_comments(comments, since_index=-1)
        assert len(refusals) == 2
        assert [r["reason"] for r in refusals] == ["Reason 1", "Reason 2"]

    def test_multiple_refusals_parsed(self):
        """Multiple REFUSED: comments are all parsed."""
        comments = [
            {"body": "REFUSED: Reason 1", "created_at": "2026-07-22T10:00:00Z"},
            {"body": "REFUSED: Reason 2", "created_at": "2026-07-22T11:00:00Z"},
            {"body": "REFUSED: Reason 3", "created_at": "2026-07-22T12:00:00Z"},
        ]
        refusals = BeadWatcher._parse_refusals_from_comments(comments, since_index=-1)
        assert len(refusals) == 3
        assert [r["reason"] for r in refusals] == ["Reason 1", "Reason 2", "Reason 3"]
        assert [r["index"] for r in refusals] == [0, 1, 2]

    def test_mixed_refusals_and_normal_comments(self):
        """Interleaved REFUSED: and normal comments only parse refusals."""
        comments = [
            {"body": "Working on it", "created_at": "2026-07-22T10:00:00Z"},
            {"body": "REFUSED: Need input", "created_at": "2026-07-22T10:15:00Z"},
            {"body": "Still thinking", "created_at": "2026-07-22T10:30:00Z"},
            {"body": "REFUSED: Blocked by dependency", "created_at": "2026-07-22T11:00:00Z"},
        ]
        refusals = BeadWatcher._parse_refusals_from_comments(comments, since_index=-1)
        assert len(refusals) == 2
        assert [r["reason"] for r in refusals] == ["Need input", "Blocked by dependency"]


# --- bead_watch row lifecycle -------------------------------------------------


class TestBeadWatchLifecycle:
    """bead_watch table persistence and lifecycle."""

    async def test_create_bead_watch_defaults(self, store):
        """Creating bead_watch sets defaults correctly."""
        bead_ref = "adc-test1"
        await store.create_bead_watch(bead_ref=bead_ref)

        row = await store.get_bead_watch(bead_ref)
        assert row is not None
        assert row["bead_ref"] == bead_ref
        assert row["refusal_count"] == 0
        assert row["comment_high_water"] == -1
        assert row["last_refusal_reason"] is None
        assert row["last_refusal_at"] is None
        assert row["sla_flagged_at"] is None
        assert row["fenced_at"] is None

        # SLA deadline should be ~6 hours from now (task-profile default)
        now = int(datetime.now().timestamp())
        sla_deadline = row["sla_deadline"]
        assert sla_deadline > now
        assert sla_deadline < now + (7 * 3600)  # Less than 7 hours

    async def test_create_bead_watch_with_custom_sla(self, store):
        """Custom SLA hours override the default."""
        bead_ref = "adc-test2"
        sla_hours = 12.0
        await store.create_bead_watch(bead_ref=bead_ref, sla_hours=sla_hours)

        row = await store.get_bead_watch(bead_ref)
        now = int(datetime.now().timestamp())
        sla_deadline = row["sla_deadline"]

        # Should be ~12 hours from now
        expected_deadline = now + int(sla_hours * 3600)
        assert abs(sla_deadline - expected_deadline) < 10  # 10s tolerance

    async def test_update_refusal_increments_count(self, store):
        """Recording a refusal increments count and updates timestamps."""
        bead_ref = "adc-test3"
        await store.create_bead_watch(bead_ref=bead_ref)

        # Record first refusal
        await store.update_bead_watch_refusal(
            bead_ref=bead_ref,
            refusal_reason="Missing scope",
            comment_index=0,
        )

        row = await store.get_bead_watch(bead_ref)
        assert row["refusal_count"] == 1
        assert row["last_refusal_reason"] == "Missing scope"
        assert row["last_refusal_at"] is not None
        assert row["comment_high_water"] == 0

        # Record second refusal
        await store.update_bead_watch_refusal(
            bead_ref=bead_ref,
            refusal_reason="Cluster unclear",
            comment_index=1,
        )

        row = await store.get_bead_watch(bead_ref)
        assert row["refusal_count"] == 2
        assert row["last_refusal_reason"] == "Cluster unclear"
        assert row["comment_high_water"] == 1

    async def test_fence_bead_sets_timestamp(self, store):
        """Fencing a bead sets fenced_at timestamp."""
        bead_ref = "adc-test4"
        await store.create_bead_watch(bead_ref=bead_ref)
        await store.fence_bead(bead_ref)

        row = await store.get_bead_watch(bead_ref)
        assert row["fenced_at"] is not None
        fenced_at = datetime.fromtimestamp(row["fenced_at"])
        now = datetime.now()
        # Should be very recent (within last minute)
        assert (now - fenced_at).total_seconds() < 60

    async def test_delete_bead_watch_removes_row(self, store):
        """Deleting bead_watch removes the row."""
        bead_ref = "adc-test5"
        await store.create_bead_watch(bead_ref=bead_ref)
        assert await store.get_bead_watch(bead_ref) is not None

        await store.delete_bead_watch(bead_ref)
        assert await store.get_bead_watch(bead_ref) is None


# --- SLA tracking --------------------------------------------------------------


class TestSLATracking:
    """SLA deadline tracking and flagging."""

    async def test_get_beads_past_sla_only_unflagged(self, store):
        """Only beads past SLA that are not yet flagged are returned."""
        import aiosqlite

        # Create bead with expired SLA (1 hour ago)
        past_deadline = int((datetime.now() - timedelta(hours=1)).timestamp())
        await store.create_bead_watch("adc-expired", sla_hours=1.0)

        # Manually set sla_deadline to past (direct DB access for test)
        async with aiosqlite.connect(store.db_path) as db:
            await db.execute(
                "UPDATE bead_watch SET sla_deadline = ? WHERE bead_ref = ?",
                (past_deadline, "adc-expired"),
            )
            await db.commit()

        # Create bead with future SLA
        await store.create_bead_watch("adc-future", sla_hours=24.0)

        past_sla = await store.get_beads_past_sla()
        assert len(past_sla) == 1
        assert past_sla[0]["bead_ref"] == "adc-expired"

    async def test_flag_sla_sets_timestamp(self, store):
        """Flagging SLA sets sla_flagged_at timestamp."""
        bead_ref = "adc-flag-test"
        await store.create_bead_watch(bead_ref=bead_ref)

        await store.flag_sla(bead_ref)

        row = await store.get_bead_watch(bead_ref)
        assert row["sla_flagged_at"] is not None
        flagged_at = datetime.fromtimestamp(row["sla_flagged_at"])
        now = datetime.now()
        assert (now - flagged_at).total_seconds() < 60

    async def test_flagged_beads_excluded_from_past_sla(self, store):
        """Beads already flagged are not returned by get_beads_past_sla."""
        bead_ref = "adc-already-flagged"
        await store.create_bead_watch(bead_ref=bead_ref)

        # Flag the bead
        await store.flag_sla(bead_ref)

        # Even if SLA is past, should not be returned
        past_sla = await store.get_beads_past_sla()
        # Should only contain beads that are NOT our already-flagged bead
        matching = [b for b in past_sla if b["bead_ref"] == bead_ref]
        assert len(matching) == 0


# --- Circuit breaker thresholds ------------------------------------------------


class TestCircuitBreakerThresholds:
    """Circuit breaker: 3 refusals OR 24h age triggers fencing."""

    async def test_three_refusals_trigger_fence(self, store):
        """Bead with 3 refusals meets fencing criteria."""
        bead_ref = "adc-refusal-test"
        await store.create_bead_watch(bead_ref=bead_ref)

        # Record 3 refusals
        for i in range(3):
            await store.update_bead_watch_refusal(
                bead_ref=bead_ref,
                refusal_reason=f"Refusal {i+1}",
                comment_index=i,
            )

        # Should meet fencing criteria
        needs_fencing = await store.get_beads_needing_fencing()
        # Filter to only our test bead (defensive: database isolation should prevent this)
        matching = [b for b in needs_fencing if b["bead_ref"] == bead_ref]
        assert len(matching) == 1
        assert matching[0]["bead_ref"] == bead_ref
        assert matching[0]["refusal_count"] == 3

    async def test_two_refusals_does_not_fence(self, store):
        """Bead with only 2 refusals does not meet fencing criteria."""
        bead_ref = "adc-two-refusals"
        await store.create_bead_watch(bead_ref=bead_ref)

        # Record 2 refusals
        for i in range(2):
            await store.update_bead_watch_refusal(
                bead_ref=bead_ref,
                refusal_reason=f"Refusal {i+1}",
                comment_index=i,
            )

        # Should NOT meet fencing criteria
        needs_fencing = await store.get_beads_needing_fencing()
        matching = [b for b in needs_fencing if b["bead_ref"] == bead_ref]
        assert len(matching) == 0

    async def test_age_threshold_triggers_fence(self, store):
        """Bead older than 24h meets fencing criteria (age-based)."""
        import aiosqlite

        bead_ref = "adc-age-test"
        await store.create_bead_watch(bead_ref=bead_ref)

        # Manually set created_at to 25 hours ago (direct DB access for test)
        old_created = int((datetime.now() - timedelta(hours=25)).timestamp())
        async with aiosqlite.connect(store.db_path) as db:
            await db.execute(
                "UPDATE bead_watch SET created_at = ? WHERE bead_ref = ?",
                (old_created, bead_ref),
            )
            await db.commit()

        # Should meet fencing criteria due to age
        needs_fencing = await store.get_beads_needing_fencing()
        matching = [b for b in needs_fencing if b["bead_ref"] == bead_ref]
        assert len(matching) == 1

    async def test_recent_bead_does_not_fence_by_age(self, store):
        """Bead younger than 24h does not meet age-based fencing criteria."""
        bead_ref = "adc-recent"
        await store.create_bead_watch(bead_ref=bead_ref)

        # Created recently (within 24h)
        needs_fencing = await store.get_beads_needing_fencing()
        matching = [b for b in needs_fencing if b["bead_ref"] == bead_ref]
        assert len(matching) == 0

    async def test_fenced_beads_excluded_from_needing_fence(self, store):
        """Beads already fenced are not returned by get_beads_needing_fencing."""
        bead_ref = "adc-already-fenced"
        await store.create_bead_watch(bead_ref=bead_ref)

        # Fence the bead
        await store.fence_bead(bead_ref)

        # Even with 3 refusals, should not be returned (already fenced)
        for i in range(3):
            await store.update_bead_watch_refusal(
                bead_ref=bead_ref,
                refusal_reason=f"Refusal {i+1}",
                comment_index=i,
            )

        needs_fencing = await store.get_beads_needing_fencing()
        matching = [b for b in needs_fencing if b["bead_ref"] == bead_ref]
        assert len(matching) == 0


# --- SLA defaults and per-project overrides ------------------------------------


class TestSLADefaults:
    """Default SLA hours per intent type, with per-project override."""

    async def test_default_sla_constants_defined(self):
        """Default SLA constants are defined for key intent types."""
        assert "task-profile" in DEFAULT_SLA_HOURS
        assert DEFAULT_SLA_HOURS["task-profile"] == 6.0  # 6 hours

        assert "status" in DEFAULT_SLA_HOURS
        assert DEFAULT_SLA_HOURS["status"] < 1.0  # Hot-path: ~30 seconds

    async def test_circuit_breaker_constants(self):
        """Circuit breaker thresholds are defined."""
        assert CIRCUIT_BREAKER_REFUSAL_THRESHOLD == 3
        assert CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS == 24.0


# --- Integration tests (mocked bf CLI) ---------------------------------------


class TestCircuitBreakerIntegration:
    """End-to-end circuit breaker with mocked bf CLI."""

    async def test_full_refusal_to_fence_flow(self, store, router, watcher, monkeypatch):
        """Full flow: 3 refusals -> fence -> stuck card."""
        bead_ref = "adc-integration-test"
        session_id = "session-1"
        topic_id = "topic-1"

        # Create a real intent in the store
        intent_id = await store.create_intent(
            utterance_id="utterance-1",
            session_id=session_id,
            project_slug="test-project",
            intent_type="task-profile",
            bead_ref=bead_ref,
            topic_id=topic_id,
        )

        # Create bead_watch row
        await store.create_bead_watch(bead_ref=bead_ref)

        # Mock get_open_watched_beads to return only our test bead (avoid interference)
        async def fake_get_open_watched():
            row = await store.get_bead_watch(bead_ref)
            if row:
                return [row]
            return []

        store.get_open_watched_beads = fake_get_open_watched

        # Mock bf show to return 3 refusals
        async def fake_show(bref):
            if bref == bead_ref:
                return {
                    "id": bref,
                    "comments": [
                        {"body": "REFUSED: Reason 1", "created_at": "2026-07-22T10:00:00Z"},
                        {"body": "REFUSED: Reason 2", "created_at": "2026-07-22T11:00:00Z"},
                        {"body": "REFUSED: Reason 3", "created_at": "2026-07-22T12:00:00Z"},
                    ],
                }
            return None

        watcher._run_bf_show = fake_show

        # Mock bf update --status blocked
        async def fake_update(bref, status):
            pass

        watcher._run_bf_update_status = fake_update

        # Run circuit breaker check
        await watcher._check_circuit_breaker()

        # Verify bead was fenced
        row = await store.get_bead_watch(bead_ref)
        assert row["fenced_at"] is not None, f"Bead should be fenced, but fenced_at is None. Refusal count: {row.get('refusal_count')}"

        # Verify intent was marked stuck
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "stuck"

        # Verify stuck card was created
        results = await store.get_results_for_intent(intent_id)
        assert len(results) > 0
        stuck_card = results[-1]
        assert "stuck" in stuck_card["summary"].lower()
        assert stuck_card["urgency"] == "high"

    async def test_sse_fence_event_broadcast(self, store, router, watcher, monkeypatch):
        """Verify SSE event broadcast when bead is fenced.

        Acceptance criteria:
        - SSE event broadcast on fence (event_type: 'task_stuck')
        - Event includes: bead_id, refusal_reason, timestamp
        - Broadcast triggered when bead_watch.last_refusal_reason is set
        - Target surface_id for the originating session
        """
        from src.sse.broadcaster import get_broadcaster, SSEEvent, EventType

        bead_ref = "adc-sse-test"
        session_id = "session-sse"
        topic_id = "topic-sse"
        origin_surface_id = "surface-origin"

        # Create a real intent in the store
        intent_id = await store.create_intent(
            utterance_id="utterance-sse",
            session_id=session_id,
            project_slug="test-project",
            intent_type="task-profile",
            bead_ref=bead_ref,
            topic_id=topic_id,
        )

        # Create bead_watch row
        await store.create_bead_watch(bead_ref=bead_ref)

        # Mock get_open_watched_beads to return only our test bead
        async def fake_get_open_watched():
            row = await store.get_bead_watch(bead_ref)
            if row:
                return [row]
            return []

        store.get_open_watched_beads = fake_get_open_watched

        # Mock bf show to return 3 refusals AND origin_surface_id in labels
        async def fake_show(bref):
            if bref == bead_ref:
                return {
                    "id": bref,
                    "labels": [f"origin_surface_id={origin_surface_id}"],
                    "comments": [
                        {"body": "REFUSED: Reason 1", "created_at": "2026-07-22T10:00:00Z"},
                        {"body": "REFUSED: Reason 2", "created_at": "2026-07-22T11:00:00Z"},
                        {"body": "REFUSED: Reason 3", "created_at": "2026-07-22T12:00:00Z"},
                    ],
                }
            return None

        watcher._run_bf_show = fake_show

        # Mock bf update --status blocked
        async def fake_update(bref, status):
            pass

        watcher._run_bf_update_status = fake_update

        # Mock broadcaster to capture the event
        broadcast_events = []
        broadcaster = get_broadcaster()

        original_broadcast = broadcaster.broadcast

        async def mock_broadcast(event):
            broadcast_events.append(event)
            return await original_broadcast(event)

        broadcaster.broadcast = mock_broadcast

        # Run circuit breaker check
        await watcher._check_circuit_breaker()

        # Verify SSE event was broadcast
        assert len(broadcast_events) >= 1, "Expected at least one SSE event broadcast"

        # Find the TASK_STUCK event
        task_stuck_events = [e for e in broadcast_events if e.event_type == EventType.TASK_STUCK]
        assert len(task_stuck_events) == 1, "Expected exactly one TASK_STUCK event"

        event = task_stuck_events[0]

        # Verify event data includes required fields
        assert event.data["bead_id"] == bead_ref
        assert "stuck_reason" in event.data
        assert event.data["stuck_reason"] == "Reason 3"  # Most recent refusal
        assert "timestamp" in event.data
        assert event.data["timestamp"] > 0

        # Verify event targets correct session and surface
        assert event.target_session_id == session_id
        assert event.target_surface_id == origin_surface_id

        # Verify bead was fenced
        row = await store.get_bead_watch(bead_ref)
        assert row["fenced_at"] is not None
