# adc-15u0 — Add failure deduplication to prevent log spam

## What changed

`src/telegram/fallback.py` already rate-limited repeated send-failure logs, but
the dedup was **global**: one first-failure WARNING per startup, then DEBUG
summaries at most once per `ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS` (default
300s) window across **all** failure types. That left a gap — a *new* failure
type appearing mid-outage was silently swallowed into the global batch instead
of being surfaced.

This bead adds **per-failure-type** dedup on top of the existing global
machinery:

- New `_seen_failure_types: set[str]` tracks every error type already logged
  this startup.
- The umbrella first-failure WARNING (adc-hyqc) now records its type.
- A subsequent failure whose type is **not** in `_seen_failure_types` is logged
  immediately and independently with its own WARNING (never swallowed by the
  ongoing-outage cooldown). It (re)seeds the rate-limit window so its own
  immediate repeats are deduped.
- Repeats of an already-seen type still fall through to the existing
  global-cooldown DEBUG summary (unchanged).

## Acceptance criteria

- ✅ Repeated failures don't flood logs — same-type repeats still deduped by the
  existing 300s window.
- ✅ Different failure types are logged independently — each distinct type gets
  its own WARNING on first appearance.
- ✅ New failure types logged immediately — a new type mid-outage emits a
  WARNING at once, regardless of the same-type cooldown.
- ✅ Reasonable rate limit — each type is WARNING'd at most once per startup
  (tighter than the "once per N minutes" upper bound); periodic re-surfacing
  remains via the DEBUG summaries.

## Design note — why not WARNING per recurring type every 5 min?

The bead description mentions "rate-limit WARNING logs for the same failure
type (e.g., once per 5 minutes)". The already-shipped behavior (adc-47l2 /
adc-hyqc) is one umbrella WARNING + DEBUG summaries for repeats, and is covered
by existing tests (e.g. `test_one_debug_summary_per_cooldown_window` asserts
those recurring same-type logs are DEBUG, not WARNING). Converting recurring
same-type summaries to WARNINGs would regress adc-47l2/adc-hyqc. The new value
this bead adds is **per-type independence** (new types logged immediately),
which is implemented here without disturbing the established WARNING/DEBUG
split. "Once per startup per type" satisfies the "once per N minutes per type"
criterion as a tighter bound.

## Observability

`get_bridge_status()` now also returns:
- `seen_failure_types: list[str]` — distinct types logged this startup (sorted)
- `distinct_failure_types: int` — count of the above

## Tests

7 new tests in `tests/test_telegram_fallback.py` under `TestPerFailureTypeDedup`:
new type logged immediately during cooldown, distinct types each get own
WARNING, seen-type repeats deduped, status exposure, reset clears seen types,
and new-type WARNING reseeds the window. All 41 telegram tests pass; the 13
failures elsewhere in the suite are pre-existing (stale `SurfaceRouter` API in
`test_exceptions_routing.py`, untracked experimental `test_ui_regen.py`) and
unrelated — verified identical on clean HEAD.

Version bumped 0.10.0 → 0.11.0 (MINOR: new dedup behavior + status fields).
