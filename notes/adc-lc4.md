# adc-lc4 — Telegram fallback: hardcoded unreachable bridge URL, no env override

**Bead:** adc-lc4 (umbrella, P2 bug)
**Depends on:** adc-44u — "Add bridge reachability warning and status indicator" (**closed**)
**Status:** Umbrella verification complete. All four acceptance criteria met by closed
sub-beads; this note records the umbrella-closer's independent contract/deployment
verification.
**Date:** 2026-07-20

> **Scope of this umbrella bead.** adc-lc4 is an `umbrella`-labelled tracking bead. The
> implementation was decomposed across closed sub-beads; this file is the umbrella closer's
> verification pass against the **real** `telegram-claude-bridge` source and the **live**
> `ardenone-cluster` deployment, plus the required commit artifact for bead closure.

---

## 1. Acceptance-criteria → completion map

| # | Acceptance criterion | Where | Verified |
|---|----------------------|-------|----------|
| 1 | Bridge URL configurable via env; unit test covers override | `src/telegram/fallback.py:46-48` reads `ADC_TELEGRAM_BRIDGE_URL`; default `DEFAULT_BRIDGE_URL` (line 33) | `tests/test_telegram_fallback.py` (`test_env_var_override`, `test_constructor_overrides_env`, `test_get_telegram_fallback_respects_env_var`) — 49 tests pass |
| 2 | Actual reachable route documented in README config table | `README.md:144` + reachability note at `README.md:149-157` | See §3 — DNS caveat re-confirmed live 2026-07-20 |
| 3 | Contract verified/corrected against real bridge; findings in bead comments | `src/telegram/fallback.py:127-137` (`/send`, payload) | See §2 — re-verified against Go source `telegram-claude-bridge` + `br comment` on adc-lc4 |
| 4 | Unreachable bridge = visible warning (WARNING + API field), not per-send debug noise | Startup probe `src/main.py:150-162`; first-failure WARNING `fallback.py:400`; status API `main.py:1477` `/api/v1/status/telegram_bridge` | All three channels confirmed |

## 2. Contract re-verification against the real source (independent of sub-bead adc-4jt)

The `telegram-claude-bridge` Go repo at `/home/coding/telegram-claude-bridge` is the bridge.
Its mesh-exposed HTTP server is `cmd/proxy/main.go` (the `telegram-proxy` binary). Route
registration (lines 46-63):

```
mux.HandleFunc("/health", handleHealth(poller))          // GET
mux.HandleFunc("/send",   handleSend(sender))            // POST  ← fallback.py hits this
... /edit, /send_photo, /send_document, /create_topic, /answer_callback, /file/{file_id} ...
```

**`POST /send`** decodes `contract.SendRequest` (`internal/contract/types.go:138-146`):

```go
type SendRequest struct {
    ChatID            int64           `json:"chat_id"`
    ThreadID          *int64          `json:"thread_id,omitempty"`
    Text              string          `json:"text"`
    ParseMode         *string         `json:"parse_mode,omitempty"`
    ReplyToMessageID  *int64          `json:"reply_to_message_id,omitempty"`
    ReplyMarkup       *InlineKeyboard `json:"reply_markup,omitempty"`
}
```

`fallback.py` sends `{"chat_id": int, "text": str, "parse_mode": "HTML"}` — a valid subset
of the required + optional fields. `parse_mode` is `*string` (nullable); sending a bare
string decodes fine. **No mismatch.** The original task's worry about `/send_message` and
"surface registration" is resolved: the real path is `/send` (not `/send_message`), and
there is no surface-registration endpoint — `register_surface()` is correctly a no-op stub
(`fallback.py:218-236`) with a documenting WARNING.

**`GET /health`** is registered (line 47); `check_bridge_available()` (`fallback.py:238-251`)
probes it and treats `200` as reachable. ✅

**Conclusion:** the request contract in `fallback.py` is correct. No code change needed.

## 3. Reachable route from this host — re-confirmed live 2026-07-20

The README documents `https://telegram-proxy-telegram-bridge-ardenone-cluster-ts.ardenone.com:8444`
as the Traefik `vpn`-entrypoint route to `svc telegram-proxy:8080` (ns `telegram-bridge`).
Live verification today:

- **Deployment is healthy.** `kubectl --server=http://traefik-ardenone-cluster:8001 get svc,pod -n telegram-bridge`:
  `service/telegram-proxy` ClusterIP `10.43.2.5:8080` (age 105d); pod
  `telegram-proxy-66c9f848f6-rxzr7` `1/1 Running` (2d5h). (A stale ReplicaSet pod
  `telegram-proxy-9699b54fc-btgb6` sits in `ImagePullBackOff` — old image, not the live one.)
- **DNS still does not resolve from this host.** `getent hosts` / `socket.getaddrinfo` for the
  `*-ts.ardenone.com` name both fail, identical to the 2026-07-19 finding in README:157.
  `tailscale status` shows no node named for telegram-proxy — there is no per-service
  Tailscale name (matches the infra convention: one Tailscale entrypoint per cluster, via Traefik).
- **Implication.** "The actual reachable URL from this host" does not exist as a *resolvable*
  name today. This is an infrastructure/split-DNS gap, not a code defect: the code is
  configurable (env override), fails visibly (startup WARNING + first-failure WARNING +
  `/api/v1/status/telegram_bridge` → `reachable: false`), and the README documents the
  limitation honestly with a dated caveat. Closing this fully requires creating the DNS
  record / mesh-DNS mapping — out of scope for this code bead.

## 4. Visibility channels (acceptance criterion 4) — all present

1. **Startup WARNING** — `src/main.py:150-162`: lifespan calls `check_bridge_available()` at
   boot; unreachable → `logger.warning("Telegram bridge unreachable at ... Telegram fallback
   will not be available.")`.
2. **First-send-failure WARNING** — `fallback.py:400` (adc-4las/adc-15u0): exactly one
   per-startup WARNING carrying error type + message; later repeats rate-limited to one
   DEBUG summary per `ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS` (default 300s), with
   per-failure-type dedup so a *new* failure type is never swallowed by the cooldown.
3. **Status API field** — `GET /api/v1/status/telegram_bridge` (`main.py:1477`) returns
   `{reachable, bridge_url, chat_id, last_check_time, failure_count, has_logged_first_failure,
   first/last_failure_timestamp, failure_log_interval_seconds, failures_since_last_log,
   seen_failure_types, distinct_failure_types}`.

## 5. Sub-beads closed under this umbrella

- adc-44u — bridge reachability warning + status indicator
- adc-4jt — verify telegram-claude-bridge API contract
- adc-4las — WARNING log with error context
- adc-47l2 — rate-limit repeated send-failure logs
- adc-4hvx — expose `last_check_time` + `chat_id` in bridge status (API endpoint)
- adc-15u0 — per-failure-type dedup for bridge failure logs

## 6. Tests

`./venv/bin/pytest tests/test_telegram_fallback.py tests/test_telegram_bridge_status.py -q`
→ **49 passed**. Env-override, constructor-override, default, and singleton (`get_telegram_fallback`)
resolution are all covered.
