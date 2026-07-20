# adc-44u — Add bridge reachability warning and status indicator

## Status

**Verified — no source changes.** This bead is the `umbrella` / `split-child`
tracker for making unreachable Telegram-bridge failures visible. Its work was
delivered across the already-closed child beads `adc-1qc` / `adc-b5j6` /
`adc-47l2` / `adc-hyqc` / `adc-20p9` (first-failure WARNING + rate-limiting +
per-failure-type dedup), `adc-4hvx` (status payload + startup probe
`last_check_time` / `chat_id`), and `adc-15u0` (per-failure-type dedup). This
session re-verified the shipped implementation end-to-end and updated this
note, which previously described a stale 60-second `_last_failure_logged`
mechanism that no longer exists.

A prior dispatch of this bead also added the missing
`get_last_scan_at()` / `refresh_registry()` / `start_background_refresh()` /
`stop_background_refresh()` functions to `src/environment/discovery.py` (they
were imported by `main.py` but absent, breaking startup). Those landed
separately and are present on `main`; the app now imports and boots cleanly.

## Acceptance criteria → shipped code

All four criteria are met by committed code:

1. **WARNING on first failed send (bridge unreachable)** —
   `src/telegram/fallback.py`, `TelegramFallback._record_failure_locked()`. The
   first failure after startup claims `_has_logged_first_failure` (False→True,
   once per process) and emits exactly one WARNING naming the error type and
   message. A *different* failure type appearing mid-outage gets its own
   independent WARNING (adc-15u0 per-failure-type dedup).

2. **Status exposed via API** — `GET /api/v1/status/telegram_bridge`
   (`src/main.py`) → `TelegramFallback.get_bridge_status()`
   (`src/telegram/fallback.py`). Returns a 12-key payload: `reachable`,
   `bridge_url`, `chat_id`, `last_check_time`, `failure_count`,
   `has_logged_first_failure`, `first_failure_timestamp`,
   `last_failure_timestamp`, `failure_log_interval_seconds`,
   `failures_since_last_log`, `seen_failure_types`, `distinct_failure_types`.

3. **Startup reachability check** — `src/main.py` `lifespan()` calls
   `check_bridge_available()` (a `GET {bridge_url}/health` probe), logs INFO on
   success and `WARNING: Telegram bridge unreachable at ... Telegram fallback
   will not be available.` on failure. Every reachability determination flows
   through `_set_reachable()`, which also stamps `last_check_time`.

4. **Per-send failures don't flood logs** — repeats of an already-seen failure
   type are rate-limited to at most one DEBUG summary per
   `ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS` (default 300s) window;
   failures inside a window are counted silently. The first-failure WARNING
   seeds the window so it is not immediately followed by a DEBUG storm.

## Verification (this session)

- `tests/test_telegram_fallback.py` — **38 passed** (covers first-failure claim,
  300s rate-limit window, per-failure-type dedup, status payload, reset).
- `from src.main import app` imports cleanly; `get_bridge_status()` returns all
  12 keys.
- Live drive against an unroutable bridge (`http://127.0.0.1:1`):
  - Startup probe → `reachable=False`, `last_check_time` set.
  - 4 same-type failures → **exactly 1** first-failure WARNING; remaining
    repeats counted silently (DEBUG summary suppressed within the seeded window).
  - 1 new failure type (`TimeoutError` after `ConnectionError`) → **exactly 1**
    independent WARNING, emitted immediately despite the same-type cooldown;
    `distinct_failure_types` correctly reached 2.

## Version

No version bump — documentation-only commit (no source changes), matching the
precedent of the sibling umbrella-verification commits (`adc-47l2`, `adc-hyqc`,
`adc-2482`). The feature itself was versioned when shipped (0.10.0 → 0.12.0).
