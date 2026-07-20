"""
Fetch strand execution unit tests (bead adc-mwrx).

Hermetic, network-free tests for src/fetch/orchestrator.py — the FetchStrand
that runs every fetch source for an intent concurrently, streams partial
results via a callback, and tracks coverage (succeeded / timed_out / failed).

Every source executor is stubbed by swapping FetchStrand._source_executors,
so no kubectl proxy, ArgoCD endpoint, git repo, or filesystem is touched.
The four things this suite locks down:

1. **Per-intent invocation** — for each intent type in FETCH_COMMAND_MATRIX,
   the strand invokes exactly that intent's source set (no more, no fewer).
2. **Parallel execution** — sources within a strand run concurrently, and
   multiple independent strands run concurrently with each other.
3. **Streaming** — the on_partial_result callback fires once per source, in
   completion order, for successes *and* failures.
4. **Coverage tracking** — succeeded/timed_out/failed are bucketed correctly,
   success_rate is right, and the right caveats (required vs optional, failed
   vs timed-out) are attached to FetchResult.
"""

import asyncio
import time
from typing import Any, Callable

import pytest

from src.fetch.commands import (
    FETCH_COMMAND_MATRIX,
    FetchCommandSpec,
    FetchContext,
    FetchRequest,
    FetchSource,
    IntentType,
    SourceResult,
)
from src.fetch.orchestrator import FetchOrchestrator, FetchStrand

# --- executor stubs --------------------------------------------------------
# Each returns an async fn(context) -> dict matching the executor contract.
# Stubbing the executor (not the whole strand) means _execute_source's
# success/timeout/error triage still runs against real SourceResult objects.


def _success_executor(data: dict | None = None) -> Callable[[FetchContext], Any]:
    """Executor that returns `data` (default {"ok": True})."""
    payload = data if data is not None else {"ok": True}

    async def _fn(_ctx: FetchContext) -> dict:
        return payload

    return _fn


def _slow_executor(delay: float, data: dict | None = None) -> Callable[[FetchContext], Any]:
    """Executor that sleeps `delay` seconds before returning — for timing tests."""
    payload = data if data is not None else {"ok": True}

    async def _fn(_ctx: FetchContext) -> dict:
        await asyncio.sleep(delay)
        return payload

    return _fn


def _timeout_executor() -> Callable[[FetchContext], Any]:
    """Executor that raises asyncio.TimeoutError — exercises the inner timeout path."""

    async def _fn(_ctx: FetchContext) -> dict:
        raise asyncio.TimeoutError()

    return _fn


def _error_executor(exc: Exception | None = None) -> Callable[[FetchContext], Any]:
    """Executor that raises — exercises the error path."""
    error = exc or RuntimeError("boom from stub")

    async def _fn(_ctx: FetchContext) -> dict:
        raise error

    return _fn


def _build_strand(
    per_source: dict[FetchSource, Callable[[FetchContext], Any]] | None = None,
) -> tuple[FetchStrand, dict[FetchSource, int]]:
    """
    Build a FetchStrand whose executors are all stubbed, plus a recorder that
    counts how many times each source's executor was actually called.

    Sources in `per_source` use the given behavior; every other source falls
    back to a success stub (so no source is ever left without an executor).
    The recorder lets tests assert *which* sources were invoked per intent.
    """
    per_source = per_source or {}
    strand = FetchStrand()
    recorder: dict[FetchSource, int] = {}

    def _wrap(src: FetchSource, fn: Callable[[FetchContext], Any]):
        async def _wrapped(ctx: FetchContext) -> dict:
            recorder[src] = recorder.get(src, 0) + 1
            return await fn(ctx)

        return _wrapped

    instrumented = {
        src: _wrap(src, per_source.get(src, _success_executor())) for src in FetchSource
    }
    strand._source_executors = instrumented
    return strand, recorder


def _request(intent_type: IntentType, **ctx_kwargs) -> FetchRequest:
    """Build a FetchRequest with a throwaway context for the given intent."""
    return FetchRequest(
        intent_type=intent_type,
        context=FetchContext(**ctx_kwargs),
        intent_id=f"intent-{intent_type.value}-test",
        session_id="session-test",
    )


# --- 1. per-intent invocation ---------------------------------------------


