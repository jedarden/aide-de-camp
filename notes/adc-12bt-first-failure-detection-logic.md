# First-Failure Detection Logic

**Bead:** adc-12bt — "Design first-failure detection logic"
**Child of:** adc-4vhr (Design first-failure tracking mechanism)
**Depends on:** adc-50ld (thread-safety approach — **closed**), and transitively on
adc-65l3 (data structure), adc-2duz (storage), adc-5xuy (comprehensive thread-safety spec)
**Status:** Design-only. Answers this bead's four acceptance criteria:
*(1) detection logic documented with pseudo-code/flow, (2) how "first" is determined,
(3) why subsequent failures are ignored, (4) edge cases (intermittent failures, config changes).*
**Date:** 2026-07-19

> **Scope boundary.** This document owns the *detection logic* — the predicate that decides
> "is this the first failure," *when* that predicate is evaluated, and the edge cases around it.
> It deliberately **does not** re-derive the thread-safety mechanism (adc-50ld), the storage
> location (adc-2duz), or the field set (adc-65l3); it consumes them. Where the detection logic
> intersects concurrency, it defers to the `asyncio.Lock` + await-free `_record_failure_locked`
> pattern already decided in adc-50ld/adc-5xuy.

---

## 1. What "detection" means here

There is one operational invariant (inherited from adc-4vhr / adc-50ld §2):

> **Exactly one notification is emitted per process startup** when the Telegram bridge first
> fails; every subsequent failure is silent (DEBUG + counters only).

"Detection" is the logic that decides, for a given failure, whether it is **the one** that
triggers the notification. Three questions define it:

1. **The predicate** — what condition makes a failure "the first"? (§2)
2. **The timing** — when in the send lifecycle is the predicate evaluated? Before send, after
   failure, or both? (§3)
3. **The win/lose semantics** — under concurrency, which of N simultaneous failures is "first"? (§4)

Then §5 covers the check logic itself (pseudo-code + flow), §6 explains why losers are ignored,
and §7 is the edge-case catalog.

---

## 2. How "first" is determined

"First" is **not** a timestamp comparison and **not** "the earliest failure." It is defined
operationally as:

> A failure is "the first" **iff it is the one that performs the `_has_logged_first_failure`
> False→True transition** inside the locked critical section.

The flag is the single source of truth (per adc-65l3). It starts `False` at startup
(`TelegramFallback.__init__`) and is monotonic within a process lifetime: it can only go
`False → True`, never back, except via explicit reset (§7.5) or process restart. Therefore:

- The **first** failure is the unique failure that observes `_has_logged_first_failure == False`
  at the moment it holds the lock, sets it to `True`, stamps `_first_failure_timestamp`, and
  returns `was_first = True`.
- Every **subsequent** failure observes `_has_logged_first_failure == True`, increments
  `_failure_count`, updates `_last_failure_timestamp`, and returns `was_first = False`.

This is a **claim-and-set**, not a comparison. "First" = "the winner of the claim." That is what
makes it well-defined under concurrency (§4) and what makes the notification exactly-once without
needing to deduplicate by time.

---

## 3. When to check — before send, after failure, or both?

**Decision: detection is reactive — evaluated only after a send has actually failed. No pre-send
check on the send path.**

### 3.1 The three places a check *could* go

| Moment | What it would mean | Verdict |
|---|---|---|
| **Before send** (proactive reachability probe inline) | Call `check_bridge_available()` (or a lightweight HEAD) before every `send_message`, and treat a failed probe as "first failure." | ❌ **Rejected** as the detection trigger |
| **After failure** (reactive) | Evaluate the predicate inside `_handle_send_failure`, which is reached only from `send_message`'s failure branches. | ✅ **Chosen** |
| **Both** | Probe-then-send, plus fall back to reactive on actual send failure. | ❌ **Rejected** — inherits both costs for no detection benefit |

### 3.2 Why reactive-only (after failure)

1. **A pre-send probe is not authoritative about send failure (TOCTOU).** A probe can succeed and
   the immediately-following send still fail (the bridge flaps in the gap), or the probe can fail
   and the send succeed (transient blip during probe). Using a probe as the "first failure" trigger
   would fire notifications for failures that never actually happened, and miss failures that did.
   The invariant is about *send* failures; only an actual send failure is evidence of one.

