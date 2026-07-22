"""
Bead watcher daemon: monitors NEEDLE beads and pushes results to surfaces.

Watches for bead close events, reads results from bead metadata, and pushes
to active surfaces via SSE or Telegram fallback.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..session.store import SessionStore
from ..sse.broadcaster import broadcast_result
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
    Watches for bead events and routes results to surfaces.

    Integration with the bf CLI (bead-forge):
    - Reads the bf workspace checkpoint JSONL (`.beads/issues.jsonl`) for
      terminal beads
    - Extracts session_id / origin_surface_id / urgency from the bead's flat
      `labels` array -- escalate/handler.py encodes these as `key=value` labels
    - Pushes results to active surfaces via SSE
    - Falls back to Telegram if no surface available

    The checkpoint is rewritten in full on every `bf sync --flush-only` (it is
    not append-only), so each tick re-reads the whole file and relies on
    `_processed_beads` to dedup already-delivered beads.
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
    # bf (bead-forge) workspace checkpoint. The live store is beads.db; this is
    # the flushed checkpoint bf writes on `bf sync --flush-only`. Absolute path
    # because the server may be launched from any CWD (matches DB_PATH in
    # src/main.py). The old value ".beads/beads.jsonl" never existed -- this file
    # is the real one and has always been named issues.jsonl.
    BEADS_JSONL = "/home/coding/aide-de-camp/.beads/issues.jsonl"
    # Terminal statuses meaning "work is done, deliver the result". bf uses
    # "closed" for normally-completed beads and "resolved" for beads closed via
    # the escalate auto-approve path. Both warrant delivery (see adc-5wtm); the
    # session_id-label guard below scopes delivery to escalate-tracked beads
    # regardless of status, so including "resolved" is safe.
    TERMINAL_STATUSES = ("closed", "resolved")

    def __init__(
        self,
        store: SessionStore,
        router: SurfaceRouter,
        beads_jsonl: str | None = None,
        telegram_fallback: TelegramFallback | None = None,
        check_interval_seconds: float | None = None,
    ):
        self.store = store
        self.router = router
        # Allow tests / alternate workspaces to point at a scratch checkpoint.
        self._beads_jsonl = beads_jsonl or self.BEADS_JSONL
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
        # Consecutive crashes since the last healthy tick; drives the backoff
        # schedule. Reset to 0 whenever a tick completes successfully.
        self._restart_count = 0
        # Liveness state, read by the GET /health watcher block (child 3).
        # last_tick_at is epoch seconds (time.time()); 0.0 means "never ticked".
        self.last_tick_at: float = 0.0
        self.tick_count: int = 0
        # Bead IDs we have already delivered. In-memory only, so a process
        # restart re-delivers currently-terminal beads (pre-existing behavior).
        self._processed_beads: set[str] = set()

    async def start(self) -> None:
        """Start the bead watcher daemon.

        Spawns a single lifespan supervisor task that owns the watch-task
        lifecycle: it runs the poll loop, and if the loop's task itself dies
        (an exception that escapes its per-iteration catch, or an unexpected
        return) it restarts the task with exponential backoff. start()/stop()
        keep their signatures and the lifespan wiring in src/main.py is
        unchanged — ``_bead_watcher`` stays the module-level instance.
        """
        self._running = True
        self._supervisor_task = asyncio.create_task(
            self._supervise(), name="bead-watcher-supervisor"
        )
        logger.info("Bead watcher started (interval=%ss)", self.check_interval_seconds)

    async def stop(self) -> None:
        """Stop the bead watcher daemon.

        Flags shutdown, then cancels and awaits the supervisor (which in turn
        tears down the watch task it spawned). The watch task is cancelled
        explicitly as well: cancelling a supervisor awaiting another task does
        not automatically cancel the awaited task.
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

    async def _check_for_events(self) -> None:
        """Check for terminal bead events and process them."""
        beads_path = Path(self._beads_jsonl)
        if not beads_path.exists():
            return

        events = await self._read_terminal_events(beads_path)

        for event in events:
            await self._process_bead_event(event)

    async def _read_terminal_events(self, beads_path: Path) -> list[BeadEvent]:
        """
        Read terminal (closed/resolved) bead events from the checkpoint.

        The bf checkpoint is rewritten in full on each flush (not appended to),
        so byte-offset tracking would silently miss beads whose status changed
        on an earlier line. We therefore re-read the whole file each tick;
        `_processed_beads` guards against re-delivering beads already routed.
        """
        events: list[BeadEvent] = []

        try:
            with open(beads_path, "r") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"Error reading beads file: {e}")
            return events

        for line in lines:
            if not line.strip():
                continue

            try:
                bead = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse bead JSON: {e}")
                continue

            bead_id = bead.get("id")
            status = bead.get("status")

            if not bead_id or bead_id in self._processed_beads:
                continue

            # Process terminal beads (closed or resolved)
            if status in self.TERMINAL_STATUSES:
                events.append(BeadEvent(
                    bead_id=bead_id,
                    event_type=status,  # 'closed' or 'resolved'
                    timestamp=int(datetime.now().timestamp()),
                    data=bead,
                ))
                self._processed_beads.add(bead_id)

        return events

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
        """Process a bead event and route to surfaces."""
        bead_data = event.data

        # Extract routing metadata from the bead's labels (escalate encoding).
        metadata = self._extract_metadata(bead_data)
        session_id = metadata.get("session_id")
        surface_id = metadata.get("origin_surface_id")

        if not session_id:
            # Not an escalate-tracked bead (no session_id label) -- nothing to
            # route. This is expected for the vast majority of bf beads, so this
            # is a debug log, not a warning.
            logger.debug(f"Bead {event.bead_id} has no session_id label; skipping")
            return

        # Determine target surface
        decision = await self.router.route_result(
            session_id=session_id,
            origin_surface_id=surface_id,
            urgency=metadata.get("urgency", "normal"),
        )

        # Extract result from bead
        result = await self._extract_result_from_bead(bead_data, session_id)

        if not result:
            logger.warning(f"Could not extract result from bead {event.bead_id}")
            return

        # Route to target surfaces
        if decision.target_surfaces:
            for surface in decision.target_surfaces:
                if surface.type == "telegram":
                    await self._send_to_telegram(result, session_id)
                else:
                    # SSE broadcast
                    await broadcast_result(
                        result=result,
                        session_id=session_id,
                        target_surface_id=surface.id,
                    )
        elif decision.fallback_used:
            # Fallback to Telegram
            await self._send_to_telegram(result, session_id)
        else:
            # No surface available - result stays in queue
            logger.info(f"No surface available for bead {event.bead_id}, result queued")

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


async def create_bead_watcher(store: SessionStore, router: SurfaceRouter) -> BeadWatcher:
    """Create and start a bead watcher daemon."""
    watcher = BeadWatcher(store, router)
    await watcher.start()
    return watcher
