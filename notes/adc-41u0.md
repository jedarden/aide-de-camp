# Thread-Safety Strategy for First-Failure State

**Bead:** adc-41u0 (child of adc-50ld — "Design thread-safety approach for async FastAPI")
**Status:** Design decision — feeds the implementation bead.
**Date:** 2026-07-19

This document is the **definitive locking-strategy decision** for first-failure
state on the `TelegramFallback` singleton. It reconciles the parent bead
(adc-50ld) with the locking research (adc-4783), states exactly which
operations need locking, gives the lock acquisition/release pattern with
pseudo-code, and documents the edge cases (timeout, deadlock, cancellation,
multi-worker).

It does **not** re-derive the race catalog (see
`docs/race-conditions-first-failure-state.md`, adc-4ol5), the data structure
(`docs/first-failure-state-structure.md`, adc-65l3), or the storage location
(`docs/first-failure-state-storage.md`, adc-2duz). It consumes those and
commits to one strategy.

---

## 1. Decision (TL;DR)

**Use a single instance-level `asyncio.Lock` on the `TelegramFallback`
singleton, scoped to the first-failure record fields only.**

- All **mutations** of the first-failure state go through
  `async with self._first_failure_lock:`.
- **Reads** (`get_bridge_status()`) take **no** lock — they are single-field
  atomic reads and tolerate stale-but-consistent values for monitoring.
- The **critical section is minimal and contains no `await`/I/O** — slow work
  (notification send, optional DB persist) happens *after* the lock is
  released, driven by a boolean captured inside it.
- This is the correct and sufficient mechanism **under the deployment
  assumptions in §3** (single-worker, in-memory, per-startup). The documented
  upgrade path (§9) is SQLite atomicity if those assumptions change.

---

## 2. Reconciling the parent bead with the research

The parent bead (adc-50ld) concluded that **"Atomic Operations — NOT
POSSIBLE"** in Python and therefore `asyncio.Lock` is the *only* viable
mechanism. The research (adc-4783) **corrects** that reasoning: it is wrong as
a *general* statement. SQLite transactions (already running under
`PRAGMA journal_mode=WAL` in `src/session/store.py`) **are** atomic operations,
strictly stronger than an in-memory lock for persisted state — they survive
restarts and work across workers, which `asyncio.Lock` does not.

The important nuance for *this* decision:

> The parent's *conclusion* (use `asyncio.Lock`) is correct for the
> first-failure state. The parent's *reason* (atomics are impossible) is not.
> The right reason is: **the first-failure state is in-memory, per-process,
> per-startup by design** (adc-2duz explicitly rejects persistence for runtime
> state). `asyncio.Lock` is the mechanism that matches where this state lives.
> If the state were persisted, we would use SQLite atomicity instead (§9).

This matters because future maintainers must not generalize "we can't do atomic
ops in Python" from this file — that generalization is false and would block a
better design elsewhere (e.g. the real `find_or_create_topic` TOCTOU noted in
adc-4783 §5b, which should be fixed with a unique index + `ON CONFLICT`, not a
lock).

---

## 3. What we are protecting, and the assumptions that make the decision valid

**State under protection** (instance attributes of the `TelegramFallback`
singleton, per adc-65l3):

```python
self._has_logged_first_failure: bool          # the check-then-act flag
self._failure_count: int                       # read-modify-write counter
self._first_failure_timestamp: datetime|None   # set-once timestamp
self._last_failure_logged: datetime|None       # updated every failure
```

**Deployment assumptions (all verified against the codebase):**

1. **Single-worker.** Run command is `uvicorn src.main:app` with no
   `--workers` (CLAUDE.md; adc-4783). → Only event-loop concurrency exists.
   No in-memory lock has to cross a process boundary.
2. **All access paths are `async def`.** `send_message` is async; the failure
   handler is called only from it (`fallback.py:84,89,93`). → No threadpool/
   `def`-route touches this state, so `asyncio.Lock` (not `threading.Lock`)
   is the correct layer.
3. **In-memory + per-startup.** Persistence of runtime state is rejected by
   design (adc-2duz §"Persistence Requirements"). → No durability requirement,
   so an in-memory lock is sufficient; process restart correctly resets the
   state, which is the desired "one WARNING per startup" semantic.
4. **The singleton is created on the serving loop.** `get_telegram_fallback()`
   is first called inside `lifespan` (`main.py:152`), so an `asyncio.Lock()`
   constructed in `__init__` is bound to the serving loop — no import-time/
   wrong-loop hazard.

