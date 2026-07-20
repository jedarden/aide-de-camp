# adc-47l2 — Rate-limiting for repeated Telegram send failures

## Outcome: already shipped (re-dispatch)

This bead was re-dispatched, but the feature was already fully implemented and
pushed in commit `e809712` (`feat(telegram): rate-limit repeated send-failure
logs (adc-47l2)`), which is present on `origin/main`. This session verified that
the shipped implementation satisfies the acceptance criteria; no source changes
were needed.

## What shipped (in `e809712`)

In `src/telegram/fallback.py`, `TelegramFallback`:

- New configurable `_failure_log_interval_seconds` (default **300s**), resolved
  as: constructor arg → `ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS` env var →
  default. Invalid env values fall back to the default rather than crashing the
  singleton on startup.
- After the one-per-startup WARNING, repeated failures inside a cooldown window
  are counted silently (`_failures_since_last_log`); when the window elapses a
  single DEBUG summary is emitted reporting the burst size
  (`"N failure(s) since last log (total M)"`), then a new window starts.
- `_last_repeated_log_timestamp` is seeded by the first-failure WARNING so the
  WARNING is not immediately followed by a DEBUG storm.
- `reset_first_failure_state()` re-arms both the first-failure flag and the
  rate-limit window; `get_bridge_status()` exposes
  `failure_log_interval_seconds` and `failures_since_last_log`.
- Version bumped `0.8.0 → 0.9.0` (new feature + env var + status fields).

## Acceptance criteria — verification (2026-07-19)

- ✅ Repeated failures don't generate multiple WARNING logs — exactly one
  WARNING per startup (`_has_logged_first_failure` claim), subsequent failures
  are DEBUG-only.
- ✅ Rate-limiting is configurable — env var + constructor arg + default.
- ✅ No log spam — repeated failures are deduped inside the cooldown window;
  one DEBUG summary per window.

Commands run:

```
.venv/bin/python -m pytest tests/test_telegram_fallback.py tests/test_telegram_bridge_status.py -q
# 33 passed

.venv/bin/python -m pytest tests/test_telegram_fallback.py -q \
  -k "rate or interval or spam or burst or window or repeated or cooldown or since_last_log"
# 10 passed, 13 deselected

.venv/bin/python -c "from src.main import app; from src.telegram.fallback import TelegramFallback"
# import OK
```

## Notes

- Related beads: `adc-12bt` / `adc-14la` (first-failure detection design),
  `adc-4las` (first-failure WARNING), this bead `adc-47l2` (cooldown dedup of
  the repeated-failure DEBUG lines).
- The pre-existing uncommitted edits to `src/test/dispatch.py`,
  `tests/e2e/conftest.py`, and `tests/e2e/test_storage_sse_verification.py`
  contain zero Telegram references and are unrelated to this bead; left
  untouched.
