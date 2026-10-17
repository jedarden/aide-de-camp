"""
Comprehensive unit tests for dispatch_timings store layer and DispatchTimings collector (bead adc-4ap7o).

This test suite verifies:
- dispatch_timings schema/columns
- record_dispatch_timings() upsert behavior (INSERT OR IGNORE row creation, partial writes must NOT clobber stages set by an earlier write)
- get_dispatch_timings()
- get_latency_percentiles() with nearest-rank p50/p95 verified against hand-computed fixture
- since-window filtering
- DispatchTimings collector: record() skips None, raises KeyError on unknown stage
- DispatchTimings: elapsed_ms(), to_fields() only emits measured stages
- percentiles() math against known inputs

Acceptance criteria:
- New unit tests pass under .venv/bin/pytest
- p50/p95 match hand-computed nearest-rank fixture (ceil(q/100*n))
- A partial-upsert test proves a second record_dispatch_timings(sse_emit_ms=...) call does NOT null router_ms set earlier
- Full existing suite still passes
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from src.session.store import SessionStore, DISPATCH_TIMING_COLUMNS
from src.instrument.timings import (
    DispatchTimings,
    DISPATCH_TIMING_STAGES,
    percentiles,
)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """Isolated SessionStore on a tmp DB."""
    db_path = tmp_path / "test.db"
    s = SessionStore(db_path)
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
def mock_clock() -> MagicMock:
    """Mock monotonic clock that returns deterministic timestamps."""
    clock = MagicMock()
    # Simulate 0, 0.5, 1.0, 1.5... seconds per call
    clock.side_effect = [i * 0.5 for i in range(100)]
    return clock


# --- Schema verification tests ----------------------------------------------


class TestDispatchTimingsSchema:
    """Verify dispatch_timings table has the correct schema and columns."""

    @pytest.mark.asyncio
    async def test_dispatch_timings_table_has_correct_columns(self, store: SessionStore):
        """dispatch_timings table exists with all expected columns."""
        import aiosqlite

        async with aiosqlite.connect(store.db_path) as db:
            # Get table schema
            cursor = await db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='dispatch_timings'"
            )
            result = await cursor.fetchone()
            assert result is not None, "dispatch_timings table does not exist"

            schema = result[0]

            # Verify all expected columns are present
            expected_columns = [
                "intent_id",
                "router_ms",
                "fetch_first_source_ms",
                "fetch_total_ms",
                "synthesize_first_token_ms",
                "synthesize_total_ms",
                "escalate_ms",
                "sse_emit_ms",
                "stt_ms",
                "first_render_ms",
                "created_at",
            ]

            for col in expected_columns:
                assert col in schema, f"Column {col} not found in dispatch_timings schema"

    @pytest.mark.asyncio
    async def test_dispatch_timings_primary_key_is_intent_id(self, store: SessionStore):
        """intent_id is the PRIMARY KEY of dispatch_timings."""
        import aiosqlite

        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='dispatch_timings'"
            )
            result = await cursor.fetchone()
            schema = result[0]

            # Normalize whitespace for comparison
            assert "PRIMARY KEY" in schema and "intent_id" in schema, \
                "intent_id should be PRIMARY KEY"
            # Verify intent_id comes before PRIMARY KEY in the schema
            assert schema.index("intent_id") < schema.index("PRIMARY KEY"), \
                "intent_id should be the PRIMARY KEY column"

    @pytest.mark.asyncio
    async def test_dispatch_timings_created_at_is_not_null(self, store: SessionStore):
        """created_at column has NOT NULL constraint."""
        import aiosqlite

        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='dispatch_timings'"
            )
            result = await cursor.fetchone()
            schema = result[0]

            # Find created_at definition
            for line in schema.split(','):
                if 'created_at' in line:
                    assert 'NOT NULL' in line, "created_at should have NOT NULL constraint"
                    break


# --- record_dispatch_timings() tests ---------------------------------------


class TestRecordDispatchTimings:
    """Test record_dispatch_timings() upsert behavior."""

    @pytest.mark.asyncio
    async def test_record_dispatch_timings_creates_row_on_first_call(self, store: SessionStore):
        """First record_dispatch_timings() call creates a new row."""
        intent_id = "test-intent-1"
        now = int(datetime.now(timezone.utc).timestamp())

        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,
            fetch_total_ms=500,
        )

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None, "Row should have been created"
        assert timings["intent_id"] == intent_id
        assert timings["router_ms"] == 100
        assert timings["fetch_total_ms"] == 500
        assert timings["created_at"] is not None

    @pytest.mark.asyncio
    async def test_record_dispatch_timings_upserts_by_intent_id(self, store: SessionStore):
        """record_dispatch_timings() upserts using intent_id as PRIMARY KEY."""
        intent_id = "test-intest-upsert"

        # First write
        await store.record_dispatch_timings(
            intent_id,
            router_ms=150,
        )

        # Second write with different columns
        await store.record_dispatch_timings(
            intent_id,
            fetch_total_ms=750,
            synthesize_total_ms=300,
        )

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings["intent_id"] == intent_id
        assert timings["router_ms"] == 150, "First write should be preserved"
        assert timings["fetch_total_ms"] == 750
        assert timings["synthesize_total_ms"] == 300

        # Should still be only one row
        import aiosqlite
        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM dispatch_timings WHERE intent_id = ?",
                (intent_id,)
            )
            count = (await cursor.fetchone())[0]
            assert count == 1, "Should only have one row per intent_id"

    @pytest.mark.asyncio
    async def test_partial_upsert_does_not_clobber_existing_values(self, store: SessionStore):
        """
        Second record_dispatch_timings(sse_emit_ms=...) call does NOT null router_ms set earlier.
        This is the critical test proving partial upsert works correctly.
        """
        intent_id = "test-partial-upsert"

        # First write: set router_ms
        await store.record_dispatch_timings(
            intent_id,
            router_ms=123,
        )

        # Verify first write
        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings["router_ms"] == 123
        assert timings["sse_emit_ms"] is None, "sse_emit_ms should be NULL initially"

        # Second write: only set sse_emit_ms (partial write)
        await store.record_dispatch_timings(
            intent_id,
            sse_emit_ms=456,
        )

        # Verify both values are present (second write did NOT null router_ms)
        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings["router_ms"] == 123, "router_ms should still be 123 after partial upsert"
        assert timings["sse_emit_ms"] == 456, "sse_emit_ms should be set to 456"

    @pytest.mark.asyncio
    async def test_record_dispatch_timings_skips_none_values(self, store: SessionStore):
        """record_dispatch_timings() skips None values (does not write NULL)."""
        intent_id = "test-none-skipping"

        # Write with some None values
        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,
            fetch_total_ms=None,  # Should be skipped
            synthesize_total_ms=200,
        )

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings["router_ms"] == 100
        assert timings["fetch_total_ms"] is None, "fetch_total_ms=None should have been skipped"
        assert timings["synthesize_total_ms"] == 200

    @pytest.mark.asyncio
    async def test_record_dispatch_timings_rejects_unknown_columns(self, store: SessionStore):
        """record_dispatch_timings() ignores columns not in DISPATCH_TIMING_COLUMNS."""
        intent_id = "test-unknown-cols"

        # This should not raise, but unknown columns should be ignored
        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,
            unknown_column=999,  # Should be ignored
        )

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings["router_ms"] == 100
        # unknown_column is not in the schema, so we just verify it didn't break anything

    @pytest.mark.asyncio
    async def test_record_dispatch_timings_sets_created_at_once_on_insert(self, store: SessionStore):
        """created_at is set once on first INSERT OR IGNORE and never overwritten."""
        intent_id = "test-created-at-once"

        # First write - sets created_at
        await store.record_dispatch_timings(intent_id, router_ms=100)

        first_timings = await store.get_dispatch_timings(intent_id)
        assert first_timings is not None
        first_created_at = first_timings["created_at"]

        # Wait a bit to ensure timestamp would differ
        import asyncio
        await asyncio.sleep(0.01)

        # Second write - should NOT change created_at
        await store.record_dispatch_timings(intent_id, fetch_total_ms=500)

        second_timings = await store.get_dispatch_timings(intent_id)
        assert second_timings is not None
        assert second_timings["created_at"] == first_created_at, \
            "created_at should not change on upsert"


# --- get_dispatch_timings() tests ------------------------------------------


class TestGetDispatchTimings:
    """Test get_dispatch_timings() retrieval behavior."""

    @pytest.mark.asyncio
    async def test_get_dispatch_timings_returns_none_for_nonexistent_intent(self, store: SessionStore):
        """get_dispatch_timings() returns None when intent_id doesn't exist."""
        timings = await store.get_dispatch_timings("nonexistent-intent")
        assert timings is None

    @pytest.mark.asyncio
    async def test_get_dispatch_timings_returns_all_columns(self, store: SessionStore):
        """get_dispatch_timings() returns all columns including NULL ones."""
        intent_id = "test-all-columns"

        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,
            fetch_total_ms=500,
        )

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None

        # Verify all timing columns are present in the result
        for col in DISPATCH_TIMING_COLUMNS:
            assert col in timings, f"Column {col} missing from result"

    @pytest.mark.asyncio
    async def test_get_dispatch_timings_returns_correct_intent_id(self, store: SessionStore):
        """get_dispatch_timings() returns the correct intent_id."""
        intent_id = "test-correct-id"

        await store.record_dispatch_timings(intent_id, router_ms=100)

        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None
        assert timings["intent_id"] == intent_id


