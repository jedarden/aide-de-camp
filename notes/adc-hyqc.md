# Bead adc-hyqc: Add WARNING on first failed Telegram send

**Type:** umbrella (split-child) — work delivered across closed child beads.
**Status:** no source changes required; closing.

## Finding

The functionality requested in this bead **already exists, fully shipped** in
`src/telegram/fallback.py`, delivered by the three closed child beads:

| Child | Title | Status |
|-------|-------|--------|
| `adc-1qc` | Add startup bridge reachability check | closed |
| `adc-b5j6` / `adc-47l2` | Rate-limiting for repeated Telegram send failures | closed |
| `adc-20p9` | Verify Telegram send failure logging end-to-end | closed |

## Current implementation

`TelegramFallback.send_message()` routes all failure paths
(HTTP non-2xx, `httpx.RequestError`, generic exceptions) into
`_handle_send_failure()` → `_record_failure_locked()`, which runs under
`_first_failure_lock` (sync critical section, await-free on purpose).

Logging policy (`fallback.py:281-348`):

- **First failure after startup** — emits exactly one `logger.warning(...)`
  claiming the `_has_logged_first_failure` False→True flip (one per process
  startup). The message includes the bridge URL, error type, and error message.
- **Repeated failures** — rate-limited: at most one `logger.debug(...)` summary
  per `_failure_log_interval_seconds` window (default **300s**, configurable via
  `ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS`). Failures inside a window are
  counted silently (`_failures_since_last_log`) so a sustained outage cannot
  spam the log. The window is seeded by the first-failure WARNING to prevent a
  follow-on DEBUG storm.
- `_failure_count` and `_last_failure_timestamp` update on every failure
  regardless of logging; both are exposed via `get_bridge_status()`.

> Note: an earlier version of this note described a 60-second
> `_last_failure_logged` implementation. That has since been superseded by the
> per-startup first-failure claim + 300s rate-limit window shipped by the child
> beads above.

## Acceptance criteria — verified

1. ✅ **First send failure logs a WARNING with context** — bridge URL + error
   type + message (`fallback.py:328-333`).
2. ✅ **Failures visible at WARNING level, not just DEBUG** — first failure is
   `WARNING`; only later failures fall through to `DEBUG`.
3. ✅ **No log spam from repeated failures** — 300s rate-limit window dedupes.

## Verification performed this session

- `tests/test_telegram_fallback.py` + `tests/test_telegram_bridge_status.py`
  → **33 passed**.
- End-to-end drive: pointed the singleton at an unreachable bridge
  (`http://127.0.0.1:9/nope`) and issued 4 sends. Result: exactly **one**
  `WARNING` (`First Telegram send failure detected ... Error type: ConnectError.
  Error: All connection attempts failed ...`), zero further
  `telegram.fallback` log lines for the 3 repeated failures
  (`failures_since_last_log: 3`), confirming the rate-limit dedupe.

## Conclusion

No source changes were needed — the feature was already present and working.
This note is the closure artifact for the umbrella.
