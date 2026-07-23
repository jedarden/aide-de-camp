"""
Bead watcher daemon: monitors NEEDLE beads and pushes results to surfaces.

Watches for bead close events, reads results from bead metadata, and pushes
to active surfaces via SSE or Telegram fallback.
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from ..session.store import (
    SessionStore,
    CIRCUIT_BREAKER_REFUSAL_THRESHOLD,
    CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS,
)
from ..sse.broadcaster import (
    broadcast_result,
    get_broadcaster,
    SSEEvent,
    EventType,
)
from ..surface.router import SurfaceRouter
from ..telegram.fallback import TelegramFallback, get_telegram_fallback

logger = logging.getLogger(__name__)


@dataclass
class BeadEvent:
    """A bead state change event."""
    bead_id: str
    event_type: str  # 'created', 'updated', 'closed', 'commented'
    timestamp: int
    data: dict


class BeadWatcher:
    """
    Watches for bead close events and routes results to surfaces.

    Detection is CLI-only (plan §10 Bead Watcher): each tick runs
    `bf list --status closed --json` via a subprocess from the aide-de-camp
    checkout (the beads workspace) and emits only beads whose close time is
    newer than an in-memory close-timestamp high-water mark. The CLI is the
    sole source of bead state -- the watcher never reads the bf workspace's
    private SQLite store or its flush checkpoint directly (both are documented
    corruption/staleness footguns in this workspace).

    Once a closure is detected, the existing per-event stage resolves routing
    metadata from the bead's flat `labels` array -- escalate/handler.py encodes
    session_id / origin_surface_id / urgency as `key=value` labels -- and pushes
    the result to active surfaces via SSE, falling back to Telegram.
    """

    # Poll interval (plan §10 Bead Watcher: "default 30s"). Kept as the
    # class-level default; the effective per-instance interval lives in
    # ``self.check_interval_seconds`` (constructor arg > env > this default).
    CHECK_INTERVAL_SECONDS = 30
    # Exponential backoff schedule for supervisor restarts of a crashed watch
    # task (plan §10: "restarted with backoff"). Each consecutive crash
    # advances one entry; the final value is the cap, so a pathological
    # crash loop cannot spin faster than every 32s.
    RESTART_BACKOFF_SECONDS = (2.0, 4.0, 8.0, 16.0, 32.0)
    # Env override for the poll interval (seconds). Honored when no explicit
    # constructor arg is passed, so operators can tune without code changes.
    INTERVAL_ENV = "ADC_WATCHER_CHECK_INTERVAL_SECONDS"
    # bf (bead-forge) CLI binary used for detection (plan §10: "Detection is
    # CLI-only: the watcher polls `bf list --status closed`"). Resolved via
    # PATH; inject an absolute path (or a missing one) for tests. The server is
    # launched by a user whose PATH includes ~/.local/bin, where bf lives.
    BF_BIN = "bf"
    # Directory bf runs from -- the aide-de-camp checkout, which is this app's
    # beads workspace (plan: "All bf invocations run from the aide-de-camp
    # repo's beads workspace" / Beads-Workspace Scoping). Absolute because the
    # server may be launched from any CWD; bf resolves its workspace from cwd.
    BF_WORKSPACE = "/home/coding/aide-de-camp"
    # Per-invocation cap on `bf list` (seconds). bf reads a local SQLite store,
    # so this is normally sub-second; the cap only bounds a wedged CLI so one
    # tick cannot stall the watch loop. A timeout is logged, not fatal.
    SUBPROCESS_TIMEOUT_SECONDS = 10.0
    # Monitoring config path (plan §10: Ambient monitoring tick)
    MONITORING_CONFIG_PATH = "/home/coding/aide-de-camp/config/monitoring.yaml"
    # Default monitoring tick interval (seconds) - plan §10: default 300 (5 minutes)
    MONITORING_TICK_INTERVAL_SECONDS = 300

    def __init__(
        self,
        store: SessionStore,
        router: SurfaceRouter,
        bf_bin: str | None = None,
        bf_workspace: str | None = None,
        subprocess_timeout_seconds: float | None = None,
        telegram_fallback: TelegramFallback | None = None,
        check_interval_seconds: float | None = None,
    ):
        self.store = store
        self.router = router
        # bf (bead-forge) CLI invocation config (plan §10: detection is
        # CLI-only -- poll `bf list --status closed`). The binary runs from the
        # aide-de-camp checkout (the beads workspace; Beads-Workspace Scoping)
        # and never reads the CLI's private store files directly. Injectable so
        # tests can point at a fake/missing binary without touching PATH.
        self._bf_bin = bf_bin or self.BF_BIN
        self._bf_workspace = bf_workspace or self.BF_WORKSPACE
        self._subprocess_timeout = (
            subprocess_timeout_seconds
            if subprocess_timeout_seconds is not None
            else self.SUBPROCESS_TIMEOUT_SECONDS
        )
        # Telegram delivery surface. Defaults to None and is resolved lazily to
        # the shared singleton (get_telegram_fallback) on first send, so the
        # bead watcher uses the SAME configured chat id, bridge URL,
        # reachability, and failure-tracking state as send_exception() /
        # send_workload_summary() in src/telegram/fallback.py. Injectable so
        # tests can drive the delivery path with a fake. (adc-372c)
        self._telegram_fallback = telegram_fallback
        # Effective poll interval: explicit arg > env override > class default
        # (30s, plan §10). Resolved once at construction; the lifespan wiring in
        # src/main.py passes no arg, so production honors the env/default.
        if check_interval_seconds is None:
            env_val = os.getenv(self.INTERVAL_ENV)
            check_interval_seconds = (
                float(env_val) if env_val else self.CHECK_INTERVAL_SECONDS
            )
        self.check_interval_seconds = float(check_interval_seconds)
        self._running = False
        # The supervisor task owns the watch-task lifecycle (spawn, await,
        # restart-on-crash). _watch_task is the currently-running poll loop;
        # it is reassigned by the supervisor on each restart. (adc-4afi)
        self._supervisor_task: Optional[asyncio.Task] = None
        self._watch_task: Optional[asyncio.Task] = None
        # Ambient monitoring task - runs independently from bead watch loop
        self._ambient_task: Optional[asyncio.Task] = None
        # Consecutive crashes since the last healthy tick; drives the backoff
        # schedule. Reset to 0 whenever a tick completes successfully.
        self._restart_count = 0
        # Liveness state, read by the GET /health watcher block (child 3).
        # last_tick_at is epoch seconds (time.time()); 0.0 means "never ticked".
        self.last_tick_at: float = 0.0
        self.tick_count: int = 0
        # Close-timestamp high-water mark: the newest bead close time (UTC epoch
        # seconds) already processed. In-memory only. Each tick emits only
        # closures strictly newer than this mark, then advances it. On the first
        # tick (and after any restart, since the mark is in-memory) the mark is
        # seeded to the newest existing close time and nothing is emitted -- so
        # a restart re-reads but does NOT re-deliver already-closed beads.
        # (adc-qw85: replaces the former in-memory _processed_beads ID set.)
        self._close_highwater: Optional[float] = None

        # Ambient monitoring state (plan §10: Ambient monitoring tick)
        # Monitoring config mtime for hot-reload detection
        self._monitoring_config_mtime: float = 0.0
        # Loaded monitoring config (cached between hot-reloads)
        self._monitoring_config: dict = {}
        # Monitoring tick interval (seconds) - loaded from config, hot-reloaded
        self._monitoring_tick_interval: float = float(self.MONITORING_TICK_INTERVAL_SECONDS)
        # Last monitoring tick time (for health tracking)
        self.last_monitoring_tick_at: float = 0.0
        self.monitoring_tick_count: int = 0

    async def start(self) -> None:
        """Start the bead watcher daemon.

        Spawns two independent tasks:
        1. Lifespan supervisor task that owns the bead watch-task lifecycle
        2. Ambient monitoring task that runs on its own timer (plan §10)

        The bead watch loop polls for closed beads and manages circuit breaker.
        The ambient monitoring loop runs independently on tick_interval_seconds from
        monitoring.yaml config (default 300s). start()/stop() keep their signatures
        and the lifespan wiring in src/main.py is unchanged — ``_bead_watcher``
        stays the module-level instance.
        """
        self._running = True
        # Start bead watch supervisor
        self._supervisor_task = asyncio.create_task(
            self._supervise(), name="bead-watcher-supervisor"
        )
        # Start ambient monitoring loop (independent timer)
        self._ambient_task = asyncio.create_task(
            self._ambient_monitoring_loop(), name="ambient-monitoring-loop"
        )
        logger.info(
            "Bead watcher started (bead interval=%ss, ambient interval=%ss)",
            self.check_interval_seconds,
            self._monitoring_tick_interval,
        )

    async def stop(self) -> None:
        """Stop the bead watcher daemon.

        Flags shutdown, then cancels and awaits the supervisor (which in turn
        tears down the watch task it spawned). The watch task is cancelled
        explicitly as well: cancelling a supervisor awaiting another task does
        not automatically cancel the awaited task. Also cancels the ambient
        monitoring task.
        """
        self._running = False
        supervisor = self._supervisor_task
        if supervisor and not supervisor.done():
            supervisor.cancel()
            try:
                await supervisor
            except asyncio.CancelledError:
                pass
        watch = self._watch_task
        if watch and not watch.done():
            watch.cancel()
            try:
                await watch
            except BaseException:  # noqa: BLE001 — tearing down, swallow anything
                pass
        ambient = self._ambient_task
        if ambient and not ambient.done():
            ambient.cancel()
            try:
                await ambient
            except BaseException:  # noqa: BLE001 — tearing down, swallow anything
                pass
        logger.info("Bead watcher stopped")

    async def _supervise(self) -> None:
        """Supervise the watch task: restart it on crash with backoff.

        The watch loop catches per-iteration (transient) exceptions itself and
        keeps polling — those never reach here. This layer handles the case the
        inner loop cannot: the task ending outright (an exception that is not a
        transient ``Exception`` -- e.g. a ``BaseException`` raised mid-tick --
        or the loop returning). On such a death, while we are still meant to be
        running, we log and respawn the task after an exponentially-growing
        backoff (2s, 4s, 8s, ... capped at 32s). Backoff resets to the short
        end once a tick completes successfully (see ``_watch_loop``).

        ``stop()`` sets ``_running = False`` before cancelling the supervisor,
        so a clean shutdown is distinguished from an unexpected task death by
        the ``_running`` flag rather than by exception type.
        """
        while self._running:
            self._watch_task = asyncio.create_task(
                self._watch_loop(),
                name=f"bead-watcher-tick-{self._restart_count}",
            )
            crash_reason: Optional[BaseException] = None
            try:
                await self._watch_task
            except asyncio.CancelledError:
                # Supervisor itself cancelled -- only stop() does that. Exit.
                return
            except (KeyboardInterrupt, SystemExit):
                # Process-level signals: never swallow, let them propagate.
                raise
            except BaseException as exc:  # noqa: BLE001 — must catch task death
                crash_reason = exc

            if not self._running:
                # stop() raced with the task ending -- clean shutdown.
                return

            self._restart_count += 1
            backoff = self._next_backoff()
            if crash_reason is not None:
                logger.warning(
                    "Bead watcher task crashed (%s); restarting in %.1fs "
                    "(restart #%d)",
                    type(crash_reason).__name__,
                    backoff,
                    self._restart_count,
                    exc_info=True,
                )
            else:
                logger.warning(
                    "Bead watcher task ended unexpectedly; restarting in %.1fs "
                    "(restart #%d)",
                    backoff,
                    self._restart_count,
                )
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                return

    def _next_backoff(self) -> float:
        """Backoff (seconds) for the upcoming restart, growing with crashes.

        ``_restart_count`` is incremented to >= 1 before each call, so the
        first restart waits RESTART_BACKOFF_SECONDS[0] (2s), the next the
        following entry (4s), and so on; once the count exceeds the schedule
        the final (cap) value is reused.
        """
        idx = min(self._restart_count - 1, len(self.RESTART_BACKOFF_SECONDS) - 1)
        return self.RESTART_BACKOFF_SECONDS[idx]

    def _stamp_tick(self) -> None:
        """Record liveness after a completed poll tick.

        Called after every tick body resolves (success or a caught transient
        error). GET /health's watcher block reads these: ``last_tick_at``
        within 2x the interval means the task is alive, and ``tick_count`` is
        the cumulative tick count. (adc-4afi, consumed by child 3.)
        """
        self.last_tick_at = time.time()
        self.tick_count += 1

    def health_snapshot(self) -> dict:
        """Return watcher liveness snapshot for GET /health.

        Computes ``alive`` as: the watch task is running AND the last tick
        occurred within 2x the poll interval. Returns a dict with ``alive``,
        ``last_tick_at`` (epoch seconds or None if never ticked), ``tick_count``,
        and ``interval`` (seconds). If ``last_tick_at`` is 0.0 (never ticked),
        ``last_tick_at`` is None and ``alive`` is False.

        Also includes monitoring tick stats (plan §10: Ambient monitoring tick).
        """
        now = time.time()
        # Task is running if the supervisor task exists and is not done/cancelled
        task_running = (
            self._watch_task is not None
            and not self._watch_task.done()
        )
        # Last tick is fresh if within 2x the interval (0.0 means never ticked)
        tick_fresh = (
            self.last_tick_at > 0.0
            and (now - self.last_tick_at) <= (2 * self.check_interval_seconds)
        )
        return {
            "alive": task_running and tick_fresh,
            "last_tick_at": int(self.last_tick_at) if self.last_tick_at > 0.0 else None,
            "tick_count": self.tick_count,
            "interval": int(self.check_interval_seconds),
            "monitoring": {
                "last_tick_at": int(self.last_monitoring_tick_at) if self.last_monitoring_tick_at > 0.0 else None,
                "tick_count": self.monitoring_tick_count,
                "interval": int(self._monitoring_tick_interval),
                "config_mtime": self._monitoring_config_mtime,
            },
        }

    async def _watch_loop(self) -> None:
        """Main watch loop - checks for new bead events each interval.

        Each iteration runs the detection tick (``_check_for_events``), stamps
        liveness, then sleeps for the poll interval. Per-iteration exceptions
        are caught and logged so a transient error never ends the task -- the
        supervisor layer restarts the task only when it truly dies. A completed
        tick (success or caught transient error) resets the crash backoff.
        """
        while self._running:
            try:
                await self._check_for_events()
            except asyncio.CancelledError:
                raise  # shutdown signal -- let the supervisor see it
            except Exception as e:
                logger.error(f"Error in bead watch loop: {e}", exc_info=True)
            # Stamp liveness after the tick body resolves. A completed tick --
            # success or a caught transient error -- means the task is healthy,
            # so reset the crash backoff schedule.
            self._stamp_tick()
            self._restart_count = 0
            try:
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                raise

    async def _ambient_monitoring_loop(self) -> None:
        """Ambient monitoring loop - runs on independent timer (plan §10).

        Each iteration:
        1. Hot-reloads monitoring config (reads tick_interval_seconds)
        2. Runs ambient monitoring tick (fetch/diff cycle)
        3. Sleeps for tick_interval_seconds

        This loop is independent from the bead watch loop and uses a separate
        timer. Per-iteration exceptions are caught and logged so a transient error
        never ends the task.
        """
        while self._running:
            try:
                # Run ambient monitoring tick (includes hot-reload)
                await self._ambient_monitoring_tick()
            except asyncio.CancelledError:
                raise  # shutdown signal
            except Exception as e:
                logger.error(f"Error in ambient monitoring loop: {e}", exc_info=True)
            # Sleep for the configured tick interval (hot-reloaded each tick)
            try:
                await asyncio.sleep(self._monitoring_tick_interval)
            except asyncio.CancelledError:
                raise

    async def _check_for_events(self) -> None:
        """Poll for newly-closed bead events and route each to surfaces.

        Detection is CLI-only (plan §10): each tick runs `bf list --status
        closed` and emits only closures newer than the close-timestamp
        high-water mark. Every emitted record is handed to the next stage
        (``_process_bead_event``); this layer does not resolve intents or write
        results itself (child 4 owns the close -> result path).

        Also runs circuit breaker check (plan §10 The Async Path):
        polls open tracked beads for REFUSED comments, updates bead_watch state,
        fences beads that meet criteria, and creates stuck cards.

        Note: Ambient monitoring tick runs in its own separate loop
        (_ambient_monitoring_loop), not here.
        """
        events = await self._poll_closed_beads()
        for event in events:
            await self._process_bead_event(event)

        # Circuit breaker tick (plan §10 The Async Path)
        await self._check_circuit_breaker()

    async def _poll_closed_beads(self) -> list[BeadEvent]:
        """Poll closed beads via the CLI and return the newly-closed subset.

        Maintains ``self._close_highwater`` (newest close timestamp already
        processed, UTC epoch seconds). Each tick returns only beads closed
        strictly AFTER that mark and advances the mark to the newest close
        time seen this tick.

        First poll (and first after any restart, since the mark is in-memory):
        seed the mark to the newest existing close time and emit nothing,
        instead of delivering the entire already-closed backlog. This is the
        documented high-water-mark semantics -- a restart re-reads but does
        not re-deliver already-closed beads; only closures after the mark
        surface. (adc-qw85)
        """
        records = await self._run_bf_list_closed()

        # (close_epoch, record) for records whose close time parsed; sorted
        # ascending so the last entry is the newest close this tick.
        parsed: list[tuple[float, dict]] = []
        for rec in records:
            ts = self._parse_close_epoch(rec.get("closed_at"))
            if ts is None:
                continue
            parsed.append((ts, rec))
        parsed.sort(key=lambda pair: pair[0])

        if self._close_highwater is None:
            # Baseline against the current backlog without delivering it.
            if parsed:
                self._close_highwater = parsed[-1][0]
                logger.debug(
                    "Bead watcher baseline: high-water mark set to %.6f "
                    "(%d closed beads already seen; none re-delivered).",
                    self._close_highwater, len(parsed),
                )
            return []

        # Emit only closures strictly newer than the mark.
        new_events: list[BeadEvent] = []
        for ts, rec in parsed:
            if ts <= self._close_highwater:
                continue
            new_events.append(BeadEvent(
                bead_id=rec.get("id", ""),
                event_type="closed",
                timestamp=int(ts),
                data=rec,
            ))
        if new_events:
            # Advance to the newest close seen overall this tick (parsed is
            # sorted ascending, so the last is the max). Every record newer
            # than the old mark was emitted, so this is also the newest emitted.
            self._close_highwater = parsed[-1][0]
        return new_events

    async def _check_circuit_breaker(self) -> None:
        """Check circuit breaker conditions for all open watched beads.

        Plan §10 The Async Path:
        - Poll open tracked beads (every unresolved intents.bead_ref) via bf show
        - Parse REFUSED: comments past the high-water mark
        - Persist refusal counts and reasons in bead_watch table
        - Fence beads meeting criteria (3 refusals OR 24h age)
        - Set intent status to 'stuck'
        - Push 'task stuck — needs your input' card to active surface
        """
        try:
            # Step 1: Get all open watched beads
            watched_beads = await self.store.get_open_watched_beads()

            if not watched_beads:
                logger.debug("No open watched beads for circuit breaker check")
                return

            logger.debug(f"Circuit breaker checking {len(watched_beads)} open beads")

            # Step 2: For each bead, fetch comments and parse refusals
            for watch_row in watched_beads:
                bead_ref = watch_row["bead_ref"]
                high_water = watch_row["comment_high_water"]

                # Fetch bead details via bf show
                bead_details = await self._run_bf_show(bead_ref)

                if not bead_details:
                    logger.warning(f"Could not fetch bead {bead_ref} for circuit breaker check")
                    continue

                # Parse comments for refusals
                refusals = self._parse_refusals_from_comments(
                    bead_details.get("comments", []),
                    since_index=high_water,
                )

                # Update bead_watch state if we found new refusals
                if refusals:
                    # Count ALL refusals found, not just the latest one
                    refusal_count = len(refusals)
                    latest_refusal = refusals[-1]  # Most recent
                    latest_index = latest_refusal["index"]
                    latest_reason = latest_refusal["reason"]

                    # Update refusal count by the number of refusals found
                    # (not just 1, since we may have multiple new refusals in one tick)
                    await self.store.update_bead_watch_refusal(
                        bead_ref=bead_ref,
                        refusal_reason=latest_reason,
                        comment_index=latest_index,
                        refusal_count_add=refusal_count,
                    )

                    logger.info(
                        f"Bead {bead_ref}: recorded {refusal_count} refusals "
                        f"(reason: {latest_reason[:50]}...)"
                    )

            # Step 3: Check SLA flags and flag beads past deadline
            await self._check_and_flag_sla_beads()

            # Step 4: Fence beads that meet criteria
            await self._fence_needs_fencing_beads()

        except Exception as e:
            logger.error(f"Error in circuit breaker check: {e}", exc_info=True)

    async def _check_and_flag_sla_beads(self) -> None:
        """Flag beads that have passed their SLA deadline.

        Plan §10 The Async Path: Visible Aging - cards past SLA are flagged.
        """
        try:
            past_sla = await self.store.get_beads_past_sla()

            for bead_watch in past_sla:
                bead_ref = bead_watch["bead_ref"]
                await self.store.flag_sla(bead_ref)
                logger.info(f"Flagged SLA for bead {bead_ref} (past deadline)")

        except Exception as e:
            logger.error(f"Error checking SLA deadlines: {e}", exc_info=True)

    async def _fence_needs_fencing_beads(self) -> None:
        """Fence beads that meet circuit breaker criteria.

        Plan §10 The Async Path: after N refusals (default 3) or T hours without
        progress (default 24h), fence the bead to status=blocked, set intent status
        to 'stuck', and push a 'task stuck — needs your input' card.
        """
        try:
            needs_fencing = await self.store.get_beads_needing_fencing()

            for bead_watch in needs_fencing:
                bead_ref = bead_watch["bead_ref"]
                refusal_count = bead_watch["refusal_count"]
                last_reason = bead_watch.get("last_refusal_reason", "No refusal reason provided")

                await self._fence_bead(bead_ref, last_reason, refusal_count)

        except Exception as e:
            logger.error(f"Error fencing beads: {e}", exc_info=True)

    async def _fence_bead(self, bead_ref: str, refusal_reason: str, refusal_count: int) -> None:
        """Fence a single bead: block it, mark intent stuck, create stuck card.

        Args:
            bead_ref: The bead ID to fence
            refusal_reason: The reason for fencing (most recent refusal or age)
            refusal_count: Number of refusals recorded
        """
        logger.info(f"Fencing bead {bead_ref} (refusals: {refusal_count})")

        # Step 1: Fetch bead details to get origin_surface_id
        bead_details = await self._run_bf_show(bead_ref)
        origin_surface_id = None
        if bead_details:
            metadata = self._extract_metadata(bead_details)
            origin_surface_id = metadata.get("origin_surface_id")

        # Step 2: Run bf update --status blocked
        try:
            await self._run_bf_update_status(bead_ref, "blocked")
            logger.info(f"Set bead {bead_ref} to blocked status")
        except Exception as e:
            logger.error(f"Failed to block bead {bead_ref}: {e}")
            # Continue to intent update even if bf fails

        # Step 3: Mark fenced in bead_watch
        await self.store.fence_bead(bead_ref)

        # Step 4: Find intent and set status to 'stuck'
        intent = await self.store.get_intent_by_bead_ref(bead_ref)

        if not intent:
            logger.warning(f"No intent found for bead {bead_ref}; cannot set stuck status")
            return

        intent_id = intent["id"]
        session_id = intent["session_id"]
        topic_id = intent.get("topic_id")

        if not topic_id:
            logger.warning(f"Intent {intent_id} has no topic_id; cannot create stuck card")
            return

        # Step 5: Update intent status to 'stuck'
        await self.store.update_intent_status(intent_id, "stuck")
        logger.info(f"Set intent {intent_id} to stuck status")

        # Step 6: Broadcast task_stuck event via SSE
        broadcaster = get_broadcaster()
        await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.TASK_STUCK,
                data={
                    "bead_id": bead_ref,
                    "stuck_reason": refusal_reason,
                    "refusal_count": refusal_count,
                    "intent_id": intent_id,
                    "session_id": session_id,
                    "topic_id": topic_id,
                    "timestamp": int(datetime.now().timestamp()),
                },
                target_session_id=session_id,
                target_surface_id=origin_surface_id,
            )
        )

        # Step 6: Create stuck result card
        await self._create_stuck_card(
            bead_ref=bead_ref,
            intent_id=intent_id,
            session_id=session_id,
            topic_id=topic_id,
            refusal_reason=refusal_reason,
            refusal_count=refusal_count,
        )

    async def _create_stuck_card(
        self,
        bead_ref: str,
        intent_id: str,
        session_id: str,
        topic_id: str,
        refusal_reason: str,
        refusal_count: int,
    ) -> None:
        """Create a 'task stuck — needs your input' result card.

        Plan §10 The Async Path: push a stuck card with the latest refusal reason.
        """
        summary = f"Task stuck — needs your input"

        # Build card data
        data = {
            "bead_id": bead_ref,
            "stuck_reason": refusal_reason,
            "refusal_count": refusal_count,
            "message": f"This task has been blocked after {refusal_count} refusals.",
            "action_hint": "Review the bead and provide the missing information or context needed to proceed.",
        }

        # Create result
        result_id = await self.store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=summary,
            data=data,
            urgency="high",  # Stuck tasks are high urgency
        )

        logger.info(f"Created stuck card {result_id} for bead {bead_ref}")

        # Broadcast result to active surfaces
        result_for_broadcast = {
            "id": result_id,
            "result_id": result_id,
            "intent_id": intent_id,
            "topic_id": topic_id,
            "session_id": session_id,
            "summary": summary,
            "data": data,
            "urgency": "high",
            "created_at": int(datetime.now().timestamp()),
        }

        decision = await self.router.route_result(
            session_id=session_id,
            origin_surface_id=None,
            urgency="high",
        )

        if decision.target_surfaces:
            for surface in decision.target_surfaces:
                if surface.type == "telegram":
                    await self._send_to_telegram(result_for_broadcast, session_id)
                else:
                    await broadcast_result(
                        result=result_for_broadcast,
                        session_id=session_id,
                        target_surface_id=surface.id,
                    )
        elif decision.fallback_used:
            await self._send_to_telegram(result_for_broadcast, session_id)
        else:
            logger.info(f"No surface available for stuck card of bead {bead_ref}")

    async def _run_bf_show(self, bead_ref: str) -> Optional[dict]:
        """Run `bf show <bead_ref>` and return parsed bead details.

        Returns bead dict with comments list, or None on failure.
        Comments are returned as a list of {index, body, created_at} dicts.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                self._bf_bin,
                "show", bead_ref, "--json",
                cwd=self._bf_workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as e:
            logger.error(f"Failed to spawn bf show {bead_ref}: {e}")
            return None

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self._subprocess_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning(f"bf show {bead_ref} timed out")
            return None

        if proc.returncode != 0:
            logger.warning(
                f"bf show {bead_ref} exited {proc.returncode}: "
                f"{stderr_b.decode(errors='replace').strip()[:200]}"
            )
            return None

        try:
            bead_data = json.loads(stdout_b.decode(errors="replace").strip())
            return bead_data
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse bf show output for {bead_ref}: {e}")
            return None

    async def _run_bf_update_status(self, bead_ref: str, status: str) -> None:
        """Run `bf update --status <status> <bead_ref>` to fence a bead.

        Raises an exception if the command fails (non-zero exit, timeout, etc.).
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                self._bf_bin,
                "update", "--status", status, bead_ref,
                cwd=self._bf_workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as e:
            raise RuntimeError(f"Failed to spawn bf update: {e}") from e

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self._subprocess_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"bf update {bead_ref} timed out")

        if proc.returncode != 0:
            error_msg = stderr_b.decode(errors="replace").strip()
            raise RuntimeError(
                f"bf update {bead_ref} exited {proc.returncode}: {error_msg[:200]}"
            )

    @staticmethod
    def _parse_refusals_from_comments(
        comments: list, since_index: int
    ) -> list[dict]:
        """Parse REFUSED: comments from bead comment list.

        Args:
            comments: List of comment dicts from bf show
            since_index: Only parse comments with index > this

        Returns:
            List of {index, reason, created_at} for each REFUSED: comment found
        """
        REFUSED_PATTERN = re.compile(r"^\s*REFUSED:\s*(.+)$", re.MULTILINE)

        refusals: list[dict] = []

        for idx, comment in enumerate(comments):
            # Skip comments at or before the high-water mark
            # (only process comments with index > since_index)
            if idx <= since_index:
                continue

            comment_body = comment.get("body", "")
            if not isinstance(comment_body, str):
                continue

            # Check for REFUSED: prefix
            match = REFUSED_PATTERN.search(comment_body)
            if match:
                reason = match.group(1).strip()
                refusals.append({
                    "index": idx,
                    "reason": reason,
                    "created_at": comment.get("created_at"),
                })

        return refusals

    @staticmethod
    def _parse_close_epoch(closed_at: object) -> Optional[float]:
        """Parse a bf ``closed_at`` (RFC3339, up to nanosecond) to UTC epoch.

        bf emits close times with nanosecond precision and a trailing ``Z`` --
        e.g. ``2026-07-22T12:47:22.595899004Z`` -- though some records omit the
        fractional part entirely. ``datetime.fromisoformat`` (3.11+) accepts
        both forms and yields a UTC-aware datetime, so ``.timestamp()`` is
        correct regardless of the host's local timezone. Returns None on any
        parse failure (a malformed/missing close time is logged, not fatal).
        """
        if not isinstance(closed_at, str) or not closed_at.strip():
            return None
        try:
            return datetime.fromisoformat(closed_at.strip()).timestamp()
        except (ValueError, TypeError) as e:
            logger.warning("Could not parse closed_at %r: %s", closed_at, e)
            return None

    async def _run_bf_list_closed(self) -> list[dict]:
        """Run `bf list --status closed --json` and return parsed bead records.

        The CLI is the sole source of bead state (plan §10: never read the bf
        workspace's private store files directly). bf runs from the
        aide-de-camp checkout (the beads workspace; Beads-Workspace Scoping) so
        it sees every bead this app owns.

        Output is JSONL -- one JSON object per line; each non-blank line is
        parsed independently so one malformed line does not discard the rest.
        Every failure mode (missing binary, spawn error, timeout, non-zero
        exit, unparseable line) is caught and logged, returning an empty list:
        one tick's failure must not kill the watch task -- the lifespan
        supervisor (child 1) is the backstop. A caught failure simply means
        "no new closures detected this tick." (adc-qw85)
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                self._bf_bin,
                "list", "--status", "closed", "--json",
                cwd=self._bf_workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error(
                "bf binary %r not found -- bead-close detection skipped this "
                "tick. Ensure bead-forge (bf) is installed and on PATH.",
                self._bf_bin,
            )
            return []
        except OSError as e:
            logger.error("Failed to spawn bf list: %s", e, exc_info=True)
            return []

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self._subprocess_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning(
                "bf list --status closed timed out after %.1fs",
                self._subprocess_timeout,
            )
            return []

        if proc.returncode != 0:
            logger.warning(
                "bf list --status closed exited %s: %s",
                proc.returncode,
                stderr_b.decode(errors="replace").strip()[:500],
            )
            return []

        records: list[dict] = []
        for lineno, line in enumerate(
            stdout_b.decode(errors="replace").splitlines(), start=1
        ):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning(
                    "Skipping unparseable bf list line %d: %s", lineno, e
                )
        return records

    def _extract_metadata(self, bead: dict) -> dict:
        """
        Reconstruct routing metadata from a bead's flat `labels` array.

        escalate/handler.py's `_create_bead` / `_create_bead_with_type` encode
        session_id, origin_surface_id, urgency, etc. as `key=value` label
        strings (e.g. `session_id=session-1`). bf issues have NO nested
        `metadata` object -- only a flat `labels` list -- so we parse those
        `key=value` entries back into a dict, matching the encoding the escalate
        handler writes. Labels without `=` (e.g. `deferred`, `split-child`) and
        `:`-style labels (e.g. `failure-count:1`) are ignored.
        """
        metadata: dict = {}
        labels = bead.get("labels", [])
        if not isinstance(labels, list):
            return metadata
        for label in labels:
            if not isinstance(label, str) or "=" not in label:
                continue
            key, _, value = label.partition("=")
            key = key.strip()
            if key:
                metadata[key] = value.strip()
        return metadata

    async def _process_bead_event(self, event: BeadEvent) -> None:
        """Process a closed bead event: resolve intent, write result, route to surfaces.

        For each closed bead:
        1. Look up intent via intents.bead_ref (not label parsing)
        2. If no matching intent, skip (most bf beads are not escalate-tracked)
        3. Write results row via store.create_result
        4. Mark intent resolved
        5. SSE push using existing router (with Telegram fallback)
        """
        bead_id = event.bead_id
        bead_data = event.data

        # Step 1: Look up intent by bead_ref (NOT from labels)
        intent = await self.store.get_intent_by_bead_ref(bead_id)

        if not intent:
            # No matching intent - not an escalate-tracked bead.
            # This is expected for most bf beads, so debug-log only.
            logger.debug(f"Closed bead {bead_id} has no matching intent.bead_ref; skipping")
            return

        # Extract intent context
        intent_id = intent["id"]
        session_id = intent["session_id"]
        topic_id = intent.get("topic_id")

        if not topic_id:
            logger.warning(f"Intent {intent_id} for bead {bead_id} has no topic_id; skipping result write")
            return

        # Step 2: Extract result from bead (reusing existing body logic)
        result = await self._extract_result_from_bead(bead_data, session_id)

        if not result:
            logger.warning(f"Could not extract result from bead {bead_id}")
            return

        # Step 3: Write results row via store.create_result
        # Build result data matching the create_result signature
        summary = result.get("summary", "Bead resolved")
        data = result.get("data", {})
        urgency = result.get("urgency", "normal")

        try:
            result_id = await self.store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary=summary,
                data=data,
                urgency=urgency,
            )
            logger.debug(f"Created result {result_id} for bead {bead_id}")
        except Exception as e:
            logger.error(f"Failed to create result for bead {bead_id}: {e}", exc_info=True)
            return

        # Construct the result dict for SSE broadcast (must include result_id)
        result_for_broadcast = {
            "id": result_id,
            "result_id": result_id,  # For test compatibility
            "intent_id": intent_id,
            "topic_id": topic_id,
            "session_id": session_id,
            "summary": summary,
            "data": data,
            "urgency": urgency,
            "created_at": int(datetime.now().timestamp()),
        }

        # Step 4: Mark intent resolved
        try:
            await self.store.update_intent_status(intent_id, "resolved")
            logger.debug(f"Marked intent {intent_id} resolved for bead {bead_id}")
        except Exception as e:
            logger.error(f"Failed to mark intent {intent_id} resolved: {e}", exc_info=True)
            # Continue to routing even if status update fails

        # Step 5: SSE push per Surface Routing Rules
        # Use existing router + broadcast_result / telegram fallback path
        # Get routing decision - no origin_surface_id from bead, use None
        decision = await self.router.route_result(
            session_id=session_id,
            origin_surface_id=None,
            urgency=urgency,
        )

        # Route to target surfaces
        if decision.target_surfaces:
            for surface in decision.target_surfaces:
                if surface.type == "telegram":
                    await self._send_to_telegram(result_for_broadcast, session_id)
                else:
                    # SSE broadcast
                    await broadcast_result(
                        result=result_for_broadcast,
                        session_id=session_id,
                        target_surface_id=surface.id,
                    )
        elif decision.fallback_used:
            # Fallback to Telegram
            await self._send_to_telegram(result_for_broadcast, session_id)
        else:
            # No surface available - result stays in queue
            logger.info(f"No surface available for bead {bead_id}, result queued")

        # Step 6: Clean up bead_watch row (bead is closed, no longer watched)
        try:
            await self.store.delete_bead_watch(bead_id)
            logger.debug(f"Deleted bead_watch row for closed bead {bead_id}")
        except Exception as e:
            logger.warning(f"Failed to delete bead_watch row for {bead_id}: {e}")

    async def _extract_result_from_bead(self, bead: dict, session_id: str) -> Optional[dict]:
        """Extract result data from a terminal bead (real bf schema)."""
        metadata = self._extract_metadata(bead)

        # bf stores the bead body in `description` (NOT `body`); fall back to
        # notes then title so the summary is never empty.
        body = bead.get("description") or bead.get("notes") or bead.get("title") or ""

        return {
            "id": bead.get("id"),
            "type": "bead_result",
            "summary": body[:200] if len(body) > 200 else body,  # Truncate for summary
            "data": {
                "bead_id": bead.get("id"),
                "title": bead.get("title"),
                "issue_type": bead.get("issue_type"),
                "description": body,
                "status": bead.get("status"),
            },
            "urgency": metadata.get("urgency", "normal"),
            "created_at": int(datetime.now().timestamp()),
            "surfaced_at": int(datetime.now().timestamp()),
        }

    async def _send_to_telegram(self, result: dict, session_id: str) -> bool:
        """Send a result to Telegram via the shared TelegramFallback singleton.

        Uses the single configured chat id (ADC_TELEGRAM_CHAT_ID) -- there is
        intentionally NO multi-user session→chat mapping, since aide-de-camp is
        a single-user personal app (plan.md Tech Stack: "single-user app"). When
        no chat id is configured this is a graceful no-op: a WARNING is logged
        and False is returned, matching send_exception() /
        send_workload_summary() and the pre-config behavior. When configured,
        the result is formatted via ``_format_telegram_message`` and delivered
        through ``send_message``, returning the bridge's real success/failure.
        """
        fallback = self._telegram_fallback or get_telegram_fallback()

        if fallback.chat_id is None:
            logger.warning(
                f"Cannot send result to Telegram for session {session_id}: "
                f"no Telegram chat id configured (set ADC_TELEGRAM_CHAT_ID). "
                f"Result push skipped."
            )
            return False

        message = self._format_telegram_message(result)
        return await fallback.send_message(fallback.chat_id, message)

    def _format_telegram_message(self, result: dict) -> str:
        """Format result as Telegram message."""
        summary = result.get("summary", "Result available")
        urgency = result.get("urgency", "normal")

        emoji_map = {
            "critical": "🚨",
            "high": "⚠️",
            "normal": "📌",
            "low": "💬",
        }

        emoji = emoji_map.get(urgency, "📌")

        # Build message
        lines = [
            f"{emoji} {summary}",
        ]

        # Add detail if available
        data = result.get("data", {})
        if "bead_id" in data:
            lines.append(f"Bead: {data['bead_id']}")

        return "\n".join(lines)

    async def _ambient_monitoring_tick(self) -> None:
        """Run ambient monitoring tick (plan §10: Ambient monitoring tick).

        - Hot-reloads config/monitoring.yaml (mtime-checked cache)
        - Evaluates each rule against watched topics
        - Runs fetch-matrix sources via src/monitoring/ambient.py
        - Diffs against topic_context_cache
        - Writes results rows with intent_id=NULL when rules fire
        - Broadcasts via SSE per Surface Routing Rules
        """
        try:
            # Step 1: Hot-reload monitoring config if changed
            await self._hot_reload_monitoring_config()

            # Step 2: Get monitoring rules from config
            active_topics = self._monitoring_config.get("monitoring", {}).get("active_topics", [])

            if not active_topics:
                logger.debug("No active monitoring topics configured")
                return

            logger.debug(f"Ambient monitoring tick: checking {len(active_topics)} topics")

            # Step 3: Import ambient monitor module (lazy import to avoid circular deps)
            from ..monitoring.ambient import AmbientMonitor

            # Create a temporary ambient monitor instance for this tick
            # (We don't keep a long-running instance - each tick creates its own
            # to ensure config hot-reload is respected)
            ambient_monitor = AmbientMonitor()

            # Step 4: Evaluate each rule
            for topic_rule in active_topics:
                topic_id = topic_rule.get("topic_id")
                project_slug = topic_rule.get("project_slug")
                intent_type = topic_rule.get("intent_type")
                urgency = topic_rule.get("urgency", "normal")
                filters = topic_rule.get("filters", [])
                notification_threshold = topic_rule.get("notification_threshold", "any_change")

                if not topic_id:
                    continue

                try:
                    # Check current state using ambient monitor
                    from ..monitoring.ambient import MonitoringRule
                    rule = MonitoringRule(
                        topic_id=topic_id,
                        project_slug=project_slug,
                        intent_type=intent_type,
                        check_interval=0,  # Not used for one-shot check
                        urgency=urgency,
                        filters=filters,
                        notification_threshold=notification_threshold,
                    )

                    current_state = await ambient_monitor.check_topic_state(rule)

                    if not current_state:
                        logger.debug(f"No state data for topic {topic_id}")
                        continue

                    # Step 5: Get topic context cache for diffing
                    cached_context = await self._get_topic_context_cache(topic_id)

                    # Step 6: Detect state change
                    has_change = self._detect_state_change(
                        current_state=current_state,
                        cached_context=cached_context,
                        notification_threshold=notification_threshold,
                    )

                    if has_change:
                        logger.info(f"Monitoring rule fired for topic {topic_id}")
                        await self._write_monitoring_result(
                            topic_id=topic_id,
                            project_slug=project_slug or "unknown",
                            current_state=current_state,
                            cached_context=cached_context,
                            urgency=urgency,
                        )

                    # Update topic context cache (even on first check, to establish baseline)
                    await self._update_topic_context_cache(topic_id, current_state)

                except Exception as e:
                    logger.error(f"Error evaluating monitoring rule for topic {topic_id}: {e}", exc_info=True)
                    continue

            # Stamp monitoring tick time for health tracking
            self.last_monitoring_tick_at = time.time()
            self.monitoring_tick_count += 1

        except Exception as e:
            logger.error(f"Error in ambient monitoring tick: {e}", exc_info=True)

    async def _hot_reload_monitoring_config(self) -> None:
        """Hot-reload monitoring config if file has changed (mtime-checked cache).

        Loads tick_interval_seconds from config and updates the tick interval.
        Plan §10: Hot-Reload Architecture - mtime-checked cache like all artifacts.
        """
        try:
            config_path = Path(self.MONITORING_CONFIG_PATH)
            if not config_path.exists():
                logger.warning(f"Monitoring config not found: {self.MONITORING_CONFIG_PATH}")
                return

            # Check mtime
            current_mtime = config_path.stat().st_mtime
            if current_mtime <= self._monitoring_config_mtime:
                # Config unchanged, skip reload
                return

            logger.info(f"Hot-reloading monitoring config from {self.MONITORING_CONFIG_PATH}")

            # Load YAML config
            import yaml
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            # Update cached config
            self._monitoring_config = config
            self._monitoring_config_mtime = current_mtime

            # Update tick interval from config
            new_interval = config.get("tick_interval_seconds", self.MONITORING_TICK_INTERVAL_SECONDS)
            self._monitoring_tick_interval = float(new_interval)

            logger.info(f"Monitoring config reloaded: tick_interval={self._monitoring_tick_interval}s")

        except Exception as e:
            logger.error(f"Error hot-reloading monitoring config: {e}", exc_info=True)

    async def _get_topic_context_cache(self, topic_id: str) -> Optional[dict]:
        """Get cached context data for a topic from topic_context_cache table."""
        try:
            async with aiosqlite.connect(self.store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT context_data FROM topic_context_cache WHERE topic_id = ?",
                    (topic_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        import json
                        return json.loads(row["context_data"])
        except Exception as e:
            logger.warning(f"Error getting topic context cache for {topic_id}: {e}")
        return None

    async def _update_topic_context_cache(self, topic_id: str, context_data: dict) -> None:
        """Update topic context cache with fresh data."""
        try:
            import json
            from datetime import datetime, timezone

            now = int(datetime.now(timezone.utc).timestamp())
            # Set expiry to 1 hour from now
            expires_at = now + 3600

            context_json = json.dumps(context_data)

            async with aiosqlite.connect(self.store.db_path) as db:
                # Use INSERT OR REPLACE to upsert
                await db.execute(
                    """INSERT OR REPLACE INTO topic_context_cache
                       (topic_id, context_data, fetched_at, expires_at)
                       VALUES (?, ?, ?, ?)""",
                    (topic_id, context_json, now, expires_at)
                )
                await db.commit()

            logger.debug(f"Updated topic context cache for {topic_id}")

        except Exception as e:
            logger.warning(f"Error updating topic context cache for {topic_id}: {e}")

    def _detect_state_change(
        self,
        current_state: dict,
        cached_context: Optional[dict],
        notification_threshold: str,
    ) -> bool:
        """Detect if state has changed since last check.

        Args:
            current_state: Current state from fetch
            cached_context: Previous state from topic_context_cache
            notification_threshold: 'any_change' | 'state_change'

        Returns:
            True if significant change detected
        """
        if not cached_context:
            # First check - baseline state, no notification
            return False

        if notification_threshold == "any_change":
            # Any field change triggers notification
            return current_state != cached_context
        elif notification_threshold == "state_change":
            # Only notify if specific state fields change
            state_fields = ["phase", "status", "health", "ready", "sync_status", "restarts"]
            return any(
                str(current_state.get(field)) != str(cached_context.get(field))
                for field in state_fields
            )

        return False

    async def _write_monitoring_result(
        self,
        topic_id: str,
        project_slug: str,
        current_state: dict,
        cached_context: Optional[dict],
        urgency: str,
    ) -> None:
        """Write a monitoring result to the session store.

        Plan §10: monitoring-originated results have:
        - topic_id set
        - intent_id NULL (system-originated, no utterance)
        - result_type 'monitoring:{project_slug}'
        - urgency from monitoring config
        - deterministic summary (no LLM)

        Result enters Surface Routing Rules like any other.
        """
        try:
            import json

            # Find or get the topic (should already exist from monitoring setup)
            # Use default monitoring session for now
            session_id = "monitoring"

            # Find or create topic
            topic_found, created = await self.store.find_or_create_topic(
                label=topic_id,
                session_id=session_id,
                topic_type="project",
                project_slugs=[project_slug] if project_slug else None,
            )

            # Build result data
            result_data = {
                "monitoring": True,
                "current_state": current_state,
                "previous_state": cached_context,
                "project_slug": project_slug,
            }

            # Add diff if we have previous state
            if cached_context:
                result_data["diff"] = self._compute_state_diff(cached_context, current_state)

            # Generate deterministic summary (no LLM)
            summary = self._generate_monitoring_summary(
                topic_id=topic_id,
                current_state=current_state,
                previous_state=cached_context,
            )

            # Write result with intent_id=NULL (plan §10: monitoring-originated results)
            result_id = await self.store.create_result(
                intent_id=None,  # NULL for monitoring-originated results
                topic_id=topic_found,
                session_id=session_id,
                summary=summary,
                data=result_data,
                urgency=urgency,
                result_type=f"monitoring:{project_slug}",  # Monitoring result type
            )

            logger.info(f"Created monitoring result {result_id} for topic {topic_id} (intent_id=NULL)")

            # Broadcast via SSE per Surface Routing Rules
            await self._broadcast_monitoring_result(
                result_id=result_id,
                topic_id=topic_found,
                session_id=session_id,
                summary=summary,
                data=result_data,
                urgency=urgency,
            )

        except Exception as e:
            logger.error(f"Error writing monitoring result for topic {topic_id}: {e}", exc_info=True)

    def _compute_state_diff(self, previous: dict, current: dict) -> dict:
        """Compute diff between previous and current state."""
        diff = {}
        for key in set(list(previous.keys()) + list(current.keys())):
            prev_val = previous.get(key)
            curr_val = current.get(key)
            if prev_val != curr_val:
                diff[key] = {"from": prev_val, "to": curr_val}
        return diff

    def _generate_monitoring_summary(
        self,
        topic_id: str,
        current_state: dict,
        previous_state: Optional[dict],
    ) -> str:
        """Generate deterministic monitoring summary (no LLM).

        Plan §10: deterministic template summary - no LLM anywhere on the tick.
        """
        if not previous_state:
            return f"Monitoring: {topic_id} initial state"

        # Check for specific state changes
        if "phase" in current_state:
            curr_phase = current_state["phase"]
            prev_phase = previous_state.get("phase")
            if curr_phase != prev_phase:
                return f"Monitoring: {topic_id} phase changed from {prev_phase} to {curr_phase}"

        if "sync_status" in current_state:
            curr_sync = current_state["sync_status"]
            prev_sync = previous_state.get("sync_status")
            if curr_sync != prev_sync:
                return f"Monitoring: {topic_id} sync status changed from {prev_sync} to {curr_sync}"

        if "status" in current_state:
            curr_status = current_state["status"]
            prev_status = previous_state.get("status")
            if curr_status != prev_status:
                return f"Monitoring: {topic_id} status changed from {prev_status} to {curr_status}"

        return f"Monitoring: {topic_id} state changed"

    async def _broadcast_monitoring_result(
        self,
        result_id: str,
        topic_id: str,
        session_id: str,
        summary: str,
        data: dict,
        urgency: str,
    ) -> None:
        """Broadcast monitoring result via SSE per Surface Routing Rules.

        Plan §10: Result enters Surface Routing Rules like any other.
        """
        try:
            # Build result dict for broadcast
            result_for_broadcast = {
                "id": result_id,
                "result_id": result_id,
                "intent_id": None,  # Monitoring results have no intent
                "topic_id": topic_id,
                "session_id": session_id,
                "summary": summary,
                "data": data,
                "urgency": urgency,
                "created_at": int(datetime.now().timestamp()),
            }

            # Get routing decision via Surface Router
            decision = await self.router.route_result(
                session_id=session_id,
                origin_surface_id=None,
                urgency=urgency,
            )

            # Route to target surfaces
            if decision.target_surfaces:
                for surface in decision.target_surfaces:
                    if surface.type == "telegram":
                        await self._send_to_telegram(result_for_broadcast, session_id)
                    else:
                        # SSE broadcast
                        await broadcast_result(
                            result=result_for_broadcast,
                            session_id=session_id,
                            target_surface_id=surface.id,
                        )
            elif decision.fallback_used:
                # Fallback to Telegram
                await self._send_to_telegram(result_for_broadcast, session_id)
            else:
                # No surface available - result stays in queue
                logger.info(f"No surface available for monitoring result {result_id}, result queued")

        except Exception as e:
            logger.error(f"Error broadcasting monitoring result {result_id}: {e}", exc_info=True)


async def create_bead_watcher(store: SessionStore, router: SurfaceRouter) -> BeadWatcher:
    """Create and start a bead watcher daemon."""
    watcher = BeadWatcher(store, router)
    await watcher.start()
    return watcher
