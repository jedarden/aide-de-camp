"""
Tests for urgency-tiered voice narration and batching.

Tests coverage:
- Critical results interrupt immediately
- High results wait for a natural pause (signal_pause)
- Normal results batch within the documented five-second window
- Low results are deferred until the session signals idle
- Claimed results are never narrated twice (duplicate delivery)
- Asynchronous narration/push errors requeue instead of dropping results

Narration rules under test are documented in docs/test-narration.md and
ResultBatcher: critical interrupts immediately, high waits for a natural
pause, normal batches within ~5s, low only when the conversation is idle.

The batcher tests run the real ResultBatcher behind a recording callback;
the listener tests mock the store/batcher boundary to pin result_listener's
own dedup (pushed_ids over intent-correlated rows) and per-result error
isolation.
"""

import asyncio
import inspect
import json
from collections.abc import Callable
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.realtime.batching import PendingResult, ResultBatcher
from src.realtime.dispatch import register_session_intents, result_listener
from src.test.narration import NarrationSession, VerifyNarrationRequest

# --- Helpers ------------------------------------------------------------------


class NarrationRecorder:
    """Recording narrate callback; fails the first `fail_first` attempts."""

    def __init__(self, fail_first: int = 0) -> None:
        self.attempts: list[list[str]] = []  # every callback invocation
        self.delivered: list[list[str]] = []  # successful invocations only
        self.fail_first = fail_first
        self.delivered_event = asyncio.Event()

    async def __call__(self, results: list[PendingResult]) -> None:
        ids = [r.result_id for r in results]
        self.attempts.append(ids)
        if len(self.attempts) <= self.fail_first:
            raise RuntimeError(f"synthetic narration failure for {ids}")
        self.delivered.append(ids)
        self.delivered_event.set()


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    """Poll a condition on the running loop until it holds or time runs out."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError("condition not met before timeout")
        await asyncio.sleep(0.01)


async def queue_result(batcher: ResultBatcher, result_id: str, urgency: str) -> None:
    """Queue one result through the public batcher API."""
    await batcher.queue_result(
        result_id=result_id,
        intent_id=f"intent-{result_id}",
        topic_id="topic-1",
        summary=f"summary {result_id}",
        data={},
        urgency=urgency,
    )


def store_result(result_id: str, intent_id: str) -> dict:
    """A result row as the session store returns it to result_listener."""
    return {
        "id": result_id,
        "intent_id": intent_id,
        "topic_id": f"topic-{result_id}",
        "summary": f"summary {result_id}",
        "urgency": "normal",
        "data": json.dumps({"summary": f"summary {result_id}"}),
    }


@pytest.fixture
async def batcher():
    """A fresh ResultBatcher; teardown cancels leftover background tasks."""
    b = ResultBatcher()
    yield b
    current = asyncio.current_task()
    stragglers = [t for t in asyncio.all_tasks() if t is not current]
    for task in stragglers:
        task.cancel()
    await asyncio.gather(*stragglers, return_exceptions=True)


# --- Urgency-tiered delivery --------------------------------------------------


class TestUrgencyTieredDelivery:
    async def test_critical_interrupts_immediately(self, batcher):
        """Critical narrates at once; the pending normal batch is retained."""
        recorder = NarrationRecorder()
        batcher.set_narrate_callback(recorder)

        await queue_result(batcher, "r-normal", "normal")
        assert recorder.attempts == []  # normal waits for its batch window
        assert batcher.get_queue_status()["pending"] == 1

        await queue_result(batcher, "r-critical", "critical")
        # Critical interrupts: narrated before queue_result even returns.
        assert recorder.delivered == [["r-critical"]]
        assert batcher.get_queue_status()["in_flight"] == 0

        # The interrupted normal result is retained, not dropped.
        await batcher.flush()
        assert recorder.delivered == [["r-critical"], ["r-normal"]]

    async def test_high_waits_for_natural_pause(self, batcher):
        """High is held for a natural pause, narrated once, then cleared."""
        recorder = NarrationRecorder()
        batcher.set_narrate_callback(recorder)

        await queue_result(batcher, "r-high", "high")
        status = batcher.get_queue_status()
        assert status["waiting_for_pause"] == 1
        assert recorder.attempts == []  # held for a pause, not the batch window

        await batcher.signal_pause()
        assert recorder.delivered == [["r-high"]]
        status = batcher.get_queue_status()
        assert status["waiting_for_pause"] == 0
        assert status["in_flight"] == 0

        # A second pause must not re-narrate the delivered result.
        await batcher.signal_pause()
        assert recorder.delivered == [["r-high"]]

    async def test_normal_results_batch_within_documented_five_second_window(
        self, batcher
    ):
        """docs/test-narration.md: normal results batch within ~5s window."""
        batcher.config.normal_urgency_batch_seconds = 5
        recorder = NarrationRecorder()
        batcher.set_narrate_callback(recorder)

        loop = asyncio.get_running_loop()
        started = loop.time()
        for result_id in ("r1", "r2", "r3"):
            await queue_result(batcher, result_id, "normal")

        # Mid-window: nothing narrated yet, all three accumulated.
        await asyncio.sleep(1.0)
        assert recorder.attempts == []
        assert batcher.get_queue_status()["pending"] == 3

        await asyncio.wait_for(recorder.delivered_event.wait(), timeout=10.0)
        elapsed = loop.time() - started

        assert elapsed >= 5.0  # the documented window is respected, not cut short
        assert recorder.delivered == [["r1", "r2", "r3"]]  # one batch, in order

    async def test_low_deferred_until_idle(self, batcher):
        """Low is held while the session is active and narrated on idle."""
        recorder = NarrationRecorder()
        batcher.set_narrate_callback(recorder)

        await queue_result(batcher, "r-low", "low")
        status = batcher.get_queue_status()
        assert status["pending"] == 1
        assert status["session_active"] is True
        assert recorder.attempts == []  # held while the conversation continues

        await batcher.signal_idle()
        assert recorder.delivered == [["r-low"]]
        assert batcher.get_queue_status()["session_active"] is False

    async def test_low_delivered_immediately_once_idle(self, batcher):
        """Once the session is idle, low results skip the queue entirely."""
        recorder = NarrationRecorder()
        batcher.set_narrate_callback(recorder)

        await batcher.signal_idle()  # no conversation in progress
        await queue_result(batcher, "r-low", "low")
        assert recorder.delivered == [["r-low"]]
        assert batcher.get_queue_status()["in_flight"] == 0


# --- Duplicates and asynchronous errors ---------------------------------------


class TestDuplicateAndErrorHandling:
    async def test_claimed_results_are_not_narrated_twice(self, batcher):
        """Every redelivery path after a successful claim finds empty queues."""
        batcher.config.normal_urgency_batch_seconds = 0
        recorder = NarrationRecorder()
        batcher.set_narrate_callback(recorder)

        await queue_result(batcher, "r1", "normal")
        await wait_until(lambda: bool(recorder.delivered))

        await batcher.signal_pause()
        await batcher.signal_idle()
        await batcher.flush()

        assert recorder.attempts == [["r1"]]
        status = batcher.get_queue_status()
        assert status["pending"] == 0
        assert status["waiting_for_pause"] == 0
        assert status["in_flight"] == 0

    async def test_async_narration_error_requeues_for_retry(self, batcher):
        """A callback raising mid-await nacks the claim and requeues the batch."""
        batcher.config.normal_urgency_batch_seconds = 0
        recorder = NarrationRecorder(fail_first=1)
        batcher.set_narrate_callback(recorder)

        await queue_result(batcher, "r1", "normal")
        # Wait for the failed attempt itself: queue state alone is ambiguous
        # (pending=1, in_flight=0 also holds before the timer first fires).
        await wait_until(
            lambda: len(recorder.attempts) == 1
            and batcher.get_queue_status()["pending"] == 1
            and batcher.get_queue_status()["in_flight"] == 0
        )
        assert recorder.delivered == []  # first attempt failed, result requeued

        await batcher.signal_idle()  # retry path delivers exactly once
        assert recorder.delivered == [["r1"]]
        assert len(recorder.attempts) == 2


# --- Documented defaults -------------------------------------------------------


class TestDocumentedDefaults:
    def test_five_second_window_is_the_documented_verification_default(self):
        """docs/test-narration.md pins the default batching window at 5.0s."""
        assert VerifyNarrationRequest(session_id="s").expected_window_seconds == 5.0
        parameters = inspect.signature(NarrationSession.verify_timing).parameters
        assert parameters["expected_window_seconds"].default == 5.0


# --- result_listener dedup and error isolation ---------------------------------


class TestResultListenerDedupAndErrors:
    @pytest.fixture
    def listener_env(self, monkeypatch):
        """Isolate result_listener from the store, batcher, canvas, feedback.

        Replaces the module-level intent registry with a fresh one so tests
        register intents without leaking into other tests.
        """
        monkeypatch.setattr("src.realtime.dispatch._pending_intents", {})

        store = AsyncMock()
        store.get_pending_approvals_for_session = AsyncMock(return_value=[])
        store.get_results_for_intent = AsyncMock(return_value=[])
        store.mark_results_surfed_by_ids = AsyncMock()
        monkeypatch.setattr(
            "src.realtime.dispatch.get_store", AsyncMock(return_value=store)
        )

        batcher = MagicMock()
        batcher.queue_result = AsyncMock()
        monkeypatch.setattr(
            "src.realtime.batching.get_result_batcher",
            MagicMock(return_value=batcher),
        )

        canvas_push = AsyncMock()
        monkeypatch.setattr("src.realtime.continuity.push_to_canvas", canvas_push)

        feedback = MagicMock()
        feedback.track_result_created = AsyncMock()
        monkeypatch.setattr(
            "src.feedback.signals.get_feedback_tracker",
            MagicMock(return_value=feedback),
        )

        return SimpleNamespace(
            store=store,
            batcher=batcher,
            canvas_push=canvas_push,
            feedback=feedback,
        )

    async def run_listener(
        self,
        env: SimpleNamespace,
        results_by_intent: dict[str, list[dict]],
        finished: Callable[[], bool],
    ) -> None:
        """Drive result_listener over correlated intents until `finished`."""
        env.store.get_results_for_intent.side_effect = (
            lambda intent_id: results_by_intent.get(intent_id, [])
        )

        task = asyncio.create_task(
            result_listener("sess", MagicMock(), use_batching=True)
        )
        try:
            await wait_until(finished, timeout=5.0)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def test_duplicate_result_rows_are_narrated_once(self, listener_env):
        """A repeated row for a tracked intent is skipped via pushed_ids."""
        env = listener_env
        duplicate = store_result("r-dup", "intent-dup")
        register_session_intents("sess", ["intent-dup"])

        await self.run_listener(
            env,
            {"intent-dup": [duplicate, duplicate]},
            finished=lambda: env.store.mark_results_surfed_by_ids.await_count >= 1,
        )

        assert env.batcher.queue_result.await_count == 1
        assert env.batcher.queue_result.call_args.kwargs["result_id"] == "r-dup"
        assert env.canvas_push.await_count == 1
        assert env.feedback.track_result_created.await_count == 1
        assert env.store.mark_results_surfed_by_ids.call_args.args == (
            "sess",
            ["r-dup"],
        )

    async def test_async_push_error_does_not_block_other_results(self, listener_env):
        """One result failing to queue leaves the other results untouched."""
        env = listener_env
        register_session_intents("sess", ["intent-bad", "intent-good"])
        attempted: list[str] = []

        async def flaky_queue(**kwargs):
            attempted.append(kwargs["result_id"])
            if kwargs["result_id"] == "r-bad":
                raise RuntimeError("synthetic queue failure")

        env.batcher.queue_result.side_effect = flaky_queue

        await self.run_listener(
            env,
            {
                "intent-bad": [store_result("r-bad", "intent-bad")],
                "intent-good": [store_result("r-good", "intent-good")],
            },
            finished=lambda: env.store.mark_results_surfed_by_ids.await_count >= 1,
        )

        assert attempted == ["r-bad", "r-good"]  # failure did not block the rest
        assert env.canvas_push.await_count == 1
        assert (
            env.batcher.queue_result.call_args_list[1].kwargs["result_id"] == "r-good"
        )
        assert env.store.mark_results_surfed_by_ids.call_args.args == (
            "sess",
            ["r-good"],
        )
