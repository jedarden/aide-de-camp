# Telegram Bot Provisioning Status

**Bead:** aidedeca-73d9fe27  
**Status:** 🔧 **BLOCKED - REQUIRES HUMAN ACTION**  
**Date:** 2026-08-29

---

## Current State Assessment

### ✅ What's Ready (Infrastructure Complete)

- **OpenBao Integration:** Fully implemented and accessible
  - Client: `src/openbao/client.py`
  - Endpoint: `http://traefik-ardenone-cluster:8200`
  - Authentication: Working (AppRole token in service file)

- **Telegram Integration Code:** Fully implemented
  - Module: `src/telegram/fallback.py`
  - Features: Direct Bot API integration, message sending, reachability checks
  - Endpoint: `/api/v1/status/telegram` (health check)

- **Provisioning Tools:** Ready to use
  - Script: `scripts/provision_telegram_credentials.py` (fully automated)
  - Alternative: `scripts/extract_telegram_chat_id.py` (chat ID extraction only)
  - Verification: `scripts/verify_telegram_send.py` (end-to-end test)

- **Documentation:** Complete
  - Provisioning guide: `TELEGRAM_PROVISIONING.md`
  - ADR-1 decision: `docs/notes/adr-1-telegram-bot-decision.md`
  - Memory records: [[telegram-bot-decision-and-configuration]]

### ❌ What's Missing (Requires Human Action)

1. **Bot Token NOT in OpenBao**
   - Expected path: `secret/ardenone-cluster/aide-de-camp/telegram_bot_token`
   - Status: Path does not exist (verified via OpenBao client)
   - Owner action: Create bot via @BotFather, store token

2. **Chat ID NOT in OpenBao**
   - Expected path: `secret/ardenone-cluster/aide-de-camp/telegram_chat_id`
   - Status: Path does not exist (verified via OpenBao client)
   - Owner action: Extract chat ID via getUpdates API, store in OpenBao

3. **Environment Variable NOT Set**
   - File: `deploy/aide-de-camp.service`
   - Missing: `Environment=ADC_TELEGRAM_CHAT_ID=<your-chat-id>`
   - Status: Currently commented out (line 34)
   - Owner action: Uncomment and set after provisioning

---

## Why This Task Is Blocked

This task is **explicitly marked as owner-only** in the bead description:

> "Owner-only steps (workers must not work this bead)"
> 1) Create the dedicated bot via BotFather  
> 2) Capture the personal chat id  
> 3) Store credentials per workspace conventions

These steps require:
- **Interactive BotFather session** (human Telegram interaction)
- **Personal chat ID** (your private Telegram identifier)
- **Secure credential storage** (OpenBao write access)

Agents/NEEDLE workers cannot perform these steps safely.

---

## Owner Action Required

### Quick Start (Automated - Recommended)

```bash
cd /home/coding/aide-de-camp

# The provisioning script guides you through everything
.venv/bin/python3 scripts/provision_telegram_credentials.py
```

This script:
✅ Checks current state  
✅ Guides you through @BotFather steps  
✅ Stores bot token securely (never in logs)  
✅ Extracts your chat ID automatically  
✅ Stores chat ID in OpenBao  
✅ Verifies everything works

### Manual Process (If Script Fails)

#### Step 1: Create Bot via @BotFather

1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Follow prompts:
   - Name: "aide-de-camp-notifications" (or your choice)
   - Username: "adc_notifications_bot" (must end in 'bot')
4. **Copy the bot token** (format: `1234567890:ABCDEF...`)

#### Step 2: Get Your Chat ID

1. Find your bot in Telegram
2. Send `/start` or any message
3. Visit: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
4. Find `chat.id` in the JSON response (usually 9-10 digit number)

#### Step 3: Store Credentials in OpenBao

```bash
# Set OpenBao environment
export BAO_ADDR="http://traefik-ardenone-cluster:8200"
export OPENBAO_TOKEN="***REMOVED***"

# Store bot token (piped via stdin - never in argv)
echo -n "YOUR_BOT_TOKEN" | bao kv put secret/ardenone-cluster/aide-de-camp/telegram_bot_token token=-

# Store chat ID
bao kv put secret/ardenone-cluster/aide-de-camp/telegram_chat_id chat_id=YOUR_CHAT_ID

# Verify (metadata only - no values exposed)
bao kv metadata get secret/ardenone-cluster/aide-de-camp/telegram_bot_token
bao kv metadata get secret/ardenone-cluster/aide-de-camp/telegram_chat_id
```

