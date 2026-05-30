"""
Surface routing: determine which surface(s) should receive a result.

Routing priority:
1. Origin surface (if still connected)
2. Most recently active connected surface
3. Any connected surface
4. Always-available fallback (Telegram)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from src.session.store import SessionStore


@dataclass
class Surface:
    """A surface representation."""
    id: str
    session_id: str
    type: str
    state: str
    always_available: bool
    last_seen: int


@dataclass
class RouteDecision:
    """Routing decision for a result."""
    target_surfaces: list[Surface]
    reason: str
    fallback_used: bool = False


class SurfaceRouter:
    """Route results to appropriate surfaces based on priority rules."""

    # Surface idle timeout: marks surface as idle after N seconds of inactivity
    IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(self, store: SessionStore):
        self.store = store

    async def route_result(
        self,
        session_id: str,
        origin_surface_id: str | None = None,
        urgency: str = "normal",
    ) -> RouteDecision:
        """
        Determine which surface(s) should receive a result.

        Args:
            session_id: The session the result belongs to
            origin_surface_id: The surface where the utterance originated (if known)
            urgency: Result urgency ('critical', 'high', 'normal', 'low')

        Returns:
            RouteDecision with target surfaces and routing reason
        """
        active_surfaces = await self.store.get_active_surfaces(session_id)

        # Filter out idle surfaces (but keep always-available ones)
        now = int(datetime.now().timestamp())
        recently_active = [
            s for s in active_surfaces
            if s["always_available"] or (now - s["last_seen"]) < self.IDLE_TIMEOUT_SECONDS
        ]

        # Priority 1: Origin surface (if still connected)
        if origin_surface_id:
            for surface in recently_active:
                if surface["id"] == origin_surface_id and surface["state"] != "disconnected":
                    return RouteDecision(
                        target_surfaces=[Surface(**surface)],
                        reason="origin-surface-active",
                    )

        # Priority 2: Most recently active connected surface
        if recently_active:
            # Sort by last_seen descending, pick the first non-telegram unless all are telegram
            recently_active.sort(key=lambda s: s["last_seen"], reverse=True)

            # Prefer non-telegram surfaces for non-critical results
            if urgency not in ("critical", "high"):
                for surface in recently_active:
                    if surface["type"] != "telegram":
                        return RouteDecision(
                            target_surfaces=[Surface(**surface)],
                            reason="most-recent-active",
                        )

            # For high urgency or if only telegram available
            return RouteDecision(
                target_surfaces=[Surface(**recently_active[0])],
                reason="most-recent-active-or-fallback",
            )

        # Priority 3: Any connected surface (including idle)
        if active_surfaces:
            active_surfaces.sort(key=lambda s: s["last_seen"], reverse=True)
            return RouteDecision(
                target_surfaces=[Surface(**active_surfaces[0])],
                reason="any-connected",
            )

        # Priority 4: Always-available fallback (Telegram)
        fallback = await self.store.get_fallback_surface()
        if fallback:
            return RouteDecision(
                target_surfaces=[Surface(**fallback)],
                reason="always-available-fallback",
                fallback_used=True,
            )

        # No surface available - result will wait in queue
        return RouteDecision(
            target_surfaces=[],
            reason="no-surface-available",
        )

    async def route_to_all_active(
        self,
        session_id: str,
        exclude_surface_id: str | None = None,
    ) -> list[Surface]:
        """
        Route to all active surfaces (for multi-surface scenarios).

        Used when a user has both canvas and audio surfaces active.
        """
        active_surfaces = await self.store.get_active_surfaces(session_id)
        now = int(datetime.now().timestamp())

        result = []
        for s in active_surfaces:
            if exclude_surface_id and s["id"] == exclude_surface_id:
                continue
            if s["always_available"] or (now - s["last_seen"]) < self.IDLE_TIMEOUT_SECONDS:
                result.append(Surface(**s))

        return result

    async def handle_surface_disconnect(self, surface_id: str, session_id: str) -> None:
        """
        Handle a surface disconnecting.
        Marks surface as disconnected and cleans up if needed.
        """
        await self.store.mark_surface_disconnected(surface_id)

    async def handle_surface_reconnect(
        self,
        surface_id: str,
        session_id: str,
        surface_type: str,
    ) -> bool:
        """
        Handle a surface reconnecting after disconnection.

        Returns True if this is a reconnection of an existing surface,
        False if it's a new surface.
        """
        # Check if surface exists
        async with self.store as store:
            surfaces = await store.get_active_surfaces(session_id)
            for existing in surfaces:
                if existing["id"] == surface_id:
                    # Reconnection - update heartbeat
                    await store.update_surface_heartbeat(surface_id)
                    return True

        # New surface - register it
        await store.register_surface(session_id, surface_type)
        return False

    async def get_workload_summary(self, session_id: str) -> dict:
        """
        Get workload summary for a session (for surface reconnection).
        """
        return await self.store.get_workload_summary(session_id)
