# Thread-Safety Design: Concurrent First-Failure State

**Bead:** adc-5xuy (child of adc-50ld — "Design thread-safety approach for async FastAPI")
**Status:** Comprehensive design — the authoritative synthesis for the implementation bead.
**Date:** 2026-07-19
**Scope:** The `TelegramFallback` singleton's first-failure state, as it exists in `src/telegram/fallback.py` today.

---

## 0. How to read this document

This is the **single, authoritative design** for making first-failure state
thread-/coroutine-safe. It synthesizes four prior beads into one implementable
specification:

| Section | Synthesizes | Source |
|---|---|---|
| §2 Race conditions | the race catalog | `notes/adc-4ol5-race-conditions.md` (adc-4ol5) |
| §3 Mechanisms considered | the locking-mechanism evaluation | `notes/adc-4783.md` (adc-4783) |
| §4–§6 Chosen strategy + implementation | the locking decision | `notes/adc-41u0.md` (adc-41u0) |
| §7 Performance | the measured cost analysis | `notes/adc-4rh3.md` (adc-4rh3) |

It also **reconciles and corrects** the parent bead
(`notes/adc-50ld-thread-safety-approach.md`, adc-50ld), which reaches the right
conclusion (use `asyncio.Lock`) but for a wrong reason (it claims "atomic
operations are NOT POSSIBLE" in Python) and carries performance figures that are
overstated by ~3,000–4,000×. **Where this document disagrees with adc-50ld, this
document is authoritative.** The race catalog and design intent in adc-50ld/adc-4ol5
remain correct; only the "atomics are impossible" claim and the inflated latency
figures are superseded.

If you read only one section, read **§11 (Developer cheat sheet)**.

---

## 1. Problem & context

### 1.1 What we are protecting

`TelegramFallback` is a process-wide singleton (`get_telegram_fallback()`,
first instantiated inside the FastAPI `lifespan` at `src/main.py:152`). It tracks
the health of the `telegram-claude-bridge` and, in particular, guarantees an
operational invariant:

> **Exactly one WARNING is logged per process startup** when the bridge first
> fails. All subsequent failures log at DEBUG.

Honoring that invariant requires protecting four instance attributes that
together form the **first-failure record** (per `docs/first-failure-state-structure.md`,
adc-65l3, and the storage decision in `docs/first-failure-state-storage.md`,
adc-2duz):

```python
self._has_logged_first_failure: bool            # the check-then-act flag
self._failure_count: int                         # read-modify-write counter
self._first_failure_timestamp: datetime | None   # set-once timestamp  (to be added)
self._last_failure_logged: datetime | None       # updated every failure
```

A fifth attribute, `_is_reachable`, is **shared mutable state too — but it is out
of scope for this lock** (see §4.2).

### 1.2 The current code is not safe

`src/telegram/fallback.py:198` — the failure handler is synchronous and unguarded:

```python
def _handle_send_failure(self, error_context: str = ""):
    self._is_reachable = False
    self._failure_count += 1                       # ❌ read-modify-write, not atomic
    now = datetime.now()
    if not self._has_logged_first_failure:         # ❌ check…
        logger.warning(...)
        self._has_logged_first_failure = True      # ❌ …then act — not atomic with the check
        self._last_failure_logged = now
    else:
        logger.debug(...)
```

It is called from three sites inside the async `send_message` (`fallback.py:84`,
`:89`, `:93`). Today that call is a plain `self._handle_send_failure(...)`, which
works only because nothing else is mutating the record concurrently — an
assumption that breaks the moment two requests fail in overlapping coroutines.

### 1.3 The deployment contract (why an in-memory lock is the right *category*)

The choice of mechanism depends entirely on **where the state lives and who
touches it**. For this state, four facts hold (all verified against the codebase):

1. **Single worker.** The run command is `uvicorn src.main:app` with no
   `--workers` (CLAUDE.md). Only event-loop concurrency exists; no in-memory lock
   has to cross a process boundary.
2. **All access paths are `async def`.** `send_message` is async; the failure
   handler is reached only from it. No `def` route, threadpool function, or
   background task touches this state. So the concurrency layer is the event
   loop, not OS threads.
3. **In-memory + per-startup by design.** Persistence of *runtime* state is
   explicitly rejected (adc-2duz). A process restart correctly resets the record
   — which is exactly the "one WARNING per startup" semantic we want.
4. **The singleton is created on the serving loop** (inside `lifespan`), so an
   `asyncio.Lock()` built in `__init__` is bound to the serving loop — no
   import-time / wrong-loop hazard.

> **The contract.** This design is valid as long as assumptions 1–3 hold. If any
> stops holding, re-open §9 (upgrade to SQLite atomicity). The contract is the
> thing future maintainers must check before assuming this design still applies.

---

## 2. Race conditions (synthesized from adc-4ol5)

Six races arise when concurrent coroutines enter `_handle_send_failure`. They
range from a hard violation of the one-WARNING invariant to cosmetic staleness.

| # | Race | Pattern | Severity | What breaks |
|---|---|---|---|---|
| 1 | **Duplicate first-failure WARNINGs** | check-then-act on `_has_logged_first_failure` | **High** | The core invariant; log spam when the bridge is down |
| 2 | **Lost counter updates** | read-modify-write on `_failure_count += 1` | Medium | Inaccurate failure count; misleading metrics |
| 3 | **First-failure timestamp overwrite** | set-once via the racy flag check (a consequence of #1) | Low | First-failure timing wrong by a few ms |
| 4 | **Last-failure timestamp lost update** | non-deterministic write ordering | Low | "Last failure" timestamp may not be the true last |
| 5 | **Read-during-write on status check** | `get_bridge_status` reads mid-mutation | Low | Transient torn snapshot for monitoring |
| 6 | **Reachability toggle** | concurrent success (`_is_reachable = True`) and failure (`= False`) | Medium | Bridge reported unreachable right after a success |

### 2.1 The decisive races

**Race 1** is the one that matters most. A cold start with burst traffic is the
canonical trigger: N requests fail at once, all read `_has_logged_first_failure`
as `False` before any sets it, and all log WARNING. Result: N WARNINGs for one
logical "first" failure — the invariant is broken.

```
T0  Req A: check _has_logged_first_failure → False
T1  Req B: check _has_logged_first_failure → False   ❌ both see False
T2  Req A: logger.warning(...); set flag = True
T3  Req B: logger.warning(...)                        ❌ DUPLICATE WARNING
```

**Race 2** is the classic lost update: `_failure_count += 1` is three bytecodes
(LOAD, ADD, STORE). Two coroutines can both read `0`, both compute `1`, both
store `1` — so two failures are recorded as one.

### 2.2 Atomic vs. non-atomic — the real dividing line

The fix for every race above is "make the operation atomic." The question is how.
The deciding factor is the **shape** of the operation, not the field:

| Operation shape | Example | Atomic? |
|---|---|---|
| Single assignment of an immutable | `self._has_logged_first_failure = True` | ✅ atomic (single bytecode, GIL-protected) |
| Read of a single field | `self._failure_count` in `get_bridge_status` | ✅ atomic |
| **Check-then-act** | `if not flag: flag = True` | ❌ **not atomic** (Race 1, 3) |
| **Read-modify-write** | `_failure_count += 1` | ❌ **not atomic** (Race 2) |
| **Multi-field consistent read** | a status dict assembled field-by-field | ❌ not atomic (Race 5) |

> The GIL makes *single bytecodes* atomic but does **not** make compound
> sequences atomic. That is precisely why a plain boolean flag is safe to *write*
> without a lock, but the check-then-set on it is not. (Full table and a
> reproducibility note in adc-4783 §5a.)

---

## 3. Mechanisms considered (synthesized from adc-4783)

### 3.1 The decision principle: match the mechanism to where the state lives

"Async FastAPI" is not one execution model. Three layers can run concurrently,
and the right lock depends on which layer your state is shared across:

| Layer | Concurrency source | `asyncio.Lock` works? |
|---|---|---|
| **Event loop** (cooperative) | coroutines yield at every `await` | ✅ native use |
| **Threadpool** (`def` routes, `run_in_threadpool`, sync libs) | preemptive OS threads | ❌ need `threading.Lock` or atomics |
| **Processes** (`uvicorn --workers N`) | separate interpreters | ❌ need DB/Redis/file atomics |

For the first-failure record only the **event-loop** layer exists (§1.3). That
makes `asyncio.Lock` the correct *category*. The mechanisms below were evaluated
against that, and against the durability requirement (none, per design).

### 3.2 Mechanism evaluation

| Mechanism | Verdict for this state | Why |
|---|---|---|
| **`asyncio.Lock`** (instance) | ✅ **CHOSEN** | Native to async, non-blocking, sub-µs when uncontended, groups the multi-field record into one consistent critical section. Correct under the §1.3 contract. |
| `asyncio` family (`Semaphore`/`Event`/`Queue`/`Condition`) | ❌ wrong shape | These model different problems (bounded concurrency, signaling, producer/consumer). Don't build a mutex out of them. (The codebase already uses `Semaphore` correctly in `src/context/warmer.py` for a different job.) |
| `threading.Lock` | ❌ wrong layer | A blocking acquire stalls the event loop; can't be held across `await`. Only legitimate inside genuinely threaded code paths — and there are none here. |
| Module-level / `app.state` lock | ⚠️ unnecessary | Correct when state is genuinely module-global, but this state is owned by the singleton instance. An instance lock is sufficient and better encapsulated. |
| Queue-based serialization | ❌ overkill | A background task + queue lifecycle for one boolean flag. |
| **SQLite atomicity** | ⚠️ **upgrade path (§9), not today** | The right tool *if* the state were persisted — `UPDATE … WHERE claimed=0` + `rowcount` is a real CAS, correct across workers and restarts. Rejected only because the state is in-memory by design. |

### 3.3 The correction to "atomics are NOT POSSIBLE"

adc-50ld (Option 4) declares atomic operations impossible in Python and concludes
that `asyncio.Lock` is the *only* viable mechanism. That reasoning is **wrong as
a general statement**, and the correction matters for future maintainers:

- **GIL-level atomics** exist for single-bytecode operations (§2.2).
- **SQLite transactions** are atomic operations — strictly stronger than an
  in-memory lock for persisted state (they survive restarts and span workers).
  `src/session/store.py` already runs `PRAGMA journal_mode=WAL`.
- **File-level atomics** (`os.replace` temp-then-rename) exist for on-disk state.

The right mental model is **pick the mechanism that matches where the state
lives** (the matrix in adc-4783), not "always reach for `asyncio.Lock`."

> **Why this nuance matters here.** For the first-failure record, the parent's
> *conclusion* (use `asyncio.Lock`) is correct — but the *reason* is "because
> this state is in-memory, per-process, per-startup," **not** "because atomics
> are impossible." Recording the right reason prevents a future maintainer from
> mis-generalizing and blocking a better design elsewhere (e.g. the real
> `find_or_create_topic` TOCTOU noted in adc-4783 §5b, which should be fixed with
> a unique index + `INSERT … ON CONFLICT DO NOTHING … RETURNING`, not a lock).

---

## 4. The chosen strategy (synthesized from adc-41u0)

### 4.1 Decision

> **Use a single instance-level `asyncio.Lock` on the `TelegramFallback`
> singleton, scoped to the first-failure record fields only.**

- All **mutations** of the record go through `async with self._first_failure_lock:`.
- **Reads** (`get_bridge_status`) take **no** lock — single-field atomic reads,
  and monitoring tolerates stale-but-consistent values.
- The **critical section contains no `await`/I/O** — slow work runs *after* the
  lock is released, keyed on a boolean captured inside it.

This is correct and sufficient under the §1.3 contract; SQLite atomicity is the
documented upgrade (§9) if that contract changes.

### 4.2 Scope: the first-failure record only — explicitly NOT `_is_reachable`

`_is_reachable` is written from *different* paths than the failure handler:

| Site | What it does |
|---|---|
| `send_message` success (`fallback.py:80`) | `_is_reachable = True` |
| `check_bridge_available` (`fallback.py:176,179`) | `_is_reachable = True/False` |
| `_handle_send_failure` (`fallback.py:207`) | `_is_reachable = False` |

**Decision: do not pull `_is_reachable` under the first-failure lock.**

- Every `_is_reachable` write is a single-bytecode `STORE_ATTR` — atomic under the
  GIL, with no check-then-act, so it needs no lock for correctness.
- It has a different lifecycle (mutated on success and on health-check, not just
  failure). Coupling it to a failure-path lock would force the success and
  health-check paths to acquire a failure lock for no reason.
- The lock's job is to keep **the first-failure record** internally consistent
  (flag ↔ timestamp ↔ count as one snapshot). `_is_reachable` is not part of that
  record.

> **Rule of thumb: one lock per logical state object.** Don't grow a lock's scope
> to cover state it wasn't designed for. (Race 6, the reachability toggle, is
> therefore accepted as benign — single-bytecode writes, last-write-wins is fine
> for a health signal.)

### 4.3 Operations map — what needs the lock

| # | Operation | Lock? | Why (ties to §2) |
|---|---|---|---|
| 1 | First-failure detection: `if not flag: set flag + ts + count=1` | ✅ Yes | Check-then-act **and** multi-field update (Race 1, 3) |
| 2 | Subsequent-failure increment: `count += 1; last_ts = now` | ✅ Yes | Read-modify-write (Race 2) |
| 3 | Manual reset: clear flag/ts (keep count) | ✅ Yes | Multi-field update; must serialize vs. in-flight failure (Race 5 variant) |
| 4 | Decide "am I the first?" → drive notification | ✅ for the **decision**; ❌ for the I/O | The decision is check-then-act; the I/O must run *outside* the lock |
| 5 | `get_bridge_status()` read of `failure_count` | ❌ No | Single-field atomic read; monitoring tolerates staleness (Race 5) |
| 6 | `_is_reachable = …` writes | ❌ No | Single-bytecode atomic; out of scope (§4.2) |

This yields exactly **two critical sections**, both on the same lock:

- **CS-1** — failure record mutation in `_handle_send_failure` (the if/else block).
- **CS-2** — reset in `reset_first_failure_state` (the field-clearing block).

Because CS-1 and CS-2 share one lock, a reset and a failure handler serialize
cleanly — resolving the reset-vs-in-flight race with no special handling.

---

## 5. Lock acquisition pattern

### 5.1 Shape

- **One `asyncio.Lock` per instance**, created in `__init__`. Safe because the
  singleton is first constructed on the serving loop (§1.3, assumption 4) and the
  constructor does not `await`.
- Acquire exclusively with **`async with self._first_failure_lock:`** — never bare
  `await lock.acquire()` (needs a manual `try/finally`, easy to leak).
- **Minimal critical section.** The block contains *only* reads of the protected
  fields, the decision, and writes to them. **No `await` inside** — no logging
  handler that could do I/O, no `httpx`, no DB write.
- **I/O runs outside the lock.** Capture a local `was_first: bool` inside, release,
  *then* do notification/persist keyed on `was_first`.

> **The single most important rule in this design:** a contended `asyncio.Lock`
> serializes every waiter on the event loop. Holding it across I/O would stall
> every concurrent failing request for the duration of that I/O — seconds, for a
> notification HTTP call. The critical section must be pure CPU.

### 5.2 Non-reentrancy — the main footgun, and the structural fix

`asyncio.Lock` is **non-reentrant** — acquiring an already-held lock from the same
task deadlocks (verified on CPython 3.12, adc-4783 appendix). There is no async
`RLock`. If a locked method ever calls another locked method, naive `async with`
in both deadlocks.

**Fix — factor the critical section into a pre-locked plain `def` helper:**

```python
async def _handle_send_failure(self, error_context: str = "") -> None:
    was_first = False
    async with self._first_failure_lock:                       # acquire ONCE
        was_first = self._record_failure_locked(error_context)  # assumes lock held
    if was_first:                                               # I/O outside the lock
        await self._notify_first_failure(error_context)

def _record_failure_locked(self, error_context: str) -> bool:
    """Pre-locked helper. Caller MUST hold self._first_failure_lock.

    Returns True iff this call recorded the *first* failure (so the caller
    knows to fire the notification). Sync on purpose: no `await` in here.
    """
    self._is_reachable = False          # atomic write; out of scope (§4.2)
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

Making the helper a plain `def` (not `async def`) does two things at once:

1. It **cannot contain an `await`** — mechanically enforcing the "no I/O in the
   critical section" rule of §5.1. (stdlib `logger` does not `await`.)
2. It can be called only while the lock is held, so it must stay private
   (`_`-prefixed) with a docstring contract.

> **Code-review rule:** never nest two `async with self._first_failure_lock:`
> blocks in the same call chain. A linter won't catch it; the docstring contract
> + review must.

---

## 6. Implementation guide

This is the concrete diff against `src/telegram/fallback.py`. It is what the
implementation bead should produce.

### 6.1 `__init__` — add the lock

```python
# src/telegram/fallback.py
import asyncio                                     # ← add
from datetime import datetime, timezone            # ← timezone for UTC stamps

class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        import os
        self.bridge_url = bridge_url or os.getenv(
            "ADC_TELEGRAM_BRIDGE_URL", self.DEFAULT_BRIDGE_URL
        )
        self._is_reachable = None
        self._last_failure_logged = None
        self._failure_count = 0
        self._has_logged_first_failure = False
        self._first_failure_timestamp: datetime | None = None     # ← add (Race 3)
        self._first_failure_lock = asyncio.Lock()                 # ← the one lock
```

### 6.2 The three entry points

```python
    # ---- CS-1: failure path (was sync; becomes async) ----
    async def _handle_send_failure(self, error_context: str = "") -> None:
        """Handle a send failure. Thread-safe first-failure detection.

        All record mutations occur under _first_failure_lock. The notification
        (I/O) runs after release, only for the winner.
        """
        was_first = False
        async with self._first_failure_lock:
            was_first = self._record_failure_locked(error_context)
        if was_first:
            await self._notify_first_failure(error_context)

    def _record_failure_locked(self, error_context: str) -> bool:
        """Pre-locked. Caller MUST hold _first_failure_lock. No `await` here."""
        # … body as in §5.2 …

    async def _notify_first_failure(self, error_context: str) -> None:
        """Fire-and-forget ops alert. Runs OUTSIDE the lock by construction."""
        # e.g. await self.send_message(ops_chat, first_failure_body)
        ...

    # ---- CS-2: reset path ----
    async def reset_first_failure_state(self) -> None:
        """Manual reset. Clears flag/ts; keeps the running failure_count."""
        async with self._first_failure_lock:
            self._has_logged_first_failure = False
            self._first_failure_timestamp = None
            # intentionally keep _failure_count and _last_failure_logged

    # ---- read path: NO lock ----
    def get_bridge_status(self) -> dict:
        return {
            "reachable": self._is_reachable,
            "bridge_url": self.bridge_url,
            "failure_count": self._failure_count,                         # atomic read
            "has_logged_first_failure": self._has_logged_first_failure,   # atomic read
        }
```

### 6.3 Call-site change

The three current call sites of the sync handler (`fallback.py:84`, `:89`,
`:93`, inside async `send_message`) become awaited:

```python
# before
self._handle_send_failure(error_msg)
# after
await self._handle_send_failure(error_msg)
```

No other call sites exist (verified: `send_result` calls `send_message`, and
`send_exception`/`send_workload_summary` are no-op stubs).

### 6.4 Reviewer's checklist

When reviewing the implementation, confirm:

- [ ] Exactly one `asyncio.Lock` instance, created in `__init__`.
- [ ] `_record_failure_locked` is a plain `def` (assertable: `inspect.iscoroutinefunction(...) is False`).
- [ ] No `await` appears between `async with self._first_failure_lock:` and its
      body's end — all I/O is after the block.
- [ ] No second `async with self._first_failure_lock:` nested inside the first
      (would deadlock).
- [ ] `_is_reachable` writes are **not** under the lock.
- [ ] `get_bridge_status` does **not** acquire the lock.
- [ ] All three call sites of `_handle_send_failure` use `await`.

---

## 7. Performance (synthesized from adc-4rh3)

### 7.1 Measured cost — and a correction to adc-50ld

Performance was measured on CPython 3.12.12 on this box (benchmark:
`~/scratch/adc-4rh3-lock-bench.py`, full listing in adc-4rh3 §8). Logging was
raised to CRITICAL to isolate the lock's cost from log-handler I/O.

| Operation | Measured cost |
|---|---|
| Uncontended `async with lock:` (empty body) | **~0.47 µs** |
| Lock-free status read (`get_bridge_status`) | **~0.09 µs** |
| Realistic section, single coroutine, **with lock** | **~0.92 µs** |
| Realistic section, single coroutine, **no lock** | **~0.60 µs** |
| **Isolated lock overhead** (with − without) | **~0.32 µs** |

**Contended throughput is flat from 2 to 128 concurrent contenders** (~1.0 µs/op,
`failure_count` exactly correct in every run). Because the section has no
`await`, a holder runs the whole section without yielding; waiters queue and are
served at the speed of the work (~0.6 µs each). Doubling contenders does not
double latency.

> **Correction.** adc-50ld and adc-4ol5 carry "~1–5 ms per failure" and
> "100 concurrent failures = 200 ms total" figures. Measurement shows the lock
> itself costs ~0.32 µs and 100 serialized failures complete in **~60–90 µs**.
> The prior figures are **overstated by ~3,000–4,000×**. They conflated lock
> acquisition cost (sub-µs) with logging-I/O latency (ms, only if a handler does
> I/O). **Do not propagate the inflated figures.**

### 7.2 The protected path is dormant today

The decisive performance argument is grounded in the code, not a microbenchmark:

- `_handle_send_failure` is reachable only through `send_message`.
- `send_message` has **no live callers** in the dispatch path. `send_result` (the
  only internal caller) has no callers itself; `send_exception` and
  `send_workload_summary` are no-op stubs; the watcher's `_send_to_telegram`
  (`watcher/daemon.py:215`) logs "mapping not implemented" and returns.
- The only live callers of the singleton are a startup health-check (writes
  `_is_reachable`, not the protected fields) and the read-only status endpoint
  (takes no lock).

**The lock's critical section is executed zero times per request today.** Even
once wired in, it fires only on the **error path** of a **secondary** channel.
You cannot contend a lock on a code path that isn't called.

### 7.3 The one real performance risk: I/O inside the critical section

The lock's acquisition cost is irrelevant. The only way this strategy develops a
real performance problem is if the critical section stops being sub-microsecond —
i.e. if it starts doing I/O while holding the lock. The dangerous mutations:

- Calling `_notify_first_failure` (a 10 s-timeout HTTP send) **inside** the
  `async with` block → every concurrent failing request serializes behind one
  10-second timeout. This is the genuine "200 ms → 10 s × N" disaster the prior
  docs' intuition gestured at — just mis-attributed to the lock itself.
- Adding a DB persist inside the section.
- Wiring in an async logging handler that `await`s inside `logger.warning`.

**Mitigation (already in the design):** §5.2 makes the in-section helper a plain
`def`, so I/O is **structurally impossible** — a type-system-enforced boundary,
not a convention.

### 7.4 Performance budget

The denominator is a `/dispatch` round-trip: multiple LLM calls, each on the
order of **seconds**. Anything that is a small fraction of a second is invisible.

| Threshold | Value | Verdict |
|---|---|---|
| Lock overhead per failure (measured) | ~0.32 µs | ✅ acceptable |
| 100 fully-serialized failures (measured) | ~60–90 µs total | ✅ acceptable |
| Lock-free status read (measured) | ~0.09 µs | ✅ acceptable |
| One SQL round-trip (SQLite-atomic path) | ~0.1–1 ms | ⚠️ only if durability required |
| Holding the lock across a notification HTTP call | up to 10 s × N | ❌ **unacceptable** — prevented by `def` helper |
| Deadlock from lock re-entry | hang (infinite) | ❌ **unacceptable** — prevented by single-lock + helper |

> **Rule of thumb:** a change that keeps the section free of `await` is
> automatically in the acceptable row. A change that introduces an `await`
> inside the section crosses into unacceptable and must be restructured.

---

## 8. Edge cases

### 8.1 Lock timeout — do not add one

Do **not** wrap acquire in `asyncio.wait_for(lock.acquire(), timeout=…)`. The
section has no `await`, so a holder can be preempted only between bytecodes for
microseconds; a waiter can never wait a meaningful duration. A timeout introduces
a *new* failure mode with no good answer (on timeout, drop the record? retry?
both are worse than the status quo). If one is ever added, the on-timeout
behavior must be "log and skip the state update, return" — never a partial write.

### 8.2 Deadlock prevention

| Risk | Prevention |
|---|---|
| Self-reentrancy (locked method calls locked method → deadlock) | Pre-locked `def` helper (§5.2); review rule "never nest two `async with` on the same lock." |
| Lock ordering (two locks, opposite orders) | N/A — there is **one** lock. Adding a second protected object → document a global acquisition order first. |
| `threading.Lock` held across `await` | N/A — we use `asyncio.Lock`. If a threaded path is ever added, never hold a `threading.Lock` across `await`. |
| I/O inside the lock | Structural prevention via the `def` helper. |

Single-lock designs have essentially one deadlock mode (self-reentrancy),
prevented by the helper. That is why we resist adding a second lock (§4.2).

### 8.3 Cancellation

- **Cancelled while waiting on `acquire()`:** clean. `async with` raises
  `CancelledError` out of the acquire; the body never runs; the lock is not
  acquired. No corruption.
- **Cancelled while holding the lock:** `async with` runs `__aexit__` during
  unwinding and releases. The lock is never leaked. (The body has no `await`, so
  the window is tiny, but correctness doesn't depend on that.)
- **Cancelled during post-lock I/O** (`_notify_first_failure`): only the
  notification is lost; the record was already written under the lock, so the
  one-WARNING guarantee holds. Acceptable — the alert is best-effort, the state
  is authoritative.

### 8.4 Exception inside the critical section

`async with` releases the lock on any exception. If a write fails mid-block, the
partial mutation stands and the lock is released. Mitigation: in the helper, read
the decision first, write last — so an exception is most likely *before* any
field is touched. Truncation (`str(error)[:500]`) belongs in the caller before
the lock, not inside it.

### 8.5 Multi-worker / multi-process

The in-memory lock does not coordinate across workers or after a restart. This
is acceptable: deployment is single-worker (§1.3), and the semantic is "one
WARNING **per startup**," so each worker legitimately having its own first-failure
event is correct. If the requirement becomes "one per **deployment**," switch to
§9.

### 8.6 Lazy-singleton init race

`get_telegram_fallback()` is safe as written because the constructor does not
`await` — no yield point between the `is None` check and the assignment
(adc-4783 Mechanism 3). It would become unsafe the moment `__init__` does async
work; then move construction into `lifespan`.

### 8.7 Reset vs. in-flight failure

Both `reset_first_failure_state` (CS-2) and `_handle_send_failure` (CS-1) take
the same lock, so they serialize: either the reset completes first (next failure
is a fresh "first") or the failure completes first (then reset clears it). No
contradictory state; no special handling.

### 8.8 Test isolation

The singleton retains state across tests. Tests should either (a) instantiate a
fresh `TelegramFallback()` directly, or (b) call `await reset_first_failure_state()`
between cases. Mutating `_has_logged_first_failure` directly from a test bypasses
the lock — practically safe in a single-loop test with no concurrency, but prefer
the reset method to keep the contract honest.

---

## 9. Upgrade path: when to switch to SQLite atomicity

Replace the in-memory lock with the SQLite-atomic pattern (adc-4783 §5b;
`aiosqlite` is already a dependency — no new deps) **if any of these becomes
true**:

- State must survive restarts (one first-failure per deployment, not per startup).
- adc is scaled to multiple workers (`--workers N`).
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

This is **not** a performance upgrade (a SQL round-trip costs ~0.1–1 ms vs ~0.32
µs for the lock — see §7.4). It is a **correctness/durability** escalation,
recorded so it need not be re-derived.

---

## 10. Verification / testing

Add these alongside the implementation (correctness tests from adc-41u0 §10;
performance assertions from adc-4rh3 §11):

- **Concurrent first-failure test:** `asyncio.gather` of N calls to
  `_handle_send_failure` → assert exactly one WARNING, `failure_count == N`, and a
  single `_first_failure_timestamp`. (Lock correctness; kills Races 1, 2, 3.)
- **Counter accuracy test:** 100 concurrent calls → `failure_count == 100`
  (no lost updates from `+=`). (Race 2.)
- **Structural no-I/O guard:** `assert inspect.iscoroutinefunction(
  fallback._record_failure_locked) is False`. The load-bearing invariant — if it
  ever becomes `async`, §7.3's risk materializes.
- **Reset-vs-failure test:** `gather(reset, handle_failure)` → state is one of the
  two consistent outcomes, never contradictory.
- **Read-doesn't-block test:** while one task holds the lock (via a test-only
  seam), `get_bridge_status()` returns promptly — proving reads are lock-free.
- **Optional no-regression budget:** a microbenchmark asserting isolated lock
  overhead stays sub-microsecond. Low priority (the path is dormant), but cheap
  insurance against an `await` creeping into the helper.

---

## 11. Developer cheat sheet

The whole design in ten rules:

1. **One `asyncio.Lock`** per `TelegramFallback` instance, created in `__init__`.
2. **Scope = the first-failure record only** (`_has_logged_first_failure`,
   `_failure_count`, `_first_failure_timestamp`, `_last_failure_logged`).
   **Not** `_is_reachable`.
3. **All mutations** go through `async with self._first_failure_lock:`.
4. **Reads take no lock** — `get_bridge_status` is lock-free (~0.09 µs).
5. **No `await` inside the critical section.** Enforce it by putting the body in
   a plain `def` helper (`_record_failure_locked`).
6. **Do I/O after release**, keyed on a `was_first` boolean captured inside.
7. **Never nest two `async with` on the same lock** — it deadlocks
   (non-reentrant). Use the pre-locked helper instead.
8. **No lock timeout** — it adds a failure mode for no benefit.
9. **Cost is ~0.32 µs/failure, flat to 128 contenders; the path is dormant today.**
   Do not believe the "~2–5 ms" figures from older docs.
10. **If durability or multi-worker correctness is ever required**, switch to the
    SQLite `UPDATE … WHERE claimed=0` + `rowcount` CAS (§9) — for correctness, not
    performance.

**The one-sentence design:** *a single instance-level `asyncio.Lock` guards a
minimal, I/O-free critical section over the first-failure record, because the
state is in-memory and per-startup — not because atomics are impossible (they
aren't), and at a measured cost of ~0.32 µs that is negligible on a dormant path.*

---

## References

- **Race catalog:** `notes/adc-4ol5-race-conditions.md` (adc-4ol5); canonical copy
  `docs/race-conditions-first-failure-state.md`.
- **Mechanism research:** `notes/adc-4783.md` (adc-4783) — `asyncio.Lock` behavior,
  GIL atomicity, the SQLite-atomic CAS pattern (§5b), and the correction to
  "atomics are impossible."
- **Strategy decision:** `notes/adc-41u0.md` (adc-41u0) — the locking design this
  doc implements.
- **Performance analysis:** `notes/adc-4rh3.md` (adc-4rh3) — measured costs and the
  correction to the inflated figures.
- **Parent approach:** `notes/adc-50ld-thread-safety-approach.md` (adc-50ld) — race
  identification; its "atomics not possible" claim and performance figures are
  superseded here.
- **Data structure / storage:** `docs/first-failure-state-structure.md` (adc-65l3),
  `docs/first-failure-state-storage.md` (adc-2duz).
- **Current code:** `src/telegram/fallback.py` — `_handle_send_failure` at `:198`,
  call sites in async `send_message` at `:84,89,93`, `__init__` at `:36`; singleton
  created in `lifespan` at `src/main.py:152`; status read at `src/main.py:1474`.
- **Benchmark:** `~/scratch/adc-4rh3-lock-bench.py` (full listing in adc-4rh3 §8).
