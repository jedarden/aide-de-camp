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
from ..fetch.executor import get_fetch_executor, FetchCommand, FetchType


logger = getLogger(__name__)

MONITORING_CONFIG_PATH = Path("/home/coding/aide-de-camp/config/monitoring.yaml")
SESSION_DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")

# Mapping of intent types to fetch types
INTENT_TYPE_TO_FETCH = {
    "status": FetchType.KUBECTL_STATUS,
    "pod_status": FetchType.POD_STATUS,
    "deployment_status": FetchType.DEPLOYMENT_STATUS,
    "argocd": FetchType.ARGOCD_STATUS,
    "ci": FetchType.CI_STATUS,
    "git": FetchType.GIT_LOG,
    "beads": FetchType.BEAD_LIST,
}


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
        self._fetch_executor = get_fetch_executor()

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

        Uses the fetch executor to get current state for the topic.
        """
        executor = get_fetch_executor()

        # Map intent_type to fetch_type
        fetch_type = INTENT_TYPE_TO_FETCH.get(rule.intent_type, FetchType.KUBECTL_STATUS)

        # Build fetch command
        command = FetchCommand(
            fetch_type=fetch_type,
            project_slug=rule.project_slug,
            args=[],  # Can be extended to support filters
            timeout=rule.check_interval,
        )

        # Execute fetch
        result = await executor.execute(command)

        if result.success:
            state_data = {
                "project_slug": rule.project_slug,
                "intent_type": rule.intent_type,
                **result.data,
            }

            # Apply filters if specified
            if rule.filters:
                if not self._passes_filters(state_data, rule.filters):
                    # Filter means we don't report this state
                    logger.debug(f"State for {rule.topic_id} filtered by {rule.filters}")
                    return None

            return state_data
        else:
            logger.warning(f"Fetch failed for {rule.topic_id}: {result.error}")
            return None

    def _passes_filters(self, state_data: dict, filters: list[str]) -> bool:
        """
        Check if state data passes all filters.

        Filters are simple expressions like "phase!=Running" or "restarts>0".
        Returns False if any filter fails.
        """
        for filter_expr in filters:
            if not self._evaluate_filter(state_data, filter_expr):
                return False
        return True

    def _evaluate_filter(self, state_data: dict, filter_expr: str) -> bool:
        """
        Evaluate a single filter expression against state data.

        Supports: !=, >, <, >=, <=, ==
        Examples: "phase!=Running", "restarts>0", "ready!=1/1"
        """
        import re

        # Parse filter expression
        match = re.match(r'(\w+)(!=|>=|<=|>|<|==)(.+)', filter_expr)
        if not match:
            logger.warning(f"Invalid filter expression: {filter_expr}")
            return True

        field_path, op, value = match.groups()

        # Get field value from nested dict
        field_value = self._get_nested_value(state_data, field_path)

        # Compare
        if field_value is None:
            return False

        try:
            if op == "!=":
                return str(field_value) != value
            elif op == "==":
                return str(field_value) == value
            elif op == ">":
                return float(field_value) > float(value)
            elif op == "<":
                return float(field_value) < float(value)
            elif op == ">=":
                return float(field_value) >= float(value)
            elif op == "<=":
                return float(field_value) <= float(value)
        except (ValueError, TypeError):
            # If comparison fails, treat as no match
            logger.warning(f"Filter comparison failed: {filter_expr} with value {field_value}")
            return False

        return True

    def _get_nested_value(self, data: dict, path: str) -> Any:
        """Get a value from nested dict using dot notation."""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

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