**If any of assumptions 1–3 stops holding, re-open §9.** This is the contract
the strategy depends on.

---

## 4. Scope of the lock: first-failure fields only (NOT `_is_reachable`)

A point the parent doc missed: `TelegramFallback` carries a **second** piece of
shared mutable state, `_is_reachable`, that is written from *different* paths
than the failure handler:

| Site | What it does |
|---|---|
| `send_message` success (`fallback.py:80`) | `self._is_reachable = True` |
| `check_bridge_available` (`fallback.py:176,179`) | `self._is_reachable = True/False` |
| `_handle_send_failure` (`fallback.py:207`) | `self._is_reachable = False` |

**Decision: do NOT pull `_is_reachable` under the first-failure lock.** Reasons:

- Every `_is_reachable` write is a single-bytecode assignment (`STORE_ATTR`),
  atomic under the GIL. There is no check-then-act on it, so it needs no lock
  for correctness.
- It has a different lifecycle (mutated on success and on health-check, not
  just on failure). Coupling it to the first-failure lock would force the
  success and health-check paths to acquire a failure-path lock for no reason.
- The lock's job is to keep **the first-failure record** internally
  consistent (flag ↔ timestamp ↔ count as one snapshot). `_is_reachable` is not
  part of that record.

**Rule of thumb:** *one lock per logical state object*. The first-failure
record is one object; `_is_reachable` is another (and one that happens to be
safe without a lock). Don't grow the lock's scope to cover state it wasn't
designed for.

---

## 5. Operations requiring locking (the map)

Grounded in the race catalog (adc-4ol5). "Needs lock" = the operation is a
non-atomic compound op (check-then-act, read-modify-write, or multi-field
update) on the protected fields.

| # | Operation | Needs lock? | Why |
|---|---|---|---|
| 1 | First-failure detection: `if not _has_logged_first_failure: set flag + ts + count=1` | ✅ **Yes** | Check-then-act **and** multi-field update (adc-4ol5 Race 1.1, 4.1) |
| 2 | Subsequent-failure increment: `_failure_count += 1; _last_failure_logged = now` | ✅ **Yes** | `+=` is read-modify-write (not atomic; adc-4783 §5a) (Race 2.1) |
| 3 | Manual reset: clear flag/ts (keep count) | ✅ **Yes** | Multi-field update; must serialize vs. in-flight failure handling (Race 5.1) |
| 4 | Decide "am I the first?" → drive notification/persist | ✅ **Yes** for the **decision**; **No** for the I/O itself | The decision is a check-then-act; the I/O must run *outside* the lock (Race 6.1/6.2) |
| 5 | `get_bridge_status()` read of `_failure_count` | ❌ **No** | Single-field atomic read; monitoring tolerates staleness (Race 1.2/2.2) |
| 6 | `_is_reachable = …` writes | ❌ **No** | Single-bytecode atomic; out of scope (§4) |
| 7 | `_failure_count` in a status read while a failure increments it | ❌ **No** | Caller may see N or N+1; both are valid snapshots for monitoring |

**Critical sections (formal list):**

- **CS-1 — first-failure record mutation** in `_handle_send_failure` (the whole
  if/else block).
- **CS-2 — reset** in `reset_first_failure_state` (the field-clearing block).
- **CS-1 and CS-2 use the same lock**, so a reset and a failure handler
  serialize cleanly (resolving Race 5.1).

---

## 6. Lock acquisition / release pattern

### 6.1 Shape

- **One `asyncio.Lock` per instance**, created in `__init__` (→ on the serving
  loop via the lifespan-created singleton, §3 assumption 4).
- Acquire exclusively with **`async with self._first_failure_lock:`** — never
  bare `await lock.acquire()` (which needs a manual `try/finally` and is easy
  to leak on exception).
- **Minimal critical section.** The block contains *only* reads of the
  protected fields, the decision, and writes to the protected fields. **No
  `await`** inside it (no logging at WARNING that could do I/O in a handler, no
  `httpx` call, no DB write). Rationale: a contended `asyncio.Lock` serializes
  every waiter on the event loop; holding it across I/O would stall every
  concurrent request that fails for the duration of that I/O (seconds, for a
  notification HTTP call). This is the single most important rule in the
  pattern.
