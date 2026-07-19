# Thread-Safety Approach for Async FastAPI First-Failure State

**Bead:** adc-50ld — "Design thread-safety approach for async FastAPI"
**Child of:** adc-4vhr (Design first-failure tracking mechanism)
**Depends on:** adc-2duz (state storage — closed), adc-5xuy (comprehensive design doc — closed)
**Status:** Authoritative parent-bead deliverable. Supersedes the prior version of this file
(dated 2026-07-08), which reached the right conclusion for the wrong reason and carried
performance figures overstated by ~3,000–4,000×. **Where this document disagrees with the
prior version, this document is authoritative.**
**Date:** 2026-07-19

> The full implementation-level specification lives in
> `notes/adc-5xuy-thread-safety-design.md` (the comprehensive synthesis). This file is the
> concise parent-bead answer to the three acceptance criteria: *(1) thread-safety approach
> documented, (2) specific race conditions identified, (3) locking strategy explained or
> justified as unnecessary.*

---

## 1. One-sentence design

> A single instance-level `asyncio.Lock` on the `TelegramFallback` singleton guards a
> minimal, **`await`-free** critical section over the first-failure record — because that
> state is in-memory, per-process, and per-startup. **The lock is defense-in-depth, not a
> fix for an active bug:** the current synchronous handler is already race-free on a single
> event loop.

---

## 2. What we are protecting

`TelegramFallback` is a process-wide singleton (`get_telegram_fallback()`, first instantiated
during the FastAPI `lifespan` at `src/main.py:152`). It upholds one operational invariant:

> **Exactly one WARNING is logged per process startup** when the bridge first fails; all
> subsequent failures log at DEBUG.

The **first-failure record** is four instance attributes (per the data-structure bead
adc-65l3 and the storage decision adc-2duz — in-memory, per-startup, **no** persistence):

```python
self._has_logged_first_failure: bool            # the check-then-act flag
self._failure_count: int                         # read-modify-write counter
self._last_failure_logged: datetime | None       # updated every failure
self._first_failure_timestamp: datetime | None   # set-once (to be added — adc-65l3)
```

All four are mutated in exactly one place today: `_handle_send_failure`
(`src/telegram/fallback.py:198`), reachable only through the async `send_message`
(`fallback.py:84,89,93`). A fifth attribute, `_is_reachable`, is shared mutable state but is
**deliberately out of scope** for this lock (§5).

---

## 3. The decisive nuance — why the current code is *already* safe (and why we lock anyway)

This is the single most important point in the design, and it refines what the prior version
of this file (and the race catalog in adc-4ol5) imply.

**Fact about CPython asyncio:** the event loop runs one task at a time and can only switch
tasks at a suspension point — an `await` that actually yields. Between suspension points, a
coroutine runs without interruption, including any *synchronous* function it calls. A
synchronous function with **no `await` inside** is therefore atomic with respect to every
other coroutine on the loop.

The current `_handle_send_failure` is exactly that:

```python
def _handle_send_failure(self, error_context: str = ""):   # sync, no `await`
    self._is_reachable = False
    self._failure_count += 1
    now = datetime.now()
    if not self._has_logged_first_failure:
        logger.warning(...)            # stdlib logging — blocking I/O, but does NOT yield
        self._has_logged_first_failure = True
        self._last_failure_logged = now
    else:
        logger.debug(...)
```

There is **no suspension point** anywhere in this body. `datetime.now()` and stdlib
`logger.*` are synchronous and do not return control to the event loop. So two overlapping
`send_message` coroutines **cannot interleave** inside `_handle_send_failure` — the
T0/T1/T2/T3 "both read False, both warn" interleaving described in the race catalog cannot
fire as the code stands.

**Therefore: the race described by the prior docs is *latent*, not *active*.** The invariant
"one WARNING per startup" currently holds because of *incidental* no-await atomicity, not
because of any explicit protection.

**Why we add a lock anyway:**

| Role of the lock | What it buys |
|---|---|
| **Defense-in-depth against future `await`s** | The moment a maintainer adds an `await` inside the critical section (async logging handler, a DB persist, an inline notification call), the incidental atomicity evaporates *silently* and the latent race goes live. An explicit lock makes correctness survive that change. |
| **Explicit, self-documenting contract** | "No `await` in here" is an invisible convention. `async with self._first_failure_lock:` makes the critical section's boundaries visible to every reader and reviewer. |
| **Negligible cost** | Measured ~0.32 µs of isolated overhead (adc-4rh3), on a path that is **dormant today** (see §6). There is no performance reason *not* to take the insurance. |