# --- get_latency_percentiles() tests ----------------------------------------


class TestGetLatencyPercentiles:
    """Test get_latency_percentiles() aggregation and nearest-rank calculation."""

    @pytest.mark.asyncio
    async def test_get_latency_percentiles_returns_empty_dict_when_no_data(self, store: SessionStore):
        """get_latency_percentiles() returns empty dict when no timing data exists."""
        percentiles_result = await store.get_latency_percentiles()
        assert percentiles_result == {}

    @pytest.mark.asyncio
    async def test_get_latency_percentiles_returns_p50_p95_per_stage(self, store: SessionStore):
        """get_latency_percentiles() returns p50 and p95 for each stage with data."""
        # Create multiple dispatch timings with router_ms values
        for i, ms in enumerate([100, 150, 200, 250, 300]):
            intent_id = f"test-percentiles-{i}"
            await store.record_dispatch_timings(intent_id, router_ms=ms)

        percentiles_result = await store.get_latency_percentiles()

        assert "router_ms" in percentiles_result
        assert "p50" in percentiles_result["router_ms"]
        assert "p95" in percentiles_result["router_ms"]
        assert "count" in percentiles_result["router_ms"]
        assert percentiles_result["router_ms"]["count"] == 5

    @pytest.mark.asyncio
    async def test_get_latency_percentiles_p50_nearest_rank_verification(self, store: SessionStore):
        """
        Verify p50 calculation against hand-computed nearest-rank fixture.
        For [100, 150, 200, 250, 300]:
        - n = 5
        - p50 index = ceil(0.50 * 5) - 1 = ceil(2.5) - 1 = 3 - 1 = 2
        - sorted values: [100, 150, 200, 250, 300]
        - index 2 = 200
        """
        values = [100, 150, 200, 250, 300]
        for i, ms in enumerate(values):
            intent_id = f"test-p50-{i}"
            await store.record_dispatch_timings(intent_id, router_ms=ms)

        percentiles_result = await store.get_latency_percentiles()

        # Hand-computed p50 = 200
        assert percentiles_result["router_ms"]["p50"] == 200

    @pytest.mark.asyncio
    async def test_get_latency_percentiles_p95_nearest_rank_verification(self, store: SessionStore):
        """
        Verify p95 calculation against hand-computed nearest-rank fixture.
        For [100, 150, 200, 250, 300]:
        - n = 5
        - p95 index = ceil(0.95 * 5) - 1 = ceil(4.75) - 1 = 5 - 1 = 4
        - sorted values: [100, 150, 200, 250, 300]
        - index 4 = 300
        """
        values = [100, 150, 200, 250, 300]
        for i, ms in enumerate(values):
            intent_id = f"test-p95-{i}"
            await store.record_dispatch_timings(intent_id, router_ms=ms)

        percentiles_result = await store.get_latency_percentiles()

        # Hand-computed p95 = 300
        assert percentiles_result["router_ms"]["p95"] == 300

    @pytest.mark.asyncio
    async def test_get_latency_percentiles_with_larger_dataset(self, store: SessionStore):
        """
        Verify p50/p95 against a larger dataset.
        For [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        - n = 10
        - p50 index = ceil(0.50 * 10) - 1 = ceil(5.0) - 1 = 5 - 1 = 4
        - p95 index = ceil(0.95 * 10) - 1 = ceil(9.5) - 1 = 10 - 1 = 9
        - sorted: [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        - p50 = index 4 = 50
        - p95 = index 9 = 100
        """
        values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        for i, ms in enumerate(values):
            intent_id = f"test-large-{i}"
            await store.record_dispatch_timings(intent_id, router_ms=ms)

        percentiles_result = await store.get_latency_percentiles()

        assert percentiles_result["router_ms"]["p50"] == 50, "p50 should be 50"
        assert percentiles_result["router_ms"]["p95"] == 100, "p95 should be 100"

    @pytest.mark.asyncio
    async def test_get_latency_percentiles_skips_null_values(self, store: SessionStore):
        """get_latency_percentiles() skips NULL values for a stage."""
        intent_ids = []

        # Create some rows with router_ms, some without
        for i, ms in enumerate([100, None, 200, None, 300]):
            intent_id = f"test-null-skip-{i}"
            intent_ids.append(intent_id)
            if ms is not None:
                await store.record_dispatch_timings(intent_id, router_ms=ms)
            else:
                # Create row without router_ms
                await store.record_dispatch_timings(intent_id, fetch_total_ms=500)

        percentiles_result = await store.get_latency_percentiles()

        # Should only count non-NULL values
        assert "router_ms" in percentiles_result
        assert percentiles_result["router_ms"]["count"] == 3

    @pytest.mark.asyncio
    async def test_get_latency_percentiles_with_since_window_filtering(self, store: SessionStore):
        """since parameter filters to recent dispatches only."""
        import time

        now = int(datetime.now(timezone.utc).timestamp())

        # Create old timing (1 hour ago)
        old_intent_id = "test-old-timing"
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
        recent_intent_id = "test-recent-timing"
        await store.record_dispatch_timings(recent_intent_id, router_ms=100)

        # Without since filter, should get both
        all_percentiles = await store.get_latency_percentiles()
        assert all_percentiles["router_ms"]["count"] == 2
        # p50 of [100, 1000]: ceil(0.50 * 2) - 1 = 0, sorted[0] = 100
        assert all_percentiles["router_ms"]["p50"] == 100

        # With since filter (5 minutes ago), should only get recent
        five_minutes_ago = now - 300
        recent_percentiles = await store.get_latency_percentiles(since=five_minutes_ago)
        assert recent_percentiles["router_ms"]["count"] == 1
        assert recent_percentiles["router_ms"]["p50"] == 100
        assert recent_percentiles["router_ms"]["p95"] == 100

    @pytest.mark.asyncio
    async def test_get_latency_percentiles_returns_multiple_stages(self, store: SessionStore):
        """get_latency_percentiles() returns percentiles for all stages with data."""
        # Create timings with multiple stages
        for i in range(3):
            intent_id = f"test-multi-stage-{i}"
            await store.record_dispatch_timings(
                intent_id,
                router_ms=100 + i * 50,
                fetch_total_ms=200 + i * 100,
                synthesize_total_ms=300 + i * 150,
            )

        percentiles_result = await store.get_latency_percentiles()

        assert "router_ms" in percentiles_result
        assert "fetch_total_ms" in percentiles_result
        assert "synthesize_total_ms" in percentiles_result


