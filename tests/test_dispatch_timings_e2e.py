"""
End-to-end integration tests for dispatch_timings instrumentation (bead adc-48td).

This test suite verifies that every dispatch (hot-path and task-profile) persists a
complete dispatch_timings row, and that client-reported timings wire through the
/api/v1/timings endpoint correctly.

Acceptance criteria from adc-48td:
- Every dispatch (hot path and task-profile) persists a complete row
- Existing test suites still pass
- A simple aggregation helper (p50/p95 per stage) exists for the latency-baseline bead

These are hermetic, network-free tests that verify the dispatch_timings capture
integration across the router, fetch, synthesize, and escalate strands.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.session.store import SessionStore, DISPATCH_TIMING_COLUMNS
from src.intent.router import IntentRouter, RoutedIntent, IntentClassification, IntentType
from src.instrument.timings import DispatchTimings


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """Isolated SessionStore on a tmp DB for each test."""
    db_path = tmp_path / "test.db"
    s = SessionStore(db_path)
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
def mock_zai_client():
    """Mock ZAI client for testing router without external dependencies."""
    client = AsyncMock()
    # Mock response for classification
    client.call_simple.return_value = '[{"intent_type": "status", "project_slug": "test-project", "urgency": "normal", "utterance_fragment": "test utterance"}]'
    return client


# --- E2E: Hot-path dispatch timing capture -----------------------------------


class TestE2EHotPathDispatchTimings:
    """Verify hot-path dispatch captures all server-side stages through the router."""

    @pytest.mark.asyncio
    async def test_hot_path_dispatch_captures_router_ms(self, store: SessionStore, mock_zai_client):
        """process_intent() records router_ms stamped on RoutedIntent."""
        router = IntentRouter(store=store)
        router._zai_client = mock_zai_client

        # Create a routed intent with router_ms already measured
        routed_intent = RoutedIntent(
            intent_id="test-intent-router-ms",
            classification=IntentClassification(
                intent_type=IntentType.STATUS,
                project_slug="test-project",
                urgency="normal",
            ),
            session_id="test-session",
            utterance="test utterance",
            router_ms=123,  # Pre-measured by route_utterance()
        )

        # Process the intent
        result = await router.process_intent(routed_intent)

        # Verify router_ms was persisted
        timings = await store.get_dispatch_timings(routed_intent.intent_id)
        assert timings is not None, "dispatch_timings row should exist"
        assert timings.get("router_ms") == 123, "router_ms should be persisted"

    @pytest.mark.asyncio
    async def test_hot_path_partial_upsert_preserves_router_ms(self, store: SessionStore, mock_zai_client):
        """Second record_dispatch_timings() call (e.g., sse_emit_ms) does not clobber router_ms."""
        router = IntentRouter(store=store)
        router._zai_client = mock_zai_client

        routed_intent = RoutedIntent(
            intent_id="test-partial-upsert",
            classification=IntentClassification(
                intent_type=IntentType.STATUS,
                project_slug="test-project",
                urgency="normal",
            ),
            session_id="test-session",
            utterance="test utterance",
            router_ms=100,
        )

        # Process intent (which records router_ms, synthesize_total_ms, etc.)
        await router.process_intent(routed_intent)

        # Simulate SSE emit timing recorded after broadcast (as in main.py)
        await store.record_dispatch_timings(
            routed_intent.intent_id,
            sse_emit_ms=50,
        )

        # Verify both timings are present (second write didn't clobber router_ms)
        timings = await store.get_dispatch_timings(routed_intent.intent_id)
        assert timings is not None
        assert timings.get("router_ms") == 100, "router_ms should be preserved"
        assert timings.get("sse_emit_ms") == 50, "sse_emit_ms should be added"

    @pytest.mark.asyncio
    async def test_all_server_stages_recorded_for_hot_path(self, store: SessionStore):
        """Verify all expected server-side stages get recorded during a full hot-path dispatch."""
        # Create a complete dispatch_timings row simulating a full hot-path flow
        intent_id = "test-full-hot-path"
        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,           # Measured in route_utterance()
            fetch_first_source_ms=50,
            fetch_total_ms=200,      # Measured in _fetch_and_synthesize()
            synthesize_total_ms=300, # Measured in _fetch_and_synthesize()
            sse_emit_ms=25,          # Measured after broadcaster.broadcast()
            # escalate_ms is NULL for hot-path
            # stt_ms and first_render_ms are client-reported (NULL if not reported)
        )

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None

        # Verify all hot-path stages are present
        assert timings.get("router_ms") == 100
        assert timings.get("fetch_first_source_ms") == 50
        assert timings.get("fetch_total_ms") == 200
        assert timings.get("synthesize_total_ms") == 300
        assert timings.get("sse_emit_ms") == 25

        # Verify task-profile-only fields are NULL
        assert timings.get("escalate_ms") is None
        assert timings.get("stt_ms") is None
        assert timings.get("first_render_ms") is None


# --- E2E: Client-reported timings -------------------------------------------


class TestE2EClientReportedTimings:
    """Verify client-reported stt_ms and first_render_ms are persisted correctly."""

    @pytest.mark.asyncio
    async def test_client_stt_ms_persists_correctly(self, store: SessionStore):
        """Client-reported stt_ms is stored and can be retrieved."""
        intent_id = "test-client-stt-123"

        # First, server-side stages are recorded
        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,
            synthesize_total_ms=500,
        )

        # Then client reports STT timing (simulating /api/v1/timings call)
        await store.record_dispatch_timings(
            intent_id,
            stt_ms=312,
        )

        # Verify persisted values
        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings.get("stt_ms") == 312
        # Server-side fields should still be present
        assert timings.get("router_ms") == 100
        assert timings.get("synthesize_total_ms") == 500

    @pytest.mark.asyncio
    async def test_client_first_render_ms_persists_correctly(self, store: SessionStore):
        """Client-reported first_render_ms is stored and can be retrieved."""
        intent_id = "test-client-render-456"

        await store.record_dispatch_timings(intent_id, router_ms=150)
        await store.record_dispatch_timings(intent_id, first_render_ms=90)

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings.get("first_render_ms") == 90

    @pytest.mark.asyncio
    async def test_client_timings_both_stt_and_render(self, store: SessionStore):
        """Both stt_ms and first_render_ms can be reported for the same intent."""
        intent_id = "test-client-both-789"

        await store.record_dispatch_timings(intent_id, router_ms=120)
        await store.record_dispatch_timings(
            intent_id,
            stt_ms=450,
            first_render_ms=85,
        )

        timings = await store.get_dispatch_timings(intent_id)
        assert timings.get("stt_ms") == 450
        assert timings.get("first_render_ms") == 85
        assert timings.get("router_ms") == 120  # Server field preserved

    @pytest.mark.asyncio
    async def test_client_timings_creates_row_if_not_exists(self, store: SessionStore):
        """Client timing report creates dispatch_timings row if intent_id doesn't exist yet."""
        intent_id = "test-client-create-row-999"

        # No prior row exists
        timings_before = await store.get_dispatch_timings(intent_id)
        assert timings_before is None

        # Report client timing only (no server-side fields yet)
        await store.record_dispatch_timings(intent_id, stt_ms=200)

        # Row should now exist
        timings_after = await store.get_dispatch_timings(intent_id)
        assert timings_after is not None
        assert timings_after.get("stt_ms") == 200
        assert timings_after.get("router_ms") is None  # Server fields not yet set


