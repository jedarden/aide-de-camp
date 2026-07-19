# Performance Implications of the First-Failure Locking Strategy

**Bead:** adc-4rh3 (child of adc-50ld — "Design thread-safety approach for async FastAPI")
**Status:** Performance analysis — consumes the locking-strategy decision in adc-41u0 and quantifies its cost.
**Date:** 2026-07-19
**Measured on:** CPython 3.12.12, this Hetzner box (single worker, `uvicorn src.main:app`).

This document does **one** thing the sibling docs don't: it puts real, measured
numbers on the cost of the chosen `asyncio.Lock` strategy, identifies the
performance-critical paths, and states explicit acceptable/unacceptable
thresholds. It does not re-derive the strategy (adc-41u0), the race catalog
(adc-4ol5), or the mechanism catalog (adc-4783) — it consumes them.

---

## 1. Bottom line

**The performance impact of the chosen locking strategy is negligible — by
measurement, not assertion.** The lock adds **~0.32 µs per failure** in the
isolated case and **stays flat under contention up to 128 concurrent failing
coroutines**. The correctness properties it buys (exactly one WARNING per
startup, an accurate failure count, a consistent multi-field snapshot) are
therefore essentially free.

Two findings dominate this conclusion, and both are stronger than the prior
docs' reasoning:

