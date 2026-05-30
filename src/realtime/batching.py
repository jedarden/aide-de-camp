"""
Notification batching for audio mode.

Controls when results are narrated in voice sessions based on urgency tiers,
quiet hours, and batching windows.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from logging import getLogger
from typing import Any, Callable, Optional
import yaml
from pathlib import Path


logger = getLogger(__name__)


class Urgency(Enum):
    """Result urgency levels."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class PendingResult:
    """A result awaiting narration."""
    result_id: str
    intent_id: str
    topic_id: str
    summary: str
    data: dict
    urgency: Urgency
    created_at: int
    batch_group: str = "default"


@dataclass
class QuietHours:
    """Quiet hours configuration."""
    enabled: bool = False
    start: str = "22:00"  # 10 PM
    end: str = "08:00"  # 8 AM
    timezone: str = "America/New_York"
    allow_critical: bool = True  # Critical notifications still push during quiet hours

    def is_quiet(self) -> bool:
        """Check if current time is within quiet hours."""
        if not self.enabled:
            return False

        try:
            from zoneinfo import ZoneInfo
            import pytz

            tz = ZoneInfo(self.timezone)
            now = datetime.now(tz)
            current_time = now.strftime("%H:%M")

            # Handle overnight quiet hours (e.g., 22:00 to 08:00)
            if self.start > self.end:
                # Quiet period spans midnight
                return current_time >= self.start or current_time < self.end
            else:
                # Quiet period within same day
                return self.start <= current_time < self.end

        except ImportError:
            # Fallback if zoneinfo/pytz not available
            logger.warning("zoneinfo/pytz not available, quiet hours disabled")
            return False


@dataclass
class BatchingConfig:
    """Batching configuration."""
    # Batch window durations (seconds)
    low_urgency_batch_seconds: int = 300  # 5 minutes
    normal_urgency_batch_seconds: int = 120  # 2 minutes
    high_urgency_batch_seconds: int = 0  # No batching
    critical_urgency_batch_seconds: int = 0  # No batching

    # Maximum batch size
    max_batch_size: int = 10

    # Quiet hours
    quiet_hours: QuietHours = field(default_factory=QuietHours)


