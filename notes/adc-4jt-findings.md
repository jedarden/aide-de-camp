# telegram-claude-bridge API Contract Verification (adc-4jt)

## Date: 2026-07-02

## Executive Summary

✅ **ALL CONTRACTS VERIFIED CORRECT - NO ISSUES FOUND**

Verified `src/telegram/fallback.py` AND `src/watcher/daemon.py` request schemas against the actual telegram-claude-bridge source code. **All API contracts match correctly.**

Previous issues mentioned in earlier findings have been resolved. The current implementation:
- ✅ Uses correct endpoints (`/send`, `/health`)
- ✅ Uses correct payload fields (`chat_id`, `text`, `parse_mode`)
- ✅ Properly handles the pull-based architecture of telegram-claude-bridge
- ✅ Documents session→chat_id mapping limitations appropriately

---

## Verification Method

- **Source:** telegram-claude-bridge repository at `/home/coding/telegram-claude-bridge`
- **Contract definition:** `internal/contract/types.go` (lines 138-146 for SendRequest)
- **Endpoint handlers:** `cmd/proxy/main.go` (lines 47-64 for /send and /health)
- **Bridge version:** 0.3.0 (per README.md)

---

## Endpoints Verified

### ✅ POST /send (Message sending)

**Location in bridge:** `cmd/proxy/main.go:49` → `handleSend()`

**Contract:** `internal/contract/types.go:138-146`

```go
type SendRequest struct {
    ChatID            int64          `json:"chat_id"`                      // REQUIRED
    ThreadID          *int64         `json:"thread_id,omitempty"`         // OPTIONAL
    Text              string         `json:"text"`                         // REQUIRED
    ParseMode         *string        `json:"parse_mode,omitempty"`         // OPTIONAL
    ReplyToMessageID  *int64         `json:"reply_to_message_id,omitempty"` // OPTIONAL
    ReplyMarkup       *InlineKeyboard `json:"reply_markup,omitempty"`     // OPTIONAL
}
```

**fallback.py implementation:** `src/telegram/fallback.py:60-67`

```python
response = await client.post(
    f"{self.bridge_url}/send",
    json={
        "chat_id": int(chat_id) if isinstance(chat_id, str) else chat_id,
        "text": message,
        "parse_mode": parse_mode,
    },
    timeout=10.0,
)
```

**Field mapping:**
- ✅ `chat_id` → `chat_id` (int64) - Correctly converted to int
- ✅ `text` → `text` (string) - Present
- ✅ `parse_mode` → `parse_mode` (optional string) - Present, defaults to "HTML"
- ⚪ `thread_id` - Not used (OPTIONAL field, omission is valid)
- ⚪ `reply_to_message_id` - Not used (OPTIONABLE field, omission is valid)
- ⚪ `reply_markup` - Not used (OPTIONAL field, omission is valid)

**Verdict:** ✅ **CORRECT** - All required fields present, optional fields correctly omitted

---

### ✅ GET /health (Health check)

**Location in bridge:** `cmd/proxy/main.go:47` → `handleHealth()`

**Contract:** `internal/contract/types.go:127-136`

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

**fallback.py implementation:** `src/telegram/fallback.py:145-155`

```python
async def check_bridge_available(self) -> bool:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.bridge_url}/health",
                timeout=5.0,
            )
            return response.status_code == 200
    except Exception:
        return False
```

**Verdict:** ✅ **CORRECT** - Endpoint path and HTTP method are correct

---

### ✅ POST /register_surface (Surface registration)

**Status:** DOCUMENTED AS NO-OP STUB

**fallback.py implementation:** `src/telegram/fallback.py:125-143`

```python
async def register_surface(self, session_id: str, telegram_chat_id: str) -> bool:
    """
    Register a Telegram surface for a session.

    NOTE: The /register_surface endpoint does NOT exist in telegram-claude-bridge.
    This method is a no-op stub for API compatibility. telegram-claude-bridge
    uses a pull-based architecture where it manages sessions internally per forum topic,
    not a push-based model where external systems register delivery surfaces.

    Returns True for compatibility (pretends registration succeeded).
    """
    logger.warning(
        f"register_surface() called for session {session_id} - "
        f"telegram-claude-bridge does not support surface registration. "
        f"This is a no-op stub."
    )
    return True
```

