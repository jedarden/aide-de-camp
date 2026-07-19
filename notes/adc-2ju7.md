# adc-2ju7: Add WARNING log on first Telegram send failure

**Status: VERIFIED COMPLETE** — umbrella bead closed. All child beads closed.

## What this bead is

`adc-2ju7` is the **umbrella** tracking bead for "add a WARNING log on the first
Telegram send failure after startup." The implementation work was split across
child beads, all now closed:

| Bead     | Title                                     | Status  |
|----------|-------------------------------------------|---------|
| adc-4667 | Find all Telegram send locations          | closed  |
| adc-4vhr | Design first-failure tracking mechanism   | closed  |
| adc-4las | Implement WARNING log with error context  | closed  |
| adc-39tx | Verify WARNING logs only on first failure | closed  |

> Earlier versions of this note referenced commit `c45a963` (the first, simpler
> attempt). That was superseded by `301b82a` (adc-4las), which is the
> **current** implementation this note now reflects.

## Final implementation

File: `src/telegram/fallback.py`, method `_record_failure_locked()` (called under
`_first_failure_lock` from the async entry `_handle_send_failure()`).

State (instance vars on the singleton, per-startup, no persistence):

- `_has_logged_first_failure: bool` — one-shot claim flag
- `_failure_count: int`, `_first_failure_timestamp`, `_last_failure_timestamp`
- `_first_failure_lock: asyncio.Lock` — serializes the claim-and-set

All three failure branches in `send_message()` route through
`_handle_send_failure()`:

- non-2xx HTTP → `error_context="status {code} - {text}"`
- `httpx.RequestError` → `error=e`
- any other `Exception` → `error=e`

`_record_failure_locked()` derives `error_type` (`type(e).__name__`, or
synthesized `"HTTPError"` for non-2xx responses) and `message`, then:

- On the **first** failure: flips `_has_logged_first_failure` True, stamps
  `_first_failure_timestamp`, and emits one `logger.warning(...)` carrying the
  error type and message. Returns `True` (this call won the claim).
- On every **later** failure in the startup: emits `logger.debug(...)` only.
  Returns `False`.

"First" is the winner of the lock-guarded claim, not a timestamp comparison — so
exactly one WARNING is emitted per process startup even under concurrent
failures.

## Acceptance-criteria verification

- ✅ **First send failure logs a WARNING with context** — `_record_failure_locked`
  WARNING branch.
- ✅ **Log includes error type and message** — `Error type: {error_type}. Error:
  {message}.` (synthesized `HTTPError` + context for non-2xx responses).
- ✅ **No duplicate logs for the same initial failure** — `_has_logged_first_failure`
  guard + `_first_failure_lock`; subsequent failures log at DEBUG only.

## Tests (24 passing)

`.venv/bin/pytest tests/test_telegram_fallback.py tests/test_telegram_bridge_status.py`
→ 24 passed.

First-failure coverage in `tests/test_telegram_fallback.py::TestFirstFailureTracking`:

- first failure logs WARNING with error type + message
- subsequent failures log at DEBUG, not WARNING
- exactly one WARNING under 50 concurrent failures (`failure_count == 50`)
- `_first_failure_timestamp` is set-once; `_last_failure_timestamp` advances
- `reset_first_failure_state()` re-arms detection, retains counters
- non-2xx response logs synthesized `HTTPError` type + context

Plus 9 tests in `tests/test_telegram_bridge_status.py` covering the failure
counter, singleton, and the `/api/v1/telegram/bridge-status` surface.

## Commits

- `c45a963` — original simpler WARNING (superseded)
- `301b82a` (adc-4las) — current impl: error type + message + lock
- `4d7e94f` (adc-39tx) — verification tests
- `2c63f2e`, `d5bf9e8` — earlier (stale) versions of this note

✅ All acceptance criteria met. Implementation complete and verified.