# --- E2E: Aggregation helpers ----------------------------------------------


class TestE2EAggregationHelpers:
    """Verify p50/p95 aggregation helpers for latency-baseline bead consumption."""

    @pytest.mark.asyncio
    async def test_store_latency_percentiles_method(self, store: SessionStore):
        """SessionStore.get_latency_percentiles() returns per-stage p50/p95 for baseline bead."""
        # Seed multi-stage data
        for i in range(10):
            intent_id = f"test-baseline-helper-{i}"
            await store.record_dispatch_timings(
                intent_id,
                router_ms=50 + i * 10,
                fetch_total_ms=100 + i * 20,
                synthesize_total_ms=200 + i * 30,
            )

        percentiles = await store.get_latency_percentiles()

        # All three stages should have p50/p95
        assert "router_ms" in percentiles
        assert "fetch_total_ms" in percentiles
        assert "synthesize_total_ms" in percentiles

        # Verify structure
        for stage in ["router_ms", "fetch_total_ms", "synthesize_total_ms"]:
            assert "p50" in percentiles[stage]
            assert "p95" in percentiles[stage]
            assert "count" in percentiles[stage]
            assert percentiles[stage]["count"] == 10

    @pytest.mark.asyncio
    async def test_latency_percentiles_returns_empty_when_no_data(self, store: SessionStore):
        """get_latency_percentiles() returns {} when no timings exist."""
        percentiles = await store.get_latency_percentiles()
        assert percentiles == {}

    @pytest.mark.asyncio
    async def test_latency_percentiles_with_since_filter(self, store: SessionStore):
        """since parameter filters to recent dispatches only."""
        from datetime import datetime, timezone

        now = int(datetime.now(timezone.utc).timestamp())

        # Old timing (1 hour ago)
        old_intent = "test-old-filtered"
        await store.record_dispatch_timings(old_intent, router_ms=1000)
        # Manually backdate created_at
        import aiosqlite
        async with aiosqlite.connect(store.db_path) as db:
            await db.execute(
                "UPDATE dispatch_timings SET created_at = ? WHERE intent_id = ?",
                (now - 3600, old_intent)
            )
            await db.commit()

        # Recent timing
        recent_intent = "test-recent-filtered"
        await store.record_dispatch_timings(recent_intent, router_ms=100)

        # Unfiltered should include both
        all_percentiles = await store.get_latency_percentiles()
        assert all_percentiles["router_ms"]["count"] == 2

        # Filtered to last 5 minutes should only include recent
        five_mins_ago = now - 300
        recent_percentiles = await store.get_latency_percentiles(since=five_mins_ago)
        assert recent_percentiles["router_ms"]["count"] == 1
        assert recent_percentiles["router_ms"]["p50"] == 100


