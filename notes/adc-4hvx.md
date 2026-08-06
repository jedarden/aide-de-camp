# ADC-4hvx: Telegram Bridge Status Endpoint

## Finding

The GET `/api/v1/status/telegram_bridge` endpoint already exists in `src/main.py` (lines 2165-2183).

## Verification

All acceptance criteria are met:

1. **Endpoint returns bridge status in JSON format** ✓
   - Returns comprehensive status from `TelegramFallback.get_status()`

2. **Status reflects current reachability state** ✓
   - `reachable`: bool | None (None=unknown, True=reachable, False=unreachable)
   - Updated via `_set_reachable()` on:
     - Startup check in `lifespan()` (line 158-169)
     - Reactive updates on `send_message()` success/failure (lines 153, 161)

3. **Endpoint documented in OpenAPI schema** ✓
   - Docstring picked up by FastAPI automatically
   - Visible in `/openapi.json` under `/api/v1/status/telegram_bridge`

## Response Schema

```json
{
  "reachable": bool | null,
  "bot_configured": bool,
  "chat_id_configured": bool,
  "chat_id": str | null,
  "last_check_time": string | null,  // ISO-8601 timestamp
  "failure_count": int,
  "has_logged_first_failure": bool,
  "has_failed_since_startup": bool,
  "first_failure_timestamp": string | null,
  "last_failure_timestamp": string | null,
  "failure_log_interval_seconds": float,
  "failures_since_last_log": int,
  "seen_failure_types": string[],
  "distinct_failure_types": int
}
```

## Test Result

```bash
$ curl http://localhost:8000/api/v1/status/telegram_bridge
{
  "reachable": null,
  "bot_configured": false,
  "chat_id_configured": false,
  "chat_id": null,
  "last_check_time": null,
  "failure_count": 0,
  "has_logged_first_failure": false,
  "has_failed_since_startup": false,
  "first_failure_timestamp": null,
  "last_failure_timestamp": null,
  "failure_log_interval_seconds": 300.0,
  "failures_since_last_log": 0,
  "seen_failure_types": [],
  "distinct_failure_types": 0
}
```

## Conclusion

The task is already complete. No code changes required.
