"""
FastAPI endpoint function tests for client-reported timings (bead adc-4lqgx).

This test suite verifies:
- report_client_timings() upserts client-reported fields (stt_ms, first_render_ms)
- Client fields merge into server-written rows without clobbering server-side stages
- Endpoint ignores unknown fields
- Endpoint handles missing/unknown intent_id gracefully
- get_latency_percentiles_endpoint() returns {stage: {p50, p95, count}}
- since query-param windowing works correctly

Acceptance criteria:
- Client-reported fields merge into a server-written row; server stages untouched.
- /percentiles returns the documented shape and matches store.get_latency_percentiles() output.
- Full existing suite still passes.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi.responses import JSONResponse

from src.session.store import SessionStore, DISPATCH_TIMING_COLUMNS
from src.main import report_client_timings, get_latency_percentiles_endpoint


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """Isolated SessionStore on a tmp DB."""
    db_path = tmp_path / "test.db"
    s = SessionStore(db_path)
    await s.initialize()
    yield s
    await s.close()


# --- report_client_timings() tests ------------------------------------------


class TestReportClientTimings:
    """Test report_client_timings() endpoint function behavior."""

    @pytest.mark.asyncio
    async def test_report_timings_creates_row_with_client_fields(self, store: SessionStore):
        """report_client_timings() creates a new row with client-reported fields."""
        intent_id = "test-client-1"

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            response = await report_client_timings({
                "intent_id": intent_id,
                "stt_ms": 312,
                "first_render_ms": 90,
            })

            # Success returns dict, error returns JSONResponse
            assert isinstance(response, dict)
            assert response["ok"] is True
            assert response["intent_id"] == intent_id
            assert set(response["recorded"]) == {"stt_ms", "first_render_ms"}

            # Verify in database
            timings = await store.get_dispatch_timings(intent_id)
            assert timings is not None
            assert timings["intent_id"] == intent_id
            assert timings["stt_ms"] == 312
            assert timings["first_render_ms"] == 90
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_report_timings_upserts_into_existing_row(self, store: SessionStore):
        """Client-reported fields upsert into server-written row without clobbering server-side stages."""
        intent_id = "test-upsert-merge"

        # First, create a server-written row with server-side stages
        await store.record_dispatch_timings(
            intent_id,
            router_ms=123,
            fetch_total_ms=456,
            synthesize_total_ms=789,
        )

        # Verify initial state
        timings = await store.get_dispatch_timings(intent_id)
        assert timings["router_ms"] == 123
        assert timings["fetch_total_ms"] == 456
        assert timings["synthesize_total_ms"] == 789
        assert timings["stt_ms"] is None
        assert timings["first_render_ms"] is None

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            # Now report client-reported fields
            response = await report_client_timings({
                "intent_id": intent_id,
                "stt_ms": 312,
                "first_render_ms": 90,
            })

            assert isinstance(response, dict)
            assert response["ok"] is True

            # Verify server stages are untouched, client fields added
            timings = await store.get_dispatch_timings(intent_id)
            assert timings["router_ms"] == 123, "Server router_ms should be preserved"
            assert timings["fetch_total_ms"] == 456, "Server fetch_total_ms should be preserved"
            assert timings["synthesize_total_ms"] == 789, "Server synthesize_total_ms should be preserved"
            assert timings["stt_ms"] == 312, "Client stt_ms should be added"
            assert timings["first_render_ms"] == 90, "Client first_render_ms should be added"
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_report_timings_partial_client_fields(self, store: SessionStore):
        """Report with only one client field (e.g., just stt_ms) works correctly."""
        intent_id = "test-partial-client"

        # Create server-written row
        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,
            synthesize_total_ms=200,
        )

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            # Report only stt_ms (no first_render_ms)
            response = await report_client_timings({
                "intent_id": intent_id,
                "stt_ms": 312,
            })

            assert isinstance(response, dict)
            assert response["ok"] is True
            assert response["recorded"] == ["stt_ms"]

            # Verify: server stages intact, stt_ms set, first_render_ms still NULL
            timings = await store.get_dispatch_timings(intent_id)
            assert timings["router_ms"] == 100
            assert timings["synthesize_total_ms"] == 200
            assert timings["stt_ms"] == 312
            assert timings["first_render_ms"] is None
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_report_timings_ignores_unknown_fields(self, store: SessionStore):
        """Unknown fields in request body are ignored gracefully."""
        intent_id = "test-unknown-fields"

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            response = await report_client_timings({
                "intent_id": intent_id,
                "stt_ms": 312,
                "unknown_field": "should_be_ignored",
                "another_unknown": 12345,
            })

            assert isinstance(response, dict)
            assert response["ok"] is True
            assert response["recorded"] == ["stt_ms"]

            # Verify only known field was written
            timings = await store.get_dispatch_timings(intent_id)
            assert timings is not None
            assert timings["stt_ms"] == 312
            assert timings["first_render_ms"] is None
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_report_timings_requires_intent_id(self):
        """Missing intent_id returns 400 error."""
        response = await report_client_timings({
            "stt_ms": 312,
            "first_render_ms": 90,
        })

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        assert "intent_id is required" in response.body.decode()

    @pytest.mark.asyncio
    async def test_report_timings_handles_unknown_intent_id(self, store: SessionStore):
        """Unknown intent_id creates a new row (idempotent)."""
        unknown_intent_id = "test-unknown-intent-id-never-seen-before"

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            response = await report_client_timings({
                "intent_id": unknown_intent_id,
                "stt_ms": 312,
            })

            assert isinstance(response, dict)
            assert response["ok"] is True

            # Verify row was created
            timings = await store.get_dispatch_timings(unknown_intent_id)
            assert timings is not None
            assert timings["intent_id"] == unknown_intent_id
            assert timings["stt_ms"] == 312
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_report_timings_string_to_int_conversion(self, store: SessionStore):
        """String values for timing fields are converted to int."""
        intent_id = "test-string-conv"

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            response = await report_client_timings({
                "intent_id": intent_id,
                "stt_ms": "312",  # String instead of int
                "first_render_ms": "90",
            })

            assert isinstance(response, dict)
            assert response["ok"] is True

            # Verify values were converted to int
            timings = await store.get_dispatch_timings(intent_id)
            assert timings["stt_ms"] == 312
            assert timings["first_render_ms"] == 90
            assert isinstance(timings["stt_ms"], int)
        finally:
            main_module.get_store = original_get_store


# --- get_latency_percentiles_endpoint() tests -------------------------------


class TestLatencyPercentilesEndpoint:
    """Test get_latency_percentiles_endpoint() function behavior."""

    @pytest.mark.asyncio
    async def test_get_percentiles_returns_empty_dict_when_no_data(self, store: SessionStore):
        """get_latency_percentiles_endpoint() returns empty dict when no timing data exists."""
        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            response = await get_latency_percentiles_endpoint(since=None)
            assert response == {}
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_get_percentiles_returns_correct_shape(self, store: SessionStore):
        """get_latency_percentiles_endpoint() returns {stage: {p50, p95, count}} for stages with data."""
        # Create sample data
        for i, ms in enumerate([100, 150, 200, 250, 300]):
            intent_id = f"test-percentiles-shape-{i}"
            await store.record_dispatch_timings(intent_id, router_ms=ms)

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            response = await get_latency_percentiles_endpoint(since=None)

            assert "router_ms" in response
            assert "p50" in response["router_ms"]
            assert "p95" in response["router_ms"]
            assert "count" in response["router_ms"]
            assert response["router_ms"]["count"] == 5
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_get_percentiles_multiple_stages(self, store: SessionStore):
        """get_latency_percentiles_endpoint() returns percentiles for all stages with data."""
        # Create timings with multiple stages
        for i in range(3):
            intent_id = f"test-multi-stage-{i}"
            await store.record_dispatch_timings(
                intent_id,
                router_ms=100 + i * 50,
                fetch_total_ms=200 + i * 100,
                synthesize_total_ms=300 + i * 150,
            )

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            response = await get_latency_percentiles_endpoint(since=None)

            assert "router_ms" in response
            assert "fetch_total_ms" in response
            assert "synthesize_total_ms" in response
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_get_percentiles_stages_with_all_null_rows_are_absent(self, store: SessionStore):
        """Stages with all-NULL rows simply don't appear in response."""
        # Create rows only for router_ms (no fetch_total_ms data)
        for i in range(3):
            intent_id = f"test-null-stages-{i}"
            await store.record_dispatch_timings(
                intent_id,
                router_ms=100 + i * 50,
            )

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            response = await get_latency_percentiles_endpoint(since=None)

            assert "router_ms" in response, "router_ms should be present (has data)"
            assert "fetch_total_ms" not in response, "fetch_total_ms should be absent (all NULL)"
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_get_percentiles_with_since_windowing(self, store: SessionStore):
        """since query-param filters to recent dispatches only."""
        now = int(datetime.now(timezone.utc).timestamp())

        # Create old timing (1 hour ago)
        old_intent_id = "test-old-percentile"
        await store.record_dispatch_timings(old_intent_id, router_ms=1000)

        # Manually set created_at to 1 hour ago
        import aiosqlite
        async with aiosqlite.connect(store.db_path) as db:
            one_hour_ago = now - 3600
            await db.execute(
                "UPDATE dispatch_timings SET created_at = ? WHERE intent_id = ?",
                (one_hour_ago, old_intent_id)
            )
            await db.commit()

        # Create recent timing (now)
        recent_intent_id = "test-recent-percentile"
        await store.record_dispatch_timings(recent_intent_id, router_ms=100)

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            # Without since filter, should get both
            all_response = await get_latency_percentiles_endpoint(since=None)
            assert all_response["router_ms"]["count"] == 2

            # With since filter (5 minutes ago), should only get recent
            five_minutes_ago = now - 300
            recent_response = await get_latency_percentiles_endpoint(since=five_minutes_ago)
            assert recent_response["router_ms"]["count"] == 1
            assert recent_response["router_ms"]["p50"] == 100
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_get_percentiles_matches_store_output(self, store: SessionStore):
        """Endpoint output matches store.get_latency_percentiles() for the same data."""
        # Create sample data
        values = [100, 150, 200, 250, 300]
        for i, ms in enumerate(values):
            intent_id = f"test-store-match-{i}"
            await store.record_dispatch_timings(intent_id, router_ms=ms)

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            # Get endpoint output
            endpoint_data = await get_latency_percentiles_endpoint(since=None)

            # Get store output
            store_data = await store.get_latency_percentiles()

            # They should match
            assert endpoint_data == store_data
        finally:
            main_module.get_store = original_get_store

    @pytest.mark.asyncio
    async def test_get_percentiles_with_client_reported_fields(self, store: SessionStore):
        """Client-reported fields (stt_ms, first_render_ms) appear in percentiles."""
        # Create rows with client-reported fields
        for i, ms in enumerate([200, 250, 300]):
            intent_id = f"test-client-percentile-{i}"
            await store.record_dispatch_timings(
                intent_id,
                stt_ms=ms,
                first_render_ms=ms + 50,
            )

        # Mock get_store to return our test store
        from src import main as main_module
        original_get_store = main_module.get_store

        async def mock_get_store():
            return store

        main_module.get_store = mock_get_store

        try:
            response = await get_latency_percentiles_endpoint(since=None)

            assert "stt_ms" in response
            assert "first_render_ms" in response
            assert response["stt_ms"]["count"] == 3
            assert response["first_render_ms"]["count"] == 3
        finally:
            main_module.get_store = original_get_store