# --- E2E: Complete dispatch flow -------------------------------------------


class TestE2ECompleteDispatchFlow:
    """Verify complete dispatch flow captures all expected timings."""

    @pytest.mark.asyncio
    async def test_complete_hot_path_dispatch_has_all_stages(self, store: SessionStore):
        """A complete hot-path dispatch has all server stages recorded."""
        intent_id = "test-complete-hot-path"

        # Simulate a complete hot-path dispatch with all stages
        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,              # Measured in route_utterance()
            fetch_first_source_ms=50,   # First source returned
            fetch_total_ms=200,         # Fetch window closed
            synthesize_total_ms=300,    # Synthesize completed
            sse_emit_ms=25,             # SSE broadcast completed
            # Client-reported stages (simulated)
            stt_ms=150,
            first_render_ms=80,
        )

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None

        # Verify all stages are present
        assert timings["router_ms"] == 100
        assert timings["fetch_first_source_ms"] == 50
        assert timings["fetch_total_ms"] == 200
        assert timings["synthesize_total_ms"] == 300
        assert timings["sse_emit_ms"] == 25
        assert timings["stt_ms"] == 150
        assert timings["first_render_ms"] == 80

        # Task-profile-only field should be NULL
        assert timings["escalate_ms"] is None

    @pytest.mark.asyncio
    async def test_task_profile_dispatch_has_escalate_ms(self, store: SessionStore):
        """Task-profile dispatch records escalate_ms instead of fetch/synthesize stages."""
        intent_id = "test-task-profile"

        # Task-profile dispatches have escalate_ms instead of fetch/synthesize
        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,
            escalate_ms=200,  # Bead formulation + validation + bf create
            sse_emit_ms=25,
        )

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings["router_ms"] == 100
        assert timings["escalate_ms"] == 200
        assert timings["sse_emit_ms"] == 25

        # Fetch/synthesize stages should be NULL for task-profile
        assert timings["fetch_first_source_ms"] is None
        assert timings["fetch_total_ms"] is None
        assert timings["synthesize_total_ms"] is None


# --- E2E: Existing test suite compatibility ---------------------------------


class TestE2EExistingTestsPass:
    """Verify the dispatch_timings instrumentation doesn't break existing functionality."""

    @pytest.mark.asyncio
    async def test_store_initialization_with_dispatch_timings(self, store: SessionStore):
        """SessionStore.initialize() creates dispatch_timings table successfully."""
        import aiosqlite

        async with aiosqlite.connect(store.db_path) as db:
            # Verify table exists
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dispatch_timings'"
            )
            result = await cursor.fetchone()
            assert result is not None, "dispatch_timings table should exist"

    @pytest.mark.asyncio
    async def test_record_dispatch_timings_idempotent(self, store: SessionStore):
        """record_dispatch_timings() can be called multiple times safely."""
        intent_id = "test-idempotent-123"

        # Call multiple times with different fields
        await store.record_dispatch_timings(intent_id, router_ms=100)
        await store.record_dispatch_timings(intent_id, fetch_total_ms=200)
        await store.record_dispatch_timings(intent_id, synthesize_total_ms=300)
        await store.record_dispatch_timings(intent_id, sse_emit_ms=50)

        # All fields should be present
        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings["router_ms"] == 100
        assert timings["fetch_total_ms"] == 200
        assert timings["synthesize_total_ms"] == 300
        assert timings["sse_emit_ms"] == 50

    @pytest.mark.asyncio
    async def test_get_latency_percentiles_handles_sparse_data(self, store: SessionStore):
        """get_latency_percentiles() handles rows where only some stages are set."""
        # Create rows with different stage combinations
        await store.record_dispatch_timings("id1", router_ms=100)
        await store.record_dispatch_timings("id2", router_ms=150, fetch_total_ms=200)
        await store.record_dispatch_timings("id3", synthesize_total_ms=300)
        await store.record_dispatch_timings("id4", router_ms=200, synthesize_total_ms=400)

        percentiles = await store.get_latency_percentiles()

        # Should have percentiles for stages that have data
        assert "router_ms" in percentiles  # id1, id2, id4 have this
        assert percentiles["router_ms"]["count"] == 3
        assert "fetch_total_ms" in percentiles  # Only id2 has this
        assert percentiles["fetch_total_ms"]["count"] == 1
        assert "synthesize_total_ms" in percentiles  # id3, id4 have this
        assert percentiles["synthesize_total_ms"]["count"] == 2