#### Step 4: Configure Service File

Edit `~/.config/systemd/user/aide-de-camp.service`:

```ini
[Service]
# ... existing config ...
Environment=ADC_TELEGRAM_CHAT_ID=YOUR_CHAT_ID
# Bot token will be fetched from OpenBao at runtime
# (TELEGRAM_BOT_TOKEN_PATH is already set in the file)
```

#### Step 5: Restart and Verify

```bash
# Reload systemd
systemctl --user daemon-reload

# Restart aide-de-camp
systemctl --user restart aide-de-camp

# Check status
systemctl --user status aide-de-camp

# Verify Telegram integration
curl -s http://localhost:8000/api/v1/status/telegram | jq .
```

Expected response:
```json
{
  "reachable": true,
  "bot_configured": true,
  "chat_id_configured": true,
  "chat_id": "123456789",
  "last_check_time": "2026-08-29T...",
  ...
}
```

### End-to-End Test

```bash
export OPENBAO_TOKEN="***REMOVED***"
export ADC_TELEGRAM_CHAT_ID="your-chat-id"

.venv/bin/python3 scripts/verify_telegram_send.py
```

This sends a test message to your Telegram chat.

---

## What Happens After Provisioning

Once credentials are provisioned and configured:

1. **Exception-class results** → Delivered to Telegram when no canvas active
2. **Workload summaries** → Periodic async task completion updates
3. **Bead closure notifications** → Results from NEEDLE watcher

The integration is automatic - no manual intervention required after setup.

---

## Security Notes

✅ **Best Practices Followed:**
- Bot token piped via stdin (never in command-line args)
- Credentials never appear in logs, shell history, or transcripts
- OpenBao provides audit trail of access
- Reference-only in code (paths, not values)

❌ **Never Do:**
- Paste bot token in command-line arguments
- Store token in git repos
- Log token values
- Use `:latest` image tags

---

## OpenBao Paths

| Credential | OpenBao Path | Purpose |
|------------|--------------|---------|
| Bot Token | `secret/ardenone-cluster/aide-de-camp/telegram_bot_token` | Telegram Bot API authentication |
| Chat ID | `secret/ardenone-cluster/aide-de-camp/telegram_chat_id` | Target chat for fallback notifications |

---

## Environment Variables (deploy/aide-de-camp.service)

| Variable | Status | Purpose |
|----------|--------|---------|
| `OPENBAO_URL` | ✅ Set | OpenBao server address |
| `OPENBAO_TOKEN` | ✅ Set | OpenBao authentication token |
| `TELEGRAM_BOT_TOKEN_PATH` | ✅ Set | Path to bot token in OpenBao |
| `ADC_TELEGRAM_CHAT_ID` | ❌ Missing | Target chat ID (needs to be set) |

---

## Related Documentation

- **Provisioning Guide:** `TELEGRAM_PROVISIONING.md` (detailed steps)
- **ADR-1:** `docs/notes/adr-1-telegram-bot-decision.md` (decision analysis)
- **Memory:** [[telegram-bot-decision-and-configuration]] (decision record)
- **Memory:** [[telegram-bot-token-openbao-path]] (OpenBao path documentation)

---

## Troubleshooting

### Bot Token Invalid
**Symptom:** `reachable: false` in status endpoint  
**Fix:** Verify with `https://api.telegram.org/bot<TOKEN>/getMe`

### Chat ID Not Found
**Symptom:** Messages fail despite `reachable: true`  
**Fix:** Re-run getUpdates after sending a new message to bot

### OpenBao Permission Denied
**Symptom:** 403 errors when storing credentials  
**Fix:** Ensure your OpenBao token has write permissions to the aide-de-camp path

### Service Won't Start
**Symptom:** aide-de-camp service fails after configuration  
**Fix:** Check journalctl: `journalctl --user -u aide-de-camp -f`

---

## Next Steps After Completion

Once credentials are provisioned:

1. ✅ Verify `/api/v1/status/telegram` shows `reachable: true`
2. ✅ Run end-to-end test with `scripts/verify_telegram_send.py`
3. ✅ Confirm test message arrives in Telegram
4. ✅ Close bead `aidedeca-73d9fe27` with confirmation

---

**This is a one-time setup.** Once credentials are stored, the Telegram integration works automatically with no further manual intervention required.