- **I/O runs outside the lock.** Capture a local `was_first: bool` inside the
  lock, release, *then* do the notification/persist keyed on `was_first`.

### 6.2 Non-reentrancy (the main footgun)

`asyncio.Lock` is **non-reentrant** — acquiring an already-held lock from the
same task deadlocks (verified, adc-4783 appendix). There is no async `RLock`.
If a locked method ever needs to call another locked method, the naive
`async with` in both deadlocks.

**Mitigation — factor out an unlocked helper:**

```python
async def _handle_send_failure(self, error_context: str = "") -> None:
    was_first = False
    async with self._first_failure_lock:           # acquire ONCE
        was_first = self._record_failure_locked(error_context)  # assumes lock held
    # ↓ I/O outside the lock, only for the winner
    if was_first:
        await self._notify_first_failure(error_context)

def _record_failure_locked(self, error_context: str) -> bool:
    """Pre-locked helper. Caller MUST hold self._first_failure_lock.

    Returns True iff this call recorded the *first* failure (so the caller
    knows to fire the notification). Sync on purpose: no `await` in here.
    """
    self._is_reachable = False        # atomic write, not protected by contract (§4)
    self._failure_count += 1
    now = datetime.now(timezone.utc)
    if not self._has_logged_first_failure:
        self._has_logged_first_failure = True
        self._first_failure_timestamp = now
        self._last_failure_logged = now
        logger.warning(
            "First Telegram send failure detected at %s. Error: %s. "
            "Subsequent failures will be logged at DEBUG level only.",
            self.bridge_url, error_context or "unknown error",
        )
        return True
    self._last_failure_logged = now
    logger.debug(
        "Repeated Telegram send failure #%d at %s. Error: %s",
        self._failure_count, self.bridge_url, error_context or "unknown error",
    )
    return False
```

Two consequences of the helper being `def` (not `async def`):

1. It **cannot** contain an `await` — which mechanically enforces the
   "no I/O in the critical section" rule. (Logging is fine; the stdlib logger
   does not `await`.)
2. It can be called only while the lock is held, so it must stay private
   (`_`-prefixed) with a docstring contract.

**Code-review rule:** never nest two `async with self._first_failure_lock:`
blocks in the same call chain. The linter can't catch this; the docstring
contract + review must.

### 6.3 Lock lifetime / creation

Created in `__init__`. This is safe here *because* the singleton is first
constructed on the serving loop (inside `lifespan`, `main.py:152`) — the
constructor does not `await`, so there is no yield between the `is None` check
and the assignment in `get_telegram_fallback()` (the lazy-singleton argument
from adc-4783 §Mechanism 3). On Python ≥3.10 the lock is not loop-bound
anyway, but we get the stronger property for free from the lifespan wiring.

If `TelegramFallback.__init__` ever becomes async (e.g. `await initialize()`),
the lazy singleton becomes unsafe and the lock must move to `app.state`
initialized in `lifespan` (adc-4783 Pattern C). Not needed today.

---

## 7. Pseudo-code: the three entry points

```python
import asyncio, logging
from datetime import datetime, timezone

class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        # …existing init…
        self._has_logged_first_failure = False
        self._failure_count = 0
        self._first_failure_timestamp: datetime | None = None
        self._last_failure_logged: datetime | None = None
        self._first_failure_lock = asyncio.Lock()          # ← the one lock

    # ---- CS-1: failure path (was sync; becomes async) ----
    async def _handle_send_failure(self, error_context: str = "") -> None:
        was_first = False
        async with self._first_failure_lock:
            was_first = self._record_failure_locked(error_context)
        if was_first:
            await self._notify_first_failure(error_context)   # I/O, outside lock

    def _record_failure_locked(self, error_context: str) -> bool:
        """Pre-locked. Caller MUST hold _first_failure_lock. No `await` here."""
        # …as in §6.2…

    async def _notify_first_failure(self, error_context: str) -> None:
        """Fire-and-forget alert. Runs OUTSIDE the lock by construction."""
        # e.g. await self.send_message(ops_chat, first_failure_body)
        ...

    # ---- CS-2: reset path ----
    async def reset_first_failure_state(self) -> None:
        """Manual reset. Clears the flag/ts; keeps the running failure_count."""
        async with self._first_failure_lock:
            self._has_logged_first_failure = False
            self._first_failure_timestamp = None
            # intentionally keep _failure_count and _last_failure_logged

    # ---- read path: NO lock ----
    def get_bridge_status(self) -> dict:
        return {
            "reachable": self._is_reachable,
            "bridge_url": self.bridge_url,
            "failure_count": self._failure_count,                 # atomic read
            "has_logged_first_failure": self._has_logged_first_failure,  # atomic read
        }
```

