# adc-39tx — Verify WARNING logs only on first Telegram failure

**Status:** VERIFIED ✅
**Date:** 2026-07-19
**Code under test:** `src/telegram/fallback.py` (landed in commit `8d88f0e` / bead `adc-4las`)

## Acceptance criteria — results

| # | Criterion | Result |
|---|-----------|--------|
| 1 | First failure produces WARNING with error context (type + message) | ✅ `Error type: ConnectError. Error: All connection attempts failed.` |
| 2 | Second failure does NOT produce another WARNING | ✅ Subsequent failures log at DEBUG only; exactly 1 WARNING across N failures |
| 3 | Logs readable in `/tmp/adc.log` (or appropriate destination) | ✅ Server uses `logging.basicConfig(level=logging.INFO)`; WARNING ≥ INFO reaches the root handler that writes `/tmp/adc.log` |
| 4 | Evidence (log excerpt) added to bead body | ✅ This file |

## How it was verified

Two complementary checks:

### 1. Unit tests (logic-level) — 24/24 pass

```
.venv/bin/python -m pytest tests/test_telegram_fallback.py tests/test_telegram_bridge_status.py -v
============================== 24 passed in 0.07s ==============================
```

Key cases: `test_first_failure_logs_warning_with_error_type`,
`test_subsequent_failures_log_debug_not_warning`,
`test_exactly_one_warning_under_concurrency` (50 concurrent failures → 1 WARNING, count==50),
`test_non_2xx_response_logs_synthesized_type_and_context`.

### 2. Runtime verification (real HTTP code path)

`notes/adc-39tx_verify.py` drives the real `TelegramFallback.send_message` against an
unreachable bridge (`http://127.0.0.1:1` → connection refused → `httpx.ConnectError`,
the same `except httpx.RequestError` branch production traffic hits) and captures the
module logger's records across 3 consecutive failures:

```
send_message returned: [False, False, False]
WARNING count: 1
DEBUG count:   2
---- WARNING records ----
[WARNING] src.telegram.fallback: First Telegram send failure detected at http://127.0.0.1:1.
  Error type: ConnectError. Error: All connection attempts failed.
  Subsequent failures will be logged at DEBUG level only.
---- DEBUG records ----
[DEBUG] src.telegram.fallback: Repeated Telegram send failure #2 at http://127.0.0.1:1. ...
[DEBUG] src.telegram.fallback: Repeated Telegram send failure #3 at http://127.0.0.1:1. ...
failure_count (instance): 3
has_logged_first_failure: True

VERIFICATION PASSED: exactly one WARNING on first failure; subsequent failures DEBUG only.
```

### 3. Log-routing confirmation (what actually reaches `/tmp/adc.log`)

The server configures logging as `logging.basicConfig(level=logging.INFO, ...)`
(`src/main.py:14-17`), so the `src.telegram.fallback` logger propagates to root.
Running the same 3 failures **under the server's INFO threshold** yields exactly one
output line — the WARNING. The two DEBUG records fall below INFO and are filtered out:

```
$ .venv/bin/python  # basicConfig(level=logging.INFO), then 3x send_message -> dead host
WARNING src.telegram.fallback: First Telegram send failure detected at http://127.0.0.1:1.
  Error type: ConnectError. Error: All connection attempts failed.
  Subsequent failures will be logged at DEBUG level only.
```

So `/tmp/adc.log` sees **one** WARNING line per process startup, regardless of how many
sends fail — no duplicate WARNINGs, no DEBUG spam. This is precisely the design intent.

## Mechanism (why it's correct)

`_handle_send_failure` acquires `_first_failure_lock` and calls `_record_failure_locked`
(a plain sync function — deliberately `await`-free, so the read-then-set of
`_has_logged_first_failure` cannot be interleaved by another coroutine). The first caller
to flip the flag `False → True` wins and emits the WARNING; every later caller logs at
DEBUG. The claim is the winner, not a timestamp comparison — hence exactly one WARNING
per startup even under concurrent failures.