class TestPerIntentInvocation:
    """Each intent type must invoke exactly its matrix-defined source set."""

    @pytest.mark.parametrize("intent_type", list(FETCH_COMMAND_MATRIX))
    @pytest.mark.asyncio
    async def test_invokes_exactly_its_matrix_sources(self, intent_type):
        expected = {spec.source for spec in FETCH_COMMAND_MATRIX[intent_type]}

        strand, recorder = _build_strand()
        result = await strand.fetch(_request(intent_type))

        invoked = {src for src, n in recorder.items() if n > 0}
        assert invoked == expected, (
            f"{intent_type.value}: invoked {invoked}, matrix defines {expected}"
        )
        # Each expected source ran exactly once.
        for src in expected:
            assert recorder[src] == 1
        # No off-matrix source was touched.
        for src, n in recorder.items():
            if n > 0:
                assert src in expected
        # Result covers the whole matrix set.
        assert set(result.sources) == expected
        assert result.coverage.total_sources == len(expected)

    @pytest.mark.asyncio
    async def test_reminder_intent_invokes_single_source(self):
        """REMINDER is the minimal case — exactly one (required) source."""
        strand, recorder = _build_strand()
        result = await strand.fetch(_request(IntentType.REMINDER))

        assert {src for src, n in recorder.items() if n > 0} == {FetchSource.REMINDERS}
        assert result.coverage.total_sources == 1
        assert result.coverage.success_rate == 1.0

    def test_every_matrix_source_has_a_registered_executor(self):
        """Guard: adding a source to the matrix without an executor would 404 at runtime."""
        strand = FetchStrand()
        registered = set(strand._source_executors)
        for intent_type, specs in FETCH_COMMAND_MATRIX.items():
            for spec in specs:
                assert spec.source in registered, (
                    f"{spec.source.value} (intent {intent_type.value}) has no executor"
                )


# --- 2. parallel execution -------------------------------------------------


class TestParallelExecution:
    """Sources run concurrently within a strand; strands run concurrently with each other."""

    @pytest.mark.asyncio
    async def test_sources_run_concurrently_within_a_strand(self):
        # STATUS has 7 sources. Each sleeps `delay`; serial would be 7*delay,
        # concurrent should be ~delay.
        delay = 0.2
        n = len(FETCH_COMMAND_MATRIX[IntentType.STATUS])
        assert n >= 3  # sanity for the concurrency claim

        slow = {src: _slow_executor(delay) for src in FetchSource}
        strand, _ = _build_strand(per_source=slow)

        start = time.monotonic()
        result = await strand.fetch(_request(IntentType.STATUS))
        elapsed = time.monotonic() - start

        # Concurrent: well under the serial bound, at least one source's duration.
        assert elapsed < n * delay / 2, f"sources ran serially: {elapsed:.3f}s >= {n * delay / 2}s"
        assert elapsed >= delay
        assert result.coverage.success_rate == 1.0

    @pytest.mark.asyncio
    async def test_multiple_strands_execute_in_parallel(self):
        """Four independent fetch() calls finish in ~one wave, not four back-to-back."""
        delay = 0.25
        slow = {src: _slow_executor(delay) for src in FetchSource}

        async def run_one():
            strand, _ = _build_strand(per_source=slow)
            return await strand.fetch(_request(IntentType.STATUS))

        start = time.monotonic()
        results = await asyncio.gather(*(run_one() for _ in range(4)))
        elapsed = time.monotonic() - start

        # 4 serial waves would be ~4*delay; concurrent is ~delay.
        assert elapsed < delay * 2, f"strands ran serially: {elapsed:.3f}s"
        assert all(r.coverage.success_rate == 1.0 for r in results)
        assert len(results) == 4


# --- 3. streaming ----------------------------------------------------------


class TestStreaming:
    """on_partial_result fires once per source, in completion order, for every outcome."""

    @pytest.mark.asyncio
    async def test_callback_fires_once_per_source(self):
        strand, _ = _build_strand()
        expected = {spec.source for spec in FETCH_COMMAND_MATRIX[IntentType.ACTION]}

        partials: list[tuple[FetchSource, SourceResult]] = []
        result = await strand.fetch(
            _request(IntentType.ACTION),
            on_partial_result=lambda src, res: partials.append((src, res)),
        )

        assert len(partials) == len(expected)
        assert {src for src, _ in partials} == expected
        # Each partial carries a fully-formed SourceResult bound to its source.
        for src, res in partials:
            assert isinstance(res, SourceResult)
            assert res.source == src
            assert res.status == "success"
        # Final result is consistent with the streamed partials.
        assert set(result.sources) == expected

    @pytest.mark.asyncio
    async def test_callback_fires_for_failed_and_timed_out_sources(self):
        """Streaming must not silently drop non-success outcomes."""
        behavior = {
            FetchSource.KUBECTL_PODS: _error_executor(ValueError("pod boom")),
            FetchSource.ARGOCD_APP: _timeout_executor(),
        }
        strand, _ = _build_strand(per_source=behavior)
        request = _request(IntentType.ACTION)  # both sources above are in ACTION

        partials: list[tuple[FetchSource, str]] = []
        await strand.fetch(request, on_partial_result=lambda s, r: partials.append((s, r.status)))

        n = len(FETCH_COMMAND_MATRIX[IntentType.ACTION])
        assert len(partials) == n  # one partial per source regardless of outcome
        statuses = dict(partials)
        assert statuses[FetchSource.KUBECTL_PODS] == "error"
        assert statuses[FetchSource.ARGOCD_APP] == "timeout"

    @pytest.mark.asyncio
    async def test_no_callback_does_not_raise(self):
        """Omitting on_partial_result is the normal path — must be a no-op."""
        strand, _ = _build_strand()
        result = await strand.fetch(_request(IntentType.LOOKUP))
        assert result.coverage.success_rate == 1.0


