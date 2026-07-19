# First-Failure Tracking — Complete Design (End-to-End)

**Bead:** adc-14la — "Document complete first-failure tracking design"
**Child of:** adc-4vhr (Design first-failure tracking mechanism)
**Synthesizes:** adc-65l3 (data structure) + adc-2duz (storage) + adc-50ld (thread-safety,
**authoritative**) + adc-12bt (detection logic)
**Status:** Authoritative end-to-end design. This is the single document the implementation bead
should implement against. **Where this document disagrees with the earlier synthesis
`notes/adc-4vhr-first-failure-tracking-design.md` (dated 2026-07-08), this document wins** —
that earlier doc predates the adc-50ld / adc-12bt refinements and proposes a structure the
authoritative child designs rejected (see §7, Reconciliation #1).
**Date:** 2026-07-19

> **How to read this.** §1–§4 are the design itself (invariant, flow, state, code). §5 is
> concurrency in one screen. §6 is the edge-case catalog (compressed). §7 is the
> reconciliation table — the places the four child designs (and the old synthesis) disagreed,
> and which answer wins. §8 is the sequenced implementation plan for the next bead. Depth lives
> in the child docs; this document integrates them and resolves their conflicts.

---

## 1. The one invariant

> **Exactly one first-failure notification is emitted per process startup** when the Telegram
> bridge first fails to accept a send. Every subsequent failure within that startup is silent
> (DEBUG + counters only).

Everything else in this design exists to make that invariant hold under concurrency, hold
without log spam, and hold robustly (not by accident). It is a **per-startup** semantic, not
per-deployment — a process restart re-arms detection intentionally (§6.5).

---

## 2. End-to-end flow

```
Process startup (FastAPI lifespan, src/main.py:152)
  │   get_telegram_fallback() → TelegramFallback() built on the serving loop
  │   __init__ sets: _has_logged_first_failure=False, _failure_count=0,
  │                  _first_failure_timestamp=None, _last_failure_timestamp=None,
  │                  _first_failure_lock=asyncio.Lock()
  │   (Separately: lifespan runs check_bridge_available() once → informs _is_reachable.
  │    This is a health-check concern, NOT the first-failure trigger — see adc-12bt §3.2.)
  ▼
send_message() called (the only live entry to the failure path)
  │
  ├─ HTTP 200 ──► _is_reachable = True; return True          (no detection involvement)
  │
  └─ FAILURE (non-2xx | httpx.RequestError | other Exception)   ◄── reactive, AFTER a real failure
        │   await _handle_send_failure(error_context)             (adc-12bt §3: reactive-only)
        │
        ├─ async with self._first_failure_lock:                  (adc-50ld §5)
        │     was_first = self._record_failure_locked(error_context)   # plain def, NO await
        │     │   inside: _is_reachable=False
        │     │           _failure_count += 1
        │     │           _last_failure_timestamp = now
        │     │           if not _has_logged_first_failure:   ← predicate
        │     │               _has_logged_first_failure = True        ← the claim (atomic w/ read)
        │     │               _first_failure_timestamp = now
        │     │               logger.warning(...)                     ← stdlib logging, no yield
        │     │               return True
        │     │           logger.debug("#%d ...", _failure_count)
        │     │           return False
        │  ── lock released; was_first is final ──
        │
        └─ if was_first:
               await _notify_first_failure(error_context)   ← SIDE CHANNEL, outside the lock
                                                            (adc-12bt §7.4; never self.send_message)
  ▼
All later failures: _has_logged_first_failure already True → _record_failure_locked
returns False → no notification, DEBUG + counter only. Suppression is stable for the
rest of the process lifetime (no timer, no window).
  ▼
Process restart → fresh singleton → all fields at defaults → next failure is "first" again.
```

**Two structural facts the whole design rests on (adc-50ld §5.5):**

1. **The decision (`was_first`) is captured inside the lock; the notification I/O runs after
   release.** This is what makes the exactly-once guarantee survive even if the notification is
   slow or fails (§6.6).
2. **`_record_failure_locked` is a plain `def` with no `await`.** Detection must not yield
   between the read of the flag and the write that flips it; the plain-`def` helper makes
   yielding mechanically impossible.

---

## 3. Integrated state model

State lives as **flat instance variables on the `TelegramFallback` singleton** (adc-2duz's
decision: in-memory, per-process, per-startup, **no persistence**), accessed via
`get_telegram_fallback()`.

| Field | Type | Init | Written by | Semantics | Source |
|---|---|---|---|---|---|
| `_has_logged_first_failure` | `bool` | `False` | `_record_failure_locked` | The check-then-act flag. Monotonic `False→True` within a startup; the failure that flips it is "first." | adc-65l3 |
| `_failure_count` | `int` | `0` | `_record_failure_locked` (unconditional `+= 1`) | Total failures since startup. Diagnostic; visible at the status endpoint. | adc-65l3 |
| `_first_failure_timestamp` | `datetime \| None` | `None` | `_record_failure_locked` (set-once) | When the first failure occurred. "Down since X." **New field** (current code lacks it). | adc-65l3 |
| `_last_failure_timestamp` | `datetime \| None` | `None` | `_record_failure_locked` (every failure) | Most recent failure. "Last failed Xs ago." **Rename** of current `_last_failure_logged` (which was updated only on the first failure — a latent bug). | adc-65l3 |
| `_first_failure_lock` | `asyncio.Lock` | `asyncio.Lock()` | (guard) | Serializes the critical section. Instance-level, created in `__init__`. | adc-50ld |

**Explicitly out of scope of the lock:** `_is_reachable` (adc-50ld §5.4). It is written from
*different* paths (send success at `:80`, health-check at `:176/:179`, failure at `:207`), each
a single atomic `STORE_ATTR` with no check-then-act. Coupling those paths to a failure-path
lock would be wrong. The failure-path write of `_is_reachable = False` stays inside
`_record_failure_locked` for locality — that does not pull the *other* writers under the lock.
Rule of thumb: **one lock per logical state object.**

---

## 4. Reference implementation (what the next bead writes)

This is the canonical, reconciled code — the four child designs collapsed into one. Every line
is annotated with the bead that owns the decision.

### 4.1 `__init__` (adc-2duz storage + adc-65l3 fields + adc-50ld lock)

```python
def __init__(self, bridge_url: str | None = None):
    import os
    self.bridge_url = bridge_url or os.getenv(
        "ADC_TELEGRAM_BRIDGE_URL", self.DEFAULT_BRIDGE_URL
    )

    # Reachability — separate logical object; its OTHER writers are NOT under the lock (adc-50ld §5.4)
    self._is_reachable = None  # None=unknown, True=reachable, False=unreachable

    # First-failure record (adc-65l3 fields; adc-2duz: flat instance vars, no separate class)
    self._has_logged_first_failure: bool = False
    self._failure_count: int = 0
    self._first_failure_timestamp: Optional[datetime] = None   # NEW — set-once
    self._last_failure_timestamp: Optional[datetime] = None    # RENAMED from _last_failure_logged

    # Thread-safety (adc-50ld §5.1): one instance lock, await-free critical section
    self._first_failure_lock: asyncio.Lock = asyncio.Lock()
```

### 4.2 `send_message` failure branches become `await`ed (adc-12bt §3.3)

```python
# Inside send_message — three failure branches, all now awaited (was: sync call):
#   non-2xx  → :84    await self._handle_send_failure(error_msg)
#   RequestError → :89   await self._handle_send_failure(error_msg)
#   other Exception → :93 await self._handle_send_failure(error_msg)
```

> ⚠️ **Sharp edge inherited unchanged (§6.3).** All three branches count as failure evidence
> today, including a 4xx (per-message error, not a bridge outage). v1 preserves current
> behavior; classifying 4xx out of the "first failure" trigger is a documented future change.

### 4.3 The reactive handler + locked helper + side-channel notify

```python
async def _handle_send_failure(self, error_context: str = "") -> None:
    """Reactive detection entry point (adc-12bt §3). Called only from send_message failure branches."""
    was_first = False
    async with self._first_failure_lock:                        # adc-50ld §5
        was_first = self._record_failure_locked(error_context)  # plain def; NO await (adc-50ld §5.5)
    # ---- lock released; the detection decision is final below ----
    if was_first:
        await self._notify_first_failure(error_context)         # side-channel I/O (adc-12bt §7.4)


def _record_failure_locked(self, error_context: str) -> bool:
    """Caller MUST hold _first_failure_lock. Sync on purpose — no await (adc-50ld §5.5).

    Returns True iff THIS call performed the _has_logged_first_failure False→True flip,
    i.e. this is the first failure of the startup (adc-12bt §2). "First" = the winner of
    the claim, not a timestamp comparison.
    """
    now = datetime.now()
    self._is_reachable = False                 # failure-path write; locality only (adc-50ld §5.4)
    self._failure_count += 1                   # unconditional, before the flag check (adc-12bt §5.2)
    self._last_failure_timestamp = now         # every failure (adc-65l3 rename)

    if not self._has_logged_first_failure:     # the predicate
        self._has_logged_first_failure = True  # the claim — atomic with the read, under the lock
        self._first_failure_timestamp = now    # set-once (adc-65l3)
        logger.warning(                        # stdlib logging: blocking I/O but does NOT yield (adc-50ld §3)
            f"First Telegram send failure detected at {self.bridge_url}. "
            f"Error: {error_context or 'unknown error'}. "
            f"Subsequent failures will be logged at DEBUG level only."
        )
        return True                            # winner → triggers notification
    logger.debug(
        f"Repeated Telegram send failure #{self._failure_count} "
        f"at {self.bridge_url}. Error: {error_context or 'unknown error'}."
    )
    return False                               # loser → suppressed


async def _notify_first_failure(self, error_context: str) -> None:
    """Deliver the once-per-startup alert over a SIDE CHANNEL (adc-12bt §7.4).

    MUST NOT call self.send_message(...): the bridge just failed for the same reason, and a
    failure here would pollute _failure_count / _last_failure_timestamp with self-failures.
    There is no infinite-recursion risk (the flag is already True, so any re-entry returns
    was_first=False), but the state pollution is real and prevented structurally by using a
    different channel. The exact channel (stderr / structured log sink / separate transport)
    is the notification-implementation bead's concern; v1 may ship this as a thin seam.
    """
    # TODO(notification bead): choose the side channel. Left as a seam here.
    return


def get_bridge_status(self) -> dict:
    """Lock-free read (adc-50ld §5.5 rule 6). Single-field atomic reads; monitoring tolerates
    staleness (Race 5)."""
    return {
        "reachable": self._is_reachable,
        "bridge_url": self.bridge_url,
        "failure_count": self._failure_count,
        "has_logged_first_failure": self._has_logged_first_failure,
        "first_failure_timestamp": self._first_failure_timestamp.isoformat()
            if self._first_failure_timestamp else None,
        "last_failure_timestamp": self._last_failure_timestamp.isoformat()
            if self._last_failure_timestamp else None,
    }


async def reset_first_failure_state(self) -> None:
    """Re-arm detection (adc-65l3 §3; adc-12bt §7.5). Used by future recovery-based reset,
    by any future hot-reload of bridge_url (§6.2), and as the test hook for re-arming.
    Counters are intentionally retained for diagnostics."""
    async with self._first_failure_lock:
        self._has_logged_first_failure = False
        self._first_failure_timestamp = None
        # _failure_count and _last_failure_timestamp intentionally retained
```

---

## 5. Concurrency in one screen

**Why the lock, given the current code is already safe?** CPython asyncio runs one task at a
time and switches only at an `await` that yields. The *current* `_handle_send_failure` is
synchronous and await-free, so it is **already atomic** with respect to every other coroutine
— the duplicate-WARNING race is *latent, not active* (adc-50ld §3). We add the lock as
**defense-in-depth**: the moment a maintainer adds an `await` inside the critical section
(async logging handler, a DB persist, an inline notification), the incidental atomicity
evaporates *silently*. An explicit lock + the plain-`def` helper make correctness survive that
change, at a measured ~0.32 µs of isolated overhead on a path that is dormant today
(adc-50ld §6; adc-4rh3).

**Under N near-simultaneous failures** (e.g. a burst of dispatches hitting a dead bridge),
all N coroutines call `_handle_send_failure`:

- The lock serializes entry to `_record_failure_locked`.
- Coroutine 1 observes `_has_logged_first_failure == False`, flips it, stamps
  `_first_failure_timestamp`, returns `was_first = True` → **it is "the first."**
- Coroutines 2…N enter serially, observe `True`, increment the counter, return `False`.
- Net: **exactly one notification**, `_failure_count == N`, one `_first_failure_timestamp`.

"First" is a **claim-and-set**, not a timestamp comparison — which is what makes it well-defined
under concurrency and exactly-once without deduplication (adc-12bt §2, §4).

**Reviewer-enforced structural rules (adc-50ld §5.5):**
1. One `asyncio.Lock` per instance, created in `__init__`.
2. No `await` inside the critical section — enforced by the plain-`def` helper.
3. I/O runs after release, keyed on `was_first`.
4. Never nest two `async with self._first_failure_lock:` (non-reentrant → deadlock).
5. No lock timeout (await-free section can only be held for microseconds).
6. `get_bridge_status` and all `_is_reachable` writes stay lock-free.

---

## 6. Edge cases (compressed — full detail in adc-12bt §7 / adc-50ld §7)

| # | Case | Resolution |
|---|---|---|
| 6.1 | **Intermittent / flapping bridge** | Exactly one notification for the whole startup, at onset. Ongoing flap severity is still visible via `_failure_count` (climbing) and `_last_failure_timestamp` (recent) on the status endpoint. Re-alerting on each flap is deliberately *not* done; the extension point is recovery-based reset (§6.4), not a time cooldown. |
| 6.2 | **Config change (`ADC_TELEGRAM_BRIDGE_URL`)** | Read once in `__init__`; singleton lives for the process, so a change has no effect until restart — and restart resets the flag, so detection and config stay consistent *by accident of the singleton lifecycle*. **Rule for any future hot-reload:** any path that mutates `bridge_url` on a live instance MUST also call `reset_first_failure_state()`, or the new URL's first failure is suppressed by a stale flag. Prefer recreating the singleton over in-place mutation. |
| 6.3 | **4xx vs 5xx vs transport (sharp edge)** | Today all three failure branches flip the flag identically, so a single 400 (per-message error) can "use up" the one notification and suppress a later real outage. v1 keeps current behavior but documents it at the call site. **Future:** scope "first failure" to reachability-class failures (`httpx.RequestError` + 5xx/429); route 4xx to a per-message DEBUG path that does not touch the flag. |
| 6.4 | **Recovery-based reset (future)** | After N consecutive successes, `_handle_send_success` flips the flag back to `False`, re-arming detection so the *next* degradation is a new "first." Requires adding `_consecutive_success_count` + threshold. Out of scope for v1. |
| 6.5 | **Restart resets everything** | Intentional. First-failure detection is a per-startup diagnostic. Each restart gets a fresh "is the bridge down right now?" window. If the bridge stays down across restarts, each restart correctly logs one WARNING. |
| 6.6 | **Notification failure does not un-set the flag** | The flag is set inside the lock, before release; `_notify_first_failure` runs after. If the notify raises/is cancelled/times out, the flag stays `True` and the next failure is "subsequent" — no re-notify. Desired exactly-once property, with the cost that a lost first notification is gone until reset/restart. Notify-retry, if ever needed, is a notification-layer concern and must NOT un-set the flag. |
| 6.7 | **Concurrent first failures** | The lock makes the claim atomic; exactly one of N wins. Detection defines *winning* (the flip); the lock is the *mechanism*. |
| 6.8 | **Dead constant** | `FAILURE_LOG_COOLDOWN_SECONDS = 300` (`fallback.py:34`) is declared but never referenced — a leftover from a superseded "re-notify after 5 min" idea. **Recommendation: delete it** in the implementation bead (or implement time-based re-notification deliberately, against `_last_failure_timestamp`, and remove this note). Do not leave a dead constant implying behavior the code does not have. |

---

## 7. Reconciliation — where the source designs disagreed, and which wins

This is the synthesis value-add. The four child designs were written over time (adc-65l3 /
adc-2duz on 2026-07-08; adc-50ld / adc-12bt on 2026-07-19), and the earlier synthesis
(`adc-4vhr-first-failure-tracking-design.md`) predates the refinements. Conflicts and winners:

| # | Conflict | Older position | Authoritative position (wins) | Why |
|---|---|---|---|---|
| 1 | **Separate `FirstFailureTracker` class / `src/telegram/first_failure_tracker.py`?** | Old 4vhr synthesis proposed a dedicated tracker class returning log-level *strings* (`'WARNING'`/`'DEBUG'`). | **No.** Flat instance variables on `TelegramFallback`, no new module. | adc-65l3 and adc-2duz (the data-structure and storage child designs, which the old synthesis was summarizing) both specify flat instance vars. The singleton owns the state; a wrapper class adds indirection without encapsulation gain. |
| 2 | **Return value of the locked helper** | Old synthesis: a `'WARNING'`/`'DEBUG'` log-level string. | **A `was_first: bool`.** | adc-12bt §5.2 / adc-50ld §5.5. The helper's job is the claim, returning whether *this call* won. The WARNING log itself stays inside the helper (sync stdlib logging, no yield). The bool drives the post-lock side-channel notify. |
| 3 | **Where does the WARNING log live?** | Implicitly "after the lock returns a level string." | **Inside `_record_failure_locked`** (under the lock); the *side-channel notification* runs after release. | adc-50ld §3: stdlib logging is blocking I/O but does not yield, so it is safe inside the await-free section. The structurally-expensive I/O (`_notify_first_failure`) is what must run after release. Two different things; the old synthesis conflated them. |
| 4 | **`_failure_count` update** | adc-65l3 sketch: `_failure_count = 1` in the first branch, `+= 1` in the else — redundant given the unconditional increment already at the top. | **Unconditional `_failure_count += 1` before the flag check** (one place). | adc-12bt §5.2. Removes the redundant branch-local write; counter is correct regardless of first/subsequent. |
| 5 | **Field naming** | Current code: `_last_failure_logged`, updated *only on the first failure*. | **`_last_failure_timestamp`, updated every failure; ADD `_first_failure_timestamp` (set-once).** | adc-65l3. The current name+behavior conflates "last" with "first." Implementation aligns names when it lands. |
| 6 | **`_is_reachable` under the lock?** | Not addressed consistently. | **No** — its other writers (success, health-check) stay lock-free; only the failure-path write happens to live in the locked helper for locality. | adc-50ld §5.4: one lock per logical state object. |
| 7 | **"Is a lock even needed?"** | Old synthesis: yes, to fix an active race. adc-65l3/adc-2duz: lock to "prevent race conditions." | **Defense-in-depth, not a bug fix.** The current await-free handler is already race-free on a single loop; the race is *latent*. | adc-50ld §3. Correct framing prevents over-engineering and records *why* the lock is cheap to take. |
| 8 | **`asyncio.Lock` rationale** | Earlier adc-50ld draft: "`asyncio.Lock` because atomic operations are impossible in Python." | **`asyncio.Lock` because this state is in-memory, per-process, per-startup** (match the mechanism to where the state lives). | adc-50ld §5.3 corrects the prior draft. GIL atomics, SQLite txns, and `os.replace` all exist; "atomics impossible" is false. Right mechanism for a persisted/cross-worker variant is the SQLite-atomic CAS (§9). |

---

## 8. Implementation plan for the next bead

The implementation bead lands the §4 reference code in `src/telegram/fallback.py`. Sequenced so
each step leaves the tree green.

### 8.1 Steps (in order)

1. **Fields + lock in `__init__`.** Add `_first_failure_timestamp = None`; rename
   `_last_failure_logged` → `_last_failure_timestamp`; add
   `self._first_failure_lock = asyncio.Lock()`. Add `import asyncio` and keep
   `from datetime import datetime`, `from typing import Optional`.
2. **Split the handler.** Rename the body of the current sync `_handle_send_failure` into a new
   plain-`def _record_failure_locked(self, error_context) -> bool` that returns `was_first`,
   applying §4.3 (unconditional counter increment first; set-once first timestamp; return
   `True`/`False`). Make the new `_handle_send_failure` an `async def` that acquires the lock,
   calls the helper, and (if `was_first`) `await`s `_notify_first_failure`.
3. **Add the seam.** Add `async def _notify_first_failure(self, error_context)` as a documented
   no-op/`return` stub (§4.3) — the channel choice is a separate bead.
4. **Update the three call sites** in `send_message` (`:84`, `:89`, `:93`) to
   `await self._handle_send_failure(...)`.
5. **Extend `get_bridge_status`** with `has_logged_first_failure`, `first_failure_timestamp`,
   `last_failure_timestamp` (§4.3). Confirm the status endpoint at `src/main.py:~1469` still
   serializes cleanly.
6. **Add `reset_first_failure_state`** (§4.3) — needed by tests and by §6.2/§6.4 future hooks.
7. **Delete the dead constant** `FAILURE_LOG_COOLDOWN_SECONDS` (§6.8) unless time-based
   re-notification is being implemented in the same bead.

### 8.2 Tests to add (adc-50ld §9 / adc-5xuy §10)

- **Concurrent first-failure:** `asyncio.gather` of N `_handle_send_failure` → exactly one
  WARNING, `_failure_count == N`, single `_first_failure_timestamp`.
- **Counter accuracy:** 100 concurrent calls → `_failure_count == 100`.
- **Structural no-I/O guard (load-bearing):**
  `assert inspect.iscoroutinefunction(fallback._record_failure_locked) is False`.
- **Subsequent suppression:** after the first failure, further failures emit DEBUG, no WARNING,
  and do not change `_first_failure_timestamp`.
- **Reset re-arms:** after `reset_first_failure_state()`, the next failure is "first" again;
  `_failure_count` is unchanged across the reset.
- **Read-doesn't-block:** `get_bridge_status()` returns promptly while a holder sleeps inside
  the (hypothetical) locked section.

### 8.3 Verification

- `.venv/bin/pytest` (the full suite; new tests collected).
- `.venv/bin/ruff check src/telegram/fallback.py`.
- Boot the server (`nohup .venv/bin/python -m uvicorn src.main:app …`) and confirm
  `/api/v1/status/telegram_bridge` returns the new fields; `/health` is still 200.

### 8.4 What NOT to do

- Do **not** create `src/telegram/first_failure_tracker.py` or a `FirstFailureTracker` class
  (Reconciliation #1).
- Do **not** put an `await` inside `_record_failure_locked` — that is the load-bearing
  invariant; the plain `def` enforces it (Reconciliation #2/#3, adc-50ld §5.5 rule 2).
- Do **not** make `_notify_first_failure` call `self.send_message(...)` (§6, adc-12bt §7.4).
- Do **not** pull `_is_reachable`'s other writers under the lock (Reconciliation #6).
- Do **not** add a lock timeout (adc-50ld §5.5 rule 5).

---

## 9. Upgrade path (when the design should change shape)

Switch the record to a **SQLite-atomic compare-and-set** (`UPDATE … SET claimed=1,
first_failure_at=? WHERE id=1 AND claimed=0` + `cur.rowcount == 1`; `aiosqlite` is already a
dependency, `src/session/store.py` already runs `PRAGMA journal_mode=WAL`) — **if any of these
becomes true** (adc-50ld §8):

- State must survive restarts (one first-failure per *deployment*, not per startup).
- adc is scaled to `uvicorn --workers N`.
- A `def` route or threadpool path starts touching this state.

This is a correctness/durability escalation (a SQL round-trip is ~0.1–1 ms vs ~0.32 µs for the
lock), **not** a performance one. Recorded here so it need not be re-derived.

---

## 10. Acceptance-criteria mapping

| Criterion (adc-14la) | Where addressed |
|---|---|
| Complete design documented in this bead body | This document |
| All components integrated coherently | §2 (flow), §3 (state), §4 (code) integrate data-structure + storage + thread-safety + detection |
| Clear implementation guidance for next phase | §8 (sequenced plan, tests, verification, anti-patterns) |
| Depends on adc-12bt completing detection logic design | adc-12bt is **closed**; its detection logic is consumed in §2, §4.3, §6 |

---

## 11. References

- **Data structure:** `notes/adc-65l3-first-failure-state-structure.md` — field set, types,
  reset/recovery semantics.
- **Storage:** `notes/adc-2duz-state-storage-design.md` — flat instance vars on the singleton,
  in-memory per-startup, no persistence; options rejected.
- **Thread-safety (authoritative):** `notes/adc-50ld-thread-safety-approach.md` — the
  `asyncio.Lock` + await-free `_record_failure_locked` pattern, latent-vs-active race framing,
  corrected performance figures.
  - Comprehensive spec: `notes/adc-5xuy-thread-safety-design.md` (concrete diff, reviewer
    checklist). Race catalog: `notes/adc-4ol5-race-conditions.md`. Performance:
    `notes/adc-4rh3.md` (benchmark at `~/scratch/adc-4rh3-lock-bench.py`).
- **Detection logic:** `notes/adc-12bt-first-failure-detection-logic.md` — reactive-only
  timing, claim-and-set definition of "first," win/lose under concurrency, edge cases.
- **Superseded synthesis:** `notes/adc-4vhr-first-failure-tracking-design.md` (2026-07-08) —
  predates adc-50ld/adc-12bt; its `FirstFailureTracker`-class proposal is rejected here (§7 #1).
- **Current code:** `src/telegram/fallback.py` — `_handle_send_failure` at `:198`, the three
  failure branches at `:84/:89/:93`, `__init__` at `:36`, dead `FAILURE_LOG_COOLDOWN_SECONDS`
  at `:34`; singleton wired in `src/main.py:152`; status endpoint at `src/main.py:~1469`.
  Deployment is single-worker (`uvicorn src.main:app`, no `--workers`).