> **The honest answer to "is a lock needed?":** Strictly, no — the synchronous, await-less
> handler is already atomic on this single-worker, single-loop deployment. We add the lock so
> that correctness does not depend on a future maintainer knowing that, and so that the
> notification I/O the design wants to add can be wired in safely.

---

## 4. Race conditions identified

Six races arise when concurrent coroutines enter the failure handler. Cataloged in full in
`notes/adc-4ol5-race-conditions.md`; the decisive ones:

| # | Race | Pattern | Severity | Status today |
|---|---|---|---|---|
| 1 | **Duplicate first-failure WARNINGs** | check-then-act on `_has_logged_first_failure` | **High** — breaks the core invariant | Latent (no `await` to interleave) → **goes live the moment an `await` enters the section** |
| 2 | **Lost counter updates** | read-modify-write `_failure_count += 1` (LOAD/ADD/STORE) | Medium | Latent for the same reason |
| 3 | **First-failure timestamp overwrite** | set-once via the racy flag check | Low | Latent |
| 4 | **Last-failure timestamp lost update** | non-deterministic write ordering | Low | Latent |
| 5 | **Read-during-write on status check** | `get_bridge_status` reads mid-mutation | Low | Tolerated (stale-but-consistent is fine for monitoring) |
| 6 | **Reachability toggle** | concurrent success (`_is_reachable = True`) vs failure (`= False`) | Medium | Accepted as benign (single-bytecode writes, last-write-wins) — see §5 |

**The dividing line is the *shape* of the operation, not the field:**

| Shape | Example | Atomic on a single loop? |
|---|---|---|
| Single assignment of an immutable | `_has_logged_first_failure = True` | ✅ atomic (one bytecode, and GIL-protected) |
| Read of a single field | `_failure_count` in `get_bridge_status` | ✅ atomic |
| **Check-then-act** | `if not flag: flag = True` | ⚠️ atomic *only while there's no `await` between check and act* |
| **Read-modify-write** | `_failure_count += 1` | ⚠️ atomic *only while there's no `await` between read and write* |
| Multi-field consistent snapshot | status dict assembled field-by-field | ⚠️ same caveat |

The GIL makes single bytecodes atomic; it does **not** make compound sequences atomic, and
asyncio does not make them atomic either — it merely happens not to interrupt them absent a
suspension point. That caveat is precisely what the lock removes.

---

## 5. Locking strategy

### 5.1 Decision

> **One instance-level `asyncio.Lock` per `TelegramFallback`, created in `__init__`, scoped to
> the first-failure record fields only.**

- **All mutations** of the record go through `async with self._first_failure_lock:`.
- **Reads** (`get_bridge_status`) take **no** lock — single-field atomic reads; monitoring
  tolerates staleness (Race 5).
- The critical section contains **no `await`/I/O** — implemented as a pre-locked **plain `def`
  helper** so I/O is structurally impossible inside it.

### 5.2 Why `asyncio.Lock` and not the alternatives

The right mechanism is dictated by **where the state lives and which concurrency layer touches
it.** For this state only the event-loop layer exists (single worker, all-async access paths,
in-memory per-startup — verified against CLAUDE.md and `src/`):

| Mechanism | Verdict | Why |
|---|---|---|
| **`asyncio.Lock` (instance)** | ✅ **Chosen** | Native to async, non-blocking, sub-µs uncontended, groups the multi-field record into one consistent section. |
| `threading.Lock` | ❌ wrong layer | Blocking acquire stalls the loop; can't be held across `await`. No threaded path touches this state. |
| Module-level / `app.state` lock | ⚠️ unnecessary | State is owned by the singleton instance; an instance lock is better encapsulated. |
| Queue-based serialization | ❌ overkill | A background task + queue lifecycle for one boolean flag. |

### 5.3 Correction: "atomic operations are NOT POSSIBLE" is false

The prior version of this file (Option 4) declared atomic operations impossible in Python and
concluded `asyncio.Lock` is the *only* viable mechanism. That reasoning is **wrong**, and the
correction matters for future maintainers:

- **GIL-level atomics** exist for single-bytecode operations (§4 table).
- **SQLite transactions are atomic** — strictly *stronger* than an in-memory lock for
  persisted state (survive restarts, span workers). `src/session/store.py` already runs
  `PRAGMA journal_mode=WAL`, and `aiosqlite` is already a dependency.
- **File-level atomics** (`os.replace` temp-then-rename) exist for on-disk state.

