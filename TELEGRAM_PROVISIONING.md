# Telegram Bot Provisioning Status

**Last Updated:** 2026-08-29  
**Bead:** aidedeca-73d9fe27  
**Status:** 🔧 REQUIRES HUMAN ACTION

## Current State

✅ **Infrastructure Ready:**
- Telegram integration code is complete (`src/telegram/fallback.py`)
- OpenBao client integration is implemented (`src/openbao/client.py`)
- Provisioning scripts are available (`scripts/provision_telegram_credentials.py`)
- OpenBao AppRole authentication is working

❌ **Credentials Missing:**
- Bot token not yet stored in OpenBao path: `secret/ardenone-cluster/aide-de-camp/telegram_bot_token`
- Chat ID not yet stored in OpenBao path: `secret/ardenone-cluster/aide-de-camp/telegram_chat_id`
- Environment variables not configured

## What Needs To Be Done

This is an **owner-only task** that requires manual human interaction with @BotFather.

### Step 1: Create Telegram Bot via @BotFather

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow the prompts:
   - Choose a name (e.g., "aide-de-camp-notifications")
   - Choose a username (e.g., "adc_notifications_bot")
4. **Copy the bot token** (format: `***REMOVED***`)

⚠️ **SECURITY:** The bot token grants full control over your bot. Keep it secure!

### Step 2: Get Your Chat ID

1. Find your newly created bot in Telegram
2. Send `/start` or any message to the bot
3. Visit this URL in your browser (replace `<BOT_TOKEN>`):
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```
4. Find your `chat.id` in the JSON response (a number, usually 9-10 digits)

### Step 3: Store Credentials in OpenBao

⚠️ **IMPORTANT:** You'll need an OpenBao token with write permissions to `secret/ardenone-cluster/aide-de-camp/`.

#### Option A: Use the Provisioning Script (Recommended)

```bash
cd /home/coding/aide-de-camp

# Set OpenBao token with write permissions
export OPENBAO_TOKEN="<YOUR_WRITE_TOKEN>"

# Run the provisioning script
.venv/bin/python3 scripts/provision_telegram_credentials.py
```

The script will:
✅ Check current state  
✅ Guide you through BotFather steps  
✅ Store bot token securely (never in logs)  
✅ Extract your chat ID automatically  
✅ Store chat ID in OpenBao  
✅ Verify everything works

#### Option B: Manual OpenBao Storage

If you prefer manual setup or the script fails:

```bash
# Set OpenBao address and token
export BAO_ADDR="http://traefik-ardenone-cluster:8200"
export OPENBAO_TOKEN="<YOUR_WRITE_TOKEN>"

# Store bot token (piped via stdin, never in argv)
echo -n "YOUR_BOT_TOKEN" | bao kv put secret/ardenone-cluster/aide-de-camp/telegram_bot_token token=-

# Store chat ID
bao kv put secret/ardenone-cluster/aide-de-camp/telegram_chat_id chat_id=YOUR_CHAT_ID

# Verify (metadata only, no values exposed)
bao kv metadata get secret/ardenone-cluster/aide-de-camp/telegram_bot_token
bao kv metadata get secret/ardenone-cluster/aide-de-camp/telegram_chat_id
```

### Step 4: Configure Environment Variables

Once credentials are stored in OpenBao, configure the aide-de-camp service:

#### Option A: Direct Environment Variables (Simpler)

Edit `~/.config/systemd/user/aide-de-camp.service`:

```ini
[Service]
# ... existing config ...
Environment=ADC_TELEGRAM_CHAT_ID=YOUR_CHAT_ID
# Bot token will be fetched from OpenBao at runtime via OPENBAO_TOKEN
Environment=OPENBAO_TOKEN=<YOUR_READ_TOKEN>
```

#### Option B: OpenBao Integration (Recommended for Production)

The code already supports fetching from OpenBao at runtime. Set:

```ini
[Service]
# ... existing config ...
Environment=TELEGRAM_BOT_TOKEN_PATH=secret/ardenone-cluster/aide-de-camp/telegram_bot_token
Environment=OPENBAO_TOKEN=<YOUR_READ_TOKEN>
Environment=ADC_TELEGRAM_CHAT_ID=YOUR_CHAT_ID
```

### Step 5: Restart and Verify

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

## OpenBao Permissions Required

The provisioning step requires write access to:
- `secret/ardenone-cluster/aide-de-camp/telegram_bot_token`
- `secret/ardenone-cluster/aide-de-camp/telegram_chat_id`

For runtime, the service only needs read access to these paths.

## Security Notes

✅ **Best Practices Followed:**
- Bot token is piped to OpenBao via stdin (never in argv)
- Token never appears in logs, shell history, or session transcript
- OpenBao provides audit trail of access
- Credentials are reference-only in code (paths, not values)

❌ **Never Do:**
- Paste bot token in command-line arguments
- Store token in git repos
- Log token values
- Use `:latest` image tags (unrelated but important)

## What Gets Delivered

Once configured, Telegram receives:

1. **Exception-class results**: Critical/high urgency when no canvas active
2. **Workload summaries**: Periodic async task completion updates  
3. **Bead closure notifications**: Results from NEEDLE watcher

## Troubleshooting

### Bot Token Invalid
**Symptom:** `reachable: false` in status endpoint  
**Fix:** Verify token with `https://api.telegram.org/bot<TOKEN>/getMe`

### Chat ID Not Found
**Symptom:** Messages fail despite `reachable: true`  
**Fix:** Re-run `getUpdates` after sending a new message to bot

### Permission Denied
**Symptom:** OpenBao returns 403 errors  
**Fix:** Use a token with write permissions for provisioning step

## Related Documentation

- **ADR-1:** `docs/notes/adr-1-telegram-bot-decision.md` — Complete decision analysis
- **OpenBao Storage:** `docs/notes/openbao-telegram-token-storage.md` — Storage procedures
- **Provisioning Guide:** `docs/notes/telegram-bot-api-provisioning.md` — BotFather steps
- **Memory:** [[telegram-bot-decision-and-configuration]] — Decision record
- **Memory:** [[telegram-bot-token-openbao-path]] — OpenBao path documentation

## Next Steps After Provisioning

Once credentials are provisioned:

1. ✅ Verify `/api/v1/status/telegram` shows `reachable: true`
2. ✅ Test by triggering an exception-class result with no canvas
3. ✅ Confirm message arrives in Telegram
4. ✅ Close bead `aidedeca-73d9fe27` with confirmation

---

**This is a one-time setup.** Once credentials are stored, the Telegram integration works automatically with no manual intervention required.