2. **It adds a network round trip to the hot path for no gain.** `check_bridge_available()` does a
   full `httpx` GET to `/health` (5 s timeout). Running it before every `send_message` would double
   the per-send latency and add a new failure surface. adc-50ld §6 establishes the send path is
   dormant today; adding a pre-probe would manufacture exactly the kind of contention and latency
   the thread-safety design worked to avoid.

3. **The "proactive" job is already done by a separate channel.** `src/main.py:150-162` already
   runs `check_bridge_available()` once during FastAPI `lifespan` startup and logs a WARNING if the
   bridge is unreachable, and `GET /api/v1/status/telegram_bridge` (`main.py:1469`) exposes
   `get_bridge_status()` for polling. Reachability *probing* is a health-check concern that feeds
   `_is_reachable`; first-failure *detection* is a send-path concern that feeds the flag. Conflating
   them would couple two different state objects — exactly what adc-50ld §5.4 warns against
   ("one lock per logical state object"; here, one *signal* per logical state object).

> **So the lifecycle is:** startup probe (separate channel, informs `_is_reachable`) → sends
> proceed → **on the first send that actually fails**, `_handle_send_failure` runs the predicate
> reactively → notify-once → all later failures suppressed. The predicate is evaluated at exactly
> one point: inside `_handle_send_failure`, after a real failure has occurred.

### 3.3 What "after failure" includes

`send_message` (`src/telegram/fallback.py:64-94`) reaches `_handle_send_failure` from **three**
branches, and the predicate treats all three as failure evidence today:

1. Non-2xx HTTP response → `:84` (`status {code} - {text}`)
2. `httpx.RequestError` (connection refused, timeout, DNS, etc.) → `:89`
3. Any other `Exception` → `:93`

> ⚠️ This breadth is a detection-logic sharp edge — see §7.3. All three currently count as "first
> failure," but only branch 2 (and arguably transport-level 5xx in branch 1) actually indicates the
> *bridge* is down. Branch 1 with a 4xx is a per-message error, not a bridge outage.

---

## 4. Win/lose under concurrency (which of N failures is "first")

When N sends fail near-simultaneously (e.g. a burst of dispatches all hitting a dead bridge), all N
coroutines call `_handle_send_failure`. The predicate + the lock together guarantee exactly one
winner:

- The lock (`asyncio.Lock`, per adc-50ld §5) serializes entry to `_record_failure_locked`.
- The first coroutine to enter observes `_has_logged_first_failure == False`, performs the
  False→True transition, and returns `was_first = True`. **It is "the first."**
- Coroutines 2…N enter serially afterward, observe `True`, and return `was_first = False`.
- Net result: **exactly one notification**, `_failure_count == N` (the counter is a
  read-modify-write also under the lock — adc-50ld Race 2), one `_first_failure_timestamp`.

This is the detection-logic reason the check-then-act must be inside the lock: "first" is defined
by *who flips the flag*, and the flip must be atomic with the read that tested it. (The thread-safety
mechanics — why `asyncio.Lock`, why the await-free `def` helper — are adc-50ld's contribution; this
bead only asserts that detection *requires* the check-and-flip to be a single atomic step.)

---

## 5. The check logic — flow and pseudo-code

### 5.1 Detection flow

```
send_message() attempted
        │
   ┌────┴───── actual send result ─────┐
   │                                    │
success (HTTP 200)                  failure (non-2xx / RequestError / Exception)
   │                                    │
_is_reachable = True                  call await _handle_send_failure(error_context)
return True                                  │
                                   ┌────────┴───── _first_failure_lock ────────────┐
                                   │  (await-free plain def: _record_failure_locked) │
                                   │                                                 │
                                   │  failure_count += 1                             │
                                   │  last_failure_timestamp = now                   │
                                   │  is_reachable = False                           │
                                   │                                                 │
                                   │  if has_logged_first_failure == False:          │
                                   │      has_logged_first_failure = True   ◄── claim│
                                   │      first_failure_timestamp = now             │
                                   │      was_first = True                          │
                                   │  else:                                          │
                                   │      was_first = False                         │
                                   └────────────┬────────────────────────────────────┘
                                                │ (lock released; was_first captured)
                                   ┌────────────┴────────────────────────────────────┐
                                   │  if was_first:                                  │
                                   │      await _notify_first_failure(error_context) │ ◄── I/O outside lock
                                   │  else:                                          │   (side-channel; §7.4)
                                   │      logger.debug(...)                         │
                                   └─────────────────────────────────────────────────┘
```

