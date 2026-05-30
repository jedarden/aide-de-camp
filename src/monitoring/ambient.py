"""
Ambient monitoring service.

Watches active topics for state changes and pushes results when detected.
Supports poll-based and event-based monitoring.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from typing import Any, Optional

import yaml
from aiohttp import ClientSession
from aiosqlite import connect

from ..session.store import get_store


logger = getLogger(__name__)

MONITORING_CONFIG_PATH = Path("/home/coding/aide-de-camp/config/monitoring.yaml")
SESSION_DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")


@dataclass
class MonitoringRule:
    """A monitoring rule for a topic."""
    topic_id: str
    project_slug: str
    intent_type: str
    check_interval: int  # seconds
    urgency: str
    filters: list[str]
    notification_threshold: str  # 'any_change' | 'state_change'


@dataclass
class ExceptionRule:
    """An exception-based monitoring rule."""
    name: str
    project_slug: Optional[str]
    condition: str
    urgency: str
    message: str


@dataclass
class MonitoringConfig:
    """Loaded monitoring configuration."""
    active_topics: list[MonitoringRule]
    exceptions: list[ExceptionRule]
    batching: dict[str, int]
    quiet_hours: dict[str, Any]
    channels: dict[str, list[str]]


class AmbientMonitor:
    """
    Ambient monitoring service.

    Polls active topics for state changes and pushes results when detected.
    Runs as a background task with configurable check intervals.
    """

    def __init__(self, config_path: Path = MONITORING_CONFIG_PATH):
        self.config_path = config_path
        self.config: Optional[MonitoringConfig] = None
        self.last_state: dict[str, Any] = {}  # topic_id -> last known state
        self.running = False
        self.tasks: list[asyncio.Task] = []
        self._http_client: Optional[ClientSession] = None

    async def _get_http_client(self) -> ClientSession:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = ClientSession()
        return self._http_client

    async def load_config(self) -> MonitoringConfig:
        """Load monitoring configuration from YAML file."""
        logger.info(f"Loading monitoring config from {self.config_path}")
        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f)

        # Parse active topics
        active_topics = []
        for item in data.get("monitoring", {}).get("active_topics", []):
            active_topics.append(MonitoringRule(
                topic_id=item["topic_id"],
                project_slug=item["project_slug"],
                intent_type=item["intent_type"],
                check_interval=item["check_interval"],
                urgency=item.get("urgency", "normal"),
                filters=item.get("filters", []),
                notification_threshold=item.get("notification_threshold", "any_change"),
            ))

        # Parse exceptions
        exceptions = []
        for item in data.get("monitoring", {}).get("exceptions", []):
            exceptions.append(ExceptionRule(
                name=item["name"],
                project_slug=item.get("project_slug"),
                condition=item["condition"],
                urgency=item.get("urgency", "high"),
                message=item["message"],
            ))

        # Parse batching
        batching = {
            "low_urgency_batch_seconds": data.get("batching", {}).get("low_urgency_batch_seconds", 300),
            "normal_urgency_batch_seconds": data.get("batching", {}).get("normal_urgency_batch_seconds", 120),
        }

        # Parse quiet hours
        quiet_hours = data.get("quiet_hours", {})

        # Parse channels
        channels = data.get("channels", {})

        self.config = MonitoringConfig(
            active_topics=active_topics,
            exceptions=exceptions,
            batching=batching,
            quiet_hours=quiet_hours,
            channels=channels,
        )
        return self.config

    async def check_topic_state(self, rule: MonitoringRule) -> Optional[dict]:
        """
        Check the current state of a topic.

        This is a placeholder - in full implementation, this would call the
        fetch strand to get current state for the topic.
        """
        # Placeholder: simulate state check
        # Full implementation would call the fetch strand with the rule's project_slug and intent_type

        # For now, return None (no change detected)
        return None

    async def detect_state_change(
        self,
        rule: MonitoringRule,
        current_state: dict,
    ) -> bool:
        """
        Detect if the state has changed since last check.

        Compares current state with last known state for the topic.
        Returns True if significant change detected.
        """
        topic_key = f"{rule.project_slug}:{rule.intent_type}"

        if topic_key not in self.last_state:
            # First check - store state and don't notify
            self.last_state[topic_key] = current_state
            return False

        last_state = self.last_state[topic_key]

        # Check for state changes based on notification threshold
        if rule.notification_threshold == "any_change":
            # Any field change triggers notification
            return current_state != last_state
        elif rule.notification_threshold == "state_change":
            # Only notify if specific state fields change
            # For status intents, check if phase, status, or health changed
            state_fields = ["phase", "status", "health", "ready", "sync_status"]
            return any(
                current_state.get(field) != last_state.get(field)
                for field in state_fields
            )

        return False

    async def push_monitoring_result(
        self,
        rule: MonitoringRule,
        current_state: dict,
        session_id: str,
    ) -> None:
        """
        Push a monitoring result to the active surface.

        Creates a result in the session store and pushes to appropriate surface.
        """
        store = get_store()

        # Find or create topic for this monitoring rule
        topic_id, _ = await store.find_or_create_topic(
            label=rule.topic_id,
            session_id=session_id,
            topic_type="project",
            project_slugs=[rule.project_slug] if rule.project_slug else None,
        )

        # Create a monitoring intent
        intent_id = await store.create_intent(
            utterance_id=f"monitoring-{datetime.now(timezone.utc).isoformat()}",
            session_id=session_id,
            project_slug=rule.project_slug,
            intent_type=rule.intent_type,
        )

        # Create result with diff info if available
        topic_key = f"{rule.project_slug}:{rule.intent_type}"
        previous_state = self.last_state.get(topic_key, {})

        result_data = {
            "monitoring": True,
            "current_state": current_state,
            "previous_state": previous_state if previous_state else None,
            "rule_filters": rule.filters,
        }

        # Add diff if we have previous state
        if previous_state:
            result_data["diff"] = self._compute_diff(previous_state, current_state)

        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=self._generate_summary(rule, current_state, previous_state),
            data=result_data,
            urgency=rule.urgency,
        )

        logger.info(f"Created monitoring result {result_id} for topic {rule.topic_id}")

        # Update last state
        self.last_state[topic_key] = current_state

    def _compute_diff(self, previous: dict, current: dict) -> dict:
        """Compute diff between previous and current state."""
        diff = {}

        for key in set(list(previous.keys()) + list(current.keys())):
            prev_val = previous.get(key)
            curr_val = current.get(key)

            if prev_val != curr_val:
                diff[key] = {
                    "from": prev_val,
                    "to": curr_val,
                }

        return diff

    def _generate_summary(
        self,
        rule: MonitoringRule,
        current_state: dict,
        previous_state: Optional[dict],
    ) -> str:
        """Generate a summary for the monitoring result."""
        if previous_state is None:
            return f"Initial state check for {rule.topic_id}"

        # Check for specific state changes
        if "phase" in current_state:
            curr_phase = current_state["phase"]
            prev_phase = previous_state.get("phase")
            if curr_phase != prev_phase:
                return f"{rule.topic_id} phase changed from {prev_phase} to {curr_phase}"

        if "sync_status" in current_state:
            curr_sync = current_state["sync_status"]
            prev_sync = previous_state.get("sync_status")
            if curr_sync != prev_sync:
                return f"{rule.topic_id} sync status changed from {prev_sync} to {curr_sync}"

        return f"{rule.topic_id} state has changed"

    async def monitor_topic(self, rule: MonitoringRule) -> None:
        """
        Monitor a single topic on its check interval.

        Runs in a loop until cancelled.
        """
        logger.info(f"Starting monitor for topic {rule.topic_id} (interval: {rule.check_interval}s)")

        # Use a default session for monitoring results
        # In full implementation, this would use the active session
        session_id = "monitoring"  # Placeholder

        while self.running:
            try:
                # Check current state
                current_state = await self.check_topic_state(rule)

                if current_state:
                    # Detect change
                    has_change = await self.detect_state_change(rule, current_state)

                    if has_change:
                        logger.info(f"State change detected for {rule.topic_id}")
                        await self.push_monitoring_result(rule, current_state, session_id)
                    else:
                        # Update last state even if no change (keeps us synced)
                        topic_key = f"{rule.project_slug}:{rule.intent_type}"
                        self.last_state[topic_key] = current_state

                # Wait for next check
                await asyncio.sleep(rule.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring topic {rule.topic_id}: {e}", exc_info=True)
                await asyncio.sleep(rule.check_interval)

    async def start(self) -> None:
        """Start ambient monitoring."""
        logger.info("Starting ambient monitoring service")

        # Load config
        config = await self.load_config()

        self.running = True

        # Start a monitor task for each active topic
        for rule in config.active_topics:
            task = asyncio.create_task(self.monitor_topic(rule))
            self.tasks.append(task)

        logger.info(f"Started {len(self.tasks)} topic monitors")

    async def stop(self) -> None:
        """Stop ambient monitoring."""
        logger.info("Stopping ambient monitoring service")
        self.running = False

        # Cancel all monitor tasks
        for task in self.tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)

        self.tasks.clear()

        # Close HTTP client
        if self._http_client:
            await self._http_client.close()

        logger.info("Ambient monitoring stopped")

    async def reload_config(self) -> None:
        """Reload monitoring configuration."""
        logger.info("Reloading monitoring configuration")

        old_tasks = self.tasks
        self.tasks = []

        # Cancel old monitors
        for task in old_tasks:
            task.cancel()
        await asyncio.gather(*old_tasks, return_exceptions=True)

        # Load new config and restart monitors
        config = await self.load_config()

        for rule in config.active_topics:
            task = asyncio.create_task(self.monitor_topic(rule))
            self.tasks.append(task)

        logger.info(f"Reloaded monitoring config, started {len(self.tasks)} topic monitors")


# Global ambient monitor instance
_ambient_monitor: Optional[AmbientMonitor] = None


def get_ambient_monitor() -> AmbientMonitor:
    """Get or create the global ambient monitor instance."""
    global _ambient_monitor
    if _ambient_monitor is None:
        _ambient_monitor = AmbientMonitor()
    return _ambient_monitor