The right mental model is **pick the mechanism that matches where the state lives**, not
"always reach for `asyncio.Lock`." For the first-failure record the *conclusion* (use
`asyncio.Lock`) is correct — but the *reason* is "because this state is in-memory,
per-process, per-startup," **not** "because atomics are impossible." Recording the right reason
prevents a future maintainer from mis-generalizing and blocking a better design elsewhere
(e.g. a genuine `find_or_create_topic` TOCTOU, which should be fixed with a unique index +
`INSERT … ON CONFLICT DO NOTHING … RETURNING`, not a lock).

### 5.4 `_is_reachable` is explicitly out of scope

`_is_reachable` is written from *different* paths (success at `:80`, health-check at `:176,179`,
failure at `:207`). **Do not pull it under the first-failure lock:** every write is a single
atomic `STORE_ATTR` with no check-then-act, it has a different lifecycle, and coupling it to a
failure-path lock would force the success/health-check paths to acquire a failure lock for no
reason. Rule of thumb: **one lock per logical state object.**

### 5.5 The structural rules (the parts a reviewer must enforce)

1. **One `asyncio.Lock`** per instance, created in `__init__` (safe — singleton built on the
   serving loop, constructor does not `await`).
2. **No `await` inside the critical section.** Enforce by putting the body in a plain `def`
   helper (`_record_failure_locked`) — a `def` mechanically cannot `await`.
3. **I/O runs after release**, keyed on a `was_first: bool` captured inside the section.
4. **Never nest two `async with self._first_failure_lock:`** — `asyncio.Lock` is non-reentrant;
   re-entry deadlocks. There is no async `RLock`; the pre-locked helper is the fix.
5. **No lock timeout** — the section is await-free, so a holder can only be preempted between
   bytecodes for microseconds; a timeout would add a failure mode with no good recovery.
6. **`get_bridge_status` and all `_is_reachable` writes stay lock-free.**

Sketch (full version + diff in `adc-5xuy-thread-safety-design.md` §5–§6):

```python
async def _handle_send_failure(self, error_context: str = "") -> None:
    was_first = False
    async with self._first_failure_lock:
        was_first = self._record_failure_locked(error_context)  # plain def; no await
    if was_first:
        await self._notify_first_failure(error_context)         # I/O outside the lock

def _record_failure_locked(self, error_context: str) -> bool:
    """Caller MUST hold _first_failure_lock. Sync on purpose — no await."""
    ...
```

---

## 6. Performance (corrected)

Measured on CPython 3.12 on this box (full benchmark + listing in adc-4rh3; logging raised to
CRITICAL to isolate lock cost from handler I/O):

| Operation | Measured cost |
|---|---|
| Uncontended `async with lock:` (empty body) | **~0.47 µs** |
| Lock-free status read | **~0.09 µs** |
| Isolated lock overhead (realistic section, with − without) | **~0.32 µs** |
| 100 fully-serialized failures | **~60–90 µs total** (count exactly correct; flat to 128 contenders) |

> **Correction to the prior version of this file.** It carried "~1–2 ms per failure",
> "2–5 ms per request", and "100 concurrent failures = 200 ms total" figures. Measurement
> shows the lock itself costs ~0.32 µs and 100 serialized failures complete in **~60–90 µs**.
> The prior figures are **overstated by ~3,000–4,000×** — they conflated lock acquisition cost
> (sub-µs) with logging-I/O latency (ms, only if a handler does I/O). **Do not propagate them.**

The decisive argument is grounded in the code, not the microbenchmark: the protected path is
**dormant today.** `_handle_send_failure` is reachable only via `send_message`, and
`send_message`/`send_result` have **no live callers** outside `fallback.py` (verified across
`src/` — `send_exception` and `send_workload_summary` are no-op stubs). The only live touchers
of the singleton are the lifespan health-check (writes `_is_reachable`, not the record) and the
read-only status endpoint. **You cannot contend a lock on a code path that isn't called.**

The one real performance risk is **I/O inside the critical section** (e.g. calling a 10 s-timeout
notification `await` inside the lock → every concurrent failing request serializes behind one
10 s timeout). That is structurally prevented by the plain-`def` helper (§5.5 rule 2).

---

## 7. Edge cases (summary)