1. **The protected path is dormant today.** The lock lives on
   `_handle_send_failure`, which is reachable only through `send_message`, and
   `send_message` has **no live callers** in the dispatch path
   ([§3](#3-hot-path-analysis--the-protected-path-is-dormant)). Realistic
   contention is therefore *zero* until that path is wired in — and even then
   it only runs on the **error** path of a **secondary** notification channel.
2. **The prior cost estimates are wrong by ~3,000–4,000×.** adc-50ld and
   adc-4ol5 carry "2–5 ms per failure" and "200 ms for 100 concurrent
   failures" figures. Measurement shows the lock itself costs ~0.32 µs and 100
   serialized failures complete in **~60–90 µs total**, not 200 ms
   ([§4](#4-measured-metrics), [§6](#6-correction-to-the-prior-estimates)).

The one performance risk that is *real* is not the lock's acquisition cost —
it is the possibility of **holding the lock across I/O**. That risk is
structurally prevented by the `def`-helper rule in adc-41u0 §6.2
([§7](#7-the-one-real-performance-risk-io-inside-the-critical-section)).

---

## 2. What is being measured

The strategy under analysis (adc-41u0 §1, §6):

- **One** instance-level `asyncio.Lock` on the `TelegramFallback` singleton.
- **Critical section** = the `_record_failure_locked` body: an int increment,
  a `datetime.now()`, a branch, a few attribute writes, and one
  `logger.warning`/`logger.debug` call. **No `await`, no I/O** — enforced by
  the helper being a plain `def`.
- **Reads** (`get_bridge_status`) take **no lock**.
- **I/O** (a first-failure notification, if ever added) runs *after* the lock
  is released, keyed on a `was_first` boolean captured inside it.

The benchmark ([§8](#8-appendix-benchmark-script)) measures exactly this
shape, plus a lock-free variant to isolate the lock's own cost from the work.

---

## 3. Hot-path analysis — the protected path is dormant

This is the most important finding, and it is grounded in the code, not in a
microbenchmark.

**Reachability of the lock's critical section:**

| Call site | Reaches `_handle_send_failure`? | Live today? |
|---|---|---|
| `send_message` non-200 branch (`fallback.py:84`) | yes (after the fix) | only if `send_message` is called |
| `send_message` `RequestError` (`fallback.py:89`) | yes | only if `send_message` is called |
| `send_message` generic `Exception` (`fallback.py:93`) | yes | only if `send_message` is called |
| `send_result` (`fallback.py:107`) | indirectly — it calls `send_message` | **`send_result` has no callers** |
| `send_exception` (`fallback.py:109`) | no — no-op stub | no |
| `send_workload_summary` (`fallback.py:128`) | no — no-op stub | no |
| `check_bridge_available` (lifespan, `main.py:153`) | no | yes (startup only) |
| `get_bridge_status` (`main.py:1474`, status endpoint) | no — read path | yes, lock-free |

A repo-wide grep for `\.send_message\b|\.send_result\b|\.send_exception\b|\.send_workload_summary\b`
returns **only** the internal `send_result → send_message` call at
`fallback.py:107`. Nothing dispatches a result or exception to Telegram. The
watcher's `_send_to_telegram` (`watcher/daemon.py:215`) does **not** use
`TelegramFallback.send_message` — it logs a "mapping not implemented" warning
and returns. `send_exception` and `send_workload_summary` are explicit no-op
stubs.

**Consequence:** the lock's critical section is, today, executed **zero times
per request**. The only live callers of the singleton are a startup
health-check (which writes `_is_reachable`, not the protected fields) and the
read-only status endpoint (which takes no lock). There is no hot path to
contend the lock until the send path is wired in.

Even once wired in, the failure path fires **only when the
telegram-claude-bridge is unreachable or returns non-200** — i.e. on the error
path of a fallback surface that is already secondary to the canvas SSE
pipeline. So the realistic steady-state contention is: zero failures (bridge
up) or a burst at the moment the bridge goes down (transient), never a
sustained high-rate hammer.

This is the decisive argument that **lock performance is a non-issue for this
strategy**: you cannot contend a lock on a code path that isn't called.

---

## 4. Measured metrics

Benchmark: `~/scratch/adc-4rh3-lock-bench.py` (full listing in
[§8](#8-appendix-benchmark-script)). Run on CPython 3.12.12, WARNING/DEBUG
logging raised to CRITICAL so we measure the lock's cost, not log-handler I/O.

| # | Operation | Measured cost | Notes |
|---|---|---|---|
| 1 | Uncontended `async with lock:` acquire+release, empty body | **~0.47 µs** | The fast path — one failure in flight, no contenders. |
| 2 | Lock-free read (`get_bridge_status` equivalent) | **~0.09 µs** | Reads take no lock by design. |
| 3 | Realistic critical section, single coroutine, **with lock** | **~0.92 µs** | The `_record_failure_locked` body + lock. |
| 4 | Realistic critical section, single coroutine, **no lock** | **~0.60 µs** | Same work, lock removed. |
| — | **Isolated lock overhead (3 − 4)** | **~0.32 µs** | The actual tax the lock adds per failure. |

**Contended throughput** (real work, WARNING suppressed, 200k total ops split
across N workers all serializing through one lock):

| Workers | Wall-clock per op | Correctness (count == 200k) |
|---|---|---|
| 2 | 1.03 µs | ✅ |
| 4 | 1.03 µs | ✅ |
| 8 | 1.02 µs | ✅ |
| 16 | 1.03 µs | ✅ |
| 32 | 1.25 µs | ✅ |
| 64 | 1.02 µs | ✅ |
| 128 | 1.03 µs | ✅ |

**The throughput is essentially flat from 2 to 128 concurrent contenders.**
This is the key contention result, and it follows directly from the design:
because the critical section contains no `await`, a task that acquires the
lock runs the whole section without yielding to the loop. Waiters are not
preempted mid-section by I/O — they simply queue and are served one after
another at the speed of the work itself (~0.6 µs each). There is no
exponential backoff, no I/O stall to multiply, no priority inversion. Doubling
contenders does not double latency; it stays ~1 µs/op because the section is
CPU-bound and sub-microsecond.

---

## 5. Bottleneck / hot-path identification

A "bottleneck" would be a path that (a) acquires the lock frequently and (b)
is on the latency-critical request path. Inventory:

| Path | Acquires lock? | Frequency | On critical path? |
|---|---|---|---|
| `_handle_send_failure` (CS-1, failure path) | yes | only on send failure; **dormant** today | no — error path of a secondary channel |
| `reset_first_failure_state` (CS-2, reset) | yes | manual/admin, rare | no |
| `get_bridge_status` (status endpoint) | **no** | per status poll | yes, but lock-free → ~0.09 µs |
| `check_bridge_available` (lifespan + health) | no (writes `_is_reachable`, out of scope per adc-41u0 §4) | startup + periodic | no |
| Successful `send_message` (bridge up) | **no** | per send | would be on path, but takes no lock |

**There is no hot path that holds the lock.** The two paths that *do* take it
are both off the latency-critical axis: one is dormant, the other is a manual
admin reset. The one path that *would* be hit per-send (successful
`send_message`) takes no lock. The status read — the most frequently-called
live path on the singleton — is lock-free.

So the bottleneck inventory is empty by construction. The strategy pays nothing
on any path that matters for request latency.

---

## 6. Correction to the prior estimates

The existing "Performance Implications" sections (adc-50ld
`notes/adc-50ld-thread-safety-approach.md` and adc-4ol5
`docs/race-conditions-first-failure-state.md`) carry these figures:

| Prior claim | Source | Measured reality | Over-stated by |
|---|---|---|---|
| "First failure … ~1–2 ms" per acquisition | adc-50ld | ~0.92 µs (whole section); ~0.47 µs (acquire alone) | ~1,000–4,000× |
| "Subsequent failure … +2 ms" lock cost | adc-50ld | ~0.32 µs isolated lock overhead | ~6,000× |
| "+2–5 ms per request" on the error path | adc-50ld, adc-4ol5 | ~0.32 µs lock overhead | ~6,000–15,000× |
| "100 concurrent failures = 200 ms total queue wait" | adc-50ld, adc-4ol5 | ~60–90 µs total serialized | ~2,000–3,000× |

**Why the prior numbers are off.** They conflate two unrelated quantities:

- **Lock acquisition cost** — the CPU work to take and release an uncontended
  `asyncio.Lock`, which is sub-microsecond (measured ~0.32–0.47 µs).
- **Logging I/O latency** — the wall-clock time a `logger.warning(...)` *can*
  take if a handler does I/O (file flush, network syslog). That can be
  milliseconds, but it is **not** the lock's cost, and in adc-41u0 the
  in-section `logger.warning` writes to the stdlib handler which does not
  `await` and is typically buffered.

The "200 ms for 100 failures" figure additionally assumes each holder keeps
the lock for ~2 ms, which can only happen if the section does I/O — exactly
what the `def`-helper rule forbids. With the rule in force, 100 holders
serialize at ~0.6 µs of work each → ~60 µs total.

**This correction matters for two reasons:**

1. It removes the false impression that there is a performance budget being
   spent. There isn't. The lock is free for practical purposes.
2. It reframes the one real risk. If a future maintainer reads "the lock costs
   2 ms," they may be tempted to "optimize" it by moving work around or
   dropping the lock — when the *actual* risk is the opposite direction:
   accidentally putting I/O *inside* the section, which is what would turn
   0.6 µs into real milliseconds ([§7](#7-the-one-real-performance-risk-io-inside-the-critical-section)).

> **Action:** The over-stated figures in adc-50ld and adc-4ol5 should not be
> propagated. This doc supersedes them for performance claims; the race
> catalog and design in those docs remain authoritative.

---

## 7. The one real performance risk: I/O inside the critical section

The lock's acquisition cost is irrelevant. The only way this strategy develops
a real performance problem is if the critical section stops being
sub-microsecond — i.e. if it starts doing I/O or otherwise `await`ing while
holding the lock. Concretely, the dangerous mutations are:

- Calling `_notify_first_failure` (an HTTP send to an ops chat) **inside** the
  `async with` block. A notification HTTP call has a 10 s timeout
  (`send_message` uses `timeout=10.0`). If held under the lock, **every
  concurrent failing request would serialize behind one 10-second HTTP
  timeout** — that is the genuine "200 ms → 10 s × N" disaster, and it is the
  scenario the prior docs' intuition was gesturing at, just mis-attributed to
  the lock itself.
- Adding a DB persist of the first-failure record inside the section (an
  `aiosqlite` round-trip, ~hundreds of µs to low ms under WAL).
- Wiring in an async logging handler (e.g. a network syslog sink) that
  `await`s inside `logger.warning`.

**Why the current design is safe.** adc-41u0 §6.2 makes the in-section helper
a plain `def` (`_record_failure_locked`). A `def` cannot `await`, so I/O is
**structurally impossible** inside the critical section — not a convention, a
type-system-enforced boundary. The notification runs *after* release, keyed on
the `was_first` boolean. The verification plan (adc-41u0 §10) includes a
"structural" check that the locked helper is a `def`.

**Mitigation (already in place, restated as a performance contract):**

| Risk | Mitigation | Where enforced |
|---|---|---|
| Notification HTTP inside lock | Capture `was_first` under lock; send after release | adc-41u0 §6.1–6.2 |
| DB persist inside lock | Either drop it, or do it after release keyed on `was_first`, or move to the SQLite-atomic path (adc-4783 §5b) which needs no Python lock at all | adc-41u0 §9 |
| Async log handler | Keep stdlib logging (no `await`); if an async handler is ever added, move the log call out of the locked `def` | adc-41u0 §6.2 |
| Re-entering the lock (deadlock → *liveness* perf hazard) | Pre-locked `def` helper; review rule "never nest two `async with` on the same lock" | adc-41u0 §6.2, §8.2 |

A deadlock from non-reentrant acquisition is not a throughput problem but a
*liveness* problem (the whole failure path hangs). It is listed here because a
hung path is the extreme of "unacceptable performance impact." It is prevented
by the single-lock + helper design.

---

## 8. Performance vs. correctness trade-off

| | **No lock** (status quo code) | **`asyncio.Lock`** (adc-41u0) | **SQLite atomic** (adc-4783 §5b) |
|---|---|---|---|
| Duplicate WARNINGs on concurrent first failures | ❌ possible | ✅ prevented | ✅ prevented |
| Lost updates on `failure_count` | ❌ possible | ✅ prevented | ✅ prevented |
| Consistent multi-field snapshot | ❌ possible | ✅ (writes) | ✅ |
| Cost per failure (measured) | 0 (but wrong) | **~0.32 µs** | one SQL round-trip (~0.1–1 ms) |
| Survives restart / multi-worker | n/a (in-memory) | ❌ no | ✅ yes |
| New dependency | none | none | none (aiosqlite already present) |

**The trade-off is overwhelmingly in favor of the lock.** The correctness
defects it prevents are real and enumerated in adc-4ol5 (duplicate alerts,
inaccurate counts, contradictory status snapshots). The price is ~0.32 µs on a
path that is dormant and, when active, is an error path. There is no realistic
adc workload where 0.32 µs on the Telegram-error path is worth tolerating
duplicate WARNINGs or a wrong failure count.

**When you would NOT pick the lock** (and the design already says so,
adc-41u0 §9): if the state must survive restarts or span workers, skip the
in-memory lock entirely and use the SQLite-atomic pattern. That is a
*correctness* upgrade (durability, cross-process), not a performance one — it
actually costs *more* per op (~0.1–1 ms SQL round-trip vs ~0.32 µs) and is
justified only by the durability requirement. Do not reach for SQLite "for
performance" — reach for it for durability.

---

## 9. Acceptable vs. unacceptable impact (the budget)

State an explicit budget so future changes can be judged against it rather
than against vibes.

**Dispatch latency context (the denominator).** A `/dispatch` round-trip
makes multiple LLM calls (intent classify + per-strand fetch + synthesize),
each on the order of **seconds**. A 1-second dispatch is the fast end. So any
cost that is a small fraction of one second is invisible to the user.

| Threshold | Value | Verdict |
|---|---|---|
| Lock overhead per failure (measured) | ~0.32 µs | ✅ **Acceptable** — ~3×10⁻⁷ of a 1-s dispatch; below noise |
| Uncontended acquire (measured) | ~0.47 µs | ✅ acceptable |
| 100 fully-serialized failures (measured) | ~60–90 µs total | ✅ acceptable — far below a single LLM call |
| Lock-free status read (measured) | ~0.09 µs | ✅ acceptable — reads free by design |
| One SQL round-trip (SQLite-atomic path) | ~0.1–1 ms | ⚠️ acceptable *only* if durability required; otherwise over-engineering |
| Holding lock across a notification HTTP call | up to 10 s × N serialized | ❌ **Unacceptable** — must never happen; prevented by `def` helper |
| Deadlock from lock re-entry | hang (infinite) | ❌ **Unacceptable** — prevented by single-lock + helper |

**Rule of thumb for future changes:** if a proposed change keeps the
in-section work to pure CPU (no `await`), its performance impact is, by
construction, in the "acceptable" row and needs no further analysis. If a
change would introduce an `await` inside the section, it crosses into the
"unacceptable" row and must be restructured (do the I/O after release, or move
to the SQLite-atomic path).

---

## 10. Mitigation strategies (summary)

1. **Lock-free reads** (already chosen, adc-41u0 §5 op 5–7). `get_bridge_status`
   takes no lock — measured ~0.09 µs. Monitoring tolerates stale-but-consistent
   values. This keeps the only *frequently-called* live path on the singleton
   off the lock entirely.
2. **No-I/O critical section, enforced by a `def` helper** (adc-41u0 §6.2). The
   single most important mitigation: it makes the "unacceptable" row of §9
   structurally unreachable, not merely discouraged.
3. **Single lock, one logical state object** (adc-41u0 §4). Refusing to pull
   `_is_reachable` under the same lock keeps the success and health-check paths
   lock-free, so they cannot contend the failure lock.
4. **I/O after release, keyed on `was_first`** (adc-41u0 §6.1). The notification
   (the only I/O the design anticipates) runs outside the lock, so its latency
   — seconds — never serializes other failures.
5. **Upgrade path to SQLite atomics** (adc-4783 §5b; adc-41u0 §9). If the path
   ever becomes both hot and high-frequency, or needs durability, replace the
   Python lock with an atomic `UPDATE … WHERE claimed=0` + `rowcount` CAS.
   This is a *correctness/durability* escalation, recorded so it need not be
   re-derived; it is **not** a performance fix (it costs more per op).

No additional mitigation is warranted today. The strategy is already on the
right side of every threshold in §9.

---

## 11. Verification approach (for the implementation bead)

Performance-relevant checks to add alongside the correctness tests in
adc-41u0 §10:

- **Structural no-I/O guard:** assert `inspect.iscoroutinefunction(...) is
  False` for `_record_failure_locked` (it must be a plain `def`). This is the
  load-bearing performance invariant — if it ever becomes `async`, §7's risk
  materializes.
- **Read-doesn't-block:** while a task holds the lock (via a test-only seam),
  `get_bridge_status()` returns promptly — proving reads are lock-free
  (already in adc-41u0 §10; restated here as a *performance* assertion).
- **No regression budget:** an optional microbenchmark (the script in §8, or a
  pytest-benchmark variant) asserting isolated lock overhead stays in the
  sub-microsecond band. Low priority given the path is dormant, but cheap
  insurance against an accidental `await` creeping into the helper.

---

## 12. Summary

- **Cost (measured):** ~0.32 µs isolated lock overhead per failure; ~0.92 µs
  for the whole locked section; flat ~1.0 µs/op under 2–128-way contention;
  ~0.09 µs for the lock-free read. These are **3,000–4,000× lower** than the
  "2–5 ms" figures in adc-50ld/adc-4ol5, which conflated lock cost with
  logging-I/O latency.
- **Hot paths:** none that hold the lock. The lock-guarded failure path is
  **dormant** (no live callers of `send_message`), and even when active it is
  an error path on a secondary channel. The frequently-called status read is
  lock-free.
- **Trade-off:** the lock prevents real correctness defects (duplicate alerts,
  lost counts, inconsistent snapshots) at sub-microsecond cost. Overwhelmingly
  worth it; no scenario favors dropping the lock for speed.
- **Real risk:** not acquisition cost, but holding the lock across I/O (a 10 s
  notification timeout serialized × N). Prevented structurally by the
  `def`-helper rule.
- **Budget:** any change that keeps the section free of `await` is
  automatically within the acceptable band; any change that introduces an
  `await` inside the section is unacceptable and must be restructured.
- **Escalation:** switch to SQLite atomics (adc-4783 §5b) only if durability or
  multi-worker correctness is required — not for performance.

---

## References

- **Strategy decision:** `notes/adc-41u0.md` (adc-41u0) — the locking design this
  doc quantifies. Especially §6.1–6.2 (no-I/O critical section, `def` helper)
  and §9 (SQLite upgrade path).
- **Mechanism research:** `notes/adc-4783.md` (adc-4783) — `asyncio.Lock` behavior,
  GIL atomicity, and the SQLite-atomic CAS pattern (§5b).
- **Parent approach:** `notes/adc-50ld-thread-safety-approach.md` (adc-50ld) —
  race identification; its performance figures are superseded by §6 here.
- **Race catalog:** `docs/race-conditions-first-failure-state.md` (adc-4ol5) —
  the correctness defects the lock prevents; its performance figures are
  superseded by §6 here.
- **Current code:** `src/telegram/fallback.py` (`_handle_send_failure` at
  `:198`, 3 call sites in async `send_message` at `:84,89,93`; singleton
  created in lifespan at `src/main.py:152`; status read at `src/main.py:1474`).
- **Benchmark script:** `~/scratch/adc-4rh3-lock-bench.py` (full listing below).

---

## Appendix: benchmark script

`~/scratch/adc-4rh3-lock-bench.py` — run with `python3`. Reproduces every
number in [§4](#4-measured-metrics). Kept in `~/scratch/` per the
"experimental code goes in `~/scratch/`" rule; listed here so the results are
reproducible without the original file.

```python
#!/usr/bin/env python3
"""Benchmark: asyncio.Lock contention for the adc-41u0 first-failure strategy."""
import asyncio, logging, time
from datetime import datetime, timezone

logging.basicConfig(level=logging.CRITICAL)   # measure lock cost, not log I/O
logger = logging.getLogger("bench")

class Bench:
    def __init__(self):
        self._has_logged_first_failure = False
        self._failure_count = 0
        self._first_failure_ts = None
        self._last_failure_logged = None
        self._lock = asyncio.Lock()

    def _record_failure_locked(self, error_context: str) -> bool:   # plain def — no await possible
        self._failure_count += 1
        now = datetime.now(timezone.utc)
        if not self._has_logged_first_failure:
            self._has_logged_first_failure = True
            self._first_failure_ts = now
            self._last_failure_logged = now
            logger.warning("first %s", error_context)
            return True
        self._last_failure_logged = now
        logger.debug("repeat #%d %s", self._failure_count, error_context)
        return False

    async def handle_failure(self, error_context: str = "e") -> bool:
        was_first = False
        async with self._lock:
            was_first = self._record_failure_locked(error_context)
        return was_first

    async def handle_failure_no_lock(self, error_context: str = "e") -> bool:
        return self._record_failure_locked(error_context)

    def get_status(self) -> dict:
        return {"failure_count": self._failure_count,
                "has_logged_first_failure": self._has_logged_first_failure}

def fmt_ns(ns):
    if ns < 1_000: return f"{ns:7.1f} ns"
    if ns < 1_000_000: return f"{ns/1_000:7.2f} us"
    return f"{ns/1_000_000:7.2f} ms"

async def bench_uncontended(n=1_000_000):
    lock = asyncio.Lock()
    t0 = time.perf_counter_ns()
    for _ in range(n):
        async with lock: pass
    return (time.perf_counter_ns() - t0) / n

async def bench_read(n=1_000_000):
    b = Bench()
    t0 = time.perf_counter_ns()
    for _ in range(n): b.get_status()
    return (time.perf_counter_ns() - t0) / n

async def bench_contended(workers, total_ops):
    b = Bench()
    done = {"n": 0}
    async def runner():
        while done["n"] < total_ops:
            await b.handle_failure("err"); done["n"] += 1
    t0 = time.perf_counter_ns()
    await asyncio.gather(*[asyncio.create_task(runner()) for _ in range(workers)])
    return (time.perf_counter_ns() - t0) / done["n"], b._failure_count

async def bench_with_work(n=500_000, lock=True):
    b = Bench()
    fn = b.handle_failure if lock else b.handle_failure_no_lock
    t0 = time.perf_counter_ns()
    for _ in range(n): await fn("err")
    return (time.perf_counter_ns() - t0) / n

async def main():
    unc = await bench_uncontended()
    rd  = await bench_read()
    wl  = await bench_with_work(lock=True)
    wn  = await bench_with_work(lock=False)
    print(f"uncontended acquire+release : {fmt_ns(unc)}")
    print(f"lock-free read              : {fmt_ns(rd)}")
    print(f"section, 1 coroutine +lock  : {fmt_ns(wl)}")
    print(f"section, 1 coroutine  no    : {fmt_ns(wn)}")
    print(f"isolated lock overhead      : {fmt_ns(wl - wn)}")
    for w in (2, 4, 8, 16, 32, 64, 128):
        ns, count = await bench_contended(w, 200_000)
        print(f"contended {w:3d} workers -> {fmt_ns(ns)}/op (count={count})")

if __name__ == "__main__":
    asyncio.run(main())
```