Two structural rules from adc-50ld §5.5 that the detection logic depends on:

- **The decision (`was_first`) is captured inside the lock; the notification I/O runs after
  release.** This is what lets the exactly-one guarantee survive even if the notification itself is
  slow or fails (§7.6).
- **`_record_failure_locked` is a plain `def` with no `await`.** Detection must not yield between
  the read of the flag and the write that flips it; the plain-`def` helper makes that mechanically
  impossible (adc-50ld §3).

### 5.2 Pseudo-code

Consistent with the sketch in adc-5xuy §5 and adc-50ld §5.5, focused on the *logic*:

```python
async def _handle_send_failure(self, error_context: str = "") -> None:
    """Reactive detection entry point. Called only from send_message failure branches."""
    was_first = False
    async with self._first_failure_lock:                       # adc-50ld
        was_first = self._record_failure_locked(error_context) # plain def; no await
    # ---- lock released; detection decision is final below ----
    if was_first:
        await self._notify_first_failure(error_context)        # side-channel I/O (§7.4)
    else:
        logger.debug(
            f"Repeated Telegram send failure #{self._failure_count} "
            f"at {self.bridge_url}. Error: {error_context or 'unknown error'}."
        )


def _record_failure_locked(self, error_context: str) -> bool:
    """Caller MUST hold _first_failure_lock. Sync on purpose — no await.

    Returns True iff THIS call is the first failure of the startup
    (i.e. this call performed the has_logged_first_failure False→True flip).
    """
    now = datetime.now()
    self._is_reachable = False
    self._failure_count += 1
    self._last_failure_timestamp = now              # adc-65l3 name (current code: _last_failure_logged)

    if not self._has_logged_first_failure:          # the predicate
        self._has_logged_first_failure = True       # the claim (atomic w/ the read, under lock)
        self._first_failure_timestamp = now         # set-once (field to be added — adc-65l3)
        logger.warning(
            f"First Telegram send failure detected at {self.bridge_url}. "
            f"Error: {error_context if error_context else 'unknown error'}. "
            f"Subsequent failures will be logged at DEBUG level only."
        )
        return True                                 # winner → triggers notification
    return False                                    # loser → suppressed
```

> **Naming note.** Current code (`fallback.py:43`) calls the last-failure field
> `_last_failure_logged` and updates it only on the first failure. adc-65l3 standardizes it to
> `_last_failure_timestamp`, updated on **every** failure, and adds the set-once
> `_first_failure_timestamp`. The pseudo-code above uses the adc-65l3 names. The detection logic
> does not depend on the rename; implementation should align names when it lands.

---

## 6. Why subsequent failures are ignored

A failure that returns `was_first = False` triggers **no notification** and logs only at DEBUG.
Three reasons, in order of importance:

1. **The core invariant is "notify once."** Re-alerting on every failure when the bridge is down
   would spam the operator — the exact problem adc-4vhr exists to solve. The flag makes
   suppression the default for every failure after the first.

2. **The flag is monotonic within a startup.** Once `_has_logged_first_failure == True`, no code
   path flips it back except explicit reset (§7.5) or process restart. So "subsequent" is a stable
   property: every failure from the second onward, for the rest of the process lifetime, is
   suppressed by construction — there is no timer to expire, no window to slide.

3. **Diagnostics are not lost — only the noisy alert is.** Subsequent failures still:
   - increment `_failure_count` (visible at `/api/v1/status/telegram_bridge`),
   - update `_last_failure_timestamp` ("how long has it been down?"),
   - emit a DEBUG line with the failure number and error.
   An operator who wants the ongoing-failure picture reads `get_bridge_status()` or DEBUG logs;
   the notification channel is reserved for the one "it just went down" signal.

> The design choice is deliberately **not** "notify once, then never again even if it recovers and
> breaks." That stricter behavior is a consequence of the current once-per-startup semantic; §7.1
> and §7.5 cover the recovery/intermittent case and the reset that re-arms detection.

