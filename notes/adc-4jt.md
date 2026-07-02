# ADC-4JT: Telegram-Claude-Bridge API Contract Verification

## Task
Verify that the request schema in `fallback.py` matches the real telegram-claude-bridge API endpoints.

## Sources Consulted

### 1. aide-de-camp fallback.py
**File:** `/home/coding/aide-de-camp/src/telegram/fallback.py`

### 2. telegram-claude-bridge contract
**File:** `/home/coding/telegram-claude-bridge/internal/contract/types.go`
**File:** `/home/coding/telegram-claude-bridge/cmd/proxy/main.go`

## Findings

### ✅ Verified: POST /send endpoint

**fallback.py sends:**
```python
{
    "chat_id": int(chat_id),
    "text": message,
    "parse_mode": parse_mode
}
```

**telegram-claude-bridge expects (SendRequest):**
```go
type SendRequest struct {
    ChatID            int64          `json:"chat_id"`
    ThreadID          *int64         `json:"thread_id,omitempty"`
    Text              string         `json:"text"`
    ParseMode         *string        `json:"parse_mode,omitempty"`
    ReplyToMessageID  *int64         `json:"reply_to_message_id,omitempty"`
    ReplyMarkup       *InlineKeyboard `json:"reply_markup,omitempty"`
}
```

**Status:** ✅ **MATCHES**

The `fallback.py` payload correctly maps to the `SendRequest` contract:
- `chat_id` → `ChatID` (int, required)
- `text` → `Text` (string, required)  
- `parse_mode` → `ParseMode` (string, optional)

All required fields are present with correct types.

### ✅ Verified: GET /health endpoint

**fallback.py calls:** `GET /health`

**telegram-claude-bridge returns (HealthResponse):**
```go
type HealthResponse struct {
    OK              bool   `json:"ok"`
    Polling         bool   `json:"polling"`
    LastUpdateID    *int64 `json:"last_update_id,omitempty"`
    UptimeSeconds   int64  `json:"uptime_seconds"`
    ContractVersion string `json:"contract_version,omitempty"`
    Version         string `json:"version,omitempty"`
    CommitSHA       string `json:"commit,omitempty"`
}
```

**Status:** ✅ **CORRECT**

The health check endpoint exists and returns a valid JSON response.

### ❌ MISMATCH FOUND: POST /register_surface endpoint

**fallback.py has a method:**
```python
async def register_surface(self, session_id: str, telegram_chat_id: str) -> bool:
    """Register a Telegram surface for a session."""
    response = await client.post(
        f"{self.bridge_url}/register_surface",
        json={
            "session_id": session_id,
            "chat_id": telegram_chat_id,
        }
    )
```

**telegram-claude-bridge proxy exposes these endpoints:**
- GET /health
- GET /updates
- POST /send
- POST /edit
- POST /send_chat_action
- POST /create_topic
- POST /edit_topic
- POST /close_topic
- POST /reopen_topic
- POST /pin_message
- GET/POST /get_message
- POST /answer_callback
- GET /file/{file_id}
- POST /send_photo
- POST /send_document
- POST /send_audio
- POST /send_video

**Status:** ❌ **ENDPOINT DOES NOT EXIST**

The `/register_surface` endpoint is **not implemented** in telegram-claude-bridge.

**Impact:** LOW - The `TelegramFallback.register_surface()` method appears to be **dead code**. It is defined but never called in the aide-de-camp codebase.

All `register_surface` calls in aide-de-camp are:
- `store.register_surface(session_id, surface_type)` - This is for the local SQLite session store
- No calls to `TelegramFallback.register_surface()`

## Recommendations

1. **Remove dead code:** Delete the `register_surface()` method from `TelegramFallback` class since it's never called and the endpoint doesn't exist.

2. **If registration is needed:** The telegram-claude-bridge operates differently - it creates sessions via forum topics automatically when messages arrive in a new topic. No explicit registration is needed.

## Testing Status

❌ **Could not test live endpoint** - telegram-claude-bridge proxy container is not currently running on the server.

However, the contract verification from source code is conclusive.

## API Contract Summary

| Endpoint | fallback.py usage | telegram-claude-bridge contract | Status |
|----------|-------------------|-------------------------------|--------|
| POST /send | ✅ Used | ✅ Exists, contract matches | VERIFIED |
| GET /health | ✅ Used | ✅ Exists | VERIFIED |
| POST /register_surface | ⚠️ Defined but unused | ❌ Does not exist | DEAD CODE |

## Conclusion

The active API contracts (`/send` and `/health`) are **correctly implemented** in fallback.py. The `/register_surface` method is dead code that should be removed to avoid confusion.
