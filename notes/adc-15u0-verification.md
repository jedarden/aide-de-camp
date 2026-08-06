# adc-15u0 Verification — Feature Already Shipped

## Date
2026-08-06

## Finding
The failure deduplication feature requested in adc-15u0 was **already implemented** in commit `5067e48` and shipped in version 0.11.0.

## Implementation Summary
The `TelegramFallback` class in `src/telegram/fallback.py` includes:

### Per-Failure-Type Deduplication
- `_seen_failure_types: set[str]` - tracks distinct error types already logged
- Immediate WARNING for new failure types (not swallowed by cooldown)
- Repeated failures of same type rate-limited to one DEBUG summary per 300s window
- Each failure type independently logged

### Key Features
1. **First failure after startup**: One WARNING with error context
2. **New failure type mid-outage**: Immediate WARNING (never hidden)
3. **Repeated same-type failures**: Rate-limited DEBUG summaries
4. **Configurable window**: Default 300s via `ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS`

### Test Coverage
All tests pass (11/11):
- `test_first_http_failure_logs_warning_with_context` ✅
- `test_repeated_http_failures_rate_limited` ✅
- `test_different_failure_types_logged_independently` ✅
- `test_warning_visible_at_warning_level` ✅
- `test_no_debug_spam_from_sustained_failures` ✅
- `test_end_to_end_failure_flow` ✅
- Plus 5 more covering all send methods and status API

## Acceptance Criteria Verification
✅ Repeated failures don't flood logs — 300s cooldown window
✅ Different failure types logged independently — `_seen_failure_types` set
✅ Log rate limits reasonable — 300s default, configurable
✅ New failure types logged immediately — WARNING at once, never swallowed

## Status
**COMPLETE** — Feature already shipped in v0.11.0. No additional work required.
