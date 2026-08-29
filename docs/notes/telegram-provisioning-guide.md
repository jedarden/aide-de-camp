# Telegram Bot Credentials Provisioning Guide

## Current Status (2026-08-29)

As of today, the Telegram bot credentials have **NOT been provisioned**. Both the bot token and chat ID are missing from OpenBao.

## Quick Status Check

To check the current status anytime:

```bash
cd /home/coding/aide-de-camp
export OPENBAO_URL="http://traefik-ardenone-cluster:8200"
export OPENBAO_TOKEN="***REMOVED***"
.venv/bin/python scripts/check_telegram_setup.py
```

## Manual Provisioning Steps

Since interactive provisioning doesn't work in this environment, follow these manual steps:

### Step 1: Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow the prompts:
   - Choose a name (e.g., "aide-de-camp Bot")
   - Choose a username (e.g., `aide_de_camp_bot`)
4. **Copy the bot token** (format: `1234567890:ABCDEF...`)

⚠️ **IMPORTANT**: Keep this token secure - never commit it to git or paste it in logs/chats.

### Step 2: Store the Bot Token in OpenBao

Using the Python script (recommended):

```bash
cd /home/coding/aide-de-camp
export OPENBAO_URL="http://traefik-ardenone-cluster:8200"
export OPENBAO_TOKEN="***REMOVED***"

# This will prompt for your token (input is hidden)
.venv/bin/python scripts/provision_telegram_credentials.py
```

**Or manually using Python:**

```python
import hvac
import getpass

# Connect to OpenBao
client = hvac.Client(
    url="http://traefik-ardenone-cluster:8200",
    token="***REMOVED***",
    verify=False,
)

# Get token securely (input is hidden)
bot_token = getpass.getpass("Paste your bot token: ")

# Store in OpenBao
client.secrets.kv.v2.create_or_update_secret(
    path="ardenone-cluster/aide-de-camp/telegram_bot_token",
    secret={"token": bot_token},
)

print("✅ Bot token stored")
```

### Step 3: Get Your Chat ID

1. **Start a conversation with your bot:**
   - Find your bot in Telegram (search for `@your_bot_username`)
   - Send `/start` or any message

2. **Extract your chat ID using the script:**

```bash
cd /home/coding/aide-de-camp
.venv/bin/python scripts/extract_and_store_chat_id.py
```

**Or manually via Telegram API:**

```bash
# Replace <YOUR_BOT_TOKEN> with your actual token
curl -s "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates" | jq '.result[-1].message.chat.id'
```

### Step 4: Store Your Chat ID in OpenBao

Using Python:

```python
import hvac

client = hvac.Client(
    url="http://traefik-ardenone-cluster:8200",
    token="***REMOVED***",
    verify=False,
)

chat_id = "YOUR_CHAT_ID_HERE"  # From Step 3

client.secrets.kv.v2.create_or_update_secret(
    path="ardenone-cluster/aide-de-camp/telegram_chat_id",
    secret={"chat_id": chat_id},
)

print(f"✅ Chat ID {chat_id} stored")
```

### Step 5: Update Systemd Service

Edit the service file to set the chat ID environment variable:

```bash
# Edit the service file
nano ~/.config/systemd/user/aide-de-camp.service

# Uncomment and update this line:
# Environment=ADC_TELEGRAM_CHAT_ID=<your-chat-id>

# Save and exit, then reload:
systemctl --user daemon-reload
systemctl --user restart aide-de-camp
```

### Step 6: Verify the Integration

```bash
# Check the Telegram status endpoint
curl -s http://localhost:8000/api/v1/status/telegram | jq .

# Expected output includes:
# {
#   "bot_configured": true,
#   "chat_id_configured": true,
#   "reachable": true,
#   ...
# }
```

## Verification

To verify everything is working:

1. **Check credentials are stored:**
   ```bash
   .venv/bin/python scripts/check_telegram_setup.py
   ```

2. **Check service status:**
   ```bash
   systemctl --user status aide-de-camp
   ```

3. **Check Telegram health:**
   ```bash
   curl -s http://localhost:8000/api/v1/status/telegram | jq .
   ```

4. **Test message delivery:**
   - Trigger an exception-class result with no canvas active
   - Or send a test message via the API (if available)

## Troubleshooting

### "Bot token not found in OpenBao"
- Run the check script: `scripts/check_telegram_setup.py`
- Re-run the provisioning script if needed

### "Chat ID not found in OpenBao"
- Make sure you've sent a message to your bot first
- Run `scripts/extract_and_store_chat_id.py`

### "Telegram unreachable" in status endpoint
- Verify the bot token is valid (check with `/getMe` API)
- Check that you've started a conversation with your bot
- Review logs: `journalctl --user -u aide-de-camp -f`

### OpenBao connection errors
- Verify `OPENBAO_URL` and `OPENBAO_TOKEN` are set
- Test connectivity: `curl -s http://traefik-ardenone-cluster:8200/v1/sys/health`

## Security Notes

✅ **DO:**
- Store credentials in OpenBao
- Use stdin/input methods that hide the token
- Verify using metadata (not by reading the value)

❌ **DON'T:**
- Paste tokens in command-line arguments
- Store tokens in git or configuration files
- Log tokens or print them to stdout
- Share tokens in chat/transcripts

## References

- ADR-1: `docs/notes/adr-1-telegram-bot-decision.md`
- OpenBao Storage: `docs/notes/openbao-telegram-token-storage.md`
- Memory: `telegram-bot-decision-and-configuration.md`
