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

import httpx

from src.session.store import SessionStore
from src.sse.broadcaster import EventType, SSEEvent, broadcast_result
from src.surface.router import SurfaceRouter

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

    Integration with br CLI (beads_rust):
    - Reads beads JSONL file for closed beads
    - Extracts session_id and surface_id from bead metadata
    - Pushes results to active surfaces via SSE
    - Falls back to Telegram if no surface available
    """

    CHECK_INTERVAL_SECONDS = 5
    BEADS_JSONL = ".beads/beads.jsonl"

    def __init__(self, store: SessionStore, router: SurfaceRouter):
        self.store = store
        self.router = router
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_position = 0  # Position in beads.jsonl
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
        """Check for new bead events and process them."""
        beads_path = Path(self.BEADS_JSONL)
        if not beads_path.exists():
            return

        # Read new lines from beads.jsonl
        events = await self._read_new_bead_events(beads_path)

        for event in events:
            await self._process_bead_event(event)

    async def _read_new_bead_events(self, beads_path: Path) -> list[BeadEvent]:
        """Read new bead events from beads.jsonl."""
        events = []

        try:
            with open(beads_path, "r") as f:
                # Seek to last position
                f.seek(self._last_position)
                new_lines = f.readlines()

                # Update position
                self._last_position = f.tell()

                for line in new_lines:
                    if not line.strip():
                        continue

                    try:
                        bead = json.loads(line)
                        bead_id = bead.get("id")
                        status = bead.get("status")

                        if not bead_id or bead_id in self._processed_beads:
                            continue

                        # Process closed beads
                        if status == "closed":
                            events.append(BeadEvent(
                                bead_id=bead_id,
                                event_type="closed",
                                timestamp=int(datetime.now().timestamp()),
                                data=bead,
                            ))
                            self._processed_beads.add(bead_id)

                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse bead JSON: {e}")

        except Exception as e:
            logger.error(f"Error reading beads file: {e}")

        return events

    async def _process_bead_event(self, event: BeadEvent) -> None:
        """Process a bead event and route to surfaces."""
        bead_data = event.data

        # Extract metadata
        metadata = bead_data.get("metadata", {})
        session_id = metadata.get("session_id")
        surface_id = metadata.get("origin_surface_id")

        if not session_id:
            # No session_id - can't route
            logger.warning(f"Bead {event.bead_id} has no session_id in metadata")
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
        """Extract result data from a closed bead."""
        # Try to extract structured result from bead body
        body = bead.get("body", "")
        metadata = bead.get("metadata", {})

        # If metadata already has result structure, use it
        if "result" in metadata:
            return metadata["result"]

        # Try to parse result from body
        # For now, create a basic result from the bead
        return {
            "id": bead.get("id"),
            "type": "bead_result",
            "summary": body[:200] if len(body) > 200 else body,  # Truncate for summary
            "data": {
                "bead_id": bead.get("id"),
                "title": bead.get("title"),
                "type": bead.get("type"),
                "body": body,
                "status": bead.get("status"),
            },
            "urgency": metadata.get("urgency", "normal"),
            "created_at": int(datetime.now().timestamp()),
            "surfaced_at": int(datetime.now().timestamp()),
        }

    async def _send_to_telegram(self, result: dict, session_id: str) -> None:
        """Send result to Telegram via telegram-claude-bridge."""
        try:
            # telegram-claude-bridge runs on Tailscale mesh
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://telegram-claude-bridge:8000/send_message",
                    json={
                        "session_id": session_id,
                        "message": self._format_telegram_message(result),
                    },
                    timeout=5.0,
                )
                if response.status_code == 200:
                    logger.info(f"Sent result to Telegram for session {session_id}")
                else:
                    logger.warning(f"Failed to send to Telegram: {response.status_code}")
        except Exception as e:
            logger.error(f"Error sending to Telegram: {e}")

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