---

## 7. Edge cases

### 7.1 Intermittent / flapping failures

**Behavior under this design:** a bridge that fails, recovers, fails, recovers… produces
**exactly one notification** — at the first failure — for the entire process lifetime. Flapping
does not re-trigger.

- **Why that's acceptable:** the operator gets the "bridge is unhealthy" signal once, at onset.
  Ongoing flap severity is still measurable via `_failure_count` (climbing) and
  `_last_failure_timestamp` (recent) on the status endpoint.
- **Why it might not be enough:** if the bridge flaps for hours after recovering between blips, the
  operator has no second alert to tell them "it degraded *again*."
- **The intended extension point is recovery-based reset, not a time cooldown.** adc-65l3 §3
  specifies a future `_handle_send_success` that, after N consecutive successes, flips
  `_has_logged_first_failure` back to `False` — re-arming detection so the *next* degradation is a
  new "first." That recovers the per-outage signal without time-based re-alerting. See §7.5.

> ⚠️ **Reconcile the dormant constant.** `src/telegram/fallback.py:34` declares
> `FAILURE_LOG_COOLDOWN_SECONDS = 300` but it is **never referenced** anywhere (verified — only the
> declaration exists). It is a leftover from an earlier "re-notify after a 5-minute cooldown" idea
> that was superseded by the once-per-startup semantic (adc-65l3/adc-50ld). **Recommendation:**
> either delete it, or — if time-based re-notification is ever actually wanted — implement it
> deliberately against `_last_failure_timestamp` and remove this note. Do not leave a dead constant
> implying behavior the code does not have.

### 7.2 Config changes (`ADC_TELEGRAM_BRIDGE_URL`)

**Behavior today:** `bridge_url` is read from the env var exactly once, in `TelegramFallback.__init__`
(`fallback.py:36-40`). The singleton is created during `lifespan` (`main.py:152`) and lives for the
whole process. So a config change has no effect until the process restarts — and a restart resets
the flag anyway, so detection and config stay consistent **by accident of the singleton lifecycle**.

