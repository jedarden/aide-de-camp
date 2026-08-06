"""
Tests for bounded concurrency limit on synthesize operations.

Verifies that the asyncio.Semaphore-based concurrency limiter:
1. Bounds concurrent synthesize calls to the configured limit
2. Allows queued calls to proceed when slots free up
3. Works correctly across multiple parallel dispatches
"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.concurrency import get_concurrency_limiter, reset_concurrency_limiter


class TestConcurrencyLimiter:
    """Test suite for ConcurrencyLimiter behavior."""

    def test_initialization_default_limit(self):
        """Verify limiter initializes with default limit."""
        reset_concurrency_limiter()  # Reset to default
        limiter = get_concurrency_limiter()
        assert limiter.limit == 8  # DEFAULT_SYNTHESIZE_CONCURRENCY_LIMIT

    def test_initialization_custom_limit(self):
        """Verify limiter accepts custom limit."""
        reset_concurrency_limiter(limit=3)
        limiter = get_concurrency_limiter()
        assert limiter.limit == 3

    def test_reset_concurrency_limiter(self):
        """Verify reset creates a new limiter instance."""
        limiter1 = get_concurrency_limiter()
        reset_concurrency_limiter(limit=5)
        limiter2 = get_concurrency_limiter()
        assert limiter2.limit == 5
        # Different instance
        assert limiter1 is not limiter2


class TestConcurrencyBehavior:
    """Test suite for actual concurrency control behavior."""

    @pytest.mark.asyncio
    async def test_concurrency_limit_respected(self):
        """
        Test that concurrent calls are bounded by the limit.

        Sets limit=3, launches 6 concurrent tasks, and verifies
        that no more than 3 execute simultaneously.
        """
        reset_concurrency_limiter(limit=3)
        limiter = get_concurrency_limiter()

        # Track active calls
        active_count = 0
        max_active = 0
        lock = asyncio.Lock()

        async def fake_synthesize_call(duration: float) -> int:
            """Mock synthesize call that tracks concurrency under limiter control."""
            nonlocal active_count, max_active

            async with limiter:
                async with lock:
                    active_count += 1
                    if active_count > max_active:
                        max_active = active_count

                # Simulate work
                await asyncio.sleep(duration)

                async with lock:
                    active_count -= 1

            return active_count

        # Launch 6 concurrent tasks, each taking 0.1s
        tasks = [
            fake_synthesize_call(0.1)
            for _ in range(6)
        ]

        results = await asyncio.gather(*tasks)

        # Verify limit was never exceeded
        assert max_active <= 3, f"Max concurrent calls {max_active} exceeded limit 3"

    @pytest.mark.asyncio
    async def test_queued_calls_proceed(self):
        """
        Test that queued calls proceed when slots free up.

        Verifies that when the limit is reached, additional calls wait
        and then execute successfully.
        """
        reset_concurrency_limiter(limit=2)

        execution_log = []

        async def tracked_call(call_id: int, duration: float):
            """Mock call that logs entry/exit times."""
            limiter = get_concurrency_limiter()
            async with limiter:
                execution_log.append(("start", call_id, time.time()))
                await asyncio.sleep(duration)
                execution_log.append(("end", call_id, time.time()))

        # Launch 4 calls with limit=2
        # First 2 should run immediately, next 2 should queue
        tasks = [
            tracked_call(1, 0.05),
            tracked_call(2, 0.05),
            tracked_call(3, 0.05),
            tracked_call(4, 0.05),
        ]

        await asyncio.gather(*tasks)

        # Verify all 4 calls completed
        starts = [log for log in execution_log if log[0] == "start"]
        ends = [log for log in execution_log if log[0] == "end"]
        assert len(starts) == 4
        assert len(ends) == 4

        # Verify calls 3 and 4 started after 1 or 2 ended
        start_1 = next(t for t in execution_log if t[1] == 1 and t[0] == "start")[2]
        start_3 = next(t for t in execution_log if t[1] == 3 and t[0] == "start")[2]
        end_1 = next(t for t in execution_log if t[1] == 1 and t[0] == "end")[2]

        # Call 3 should start after call 1 or 2 ended (due to limit=2)
        assert start_3 >= end_1 - 0.01, "Call 3 should wait for a slot to free"

    @pytest.mark.asyncio
    async def test_concurrent_high_water_mark(self):
        """
        Test tracking the high-water mark of concurrent calls.

        Simulates a realistic workload where:
        - Router splits utterance into many threads
        - Each thread calls synthesize_intent()
        - Concurrency limiter bounds parallel LLM calls
        """
        reset_concurrency_limiter(limit=5)

        # Use the real ConcurrencyLimiter
        limiter = get_concurrency_limiter()

        active_count = 0
        max_active = 0
        lock = asyncio.Lock()

        async def mock_llm_call():
            """Mock LLM call under concurrency control."""
            nonlocal active_count, max_active

            async with limiter:
                async with lock:
                    active_count += 1
                    if active_count > max_active:
                        max_active = active_count

                # Simulate LLM latency (50ms)
                await asyncio.sleep(0.05)

                async with lock:
                    active_count -= 1

            return "synthesized_result"

        # Launch 15 concurrent calls (3x the limit)
        tasks = [mock_llm_call() for _ in range(15)]
        await asyncio.gather(*tasks)

        # Verify high-water mark never exceeded limit
        assert max_active <= 5, f"High-water mark {max_active} exceeded limit 5"

    @pytest.mark.asyncio
    async def test_context_manager_usage(self):
        """Test that limiter works as an async context manager."""
        reset_concurrency_limiter(limit=2)

        limiter = get_concurrency_limiter()
        acquired = []

        async def acquire_release():
            async with limiter:
                acquired.append(time.time())
                await asyncio.sleep(0.01)

        # Launch 4 concurrent tasks
        tasks = [acquire_release() for _ in range(4)]
        await asyncio.gather(*tasks)

        assert len(acquired) == 4


class TestSynthesizeIntegration:
    """Integration tests with synthesize strand."""

    @pytest.mark.asyncio
    async def test_synthesize_respects_limit(self):
        """
        Test that synthesize_intent calls respect the concurrency limit.

        Uses a mock ZAI client to simulate LLM latency while avoiding
        real network calls.
        """
        from src.synthesize.strand import SynthesizeRequest, synthesize_intent
        from src.fetch.commands import IntentType, FetchResult, FetchCoverage
        from src.concurrency import reset_concurrency_limiter

        # Set low limit for test
        reset_concurrency_limiter(limit=2)
        limiter = get_concurrency_limiter()

        active_count = 0
        max_active = 0
        lock = asyncio.Lock()

        # Mock the ZAI client to track concurrency
        async def mock_call_simple(*args, **kwargs):
            nonlocal active_count, max_active

            # This code runs inside limiter context in synthesize()
            async with lock:
                active_count += 1
                if active_count > max_active:
                    max_active = active_count

            await asyncio.sleep(0.02)  # Simulate LLM latency

            async with lock:
                active_count -= 1

            # Return mock response
            return '{"data": {"test": "result"}, "summary": "test", "urgency": "normal"}'

        # Patch the ZAI client
        with patch('src.synthesize.strand.get_zai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.call_simple = mock_call_simple
            mock_get_client.return_value = mock_client

            # Create mock fetch result
            fetch_result = FetchResult(
                intent_id="test-intent",
                intent_type=IntentType.STATUS,
                sources={},
                coverage=FetchCoverage(
                    total_sources=0,
                    succeeded=[],
                    timed_out=[],
                    failed=[],
                    skipped=[],
                ),
                total_duration_ms=100,
                caveats=None,
            )

            # Launch 5 concurrent synthesize calls with limit=2
            requests = [
                SynthesizeRequest(
                    intent_id=f"intent-{i}",
                    intent_type=IntentType.STATUS,
                    utterance="test utterance",
                    project_slug="test-project",
                    fetched_context=fetch_result,
                )
                for i in range(5)
            ]

            tasks = [synthesize_intent(req) for req in requests]
            await asyncio.gather(*tasks)

            # Verify limit was respected
            assert max_active <= 2, f"Max concurrent LLM calls {max_active} exceeded limit 2"
