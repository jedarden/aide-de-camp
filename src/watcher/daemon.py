"""
Bead watcher daemon: monitors NEEDLE beads and pushes results to surfaces.

Watches for bead close events, reads results from bead metadata, and pushes
to active surfaces via SSE or Telegram fallback.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..session.store import SessionStore
from ..sse.broadcaster import broadcast_result
from ..surface.router import SurfaceRouter

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

    CHECK_INTERVAL_SECONDS = 5
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
    ):
        self.store = store
        self.router = router
        # Allow tests / alternate workspaces to point at a scratch checkpoint.
        self._beads_jsonl = beads_jsonl or self.BEADS_JSONL
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # Bead IDs we have already delivered. In-memory only, so a process
        # restart re-delivers currently-terminal beads (pre-existing behavior).
        self._processed_beads: set[str] = set()

    async def start(self) -> None:
        """Start the bead watcher daemon."""
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("Bead watcher started")

    async def stop(self) -> None:
        """Stop the bead watcher daemon."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Bead watcher stopped")

    async def _watch_loop(self) -> None:
        """Main watch loop - checks for new bead events."""
        while self._running:
            try:
                await self._check_for_events()
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in bead watch loop: {e}", exc_info=True)
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

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

    async def _send_to_telegram(self, result: dict, session_id: str) -> None:
        """Send result to Telegram via telegram-claude-bridge.

        NOTE: This requires a session→telegram_chat_id mapping. Current implementation
        logs a warning because telegram-claude-bridge uses a pull-based architecture
        (manages sessions internally per forum topic) rather than push-based message delivery.
        """
        try:
            # telegram-claude-bridge proxy expects actual Telegram chat_id (int64), not session_id
            # Since we don't have a session→chat mapping, log this as unavailable
            logger.warning(
                f"Cannot send result to Telegram for session {session_id}: "
                f"session→telegram_chat mapping not implemented. "
                f"telegram-claude-bridge uses pull-based architecture (per forum topic sessions)."
            )

            # Correct contract for reference (if mapping is implemented later):
            # POST http://telegram-claude-bridge:8000/send
            # {
            #   "chat_id": 123456789,  # int64, REQUIRED - actual Telegram chat ID
            #   "text": "message",     # string, REQUIRED - message content
            #   "parse_mode": "HTML"   # string, OPTIONAL
            # }

        except Exception as e:
            logger.error(f"Error in Telegram send logic: {e}")

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
