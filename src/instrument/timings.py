"""Per-stage timing capture helpers for dispatch instrumentation.

``DispatchTimings`` is a small accumulator that records stage durations in
milliseconds during a single dispatch. It is passed through the router
(``route_utterance`` → ``process_intent`` → the fetch/synthesize/escalate
branches); each stage records the duration it measures, and ``process_intent``
persists one ``dispatch_timings`` row per intent thread via
``SessionStore.record_dispatch_timings(**timings.to_fields())``.

Design notes:

- The clock is injectable (default ``time.monotonic``) so tests get
  deterministic durations without sleeping.
- Only stages actually measured appear in ``to_fields()``; unmeasured stages
  are simply absent (the store upsert leaves them NULL), which is the honest
  representation — e.g. ``synthesize_first_token_ms`` cannot be measured until
  the synthesize strand streams, and ``escalate_ms`` is absent for hot-path
  dispatches.
- ``percentiles`` uses the nearest-rank method (ceil(q/100 * n)), matching how
  latency SLOs are typically reported. SQLite has no built-in percentile, so
  the store fetches ordered per-stage values and calls into here.
"""

import time
from typing import Callable, Optional


Clock = Callable[[], float]

# The timing stages tracked per dispatch. Mirrors the dispatch_timings columns
# (minus intent_id/created_at). Kept here as the canonical list the collector
# accepts so a typo in a stage name is a KeyError, not a silent no-op.
DISPATCH_TIMING_STAGES = (
    "router_ms",
    "json_parse_ms",
    "fetch_first_source_ms",
    "fetch_total_ms",
    "synthesize_first_token_ms",
    "synthesize_total_ms",
    "escalate_ms",
    "sse_emit_ms",
    "stt_ms",
    "first_render_ms",
)


class DispatchTimings:
    """Accumulates per-stage millisecond durations for one dispatch.

    Usage in the router::

        timings = DispatchTimings()
        timings.record("router_ms", routed_intent.router_ms)

        fetch_start = timings.clock()
        ...
        timings.record("fetch_total_ms", fetch_result.total_duration_ms)

        await store.record_dispatch_timings(intent_id, **timings.to_fields())
    """

    def __init__(self, clock: Clock = time.monotonic):
        self._clock = clock
        self._durations: dict[str, int] = {}

    @property
    def clock(self) -> Clock:
        """The monotonic clock callable (exposed so callers share one clock)."""
        return self._clock

    def record(self, stage: str, ms: int | float | None) -> None:
        """Record a stage duration in ms. None is ignored (stage stays absent)."""
        if ms is None:
            return
        if stage not in DISPATCH_TIMING_STAGES:
            raise KeyError(f"Unknown dispatch timing stage: {stage!r}")
        self._durations[stage] = int(ms)

    def elapsed_ms(self, start: float, end: float | None = None) -> int:
        """Milliseconds between ``start`` and ``end`` (default: now), via the clock."""
        return int(((end if end is not None else self._clock()) - start) * 1000)

    def to_fields(self) -> dict[str, int]:
        """Return the recorded stages as a kwargs dict for record_dispatch_timings."""
        return dict(self._durations)

    def get(self, stage: str) -> Optional[int]:
        """Return a recorded stage duration, or None if unmeasured."""
        return self._durations.get(stage)


def percentiles(values: list[int], qs: tuple[int, ...] = (50, 95)) -> dict[int, int]:
    """Nearest-rank percentiles for a list of integer samples.

    Each ``q`` (0..100) maps to ``values[ceil(q/100 * n) - 1]`` after sorting
    ascending, clamped to ``[0, n-1]``. Returns ``{q: value}``. Raises
    ``ValueError`` on an empty list — callers should skip empty stages rather
    than call this (the store does so).
    """
    if not values:
        raise ValueError("percentiles() requires at least one value")
    ordered = sorted(values)
    n = len(ordered)
    out: dict[int, int] = {}
    for q in qs:
        if not 0 <= q <= 100:
            raise ValueError(f"percentile q must be in [0, 100], got {q}")
        idx = (q * n + 99) // 100 - 1  # ceil(q/100 * n) - 1
        idx = max(0, min(n - 1, idx))
        out[q] = ordered[idx]
    return out