class ResultBatcher:
    """
    Batches results for audio narration based on urgency and quiet hours.

    Rules:
    - Critical: Interrupt immediately
    - High: Wait for natural pause
    - Normal: Batch within ~5s window (configurable)
    - Low: Narrate only if idle
    - Respect quiet hours (non-critical suppressed)
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config = BatchingConfig()
        self._pending: list[PendingResult] = []
        self._waiting_for_pause: list[PendingResult] = []
        self._last_narration: int = 0
        self._session_active: bool = True
        self._on_narrate_callback: Optional[Callable[[list[PendingResult]], Any]] = None
        self._batch_task: Optional[asyncio.Task] = None
        self._running: bool = False

        if config_path and config_path.exists():
            self._load_config(config_path)

    def _load_config(self, config_path: Path) -> None:
        """Load batching configuration from monitoring.yaml."""
        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f)

            batching_config = data.get("batching", {})
            quiet_hours_config = data.get("quiet_hours", {})

            self.config.low_urgency_batch_seconds = batching_config.get(
                "low_urgency_batch_seconds", 300
            )
            self.config.normal_urgency_batch_seconds = batching_config.get(
                "normal_urgency_batch_seconds", 120
            )

            if quiet_hours_config:
                self.config.quiet_hours = QuietHours(
                    enabled=quiet_hours_config.get("enabled", False),
                    start=quiet_hours_config.get("start", "22:00"),
                    end=quiet_hours_config.get("end", "08:00"),
                    timezone=quiet_hours_config.get("timezone", "America/New_York"),
                    allow_critical=quiet_hours_config.get("allow_critical", True),
                )

            logger.info(f"Loaded batching config from {config_path}")

        except Exception as e:
            logger.warning(f"Failed to load batching config: {e}")

    def set_narrate_callback(self, callback: Callable[[list[PendingResult]], Any]) -> None:
        """Set the callback to invoke when results should be narrated."""
        self._on_narrate_callback = callback

    async def queue_result(
        self,
        result_id: str,
        intent_id: str,
        topic_id: str,
        summary: str,
        data: dict,
        urgency: str,
    ) -> None:
        """
        Queue a result for narration.

        Returns immediately; narration happens per batching rules.
        """
        urgency_enum = Urgency(urgency.lower())
        now = int(datetime.now(timezone.utc).timestamp())

        pending = PendingResult(
            result_id=result_id,
            intent_id=intent_id,
            topic_id=topic_id,
            summary=summary,
            data=data,
            urgency=urgency_enum,
            created_at=now,
        )

        # Check quiet hours
        if self.config.quiet_hours.is_quiet():
            if urgency_enum != Urgency.CRITICAL or not self.config.quiet_hours.allow_critical:
                logger.info(f"Result {result_id} suppressed during quiet hours")
                return

        # Handle based on urgency
        if urgency_enum == Urgency.CRITICAL:
            # Critical: interrupt immediately
            await self._narrate_now([pending])

        elif urgency_enum == Urgency.HIGH:
            # High: wait for natural pause (or timeout)
            self._waiting_for_pause.append(pending)
            # Set timeout for high urgency (30s max wait)
            asyncio.create_task(self._high_urgency_timeout(pending))

        elif urgency_enum == Urgency.NORMAL:
            # Normal: batch within window
            self._pending.append(pending)
            # Schedule batch if not already scheduled
            if self._batch_task is None or self._batch_task.done():
                self._batch_task = asyncio.create_task(
                    self._normal_batch_timer(pending)
                )

        elif urgency_enum == Urgency.LOW:
            # Low: only narrate if idle (no active conversation)
            if self._session_active:
                # Session is active, queue for idle narration
                self._pending.append(pending)
            else:
                # Session idle, narrate immediately
                await self._narrate_now([pending])

    async def _narrate_now(self, results: list[PendingResult]) -> None:
        """Narrate results immediately."""
        if not results:
            return

        self._last_narration = int(datetime.now(timezone.utc).timestamp())

        if self._on_narrate_callback:
            try:
                await self._on_narrate_callback(results)
            except Exception as e:
                logger.error(f"Error in narrate callback: {e}", exc_info=True)

    async def _high_urgency_timeout(self, pending: PendingResult) -> None:
        """Timeout for high urgency results that haven't found a pause."""
        await asyncio.sleep(30)  # 30 second max wait
        if pending in self._waiting_for_pause:
            self._waiting_for_pause.remove(pending)
            await self._narrate_now([pending])

    async def _normal_batch_timer(self, pending: PendingResult) -> None:
        """Timer for normal urgency batch window."""
        await asyncio.sleep(self.config.normal_urgency_batch_seconds)

        # Collect all normal urgency results that are ready
        now = int(datetime.now(timezone.utc).timestamp())
        ready = [r for r in self._pending if now - r.created_at >= self.config.normal_urgency_batch_seconds]

        # Remove from pending
        for r in ready:
            if r in self._pending:
                self._pending.remove(r)

        # Narrate batch
        await self._narrate_now(ready)

    async def signal_pause(self) -> None:
        """
        Signal a natural pause in conversation.

        High urgency results waiting for pause can be narrated now.
        """
        if self._waiting_for_pause:
            results = self._waiting_for_pause.copy()
            self._waiting_for_pause.clear()
            await self._narrate_now(results)

    async def signal_idle(self) -> None:
        """
        Signal session is idle (no active conversation).

        All pending results (including low urgency) can be narrated.
        """
        self._session_active = False

        if self._pending:
            results = self._pending.copy()
            self._pending.clear()
            await self._narrate_now(results)

    async def signal_active(self) -> None:
        """Signal session is active (conversation happening)."""
        self._session_active = True

    async def flush(self) -> None:
        """Flush all pending results immediately."""
        all_pending = self._waiting_for_pause + self._pending

        if all_pending:
            self._waiting_for_pause.clear()
            self._pending.clear()
            await self._narrate_now(all_pending)

    def get_queue_status(self) -> dict:
        """Get current queue status for monitoring."""
        return {
            "pending": len(self._pending),
            "waiting_for_pause": len(self._waiting_for_pause),
            "session_active": self._session_active,
            "last_narration": self._last_narration,
            "quiet_hours_active": self.config.quiet_hours.is_quiet(),
        }


# Global batcher instance
_batcher: Optional[ResultBatcher] = None


def get_result_batcher(config_path: Optional[Path] = None) -> ResultBatcher:
    """Get or create the global result batcher instance."""
    global _batcher
    if _batcher is None:
        config = config_path or Path("/home/coding/aide-de-camp/config/monitoring.yaml")
        _batcher = ResultBatcher(config_path=config)
    return _batcher