# --- 4. coverage tracking --------------------------------------------------


class TestCoverageTracking:
    """succeeded / timed_out / failed buckets, success_rate, and caveats."""

    @pytest.mark.asyncio
    async def test_all_success(self):
        strand, _ = _build_strand()
        result = await strand.fetch(_request(IntentType.BRAINSTORM))
        cov = result.coverage
        n = len(FETCH_COMMAND_MATRIX[IntentType.BRAINSTORM])

        assert cov.total_sources == n
        assert set(cov.succeeded) == {
            spec.source for spec in FETCH_COMMAND_MATRIX[IntentType.BRAINSTORM]
        }
        assert cov.timed_out == []
        assert cov.failed == []
        assert cov.skipped == []
        assert cov.success_rate == 1.0
        assert cov.has_required_failure is False
        assert result.caveats is None  # nothing went wrong

    @pytest.mark.asyncio
    async def test_timeouts_bucketed_with_caveat(self):
        behavior = {src: _timeout_executor() for src in FetchSource}
        strand, _ = _build_strand(per_source=behavior)
        result = await strand.fetch(_request(IntentType.LOOKUP))

        expected = {spec.source for spec in FETCH_COMMAND_MATRIX[IntentType.LOOKUP]}
        assert set(result.coverage.timed_out) == expected
        assert result.coverage.succeeded == []
        assert result.coverage.failed == []
        assert result.coverage.success_rate == 0.0
        # Every timed-out source produces a caveat.
        assert result.caveats is not None
        assert len(result.caveats) == len(expected)
        for src in expected:
            assert any(src.value in c and "timed out" in c for c in result.caveats)
            assert result.sources[src].status == "timeout"

    @pytest.mark.asyncio
    async def test_required_failure_emits_required_caveat(self):
        """KUBECTL_DEPLOYMENTS is required for ACTION — its failure is flagged required."""
        behavior = {FetchSource.KUBECTL_DEPLOYMENTS: _error_executor(ValueError("deploy down"))}
        strand, _ = _build_strand(per_source=behavior)
        result = await strand.fetch(_request(IntentType.ACTION))

        assert FetchSource.KUBECTL_DEPLOYMENTS in result.coverage.failed
        assert result.coverage.has_required_failure is True
        assert result.caveats is not None
        assert any("Required source" in c and "kubectl_deployments" in c for c in result.caveats)

    @pytest.mark.asyncio
    async def test_optional_failure_emits_optional_caveat(self):
        """BEAD_LIST is optional for ACTION — its failure is flagged optional, not required."""
        behavior = {FetchSource.BEAD_LIST: _error_executor(ValueError("bead cli missing"))}
        strand, _ = _build_strand(per_source=behavior)
        result = await strand.fetch(_request(IntentType.ACTION))

        assert FetchSource.BEAD_LIST in result.coverage.failed
        assert result.caveats is not None
        assert any("Optional source" in c and "bead_list" in c for c in result.caveats)
        # No required-source caveat should have fired for this optional failure.
        assert not any("Required source" in c and "bead_list" in c for c in result.caveats)

    @pytest.mark.asyncio
    async def test_success_rate_with_mixed_outcomes(self):
        behavior = {
            FetchSource.KUBECTL_PODS: _error_executor(),
            FetchSource.ARGOCD_APP: _timeout_executor(),
        }
        strand, _ = _build_strand(per_source=behavior)
        result = await strand.fetch(_request(IntentType.STATUS))

        n = len(FETCH_COMMAND_MATRIX[IntentType.STATUS])
        assert result.coverage.total_sources == n
        assert len(result.coverage.succeeded) == n - 2
        assert len(result.coverage.failed) == 1
        assert len(result.coverage.timed_out) == 1
        assert result.coverage.success_rate == pytest.approx((n - 2) / n)

    @pytest.mark.asyncio
    async def test_real_per_task_timeout_via_wait_for(self, monkeypatch):
        """
        Exercise the actual asyncio.wait_for branch (not the executor-raised
        TimeoutError): a slow executor against a tiny per-spec timeout must be
        cancelled and bucketed as timed_out, with the required-source caveat.
        """
        slow_spec = FetchCommandSpec(
            source=FetchSource.KUBECTL_PODS,
            command_template="ignored",
            timeout_seconds=0.05,
            required=True,
        )
        monkeypatch.setattr(
            "src.fetch.orchestrator.get_fetch_commands",
            lambda _intent: [slow_spec],
        )
        monkeypatch.setattr(
            "src.fetch.orchestrator.get_required_sources",
            lambda _intent: [FetchSource.KUBECTL_PODS],
        )

        strand, _ = _build_strand(per_source={FetchSource.KUBECTL_PODS: _slow_executor(0.5)})
        result = await strand.fetch(_request(IntentType.STATUS))

        assert result.coverage.total_sources == 1
        assert FetchSource.KUBECTL_PODS in result.coverage.timed_out
        assert result.sources[FetchSource.KUBECTL_PODS].status == "timeout"
        assert any("Required source" in c and "timed out" in c for c in (result.caveats or []))

    @pytest.mark.asyncio
    async def test_empty_intent_has_zero_coverage(self):
        """An intent with no matrix entry yields an empty, well-formed result."""
        strand, _ = _build_strand()
        result = await strand.fetch(_request(IntentType.TASK_PROFILE))

        assert result.coverage.total_sources == 0
        assert result.coverage.success_rate == 0.0
        assert result.sources == {}