Call-site change (the implementation bead's job): the three current call sites
of the sync `_handle_send_failure` (`fallback.py:84,89,93`, inside the async
`send_message`) become `await self._handle_send_failure(error_msg)`.

---

## 8. Edge cases

### 8.1 Lock timeout — **do not add one**

We deliberately do **not** wrap acquire in
`asyncio.wait_for(lock.acquire(), timeout=…)`. Reasons:

- The critical section has **no `await`/I/O** (§6.1), so a holder can only be
  preempted between bytecodes for microseconds. A waiter can never wait a
  meaningful duration.
- A timeout introduces a *new* failure mode with no good answer: on timeout,
  do we drop the failure record (losing the count and possibly the "first"
  detection)? Retry? Either choice is worse than the status quo.
- The only way a waiter could genuinely stall is if someone violates the
  "no I/O in the critical section" rule — which the `def` helper (§6.2)
  makes structurally impossible and a concurrent-failures test (§10) catches.

**If a timeout is ever added** (e.g. to defend against a future async logging
handler that does I/O), the on-timeout behavior must be **"log and skip the
state update, return"** — never a partial write.

### 8.2 Deadlock prevention

| Risk | Prevention |
|---|---|
| **Self-reentrancy** (a locked method calls another locked method → deadlock) | Factor out a pre-locked `_locked` helper (§6.2); code-review rule "never nest two `async with` on the same lock." |
| **Lock ordering** (two locks acquired in opposite orders) | N/A — there is **one** lock. Adding a second protected state object → document a global acquisition order before doing it. |
| **`threading.Lock` held across an `await`** (blocks the loop, can deadlock) | N/A — we use `asyncio.Lock`. Boundary rule if a threaded path is ever added: never hold a `threading.Lock` across `await`; use the async lock for any `await`-spanning section (adc-4783 §Mechanism 4). |
| **I/O inside the lock** (serializes all waiters) | Structural prevention via the `def` helper; I/O runs after release (§6.1). |

Single-lock designs have essentially one deadlock mode (self-reentrancy), and
it is prevented by the helper pattern. That is why we resist adding a second
lock (§4) without a documented acquisition order.

### 8.3 Cancellation

- **Cancelled while *waiting* on `lock.acquire()`**: clean. `async with` raises
  `CancelledError` out of the acquire, the body never runs, and the lock is not
  acquired — no corruption, next waiter proceeds (verified, adc-4783 appendix).
- **Cancelled while *holding* the lock** (inside the body): `async with` runs
  `__aexit__` during cancellation unwinding and **releases the lock**. The lock
  is never leaked. Because the body has no `await`, the cancellation window is
  tiny, but correctness does not depend on that.
- **Cancelled during the post-lock I/O** (`_notify_first_failure`): only the
  notification is lost; the first-failure record was already written under the
  lock, so the "one WARNING" guarantee holds (the flag is set; a later failure
  won't re-trigger). Acceptable — the alert is best-effort, the state is
  authoritative.

### 8.4 Exception inside the critical section

`async with` releases the lock on any exception. If a write fails mid-block
(e.g. a malformed `error_context` trips something), the partial mutation
stands and the lock is released. Mitigation: keep the decision read first,
writes last, in the helper — so an exception is most likely *before* any field
is touched. `str(error)[:500]` style truncation belongs in the caller before
the lock, not inside it.

### 8.5 Multi-worker / multi-process boundary

In-memory `asyncio.Lock` does **not** coordinate across uvicorn workers or
after a restart. This is **acceptable** because:

- Deployment is single-worker (§3 assumption 1).
- The semantic is "one WARNING **per startup**" (per-process), so each worker
  legitimately having its own first-failure event is correct, not a bug.

If adc is ever scaled to `--workers N`, each worker independently logs one
first-failure WARNING. If the requirement becomes "one per **deployment**",
switch to the SQLite-atomic pattern in §9.

### 8.6 Lazy-singleton init race

`get_telegram_fallback()` is safe as written because the constructor does not
`await` — no yield point exists between the `is None` check and the assignment
(adc-4783 §Mechanism 3). It would become unsafe the moment `__init__` does
async work; then move construction into `lifespan` (§6.3).

### 8.7 Reset vs. in-flight failure (adc-4ol5 Race 5.1)

Both `reset_first_failure_state` (CS-2) and `_handle_send_failure` (CS-1) take
the same lock, so they serialize: either the reset completes first (next
failure is treated as a fresh "first") or the failure completes first (then
reset clears it). No partial/contradictory state. No special handling needed —
the single shared lock resolves it.

### 8.8 Test isolation

The singleton retains state across tests. Tests should either (a) instantiate a
fresh `TelegramFallback()` directly (the unit tests in adc-50ld/adc-4ol5 do
this), or (b) call `await reset_first_failure_state()` between cases. Mutating
`_has_logged_first_failure` directly from a test bypasses the lock — *practically*
safe in a single-loop test with no concurrency, but use the reset method to
keep the contract honest.

---

## 9. Upgrade path: when to switch to SQLite atomicity

If any of these becomes true, replace the in-memory lock with the SQLite-atomic
pattern (adc-4783 §5b; `aiosqlite` is already a dependency — no new deps):

- State must **survive restarts** (one first-failure per deployment, not per
  startup).
- adc is scaled to **multiple workers**.
- A `def` route or threadpool path starts touching this state.

The atomic pattern is a single SQL statement as the check-and-set, using
`rowcount` as the CAS result — no Python lock, correct under all three
concurrency layers:

```python
async with aiosqlite.connect(db_path) as db:
    cur = await db.execute(
        "UPDATE first_failure SET claimed=1, first_failure_at=? "
        "WHERE id=1 AND claimed=0",
        (now_iso,),
    )
    await db.commit()
    was_first = cur.rowcount == 1   # exactly one writer wins
```

This is **not** needed today; it is recorded so the migration is obvious when
the assumptions change, and so nobody re-derives the parent's "atomics are
impossible" error.

---

## 10. Verification approach (for the implementation bead)

- **Concurrent first-failure test**: `asyncio.gather` of N calls to
  `_handle_send_failure` → assert exactly one WARNING, `failure_count == N`,
  and a single `_first_failure_timestamp`. (Lock correctness.)
- **Counter accuracy test**: 100 concurrent calls → `failure_count == 100`
  (no lost updates from `+=`).
- **No-I/O-in-lock guard**: assert the locked helper is a plain `def` (no
  `await` possible). Structural.
- **Reset-vs-failure test**: `gather(reset, handle_failure)` → state is one of
  the two consistent outcomes, never contradictory.
- **Read-doesn't-block test**: while one task holds the lock (briefly, via a
  test-only seam), a `get_bridge_status()` call returns promptly — proving
  reads are lock-free.

---

## 11. Summary

- **Mechanism:** one instance-level `asyncio.Lock` on the `TelegramFallback`
  singleton.
- **Scope:** the first-failure record fields only — explicitly **not**
  `_is_reachable` (§4).
- **Lock:** all mutations (CS-1 failure path, CS-2 reset) via
  `async with`; reads (`get_bridge_status`) lock-free.
- **Pattern:** minimal critical section, no `await` inside (enforced by a `def`
  helper), I/O after release, non-reentrancy handled by the helper.
- **Edge cases:** no timeout (would add a failure mode for no benefit);
  deadlock prevented by single-lock + helper pattern; cancellation safe under
  `async with`; multi-worker is out of scope today with a documented upgrade to
  SQLite atomics.
- **Why `asyncio.Lock` and not "atomics":** because of *where this state lives*
  (in-memory, per-startup), not because atomics are impossible (they aren't —
  adc-4783 corrects the parent on this).

---

## References

- **Research:** `notes/adc-4783.md` — locking-mechanism catalog + the correction
  to "atomics are impossible."
- **Parent:** `notes/adc-50ld-thread-safety-approach.md` — race identification
  and the (correct-conclusion / wrong-reason) recommendation this doc refines.
- **Race catalog:** `docs/race-conditions-first-failure-state.md` (adc-4ol5).
- **Data structure:** `docs/first-failure-state-structure.md` (adc-65l3).
- **Storage location:** `docs/first-failure-state-storage.md` (adc-2duz).
- **Current code:** `src/telegram/fallback.py` (`_handle_send_failure` sync,
  3 call sites in async `send_message`; singleton created in `lifespan` at
  `src/main.py:152`).
