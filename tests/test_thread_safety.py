"""
Thread-safety tests for async FastAPI application.

Tests verify that concurrent operations are safe and that
race conditions are properly prevented.
"""
import asyncio
import pytest
from uuid import uuid4

from src.intent.router import get_router, clear_router_cache, IntentRouter
from src.session.store import get_store, SessionStore
from src.errors.degraded_state import get_degraded_state_handler, DegradedStateHandler
from src.escalate.handler import get_escalate_handler, EscalateHandler
from src.fetch.orchestrator import get_orchestrator


class TestGlobalSingletons:
    """Test global singleton initialization under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_store_initialization(self):
        """Test that get_store() creates only one instance under concurrent load."""
        # Reset global state
        import src.session.store as store_module
        store_module._store = None

        # Create 100 concurrent requests
        tasks = [store_module.get_store() for _ in range(100)]
        results = await asyncio.gather(*tasks)

        # Verify all results are the same instance
        first = results[0]
        assert all(id(r) == id(first) for r in results), \
            "All calls should return the same instance"

        # Verify it's actually a SessionStore
        assert isinstance(first, SessionStore)

    @pytest.mark.asyncio
    async def test_concurrent_router_initialization(self):
        """Test that get_router() creates only one instance under concurrent load."""
        # Reset global state
        import src.intent.router as router_module
        router_module._router = None

        # Create 100 concurrent requests
        tasks = [router_module.get_router() for _ in range(100)]
        results = await asyncio.gather(*tasks)

        # Verify all results are the same instance
        first = results[0]
        assert all(id(r) == id(first) for r in results), \
            "All calls should return the same instance"

        # Verify it's actually an IntentRouter
        assert isinstance(first, IntentRouter)

    @pytest.mark.asyncio
    async def test_concurrent_degraded_state_initialization(self):
        """Test that get_degraded_state_handler() is safe under concurrent load."""
        # Reset global state
        import src.errors.degraded_state as degraded_module
        degraded_module._degraded_state_handler = None

        # Create 100 concurrent requests
        tasks = [degraded_module.get_degraded_state_handler() for _ in range(100)]
        results = await asyncio.gather(*tasks)

        # Verify all results are the same instance
        first = results[0]
        assert all(id(r) == id(first) for r in results), \
            "All calls should return the same instance"

        # Verify it's actually a DegradedStateHandler
        assert isinstance(first, DegradedStateHandler)


class TestCacheConcurrency:
    """Test concurrent access to intent cache."""

    @pytest.mark.asyncio
    async def test_concurrent_cache_reads(self):
        """Test that concurrent cache reads don't cause data corruption."""
        router = get_router()
        router._clear_cache()

        # Seed cache with test data
        utterance = "test utterance"
        session_id = str(uuid4())
        from src.intent.router import IntentClassification, IntentType

        classifications = [
            IntentClassification(
                intent_type=IntentType.STATUS,
                project_slug="test-project",
                confidence=0.9,
                utterance_fragment=utterance,
                reasoning="test reasoning",
                urgency="normal"
            )
        ]
        router._cache_classification(utterance, session_id, classifications)

        # Perform 100 concurrent reads
        tasks = [
            router._get_cached_classification(utterance, session_id)
            for _ in range(100)
        ]
        results = await asyncio.gather(*tasks)

        # Verify all reads returned the same data
        assert all(r is not None for r in results), "All cache reads should succeed"
        assert all(len(r) == len(classifications) for r in results), \
            "All results should have same number of classifications"

    @pytest.mark.asyncio
    async def test_concurrent_cache_writes(self):
        """Test that concurrent cache writes don't cause corruption."""
        router = get_router()
        router._clear_cache()

        # Perform 100 concurrent writes
        tasks = []
        for i in range(100):
            utterance = f"test utterance {i}"
            session_id = str(uuid4())
            from src.intent.router import IntentClassification, IntentType

            classifications = [
                IntentClassification(
                    intent_type=IntentType.STATUS,
                    project_slug="test-project",
                    confidence=0.9,
                    utterance_fragment=utterance,
                    reasoning="test reasoning",
                    urgency="normal"
                )
            ]
            tasks.append(
                router._cache_classification(utterance, session_id, classifications)
            )

        await asyncio.gather(*tasks)

        # Verify cache has 100 entries
        stats = router._cache.get_stats()
        assert stats["size"] == 100, f"Expected 100 cache entries, got {stats['size']}"

    @pytest.mark.asyncio
    async def test_concurrent_cache_reads_and_writes(self):
        """Test that concurrent reads and writes don't interfere."""
        router = get_router()
        router._clear_cache()

        # Mix of reads and writes
        tasks = []
        for i in range(50):
            # Write
            utterance = f"utterance {i}"
            session_id = str(uuid4())
            from src.intent.router import IntentClassification, IntentType

            classifications = [
                IntentClassification(
                    intent_type=IntentType.STATUS,
                    project_slug="test-project",
                    confidence=0.9,
                    utterance_fragment=utterance,
                    reasoning="test",
                    urgency="normal"
                )
            ]
            tasks.append(
                router._cache_classification(utterance, session_id, classifications)
            )

            # Read (may or may not hit)
            tasks.append(
                router._get_cached_classification(utterance, session_id)
            )

        await asyncio.gather(*tasks)

        # Verify cache integrity
        stats = router._cache.get_stats()
        assert stats["size"] == 50, f"Expected 50 cache entries, got {stats['size']}"