# --- 5. result accessors, serialization, and orchestrator wiring -----------


class TestResultAccessorsAndOrchestrator:
    """FetchResult helpers, FetchContext template expansion, and FetchOrchestrator delegation."""

    @pytest.mark.asyncio
    async def test_get_source_result_and_successful_data(self):
        behavior = {FetchSource.KUBECTL_PODS: _error_executor()}
        strand, _ = _build_strand(per_source=behavior)
        result = await strand.fetch(_request(IntentType.STATUS))

        # The errored source is retrievable but excluded from successful data.
        pods = result.get_source_result(FetchSource.KUBECTL_PODS)
        assert pods is not None and pods.status == "error"
        successful = result.get_successful_data()
        assert FetchSource.KUBECTL_PODS not in successful
        # A source that's in STATUS and succeeded.
        assert FetchSource.GIT_LOG in successful
        # A source not in STATUS resolves to None.
        assert result.get_source_result(FetchSource.LOGS) is None

    @pytest.mark.asyncio
    async def test_to_dict_round_trip(self):
        strand, _ = _build_strand()
        result = await strand.fetch(_request(IntentType.MONITORING_CONFIG))
        d = result.to_dict()

        assert d["intent_type"] == IntentType.MONITORING_CONFIG.value
        assert d["intent_id"] == result.intent_id
        assert "sources" in d and "coverage" in d
        assert d["coverage"]["total_sources"] == len(
            FETCH_COMMAND_MATRIX[IntentType.MONITORING_CONFIG]
        )
        assert d["coverage"]["success_rate"] == 1.0

    def test_fetch_context_expand_template(self):
        ctx = FetchContext(project_slug="my-proj", namespace="ns1", proxy="http://p")
        rendered = ctx.expand_template("kubectl --server={proxy} -n {namespace} {project_slug}")
        assert rendered == "kubectl --server=http://p -n ns1 my-proj"

    def test_fetch_context_leaves_unset_placeholders_intact(self):
        ctx = FetchContext()
        assert ctx.expand_template("git -C {repo_path} log") == "git -C {repo_path} log"

    @pytest.mark.asyncio
    async def test_orchestrator_delegates_to_strand(self):
        """FetchOrchestrator.execute_fetch is a thin wrapper over FetchStrand.fetch."""
        strand, _ = _build_strand()
        orch = FetchOrchestrator(strand)
        result = await orch.execute_fetch(_request(IntentType.STATUS))
        assert result.coverage.success_rate == 1.0
        assert set(result.sources) == {
            spec.source for spec in FETCH_COMMAND_MATRIX[IntentType.STATUS]
        }

    @pytest.mark.asyncio
    async def test_orchestrator_streaming_callback_plumbs_through(self):
        strand, _ = _build_strand()
        orch = FetchOrchestrator(strand)
        partials: list[FetchSource] = []
        await orch.execute_fetch(
            _request(IntentType.LOOKUP),
            stream_callback=lambda src, _res: partials.append(src),
        )
        expected = {spec.source for spec in FETCH_COMMAND_MATRIX[IntentType.LOOKUP]}
        assert set(partials) == expected
        assert len(partials) == len(expected)
