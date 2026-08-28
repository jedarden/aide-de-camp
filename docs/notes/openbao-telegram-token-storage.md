# OpenBao Telegram Bot Token Storage

## Purpose

This document describes how to securely store the aide-de-camp Telegram bot token in OpenBao, following the project's security requirements.

## OpenBao Path

**Target Path:** `secret/ardenone-cluster/aide-de-camp/telegram_bot_token`

This path is defined in ADR-1 and is specific to aide-de-camp's dedicated Telegram bot.

## Storage Procedure

**CRITICAL SECURITY RULES:**

1. **NEVER** pass the bot token as a command-line argument
2. **NEVER** let the token appear in shell history, logs, or the session transcript
3. **ALWAYS** use stdin input or file descriptors to pass the token to OpenBao
4. The token must travel through pipes or files, never through argv

### Step 1: Authenticate to OpenBao

```bash
# Set the OpenBao address for ardenone-cluster
export BAO_ADDR="http://traefik-ardenone-cluster:8200"

# Login with your token (if not already authenticated)
bao login <method>
```

### Step 2: Store the Bot Token Securely

Use stdin input to pass the token value. The token is piped directly to OpenBao and never appears in the command line:

```bash
# Method 1: Pipe from stdin (recommended)
echo -n "<YOUR_BOT_TOKEN>" | bao kv put secret/ardenone-cluster/aide-de-camp/telegram_bot_token token=-

# Method 2: Use a temporary file (secure)
# Create a temp file with mode 600
install -m 600 /dev/null /tmp/telegram_token.tmp
# Write the token to the file (use your editor)
nano /tmp/telegram_token.tmp  # paste the token, save
# Store from file
bao kv put secret/ardenone-cluster/aide-de-camp/telegram_bot_token @/tmp/telegram_token.tmp
# Shred the temp file
shred -u /tmp/telegram_token.tmp
```

**Both methods ensure the token never appears in `ps`, `.bash_history`, or logs.**

### Step 3: Verify Storage (Without Reading the Value)

Verify the secret exists and check its metadata **without** reading the actual token value:

```bash
# Check metadata only (shows version, created time, NO token value)
bao kv metadata get secret/ardenone-cluster/aide-de-camp/telegram_bot_token
```

Expected output:
```
Key                      Value
---                      -----
created_time             2026-08-28T...
current_version          1
delete_version_after     0s
max_versions             0
oldest_version           0
updated_time             2026-08-28T...
```

### Step 4: Test Retrieval (To a Safe Destination)

To verify the token can be retrieved, read it directly to a file **without** echoing to stdout:

```bash
# Read to file (mode 600), never to terminal
bao kv get -field=token secret/ardenone-cluster/aide-de-camp/telegram_bot_token > /tmp/verify_token.tmp
chmod 600 /tmp/verify_token.tmp

# Use the file to test the Telegram Bot API
curl -s "https://api.telegram.org/bot$(cat /tmp/verify_token.tmp)/getMe" | jq .

# Clean up
shred -u /tmp/verify_token.tmp
```

Expected API response:
```json
{
  "ok": true,
  "result": {
    "id": 123456789,
    "is_bot": true,
    "first_name": "Your Bot Name",
    "username": "your_bot_username",
    "can_join_groups": true,
    "can_read_all_group_messages": false,
    "supports_inline_queries": false
  }
}
```

## What NOT To Do

❌ **NEVER** do this (token appears in argv and logs):
```bash
bao kv put secret/ardenone-cluster/aide-de-camp/telegram_bot_token token=1234567890:ABCDEF...
```

❌ **NEVER** do this (token appears in stdout/transcript):
```bash
bao kv get -field=token secret/ardenone-cluster/aide-de-camp/telegram_bot_token
```

❌ **NEVER** store the token in:
- Git repositories
- Configuration files tracked by git
- Environment variable files (`.env`, `.bashrc`)
- Unencrypted files
- Logs or transcripts

## Kubernetes Integration

Once stored in OpenBao, the token is available to aide-de-camp via:

1. **ExternalSecret** (if using External Secrets Operator)
2. **Environment variable** via systemd service `EnvironmentFile` pointing to an OpenBao-fetched file
3. **Direct OpenBao read** at application startup (if app has OpenBao credentials)

The current implementation uses environment variables (`ADC_TELEGRAM_BOT_TOKEN`), which should be set from an OpenBau-fetched source, not hardcoded.

## Token Rotation

If the bot token is compromised or needs rotation:

1. Generate a new token via BotFather (`/revoke` command)
2. Store the new token using the procedure above
3. Update the environment variable/ExternalSecret
4. Restart aide-de-camp
5. Verify with the `/api/v1/status/telegram` endpoint

## Related Documentation

- ADR-1: `docs/notes/adr-1-telegram-bot-decision.md`
- Provisioning Guide: `docs/notes/telegram-bot-api-provisioning.md`
- OpenBao Agent Access: `/home/coding/CLAUDE.md` (see "OpenBao — Agent Read/Write Access")
