# ADR-1 Telegram Bot Decision: Dedicated Bot

**Decision Date:** 2026-08-28  
**Bead:** aidedeca-baeeb0a8  
**Status:** DECISION MADE - Create dedicated bot

## Decision

**Create a dedicated Telegram bot for aide-de-camp via BotFather.**

Do NOT reuse the telegram-claude-bridge or telegram-relay bot token.

## Rationale

### 1. Infrastructure Independence
- telegram-relay exists but is NOT currently deployed/running (confirmed: not accessible on localhost:8080)
- Deploying and maintaining telegram-relay adds infrastructure complexity
- A dedicated bot token requires zero additional services - just an environment variable

### 2. ADR-1 Alignment
The ADR-1 decision (accepted 2026-07-22) explicitly states:
> "Give aide-de-camp its **own** direct, minimal Telegram Bot API integration"

The stateless proxy variant (telegram-relay reuse) is mentioned as an optional alternative "if reusing its bot-token holder is **preferred**" - but the primary and recommended approach is a dedicated bot.

### 3. Operational Simplicity
- **Dedicated bot**: One-time BotFather provisioning → bot token in OpenBao → env var → done
- **Reused proxy**: Deploy telegram-relay → monitor health → maintain service → dependency on another service

The dedicated bot approach has fewer moving parts and lower operational overhead.

### 4. Architectural Decoupling
- aide-de-camp owns its Telegram integration end-to-end
- No dependency on telegram-relay deployment status or API contract changes
- Failures are isolated to aide-de-camp's own bot token

## Implementation Path

Per ADR-1 implementing steps:

1. **Provisioning (one-time human step):**
   - Create bot via @BotFather on Telegram
   - Capture bot token and chat_id
   - Store bot token in OpenBao: `secret/ardenone-cluster/aide-de-camp/telegram_bot_token`
   - Set `ADC_TELEGRAM_CHAT_ID` in aide-de-camp environment

2. **Code changes:**
   - Rewrite `src/telegram/fallback.py` against Telegram Bot API (direct `sendMessage`/`editMessageText`)
   - Remove stubbed methods: `send_exception()`, `send_workload_summary()`, `register_surface()`
   - Remove session→Telegram binding from surfaces model

3. **Verification:**
   - Force exception-class result with no canvas connected
   - Confirm message arrives in Telegram
   - Remove ⚠ NON-FUNCTIONAL annotations from plan.md and README.md

## Why Not telegram-relay?

While telegram-relay (`/home/coding/telegram-relay`) provides the exact stateless proxy pattern that ADR-1 permits as an alternative:

1. **Not deployed**: Would need to be deployed to k8s or run as a service
2. **Additional dependency**: aide-de-camp would depend on telegram-relay being healthy
3. **No operational advantage**: Bot token management is the same either way (both use OpenBao)
4. **ADR-1 primary path**: The dedicated bot is the recommended approach; proxy is the alternative

telegram-relay remains available for other services that want a shared Telegram relay, but aide-de-camp's critical fallback notifications should not depend on it.

## Related Documentation

- ADR-1: `docs/plan/plan.md#adr-1-2026-07-20-decouple-the-telegram-fallback-surface-from-telegram-claude-bridge`
- Telegram provisioning guide: `docs/notes/telegram-bot-api-provisioning.md`
- telegram-relay: `/home/coding/telegram-relay/README.md`