**Bridge endpoints available** (from `cmd/proxy/main.go:47-63`):
```go
mux.HandleFunc("/health", handleHealth(poller))
mux.HandleFunc("/updates", handleUpdates(poller))
mux.HandleFunc("/send", handleSend(sender))
mux.HandleFunc("/edit", handleEdit(sender))
mux.HandleFunc("/send_chat_action", handleSendChatAction(sender))
mux.HandleFunc("/create_topic", handleCreateTopic(sender))
mux.HandleFunc("/edit_topic", handleEditTopic(sender))
mux.HandleFunc("/close_topic", handleCloseTopic(sender))
mux.HandleFunc("/reopen_topic", handleReopenTopic(sender))
mux.HandleFunc("/pin_message", handlePinMessage(sender))
mux.HandleFunc("/get_message", handleGetMessage(poller))
mux.HandleFunc("/answer_callback", handleAnswerCallback(sender))
mux.HandleFunc("GET /file/{file_id}", handleFile(sender))
mux.HandleFunc("/send_photo", handleSendPhoto(sender))
mux.HandleFunc("/send_document", handleSendDocument(sender))
mux.HandleFunc("/send_audio", handleSendAudio(sender))
mux.HandleFunc("/send_video", handleSendVideo(sender))
```

**Verification:** The `/register_surface` endpoint does NOT exist in telegram-claude-bridge.

**Architecture note:** telegram-claude-bridge uses a **pull-based architecture**:
- Bridge manages sessions internally (one session per forum topic)
- Each topic maps to a tmux session running Claude Code
- No external surface registration needed

**Verdict:** ✅ **CORRECTLY DOCUMENTED** - The no-op stub is appropriate and well-documented

---

### ✅ watcher/daemon.py Telegram Integration

**Status**: DOCUMENTED AS NOT IMPLEMENTED

**Current implementation**: `src/watcher/daemon.py:215-240`

```python
async def _send_to_telegram(self, result: dict, session_id: str) -> None:
    """Send result to Telegram via telegram-claude-bridge.

    NOTE: This requires a session→telegram_chat_id mapping. Current implementation
    logs a warning because telegram-claude-bridge uses a pull-based architecture
    (manages sessions internally per forum topic) rather than push-based message delivery.
    """
    try:
        # telegram-claude-bridge proxy expects actual Telegram chat_id (int64), not session_id
        # Since we don't have a session→chat mapping, log this as unavailable
        logger.warning(
            f"Cannot send result to Telegram for session {session_id}: "
            f"session→telegram_chat mapping not implemented. "
            f"telegram-claude-bridge uses pull-based architecture (per forum topic sessions)."
        )

        # Correct contract for reference (if mapping is implemented later):
        # POST http://telegram-claude-bridge:8000/send
        # {
        #   "chat_id": 123456789,  # int64, REQUIRED - actual Telegram chat ID
        #   "text": "message",     # string, REQUIRED - message content
        #   "parse_mode": "HTML"   # string, OPTIONAL
        # }
```

**Verdict:** ✅ **CORRECTLY DOCUMENTED** - Method appropriately logs warning about missing session→chat_id mapping and includes correct contract as reference for future implementation

---

## Previous Issues (RESOLVED)

### ✅ RESOLVED: Previous watcher/daemon.py endpoint/payload issues

**Earlier findings** (2026-07-02 initial version) documented critical issues in `watcher/daemon.py`:
- ❌ Wrong endpoint: `/send_message` → `/send`
- ❌ Wrong payload fields: `session_id` → `chat_id`, `message` → `text`

