# Telegram Bot Environment Configuration

**Status:** ✅ Configured (2026-08-28)

## Overview

This document describes the Telegram bot environment variable configuration for aide-de-camp, including OpenBao integration for secure runtime token retrieval.

## Environment Variables

### OpenBao Configuration

| Variable | Value | Purpose | Required |
|----------|-------|---------|----------|
| `OPENBAO_URL` | `http://traefik-ardenone-cluster:8200` | OpenBao server URL (ardenone-cluster instance) | No (default) |
| `OPENBAO_TOKEN` | *(varies)* | OpenBao authentication token | Yes |

### Telegram Bot Configuration

| Variable | Value | Purpose | Required |
|----------|-------|---------|----------|
| `TELEGRAM_BOT_TOKEN_PATH` | `secret/ardenone-cluster/aide-de-camp/telegram_bot_token` | OpenBao path to bot token | No (but needed for OpenBao retrieval) |
| `TELEGRAM_BOT_NAME` | `aide_de_camp_bot` | Bot name for identification/logging | No (informational) |
| `ADC_TELEGRAM_CHAT_ID` | *(varies)* | Telegram chat ID for notifications | Yes |
| `ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS` | `300` | Min seconds between repeated-failure logs | No (default: 300) |

### Legacy Direct Token (Alternative)

| Variable | Value | Purpose | Required |
|----------|-------|---------|----------|
| `ADC_TELEGRAM_BOT_TOKEN` | *(varies)* | Direct bot token value (no OpenBao) | No |

## Token Resolution Priority

The Telegram fallback module resolves the bot token in this order:

1. **Constructor argument** - Direct value passed to `TelegramFallback(bot_token=...)`
2. **Direct environment variable** - `ADC_TELEGRAM_BOT_TOKEN` env var
3. **OpenBao path** - `TELEGRAM_BOT_TOKEN_PATH` env var → retrieve from OpenBao
4. **None** - No token configured (graceful no-op with WARNING)

## OpenBao Secret Structure

The bot token is stored in OpenBao at:

```
secret/ardenone-cluster/aide-de-camp/telegram_bot_token
```

Field name: `token`

**Example secret structure:**
```json
{
  "data": {
    "data": {
      "token": "***REMOVED***"
    }
  }
}
```

## Deployment Configuration

### systemd Service

Environment variables are configured in `deploy/aide-de-camp.service`:

```ini
[Service]
# OpenBao configuration
Environment=OPENBAO_URL=http://traefik-ardenone-cluster:8200
# Environment=OPENBAO_TOKEN=<your-openbao-token>

# Telegram bot configuration
Environment=TELEGRAM_BOT_TOKEN_PATH=secret/ardenone-cluster/aide-de-camp/telegram_bot_token
Environment=TELEGRAM_BOT_NAME=aide_de_camp_bot
# Environment=ADC_TELEGRAM_CHAT_ID=<your-telegram-chat-id>
```

### Required Manual Setup

To enable Telegram integration:

1. **Set OpenBao token** (retrieve via `bao token lookup`)
   ```bash
   # Edit aide-de-camp.service and uncomment:
   Environment=OPENBAO_TOKEN=<retrieved-token>
   ```

2. **Set Telegram chat ID** (obtain via `getUpdates` API)
   ```bash
   # Edit aide-de-camp.service and uncomment:
   Environment=ADC_TELEGRAM_CHAT_ID=<your-chat-id>
   ```

3. **Reload systemd** and restart service
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart aide-de-camp
   ```

## Security Considerations

- ✅ Bot token is NEVER exposed in environment variables when using OpenBao path
- ✅ Token value is NEVER logged or printed
- ✅ Token is retrieved only at runtime from OpenBao
- ✅ OpenBao token is required for secret access
- ✅ Self-signed Traefik certificates are handled correctly (`verify=False`)

## Code Implementation

### OpenBao Client Module

**File:** `src/openbao/client.py`

Provides secure secret retrieval from OpenBao:

```python
from src.openbao import get_openbao_client

client = get_openbao_client()
token = client.get_secret("secret/ardenone-cluster/aide-de-camp/telegram_bot_token", field="token")
```

### Telegram Fallback Integration

**File:** `src/telegram/fallback.py`

The `TelegramFallback` class automatically retrieves the bot token from OpenBao when `TELEGRAM_BOT_TOKEN_PATH` is set:

```python
# No token argument - will retrieve from OpenBao
fallback = TelegramFallback()
# fallback.bot_token now contains the retrieved value
```

## Testing

Comprehensive tests verify the OpenBao integration:

```bash
# Run OpenBao integration tests
.venv/bin/pytest tests/test_openbao_integration.py -v

# Run all Telegram-related tests
.venv/bin/pytest tests/test_telegram_fallback.py tests/test_openbao_integration.py -v
```

**Current status:** All 65 tests pass ✅

## Verification

To verify the configuration is working:

1. **Check OpenBao metadata** (does NOT read the token value):
   ```bash
   bao kv metadata get -address=http://traefik-ardenone-cluster:8200 \
     secret/ardenone-cluster/aide-de-camp/telegram_bot_token
   ```

2. **Test token retrieval** (via pipe, never to stdout):
   ```bash
   bao kv get -field=token -address=http://traefik-ardenone-cluster:8200 \
     secret/ardenone-cluster/aide-de-camp/telegram_bot_token | \
     curl -sS -X POST "https://api.telegram.org/bot$(cat)/getMe"
   ```

3. **Check service status**:
   ```bash
   systemctl --user status aide-de-camp
   journalctl --user -u aide-de-camp -n 50
   ```

## Related Documentation

- **OpenBao Path:** [[telegram-bot-token-openbao-path]]
- **Bot Decision:** [[telegram-bot-decision-and-configuration]]
- **ADR-1:** `docs/notes/adr-1-telegram-bot-decision.md`
- **Storage Procedure:** `docs/notes/openbao-telegram-token-storage.md`
