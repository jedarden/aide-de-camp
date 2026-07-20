# adc-20p9 — Verify Telegram send-failure logging end-to-end

## Outcome: VERIFIED (feature already shipped)

The Telegram send-failure logging + rate-limiting was implemented in `e809712`
(adc-47l2) and re-verified in `e891122`. This bead confirms the behavior
**end-to-end** by driving the real `TelegramFallback.send_message()` network
path through actual httpx failures and observing it through Python's genuine
logging pipeline (not just `caplog`). No source changes were needed; this is a
verification record.

## What was driven

Instead of calling `_handle_send_failure` directly (as the unit tests do), this
verification exercised the full public surface:

- **Connection-refused path:** `send_message()` against `http://127.0.0.1:1`
  → httpx raises `ConnectError` (subclass of `httpx.RequestError`) →
  `send_message`'s `except httpx.RequestError` branch → `_handle_send_failure(error=...)`.
- **Non-2xx HTTP path:** a real local `HTTPServer` returning `500 upstream
  down` → `send_message`'s non-2xx branch → `_handle_send_failure(error_context="status 500 - ...")`.

Observation was via a real `logging.Handler` attached to the
`src.telegram.fallback` logger, mirroring `src/main.py`'s
`logging.basicConfig(level=INFO, ...)` so the level-visibility result reflects
the actual running server.

## Acceptance criteria — results

| # | Criterion | Result |
|---|-----------|--------|
| 1 | First send failure logs a visible WARNING with context | ✅ 1 WARNING carrying error type (`ConnectError` / `HTTPError`) + message on the first failure |
| 2 | Repeated failures are rate-limited (no spam) | ✅ 50 rapid failures → exactly 1 WARNING, **0** DEBUG summaries in the cooldown window; `failures_since_last_log == 49` counted silently |
| 3 | Visible at WARNING level (not DEBUG-only) | ✅ the WARNING survives a handler threshold set to both INFO and the stricter WARNING level; a DEBUG-level handler still shows zero DEBUG noise for the burst |

## Commands run (2026-07-19)

```
# Unit-test confirmation (33 tests)
.venv/bin/python -m pytest tests/test_telegram_fallback.py tests/test_telegram_bridge_status.py -q
# 33 passed in 0.07s

# End-to-end driver (real httpx network failures + real logging pipeline)
.venv/bin/python /tmp/verify_adc_20p9.py
# ALL END-TO-END CHECKS PASSED
#   [1+3] first-failure WARNING via real network path (refused), visible at INFO
#   [3]  WARNING survives a strict WARNING-level handler (truly WARNING, not DEBUG)
#   [1]  non-2xx HTTP 500 path logs WARNING with synthesized HTTPError type + context
#   [2]  50 rapid failures → 1 WARNING, 0 DEBUG (rate-limited, no spam)
#   [2]  silent dedup counter tracks suppressed failures (failures_since_last_log=49)
```

## Conclusion

The shipped implementation in `src/telegram/fallback.py` satisfies all
acceptance criteria end-to-end: the first failure after startup emits exactly
one visible WARNING (with error-type and message context) through the real
`send_message` network path, and a sustained outage of 50 failures produces no
log spam — one WARNING total, zero DEBUG summaries while inside the
`_failure_log_interval_seconds` (300s) cooldown window. The WARNING is a true
WARNING-level record (visible at the server's INFO root level), not DEBUG-only.