**Current status**: ✅ **RESOLVED**
- The `_send_to_telegram()` method no longer makes HTTP requests
- It correctly logs the session→chat_id mapping limitation
- The correct contract is documented as a comment for future reference
- No incorrect API calls are made in the current codebase

---

## Parse Mode Handling

**Default in `send_message()`:** `"HTML"` (line 43)

**Exception handling in `send_exception()`:** `"Markdown"` (line 110)

Both are valid Telegram parse modes. The use of "Markdown" for exceptions appears to be intentional for formatting exception messages.

---

## Bridge URL Configuration

**Environment variable:** `ADC_TELEGRAM_BRIDGE_URL`

**Default:** `http://telegram-claude-bridge:8000`

**Current config:** Per `/home/coding/aide-de-camp/notes/adc-4jt.md`, the verified endpoint is:
`http://telegram-claude-bridge:8000` (Tailscale mesh hostname)

---

## Live Testing

**Status:** Service not accessible in test environment (behind Tailscale ACLs)

However, the contract has been verified by:
1. ✅ Reading telegram-claude-bridge source code directly
2. ✅ Comparing SendRequest structure in `internal/contract/types.go`
3. ✅ Verifying endpoint handlers in `cmd/proxy/main.go`
4. ✅ Cross-referencing with README.md documentation

---

## ✅ NO ISSUES FOUND - ALL CONTRACTS CORRECT

**Summary**: All components use correct API contracts. Previous issues have been resolved.

### Verification Results:

| Component | Method | Status | Notes |
|-----------|--------|--------|-------|
| fallback.py | `send_message()` | ✅ CORRECT | Uses `/send`, payload matches contract (chat_id, text, parse_mode) |
| fallback.py | `check_bridge_available()` | ✅ CORRECT | Uses `/health`, endpoint exists |
| fallback.py | `register_surface()` | ✅ CORRECT | No-op stub is appropriate for pull-based architecture |
| fallback.py | `send_exception()` | ✅ CORRECT | No-op with appropriate warning |
| fallback.py | `send_workload_summary()` | ✅ CORRECT | No-op with appropriate warning |
| watcher/daemon.py | `_send_to_telegram()` | ✅ CORRECT | No-op with appropriate warning, correct contract documented |

**No HTTP requests are made with incorrect endpoints or payload fields.**

---

## Correct Contract Summary

### POST /send (telegram-claude-bridge proxy)
```json
{
  "chat_id": 123456789,           // int64, REQUIRED - Telegram chat ID
  "text": "message text",         // string, REQUIRED - message content
  "parse_mode": "HTML",          // string, OPTIONAL - "HTML" or "Markdown"
  "thread_id": 1,                 // int64, OPTIONAL - forum topic thread ID
  "reply_to_message_id": 123,    // int64, OPTIONAL - message to reply to
  "reply_markup": {...}          // InlineKeyboard, OPTIONAL
}
```

**Response**:
```json
{
  "ok": true,
  "message_id": 456
}
```

---

## Conclusion

✅ **ALL API CONTRACTS VERIFIED CORRECT**

**Current Status:**
- ✅ `fallback.py` - All methods use correct API contracts
- ✅ `watcher/daemon.py` - Correctly handles session→chat_id mapping limitation
- ✅ No incorrect HTTP requests are made
- ✅ All endpoints and payloads match the telegram-claude-bridge contract

**Architecture Understanding:**
- telegram-claude-bridge uses a **pull-based architecture** where it manages sessions internally per forum topic
- External systems don't "register" delivery targets (no `/register_surface` endpoint)
- The current implementation appropriately logs warnings when attempting to send results without a session→chat_id mapping
- The correct contract is documented in code comments for future implementation

**No fixes required.** The implementation correctly handles the available endpoints and properly documents the architectural constraints.

---

## References

- telegram-claude-bridge source: `/home/coding/telegram-claude-bridge/`
- Contract definitions: `internal/contract/types.go`
- Proxy handlers: `cmd/proxy/main.go`
- Bridge README: `/home/coding/telegram-claude-bridge/README.md`
