# Telegram Bot Provisioning Status

**Last Updated:** 2026-08-29  
**Bead:** aidedeca-73d9fe27  
**Status:** 🔒 AWAITING MANUAL OWNER PROVISIONING

---

## Summary

All infrastructure for Telegram bot integration is complete and ready. The remaining steps require manual human intervention (BotFather interaction, OpenBao authentication) that cannot be performed by worker agents.

---

## ✅ Infrastructure Complete (Ready)

### Code Implementation
- **File:** `src/telegram/fallback.py`
- **Status:** Fully implemented with OpenBao integration
- **Features:** 
  - Direct Telegram Bot API integration (per ADR-1)
  - OpenBao runtime token retrieval
  - Graceful degradation when credentials missing
  - Comprehensive failure tracking and logging

### Testing
- **Test suite:** 60+ tests passing
- **Coverage:** 
  - OpenBao integration
  - Telegram API contract
  - Failure state tracking
  - End-to-end logging verification

### Documentation
- **Provisioning guide:** `docs/notes/telegram-bot-api-provisioning.md`
- **OpenBao storage:** `docs/notes/openbao-telegram-token-storage.md`
- **Environment config:** `docs/notes/telegram-bot-environment-configuration.md`
- **Decision record:** Memory documented (create dedicated bot)

### Scripts
- **Setup script:** `scripts/complete_telegram_setup.sh`
- **Chat ID extraction:** `scripts/extract_telegram_chat_id.py`
- **Verification:** `scripts/verify_telegram_send.py`

### Service Configuration
- **File:** `deploy/aide-de-camp.service`
- **Status:** Environment placeholders configured
- **Needs:** OPENBAO_TOKEN and ADC_TELEGRAM_CHAT_ID values

### OpenBao Path
- **Bot token:** `secret/ardenone-cluster/aide-de-camp/telegram_bot_token` (field: `token`)
- **Chat ID:** `secret/ardenone-cluster/aide-de-camp/telegram_chat_id` (field: `chat_id`)
- **Instance:** `http://traefik-ardenone-cluster:8200` (ardenone-cluster)

---

## 🔒 Manual Owner Steps Required

### Step 1: Create Bot via BotFather
1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow prompts to create your bot
4. Copy the bot token (format: `***REMOVED***`)

### Step 2: Get OpenBao Token
```bash
bao login -address=http://traefik-ardenone-cluster:8200 <method>
bao token lookup -address=http://traefik-ardenone-cluster:8200
```

### Step 3: Store Bot Token in OpenBao
```bash
# CRITICAL: Use stdin to avoid token appearing in logs
echo -n "<YOUR_BOT_TOKEN>" | \
  bao kv put -address=http://traefik-ardenone-cluster:8200 \
  secret/ardenone-cluster/aide-de-camp/telegram_bot_token token=-
```

### Step 4: Get Chat ID
1. Start conversation with your bot in Telegram
2. Send `/start` or any message
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Find `message.chat.id` in the JSON response

### Step 5: Store Chat ID in OpenBao
```bash
echo -n "<YOUR_CHAT_ID>" | \
  bao kv put -address=http://traefik-ardenone-cluster:8200 \
  secret/ardenone-cluster/aide-de-camp/telegram_chat_id chat_id=-
```

### Step 6: Update Service Configuration
Edit `deploy/aide-de-camp.service`:
```ini
Environment=OPENBAO_TOKEN=<your-openbao-token>
Environment=ADC_TELEGRAM_CHAT_ID=<your-chat-id>
```

### Step 7: Restart Service
```bash
systemctl --user daemon-reload
systemctl --user restart aide-de-camp
```

### Step 8: Verify Integration
```bash
# Check status endpoint
curl -s http://localhost:8000/api/v1/status/telegram | jq .

# Run verification script
python3 scripts/verify_telegram_send.py
```

---

## 🔍 Verification Checklist

Once manual steps are complete, verify:

- [ ] OpenBao metadata shows both secrets exist
- [ ] `/api/v1/status/telegram` returns `reachable: true`
- [ ] `/api/v1/status/telegram` shows `bot_configured: true`
- [ ] `/api/v1/status/telegram` shows `chat_id_configured: true`
- [ ] Test message arrives in Telegram
- [ ] Exception-class results are delivered when no canvas active

---

## 📋 Related Documentation

- **ADR-1:** `docs/notes/adr-1-telegram-bot-decision.md` - Complete decision analysis
- **Provisioning:** `docs/notes/telegram-bot-api-provisioning.md` - BotFather walkthrough
- **Storage:** `docs/notes/openbao-telegram-token-storage.md` - Secure storage procedures
- **Environment:** `docs/notes/telegram-bot-environment-configuration.md` - Environment setup
- **README:** Configuration table with all environment variables

---

## 🎯 Next Steps

1. Complete manual owner steps above
2. Verify integration with status endpoint and test script
3. Test end-to-end delivery (fallback-rewrite bead can validate)
4. Consider provisioning complete when server reads both values successfully

---

## ⚠️ Security Notes

- **NEVER** pass bot token as command-line argument
- **NEVER** let token appear in logs, stdout, or session transcript
- **ALWAYS** use stdin input (`token=-`) or file input (`@file.txt`)
- **ALWAYS** verify storage using `bao kv metadata get` (doesn't read value)
- **NEVER** commit actual token values to git

The infrastructure enforces these rules - the code retrieves tokens securely from OpenBao at runtime.

---

**Worker agents cannot complete this bead due to owner-only constraints. Bead released to unassigned status awaiting manual provisioning.**