- **The latent risk:** if hot-reload of `bridge_url` is ever added (e.g. SIGHUP re-reads the env
  var and mutates the live singleton's `self.bridge_url`), the first-failure flag would become
  **stale relative to the new target** — the new URL's first failure would be suppressed because
  the flag is still `True` from the old URL's failure.
- **Detection rule for that future world:** detection state is logically keyed to the pair
  *(instance ↔ bridge_url)*. Any code path that changes `bridge_url` on a live instance **MUST**
  also call `reset_first_failure_state()` (§7.5), so the new URL gets its own first-failure window.
  Equivalently: prefer recreating the singleton over mutating `bridge_url` in place.

### 7.3 Failure classification — 4xx vs 5xx vs transport (sharp edge)

Today all three failure branches (§3.3) flip the flag identically. That means a **single 400 Bad
Request** (a malformed message — a per-message application error, not a bridge outage) would "use
up" the one notification, and a subsequent genuine bridge-down event (503 / connection refused)
would be **suppressed**.

- This is almost certainly not the intent: the invariant is about *bridge reachability*, and a 4xx
  says the bridge is up but rejected one payload.
- **Recommendation (detection-logic level):** scope "first failure" to **reachability-class**
  failures only — `httpx.RequestError` (transport) and 5xx/429 responses — and route 4xx to a
  per-message DEBUG path that does **not** touch `_has_logged_first_failure` or
  `_first_failure_timestamp` (it may still bump `_failure_count` under the lock, or not, per a
  separate decision). This keeps the one notification reserved for actual outages.
- This also aligns `_is_reachable`: today a 4xx sets `_is_reachable = False`, which is misleading
  for the same reason. Classifying before the handler fixes both.
- If the broad behavior is intentionally accepted for now, it must at least be **documented at the
  call site** so a future maintainer doesn't assume "first failure" means "first outage."

### 7.4 Self-failure / notification recursion guard

`_notify_first_failure` must deliver the alert over a **side channel** — it must **not** call
`self.send_message(...)`. Reasons:

- If the notify attempt fails and routes back through `_handle_send_failure`, it would bump
  `_failure_count` and overwrite `_last_failure_timestamp` with the *notification's own* failure,
  polluting the failure record with self-failures.
- There is **no infinite recursion** risk: by the time `_notify_first_failure` runs, the flag is
  already `True`, so any failure it triggers returns `was_first = False` and does not re-notify.
  But the state pollution is real and worth preventing structurally.
- Additionally, notifying over the *same bridge that just went down* is self-defeating — the
  notification would fail for the same reason the original send did.

**Rule:** `_notify_first_failure` writes to a channel independent of the Telegram bridge — e.g.
stderr / a structured log sink / a different transport. The exact channel is out of scope for this
bead (it belongs to the notification-implementation bead), but the detection logic **requires** the
side-channel property and asserts it here.

### 7.5 Reset re-arms detection

`reset_first_failure_state()` (future, adc-65l3) flips `_has_logged_first_failure` back to `False`
(under the same lock) and clears `_first_failure_timestamp`, while **keeping** `_failure_count` and
`_last_failure_timestamp` for diagnostics. From the detection logic's perspective, reset means
**"re-zero the predicate"**: the next failure to claim the flag is "first" again and triggers a new
notification. This is the mechanism behind both the recovery-based reset (§7.1) and the
config-change requirement (§7.2). It is also the test hook for re-arming detection in unit tests.

### 7.6 Notification failure does not un-set the flag

The flag is set to `True` **inside** the lock, before release; `_notify_first_failure` runs
**after** release. Therefore if the notification raises, is cancelled, or its I/O times out:

- The flag stays `True`. The next failure is "subsequent" (`was_first = False`) and will **not**
  re-attempt the notification.
- This is the desired exactly-once property, but it has a cost: **a lost first notification is gone
  until reset or restart.** There is no retry of the notify itself built into detection. (This
  matches adc-50ld §7: "Only the best-effort alert is lost; the record was already written, so the
  one-WARNING guarantee holds.") If notify-retry is ever required, it is a notification-layer
  concern, not a detection-layer one — and it must not be implemented by un-setting the flag.

### 7.7 Concurrent first failures

Covered by adc-50ld (Race 1) and §4 here: the lock makes the claim atomic; exactly one of N
concurrent failures wins. Detection's only contribution is the *definition* of winning (the
False→True flip); the *mechanism* is the lock.

---

## 8. Acceptance criteria — mapping

| Criterion | Where addressed |
|---|---|
| Detection logic documented with clear pseudo-code or flow | §5 (flow §5.1, pseudo-code §5.2) |
| Explains how "first" is determined | §2 (claim-and-set on the flag) + §4 (win/lose) |
| Explains why subsequent failures are ignored | §6 (three reasons) |
| Considers edge cases (intermittent failures, config changes) | §7.1 (intermittent), §7.2 (config), §7.3–§7.7 |
| Depends on adc-50ld completing thread-safety design | adc-50ld is **closed**; this design consumes its lock + `_record_failure_locked` pattern (§5) |

---

## 9. References

- **Thread-safety (direct dependency):** `notes/adc-50ld-thread-safety-approach.md` — the
  `asyncio.Lock` + await-free `_record_failure_locked` pattern this detection logic runs inside.
- **Comprehensive spec:** `notes/adc-5xuy-thread-safety-design.md` — the `_record_failure_locked` /
  `_notify_first_failure` sketch (§5) this doc's pseudo-code aligns with.
- **Data structure:** `notes/adc-65l3-first-failure-state-structure.md` — the field set
  (`_has_logged_first_failure`, `_failure_count`, `_first_failure_timestamp`,
  `_last_failure_timestamp`) and the reset/recovery semantics referenced in §2, §7.1, §7.5.
- **Storage:** `notes/adc-2duz-state-storage-design.md` — instance vars on the singleton,
  in-memory per-startup (why restart resets the flag, §7.2).
- **Current code:** `src/telegram/fallback.py` — `_handle_send_failure` at `:198`, the three
  failure branches at `:84/:89/:93`, dormant `FAILURE_LOG_COOLDOWN_SECONDS` at `:34`, singleton
  wiring in `src/main.py:152` and status endpoint at `main.py:1469`.
- **Downstream consumer:** bead adc-14la ("Document complete first-failure tracking design") will
  synthesize this detection logic with the data-structure, storage, and thread-safety designs into
  the end-to-end design for the implementation bead.
