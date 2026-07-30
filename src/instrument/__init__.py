"""Dispatch instrumentation: per-stage timing capture for the latency budget.

See docs/plan/plan.md → "Latency Budget & Instrumentation". The
``DispatchTimings`` collector accumulates per-stage millisecond durations
during a dispatch; ``percentiles`` turns a list of per-stage samples into the
p50/p95 the plan's Measured columns need.
"""