| Case | Resolution |
|---|---|
| Lock timeout | None added (§5.5 rule 5). If ever added, on-timeout behavior must be "log + skip the update," never a partial write. |
| Deadlock / self-reentrancy | Prevented: single lock + pre-locked `def` helper; review rule "never nest two `async with` on the same lock." |
| Cancellation while waiting / holding | `async with` releases on `CancelledError`; body never runs or runs atomically; lock never leaked. |
| Cancellation during post-lock notification | Only the (best-effort) alert is lost; the record was already written, so the one-WARNING guarantee holds. |
| Exception inside the section | `async with` releases the lock; read the decision first, write last so an exception is most likely before any field is touched. |
| Reset vs. in-flight failure | Both `reset_first_failure_state` and `_handle_send_failure` take the same lock → they serialize cleanly; no contradictory state. |
| Lazy-singleton init | `get_telegram_fallback()` is safe because `__init__` does not `await` — no yield between the `is None` check and the assignment. Would need to move into `lifespan` if `__init` ever awaits. |
| Multi-worker / restart | In-memory lock does not coordinate across workers or after restart. Acceptable: deployment is single-worker, and the semantic is "one WARNING **per startup**." If it becomes "one per **deployment**," escalate to the SQLite-atomic CAS (§8). |

---

## 8. Upgrade path (when atomics become the right answer)

Switch the record to the SQLite-atomic pattern (`UPDATE … SET claimed=1, first_failure_at=? WHERE
id=1 AND claimed=0` + `cur.rowcount == 1` as the compare-and-set; `aiosqlite` already a dep, no
new deps) **if any of these becomes true:**

- State must survive restarts (one first-failure per deployment, not per startup).
- adc is scaled to `uvicorn --workers N`.
- A `def` route or threadpool path starts touching this state.

This is a **correctness/durability** escalation (a SQL round-trip is ~0.1–1 ms vs ~0.32 µs for the
lock), not a performance one. Recorded so it need not be re-derived.

---

## 9. Verification pointers

Tests to add alongside the implementation (details in adc-5xuy §10 / adc-4rh3 §11):

- **Concurrent first-failure:** `asyncio.gather` of N `_handle_send_failure` → exactly one
  WARNING, `failure_count == N`, single `_first_failure_timestamp`.
- **Counter accuracy:** 100 concurrent calls → `failure_count == 100`.
- **Structural no-I/O guard:** `assert inspect.iscoroutinefunction(fallback._record_failure_locked)
  is False` — the load-bearing invariant.
- **Reset-vs-failure** and **read-doesn't-block** tests.

---

## 10. Corrections logged vs. the prior version of this file

| Prior claim (2026-07-08) | Status | Why |
|---|---|---|
| "Atomic operations NOT POSSIBLE" (Option 4) | **Wrong** | GIL atomics, SQLite txns, and `os.replace` all exist. Use `asyncio.Lock` because the state is in-memory per-startup, not because atomics are impossible. |
| "~2–5 ms per request", "100 failures = 200 ms" | **Overstated ~3,000–4,000×** | Measured ~0.32 µs lock overhead; 100 failures ≈ 60–90 µs. Conflated lock cost with logging-I/O latency. |
| Current code "breaks the moment two requests fail in overlapping coroutines" | **Imprecise** | Overlapping coroutines do **not** interleave inside a synchronous, await-less function on a single event loop. The race is **latent**, held off by incidental no-await atomicity. The lock makes the property robust rather than incidental. |
| `asyncio.Lock` recommended (Option 1) | **Correct** | Conclusion stands; reasoning refined. |
| Race catalog (duplicate WARNING, lost counter, timestamp overwrite) | **Correct** | Unchanged; reframed as latent. |

---

## References

- **Comprehensive implementation spec:** `notes/adc-5xuy-thread-safety-design.md` (adc-5xuy) — the
  deep dive; concrete diff, reviewer checklist, cheat sheet.
- **Race catalog:** `notes/adc-4ol5-race-conditions.md` (adc-4ol5).
- **Mechanism research:** `notes/adc-4783.md` (adc-4783) — `asyncio.Lock` behavior, GIL atomicity,
  SQLite-atomic CAS pattern, correction to "atomics impossible."
- **Strategy decision:** `notes/adc-41u0.md` (adc-41u0).
- **Performance analysis:** `notes/adc-4rh3.md` (adc-4rh3) — measured costs; benchmark at
  `~/scratch/adc-4rh3-lock-bench.py`.
- **Data structure / storage (dependencies):** `notes/adc-65l3-first-failure-state-structure.md`
  (adc-65l3), `notes/adc-2duz-state-storage-design.md` (adc-2duz) — storage decision is
  in-memory, per-startup, no persistence.
- **Current code:** `src/telegram/fallback.py` — `_handle_send_failure` at `:198`, call sites at
  `:84,89,93`, `__init__` at `:36`; singleton created in `lifespan` at `src/main.py:152`; status
  read at `src/main.py:1474`. Deployment: single worker (`uvicorn src.main:app`, no `--workers`).
