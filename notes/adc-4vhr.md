# First-Failure Tracking Mechanism — Umbrella Design (adc-4vhr)

**Status:** Design COMPLETE.
**Authoritative source:** `notes/adc-14la-first-failure-tracking-design.md` (the synthesized
end-to-end design). **This note is the umbrella entry point**; depth lives in adc-14la and its
child designs. Where any earlier `adc-4vhr*` note disagrees with adc-14la, **adc-14la wins.**

> **Why this note exists.** adc-4vhr is the umbrella bead ("Design first-failure tracking
> mechanism"). Its children — data-structure (adc-65l3), storage (adc-2duz), thread-safety
> (adc-50ld, authoritative), detection logic (adc-12bt) — were synthesized into one coherent
> design by adc-14la. That synthesis satisfies this bead's acceptance criteria directly. This
> note records that decision, verifies it against the current code, de-conflicts the older
> superseded drafts, and hands off to the implementation bead.

---

## 1. The one invariant

> **Exactly one first-failure notification is emitted per process startup** when the Telegram
> bridge first fails to accept a send. Every subsequent failure within that startup is silent
> (DEBUG + counters only).

First-failure is a **per-startup** semantic — a process restart re-arms detection intentionally.
Everything else in the design exists to make that invariant hold under concurrency, hold without
log spam, and hold robustly rather than by accident.

---

## 2. Acceptance-criteria resolution

| Criterion (adc-4vhr) | Resolution | Detail |
|---|---|---|
| Design documented in bead body | ✅ This note + authoritative synthesis adc-14la | adc-14la is the single document the implementation bead implements against |
| State storage | ✅ **Flat instance variables on the `TelegramFallback` singleton** (`get_telegram_fallback()`); in-memory, per-process, per-startup; **no persistence layer** | adc-2duz (storage) + adc-65l3 (fields); rejected: a separate `FirstFailureTracker` class / module, and any SQLite/file persistence for v1 |
| Initialization | ✅ All fields set in `TelegramFallback.__init__` (incl. the `asyncio.Lock`); reachability `_is_reachable` is a *separate* logical object whose other writers stay lock-free | adc-14la §4.1 |
| Race-condition handling | ✅ `asyncio.Lock` serializes the critical section; `_record_failure_locked` is a plain `def` with **no `await`** (makes check-then-act atomic by construction); notification I/O runs **after** lock release, keyed on `was_first: bool` | adc-50ld (authoritative) + adc-12bt; adc-14la §5 |
| Clear implementation guidance for next bead | ✅ adc-14la §8 — sequenced 7-step plan, tests, verification, anti-patterns | "What NOT to do" in §8.4 |

---

## 3. Design at a glance (umbrella altitude)

**State model** (flat on the singleton — no wrapper class):

| Field | Type | Init | Semantics |
|---|---|---|---|
| `_has_logged_first_failure` | `bool` | `False` | The check-then-act flag. Monotonic `False→True` within a startup; the failure that flips it is "first." |
| `_failure_count` | `int` | `0` | Total failures since startup (unconditional `+= 1`). Diagnostic; surfaced on the status endpoint. |
| `_first_failure_timestamp` | `datetime \| None` | `None` | **NEW**, set-once. When the first failure occurred. |
| `_last_failure_timestamp` | `datetime \| None` | `None` | **RENAMED** from current `_last_failure_logged` (which was updated *only* on the first failure — a latent bug); now updated on *every* failure. |
| `_first_failure_lock` | `asyncio.Lock` | `asyncio.Lock()` | Serializes the critical section. Instance-level, created in `__init__`. |

**Flow:** `send_message()` failure branch → `await _handle_send_failure(ctx)` →
`async with self._first_failure_lock:` → `_record_failure_locked(ctx)` (plain `def`, returns
`was_first: bool`) → lock released → if `was_first`: `await _notify_first_failure(ctx)`
(side-channel I/O, **never** `self.send_message`).

**Concurrency framing (load-bearing):** CPython asyncio runs one task at a time and switches only
at an `await` that yields. The *current* `_handle_send_failure` is synchronous and await-free, so
it is **already atomic** with respect to every other coroutine — the duplicate-WARNING race is
**latent, not active**. The lock is **defense-in-depth**: the moment a maintainer adds an `await`
inside the critical section (async logging handler, a DB persist, an inline notification), the
incidental atomicity evaporates *silently*. An explicit lock + the plain-`def` helper make
correctness survive that change. Measured overhead: ~0.32 µs on a path that is dormant today
(adc-4rh3).

**"First" = claim-and-set, not a timestamp comparison** — which is what makes it well-defined under
concurrency and exactly-once without deduplication. Under N near-simultaneous failures the lock
serializes entry; coroutine 1 flips the flag and returns `was_first=True`; coroutines 2…N observe
`True`, increment the counter, return `False`. Net: exactly one notification, `_failure_count == N`,
one `_first_failure_timestamp`.

---

## 4. Code verification (performed 2026-07-19 against current tree)

CLAUDE.md directs verification of any design that names files/flags before recommending it. I
checked every code claim in adc-14la against the live source — **all accurate**:

| Claim (adc-14la) | Verified |
|---|---|
| `TelegramFallback.__init__` at `src/telegram/fallback.py:36` | ✅ `:36` |
| Current fields `_is_reachable`/`_last_failure_logged`/`_failure_count`/`_has_logged_first_failure` at `:42–45` | ✅ exact |
| Three failure branches in `send_message`: non-2xx `:84`, `RequestError` `:89`, other `Exception` `:93` — all currently **sync** `self._handle_send_failure(...)` | ✅ exact; `send_message` is `async def`, so these can become `await` |
| `_handle_send_failure` at `:198` | ✅ `:198` |
| `_is_reachable = True` written on send success at `:80`; by health-check at `:176`/`:179` | ✅ exact |
| `_last_failure_logged = now` set **only** on the first failure (`:219`) — confirms the latent bug | ✅ confirmed |
| `FAILURE_LOG_COOLDOWN_SECONDS = 300` at `:34` is a **dead constant** (declared, never referenced) | ✅ `grep` across `src/` returns only the declaration — dead |
| Singleton wired in FastAPI lifespan at `src/main.py:152`; `check_bridge_available()` at `:153` (health check, **not** the first-failure trigger) | ✅ exact |
| Status endpoint `/api/v1/status/telegram_bridge` at `src/main.py:1469`, reads `get_bridge_status()` at `:1474` | ✅ exact (`:1469`/`:1474`) |
| `import asyncio` not yet present; `from typing import Optional` and `from datetime import datetime` already imported | ✅ confirmed |
| Deployment is single-worker (`uvicorn src.main:app`, no `--workers`) | ✅ per CLAUDE.md startup command |

**No drift between the design and the code.** The implementation bead can apply adc-14la §4
verbatim.

---

## 5. De-conflicting the earlier adc-4vhr drafts

There are three **superseded** `adc-4vhr*` design notes. Do not implement against any of them —
adc-14la is authoritative:

| Note | Status | Why superseded |
|---|---|---|
| `notes/adc-4vhr-design.md` (early draft) | Superseded | Predates the adc-50ld/adc-12bt refinements; no reconciliation of the child-design conflicts. |
| `notes/adc-4vhr-first-failure-tracking-design.md` (2026-07-08 synthesis) | Superseded | Explicitly named "superseded synthesis" by adc-14la §11. Proposed a dedicated `FirstFailureTracker` class returning log-level *strings* — **rejected** (adc-14la §7 #1): the singleton owns the state; a wrapper class adds indirection without encapsulation gain. |
| This note, prior to 2026-07-19 | Replaced | The pre-2026-07-19 version of `notes/adc-4vhr.md` *also* proposed the `FirstFailureTracker`-class + optional-SQLite-persistence approach. Both elements are rejected by the authoritative child designs (adc-65l3/adc-2duz: flat instance vars, no persistence for v1). |

The earlier notes are retained for the decision history (adc-14la §7 reconciliation table references
them), but the design they propose is **not** the design.

---

## 6. Rejected alternatives (decision rationale, preserved)

- **Separate `FirstFailureTracker` class / `src/telegram/first_failure_tracker.py`** — rejected.
  Flat instance vars on the singleton (adc-65l3, adc-2duz). A wrapper adds indirection without
  encapsulation gain; the singleton already owns the state.
- **SQLite / file persistence for v1** — rejected. State is per-startup diagnostic, not a
  per-deployment record; persistence adds cleanup + failure modes with no current requirement.
  Recorded as the **upgrade path** (adc-14la §9): switch to a SQLite-atomic compare-and-set *if*
  state must survive restarts, adc is scaled to `--workers N`, or a threadpool path touches the
  state.
- **`threading.Lock`** — rejected. Mixes threading and asyncio models; `asyncio.Lock` is the
  idiomatic match for state that is in-memory, per-process, per-startup.
- **Time-based re-notification cooldown** — the dead `FAILURE_LOG_COOLDOWN_SECONDS` constant is a
  leftover from a superseded "re-notify after 5 min" idea. Implementation bead: **delete it**
  (adc-14la §6.8) — do not leave a constant implying behavior the code does not have. Re-alerting,
  if ever wanted, is recovery-based reset (adc-14la §6.4), not a timer.
- **Pulling `_is_reachable`'s other writers under the lock** — rejected. One lock per logical state
  object (adc-50ld §5.4); `_is_reachable` is written from success/health-check/failure paths, each a
  single atomic `STORE_ATTR` with no check-then-act.

---

## 7. Hand-off to the implementation bead

The implementation bead **does not yet exist** as a tracked bead (the prior reference to `adc-5jl`
in this note's history was wrong — `adc-5jl` is an unrelated kubectl action bead). Its spec is
**adc-14la §8**, condensed:

1. Fields + `asyncio.Lock` in `__init__` (add `_first_failure_timestamp`; rename
   `_last_failure_logged`→`_last_failure_timestamp`; add `_first_failure_lock`; `import asyncio`).
2. Split the current sync `_handle_send_failure` into an `async def _handle_send_failure` (acquires
   lock, calls helper, awaits notify if first) + a plain-`def _record_failure_locked(...) -> bool`
   (returns `was_first`; unconditional counter increment first; set-once first timestamp).
3. Add `async def _notify_first_failure(...)` as a documented no-op seam (channel choice is a
   separate bead).
4. `await` the three call sites in `send_message` (`:84`/`:89`/`:93`).
5. Extend `get_bridge_status` with `has_logged_first_failure` / `first_failure_timestamp` /
   `last_failure_timestamp`; confirm `src/main.py:1469` serializes.
6. Add `reset_first_failure_state()` (test hook + future recovery/hot-reload).
7. Delete the dead `FAILURE_LOG_COOLDOWN_SECONDS`.

**Tests (adc-14la §8.2):** concurrent first-failure (exactly one WARNING, `_failure_count == N`),
counter accuracy under 100 concurrent calls, **structural no-I/O guard**
(`assert inspect.iscoroutinefunction(fallback._record_failure_locked) is False` — the load-bearing
invariant), subsequent suppression, reset re-arms, read-doesn't-block.

**Anti-patterns (adc-14la §8.4):** no `FirstFailureTracker` class/module; no `await` inside
`_record_failure_locked`; `_notify_first_failure` must not call `self.send_message`; don't pull
`_is_reachable`'s other writers under the lock; no lock timeout.

---

## 8. References

- **Authoritative synthesis:** `notes/adc-14la-first-failure-tracking-design.md`
- **Child designs:** adc-65l3 (data structure), adc-2duz (storage), adc-50ld (thread-safety,
  authoritative; comprehensive spec adc-5xuy; race catalog adc-4ol5; perf adc-4rh3), adc-12bt
  (detection logic).
- **Current code:** `src/telegram/fallback.py` (`__init__` :36, `_handle_send_failure` :198,
  failure branches :84/:89/:93, dead constant :34); singleton wired `src/main.py:152`; status
  endpoint `src/main.py:1469`.
- **Superseded drafts:** `notes/adc-4vhr-design.md`, `notes/adc-4vhr-first-failure-tracking-design.md`
  (and the pre-2026-07-19 version of this note).

**Bead:** adc-4vhr · **Status:** Design Complete · **Date:** 2026-07-19