# --- DispatchTimings collector tests ----------------------------------------


class TestDispatchTimingsCollector:
    """Test DispatchTimings collector behavior."""

    def test_dispatch_timings_init(self, mock_clock: MagicMock):
        """DispatchTimings initializes with clock and empty durations."""
        timings = DispatchTimings(clock=mock_clock)

        assert timings.clock == mock_clock
        assert timings._durations == {}

    def test_dispatch_timings_record_skips_none(self, mock_clock: MagicMock):
        """record() skips None values (stage stays absent)."""
        timings = DispatchTimings(clock=mock_clock)

        timings.record("router_ms", None)

        assert timings.get("router_ms") is None, "None should be skipped"

    def test_dispatch_timings_record_stores_value(self, mock_clock: MagicMock):
        """record() stores the stage duration."""
        timings = DispatchTimings(clock=mock_clock)

        timings.record("router_ms", 123)

        assert timings.get("router_ms") == 123

    def test_dispatch_timings_record_raises_keyerror_on_unknown_stage(self, mock_clock: MagicMock):
        """record() raises KeyError on unknown stage name."""
        timings = DispatchTimings(clock=mock_clock)

        with pytest.raises(KeyError, match="Unknown dispatch timing stage"):
            timings.record("unknown_stage_ms", 100)

    def test_dispatch_timings_record_accepts_all_valid_stages(self, mock_clock: MagicMock):
        """record() accepts all stages in DISPATCH_TIMING_STAGES."""
        timings = DispatchTimings(clock=mock_clock)

        for stage in DISPATCH_TIMING_STAGES:
            timings.record(stage, 100)  # Should not raise

    def test_dispatch_timings_record_converts_float_to_int(self, mock_clock: MagicMock):
        """record() converts float values to int."""
        timings = DispatchTimings(clock=mock_clock)

        timings.record("router_ms", 123.456)

        assert timings.get("router_ms") == 123

    def test_dispatch_timings_elapsed_ms(self, mock_clock: MagicMock):
        """elapsed_ms() returns milliseconds between two timestamps."""
        timings = DispatchTimings(clock=mock_clock)

        # Use the first clock value as start (0.0 from fixture)
        start = mock_clock()
        # Next clock call will return 0.5
        elapsed = timings.elapsed_ms(start)

        assert elapsed == 500  # 0.5 seconds = 500ms

    def test_dispatch_timings_elapsed_ms_with_end(self, mock_clock: MagicMock):
        """elapsed_ms() with explicit end parameter."""
        timings = DispatchTimings(clock=mock_clock)

        start = 0.0
        end = 1.0
        elapsed = timings.elapsed_ms(start, end)

        assert elapsed == 1000  # 1.0 seconds = 1000ms

    def test_dispatch_timings_to_fields_returns_only_measured_stages(self, mock_clock: MagicMock):
        """to_fields() only emits stages that were actually measured."""
        timings = DispatchTimings(clock=mock_clock)

        timings.record("router_ms", 100)
        timings.record("fetch_total_ms", 500)
        # Don't record other stages

        fields = timings.to_fields()

        assert fields == {
            "router_ms": 100,
            "fetch_total_ms": 500,
        }
        assert "synthesize_total_ms" not in fields, "Unmeasured stages should be absent"

    def test_dispatch_timings_get_returns_none_for_unmeasured_stage(self, mock_clock: MagicMock):
        """get() returns None for unmeasured stages."""
        timings = DispatchTimings(clock=mock_clock)

        assert timings.get("router_ms") is None


