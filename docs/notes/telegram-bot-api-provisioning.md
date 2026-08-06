# Telegram Bot API Provisioning Guide

## Context

Per ADR-1 (2026-07-20), aide-de-camp uses a direct Telegram Bot API integration for fallback notifications. This note documents the one-time human provisioning step required before the Telegram fallback can function.

## Prerequisites

1. A Telegram account
2. Access to the Telegram app or web interface

## Step-by-Step Provisioning

### 1. Create a Bot via BotFather

1. Open Telegram and search for `@BotFather`
2. Send the command `/newbot`
3. Follow the prompts:
   - Choose a name for your bot (e.g., "aide-de-camp-notifications")
   - Choose a username for your bot (e.g., "adc_notifications_bot")
4. BotFather will respond with a bot token like:
   ```
   1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
5. **Save this token securely** — it grants full control over your bot

### 2. Obtain Your Chat ID

1. Start a conversation with your newly created bot
2. Send any message to the bot (e.g., "Hello")
3. Visit the following URL in your browser, replacing `<YOUR_BOT_TOKEN>` with your actual token:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
4. Look for the `message.chat.id` field in the JSON response. It will be a number (e.g., `123456789`) or a string starting with `@` for usernames.

Example response structure:
```json
{
  "ok": true,
  "result": [
    {
      "update_id": 123456789,
      "message": {
        "message_id": 1,
        "from": {
          "id": 987654321,
          "is_bot": false,
          "first_name": "Your Name"
        },
        "chat": {
          "id": 987654321,
          "first_name": "Your Name",
          "type": "private"
        },
        "date": 1699999999,
        "text": "Hello"
      }
    }
  ]
}
```

In this example, your chat ID is `987654321`.

### 3. Configure Environment Variables

Set the following environment variables on the aide-de-camp server:

```bash
export ADC_TELEGRAM_BOT_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
export ADC_TELEGRAM_CHAT_ID="987654321"
```

For persistent configuration (survives server restarts), add these to the server's environment configuration:
- **Systemd service**: Add `Environment=` directives to the service file
- **Shell profile**: Add to `/home/coding/.bashrc` or `/home/coding/.profile`
- **Docker/Podman**: Pass as `-e` flags or in a compose file

### 4. Restart aide-de-camp

After setting the environment variables, restart the aide-de-camp server:

```bash
# From /home/coding/aide-de-camp/
kill -2 $(ps aux | grep "uvicorn src.main" | grep -v grep | awk '{print $2}') 2>/dev/null; true
nohup .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > /tmp/adc.log 2>&1 &
```

### 5. Verify the Integration

1. Check the status endpoint:
   ```bash
   curl -s http://localhost:8000/api/v1/status/telegram | jq
   ```

   Expected response (when configured):
   ```json
   {
     "reachable": true,
     "bot_configured": true,
     "chat_id_configured": true,
     "chat_id": "987654321",
     "last_check_time": "2026-08-05T22:00:00.000000",
     ...
   }
   ```

2. Monitor the startup log for reachability confirmation:
   ```bash
   tail -f /tmp/adc.log | grep -i telegram
   ```

   Expected log line:
   ```
   INFO - Telegram Bot API reachable
   ```

## What Gets Delivered

Once configured, the Telegram integration delivers:

1. **Exception-class results**: Critical/high urgency items when no canvas is active
2. **Workload summaries**: Periodic summaries of async task completion
3. **Bead closure notifications**: Results from NEEDLE bead watcher

## Troubleshooting

### Bot token invalid

- **Symptom**: `/api/v1/status/telegram` returns `reachable: false`
- **Check**: Verify the token is correct and hasn't expired
- **Test**: Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe` in browser

### Chat ID incorrect

- **Symptom**: Messages fail to deliver despite `reachable: true`
- **Check**: Re-run `getUpdates` after sending a new message to the bot
- **Note**: Group/supergroup chat IDs are typically negative numbers

### Bot cannot find user

- **Symptom**: `403 Forbidden` or "chat not found" errors
- **Cause**: User must start the conversation first (send `/start` or any message)
- **Fix**: Open your bot in Telegram and send it a message

## Security Notes

1. **Bot tokens are sensitive credentials** — treat them like passwords
2. **Never commit bot tokens to git** — use environment variables only
3. **Rotate compromised tokens immediately** via BotFather (`/revoke` command)
4. **Limit bot permissions** — avoid granting unnecessary group admin rights

## Related Documentation

- ADR-1: `docs/plan/plan.md#adr-1-2026-07-20-decouple-the-telegram-fallback-surface-from-telegram-claude-bridge`
- Telegram Bot API: https://core.telegram.org/bots/api
- BotFather commands: https://core.telegram.org/bots#botfather