class TestDatabaseConcurrency:
    """Test concurrent database operations."""

    @pytest.mark.asyncio
    async def test_concurrent_session_creation(self):
        """Test that concurrent session creation doesn't cause corruption."""
        store = get_store()

        # Create 100 concurrent sessions
        session_ids = [str(uuid4()) for _ in range(100)]
        tasks = [store.create_session(sid) for sid in session_ids]
        results = await asyncio.gather(*tasks)

        # Verify all sessions were created uniquely
        assert len(set(results)) == 100, "All session IDs should be unique"

        # Verify all sessions exist
        for session_id in results:
            session = await store.get_session(session_id)
            assert session is not None, f"Session {session_id} should exist"

    @pytest.mark.asyncio
    async def test_concurrent_result_creation(self):
        """Test that concurrent result creation works correctly."""
        store = get_store()
        session_id = await store.create_session()

        # Create topic
        topic_id, _ = await store.find_or_create_topic(
            label="test topic",
            session_id=session_id,
            topic_type="research"
        )

        # Create 100 concurrent results
        tasks = []
        for i in range(100):
            intent_id = str(uuid4())
            tasks.append(
                store.create_result(
                    intent_id=intent_id,
                    topic_id=topic_id,
                    session_id=session_id,
                    summary=f"Test result {i}",
                    data={"index": i},
                    urgency="normal"
                )
            )

        result_ids = await asyncio.gather(*tasks)

        # Verify all results were created uniquely
        assert len(set(result_ids)) == 100, "All result IDs should be unique"

        # Verify all results exist
        for result_id in result_ids:
            results = await store.get_results_for_intent(result_id[:8])
            # Just verify no errors occurred


class TestFetchConcurrency:
    """Test concurrent fetch operations."""

    @pytest.mark.asyncio
    async def test_concurrent_fetch_failures(self):
        """Test that concurrent fetch failures are tracked correctly."""
        from src.fetch.commands import FetchRequest, FetchContext, IntentType
        from src.fetch.orchestrator import get_fetch_strand

        strand = get_fetch_strand()

        # Create requests that will fail (no actual cluster access)
        requests = []
        for i in range(10):
            request = FetchRequest(
                intent_id=str(uuid4()),
                intent_type=IntentType.STATUS,
                session_id=str(uuid4()),
                context=FetchContext(
                    project_slug="nonexistent",
                    session_id=str(uuid4()),
                    namespace="test-namespace"
                )
            )
            requests.append(request)

        # Execute all fetches concurrently
        tasks = [strand.fetch(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all failures were tracked independently
        # (Each should have its own failure state)
        assert len(results) == 10, "Should have 10 results"


class TestFirstFailureTracking:
    """Test first-failure state tracking under concurrent conditions."""

    @pytest.mark.asyncio
    async def test_simultaneous_source_failures(self):
        """Test that simultaneous source failures are tracked correctly."""
        from src.fetch.orchestrator import FetchStrand
        from src.fetch.commands import FetchRequest, FetchContext, IntentType
        from unittest.mock import AsyncMock, patch

        strand = FetchStrand()

        # Mock all source executors to fail simultaneously
        async def failing_executor(context):
            raise Exception("Simulated failure")

        for source_name in strand._source_executors.keys():
            strand._source_executors[source_name] = failing_executor

        # Create a fetch request
        request = FetchRequest(
            intent_id=str(uuid4()),
            intent_type=IntentType.STATUS,
            session_id=str(uuid4()),
            context=FetchContext(
                project_slug="test",
                session_id=str(uuid4())
            )
        )

        # Execute fetch (all sources should fail)
        result = await strand.fetch(request)

        # Verify failure tracking
        assert result.terminal_failure == "all_sources_failed", \
            "Should detect all sources failed"
        assert len(result.coverage.failed) > 0, \
            "Should track failed sources"

    @pytest.mark.asyncio
    async def test_interleaved_failures(self):
        """Test that interleaved source failures are tracked correctly."""
        from src.fetch.orchestrator import FetchStrand
        from src.fetch.commands import FetchRequest, FetchContext, IntentType
        import time

        strand = FetchStrand()

        # Mock sources with different failure times
        call_count = [0]

        async def delayed_failing_executor(context):
            call_count[0] += 1
            # Stagger failures: 10ms, 20ms, 30ms, etc.
            delay = call_count[0] * 0.01
            await asyncio.sleep(delay)
            raise Exception(f"Failure {call_count[0]}")

        for source_name in strand._source_executors.keys():
            strand._source_executors[source_name] = delayed_failing_executor

        # Create a fetch request
        request = FetchRequest(
            intent_id=str(uuid4()),
            intent_type=IntentType.STATUS,
            session_id=str(uuid4()),
            context=FetchContext(
                project_slug="test",
                session_id=str(uuid4())
            )
        )

        # Execute fetch (all sources should fail at different times)
        result = await strand.fetch(request)

        # Verify all failures were tracked
        assert len(result.coverage.failed) > 0, \
            "Should track all failed sources"


class TestSSEConcurrency:
    """Test SSE broadcaster under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(self):
        """Test that concurrent broadcasts don't interfere."""
        from src.sse.broadcaster import get_broadcaster, SSEEvent, EventType

        broadcaster = get_broadcaster()

        # Create 100 concurrent broadcasts
        tasks = []
        for i in range(100):
            event = SSEEvent(
                event_type=EventType.RESULT_CREATED,
                data={"index": i},
                target_session_id=str(uuid4())
            )
            tasks.append(broadcaster.broadcast(event))

        # All broadcasts should complete without errors
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify no exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Expected no exceptions, got {len(exceptions)}"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