# --- percentiles() helper tests --------------------------------------------


class TestPercentilesHelper:
    """Test percentiles() helper function."""

    def test_percentiles_returns_empty_dict_for_empty_qs(self):
        """percentiles() returns empty dict when qs is empty."""
        result = percentiles([1, 2, 3], qs=())
        assert result == {}

    def test_percentiles_raises_on_empty_values(self):
        """percentiles() raises ValueError on empty values list."""
        with pytest.raises(ValueError, match="requires at least one value"):
            percentiles([])

    def test_percentiles_raises_on_invalid_q(self):
        """percentiles() raises ValueError on q outside [0, 100]."""
        with pytest.raises(ValueError, match="must be in \\[0, 100\\]"):
            percentiles([1, 2, 3], qs=(150,))

    def test_percentiles_single_value(self):
        """percentiles() returns the single value for any percentile."""
        result = percentiles([42], qs=(50, 95))
        assert result == {50: 42, 95: 42}

    def test_percentiles_p50_nearest_rank_formula(self):
        """
        Verify p50 uses ceil(q/100 * n) - 1 formula.
        For [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        - n = 10
        - p50 index = ceil(0.50 * 10) - 1 = ceil(5.0) - 1 = 5 - 1 = 4
        - sorted[4] = 5
        """
        result = percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], qs=(50,))
        assert result == {50: 5}

    def test_percentiles_p95_nearest_rank_formula(self):
        """
        Verify p95 uses ceil(q/100 * n) - 1 formula.
        For [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        - n = 10
        - p95 index = ceil(0.95 * 10) - 1 = ceil(9.5) - 1 = 10 - 1 = 9
        - sorted[9] = 10
        """
        result = percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], qs=(95,))
        assert result == {95: 10}

    def test_percentiles_clamps_index_to_bounds(self):
        """
        percentiles() clamps index to [0, n-1].
        For q=100, index = ceil(1.0 * n) - 1 = n - 1, which is the last element.
        """
        result = percentiles([10, 20, 30], qs=(100,))
        assert result == {100: 30}  # Last element

    def test_percentiles_unsorted_input(self):
        """percentiles() sorts input before computing percentiles."""
        result = percentiles([5, 1, 3, 2, 4], qs=(50,))
        assert result == {50: 3}  # Median of [1, 2, 3, 4, 5]

    def test_percentiles_duplicate_values(self):
        """percentiles() handles duplicate values correctly."""
        result = percentiles([10, 10, 10, 10], qs=(50, 95))
        assert result == {50: 10, 95: 10}

    def test_percentiles_multiple_percentiles_at_once(self):
        """percentiles() can compute multiple percentiles in one call."""
        result = percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], qs=(25, 50, 75, 95))
        expected = {
            25: 3,   # ceil(0.25 * 10) - 1 = 3 - 1 = 2 -> sorted[2] = 3
            50: 5,   # ceil(0.50 * 10) - 1 = 5 - 1 = 4 -> sorted[4] = 5
            75: 8,   # ceil(0.75 * 10) - 1 = 8 - 1 = 7 -> sorted[7] = 8
            95: 10,  # ceil(0.95 * 10) - 1 = 10 - 1 = 9 -> sorted[9] = 10
        }
        assert result == expected

    def test_percentiles_p0_returns_minimum(self):
        """percentiles(0) returns the minimum value."""
        result = percentiles([10, 20, 30, 40, 50], qs=(0,))
        assert result == {0: 10}  # First element

    def test_percentiles_p100_returns_maximum(self):
        """percentiles(100) returns the maximum value."""
        result = percentiles([10, 20, 30, 40, 50], qs=(100,))
        assert result == {100: 50}  # Last element
