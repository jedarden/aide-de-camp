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

from ..session.store import SessionStore, get_store
from ..fetch.orchestrator import get_fetch_strand, execute_fetch, FetchRequest
from ..fetch.commands import FetchContext, FetchSource, IntentType
from ..sse.broadcaster import get_broadcaster, SSEEvent, broadcast_result
from ..render.hot_path import derive_result_type, get_renderer
from .config_loader import get_monitoring_config_loader


logger = getLogger(__name__)

MONITORING_CONFIG_PATH = Path("/home/coding/aide-de-camp/config/monitoring.yaml")
SESSION_DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")

# Default TTL for topic context cache (10 minutes)
TOPIC_CONTEXT_TTL_SECONDS = 600

# Mapping of monitoring intent types to fetch IntentTypes
INTENT_TYPE_MAPPING = {
    "status": IntentType.STATUS,
    "pod_status": IntentType.STATUS,
    "deployment_status": IntentType.ACTION,
    "argocd": IntentType.STATUS,
    "ci": IntentType.STATUS,
    "git": IntentType.STATUS,
    "beads": IntentType.STATUS,
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

    def __init__(
        self,
        config_path: Path = MONITORING_CONFIG_PATH,
        session_store: Optional[SessionStore] = None,
    ):
        self.config_path = config_path
        self.config: Optional[MonitoringConfig] = None
        self.running = False
        self.tasks: list[asyncio.Task] = []
        self._http_client: Optional[ClientSession] = None
        self._fetch_strand = get_fetch_strand()
        # Use provided store or get default
        self._store = session_store or get_store()
        # Create config loader instance (not singleton) to respect config_path
        from .config_loader import ConfigLoader
        self._config_loader = ConfigLoader(config_path=config_path, default_tick_interval_seconds=300)
        self._ticker_task: Optional[asyncio.Task] = None
        self._last_tick_config_hash: Optional[int] = None

    async def _get_http_client(self) -> ClientSession:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = ClientSession()
        return self._http_client

    async def load_config(self) -> MonitoringConfig:
        """Load monitoring configuration from YAML file (with hot-reload cache)."""
        logger.info(f"Loading monitoring config from {self.config_path} (via hot-reload cache)")

        # Use config loader which handles mtime checking and caching
        data = await self._config_loader.get_config()

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

        Uses the fetch orchestrator with the full command matrix to get current state.
        """
        # Map monitoring intent_type to fetch IntentType
        intent_type = INTENT_TYPE_MAPPING.get(rule.intent_type, IntentType.STATUS)

        # Build fetch context
        context = FetchContext(
            project_slug=rule.project_slug,
            namespace=rule.project_slug.replace("-", "") if rule.project_slug else None,
            repo_path=f"/home/coding/{rule.project_slug}" if rule.project_slug else None,
            app_name=rule.project_slug,
            deployment=rule.project_slug,
        )

        # Create fetch request
        request = FetchRequest(
            intent_type=intent_type,
            context=context,
            intent_id=f"monitoring-{rule.topic_id}",
            session_id="monitoring",
        )

        # Execute fetch using the orchestrator (uses full fetch command matrix)
        try:
            fetch_result = await execute_fetch(request)

            # Extract successful source data
            successful_data = fetch_result.get_successful_data()

            if not successful_data:
                logger.warning(f"No successful sources for {rule.topic_id}")
                return None

            # Build state data from all successful sources
            state_data = {
                "project_slug": rule.project_slug,
                "intent_type": rule.intent_type,
                "sources": list(successful_data.keys()),
                **{k: v for source in successful_data for k, v in successful_data[source].items()},
            }

            # Apply filters if specified
            if rule.filters:
                if not self._passes_filters(state_data, rule.filters):
                    # Filter means we don't report this state
                    logger.debug(f"State for {rule.topic_id} filtered by {rule.filters}")
                    return None

            logger.debug(f"Fetched state for {rule.topic_id} from {len(successful_data)} sources")
            return state_data

        except Exception as e:
            logger.error(f"Error checking state for {rule.topic_id}: {e}", exc_info=True)
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

    async def _get_topic_context_cache(self, topic_id: str) -> Optional[dict]:
        """Get cached context data for a topic from topic_context_cache table."""
        cached = await self._store.get_topic_context(topic_id)
        if cached:
            return cached.get("context")
        return None

    async def _update_topic_context_cache(
        self,
        topic_id: str,
        context_data: dict,
        ttl_seconds: int = TOPIC_CONTEXT_TTL_SECONDS,
    ) -> None:
        """Store context data in topic_context_cache table."""
        await self._store.set_topic_context(
            topic_id=topic_id,
            context_data=context_data,
            ttl_seconds=ttl_seconds,
        )

    async def detect_state_change(
        self,
        rule: MonitoringRule,
        current_state: dict,
    ) -> tuple[bool, dict]:
        """
        Detect if the state has changed since last check.

        Reads from topic_context_cache to get previous state.
        Returns (has_change, changes_dict) where changes_dict tracks what changed.

        The changes_dict includes:
        - 'changed_fields': list of field names that changed
        - 'diff': full diff between previous and current state
        - 'is_first': True if this is the first check (no previous state)
        """
        # Get cached context from database
        cached_context = await self._get_topic_context_cache(rule.topic_id)

        if cached_context is None:
            # First check - no previous state in cache yet
            # Store current state as baseline and don't notify
            await self._update_topic_context_cache(rule.topic_id, current_state)
            return False, {
                "is_first": True,
                "changed_fields": [],
                "diff": {},
            }

        # Compute diff between previous and current state
        diff = self._compute_diff(cached_context, current_state)
        changed_fields = list(diff.keys())

        # Check for state changes based on notification threshold
        if rule.notification_threshold == "any_change":
            # Any field change triggers notification
            has_change = len(changed_fields) > 0
        elif rule.notification_threshold == "state_change":
            # Only notify if specific state fields change
            # For status intents, check if phase, status, or health changed
            state_fields = ["phase", "status", "health", "ready", "sync_status", "sync_status"]
            significant_changes = [f for f in changed_fields if f in state_fields]
            has_change = len(significant_changes) > 0
        else:
            has_change = False

        return has_change, {
            "is_first": False,
            "changed_fields": changed_fields,
            "diff": diff,
        }

    async def push_monitoring_result(
        self,
        rule: MonitoringRule,
        current_state: dict,
        changes_dict: dict,
        session_id: str,
    ) -> None:
        """
        Push a monitoring result to the active surface.

        Creates a result in the session store with intent_id=NULL (system-originated).
        Reads previous state from topic_context_cache and updates it after writing result.
        """
        # Find or create topic for this monitoring rule
        topic_id, _ = await self._store.find_or_create_topic(
            label=rule.topic_id,
            session_id=session_id,
            topic_type="project",
            project_slugs=[rule.project_slug] if rule.project_slug else None,
        )

        # Get previous state from cache
        previous_state = await self._get_topic_context_cache(rule.topic_id)

        result_data = {
            "monitoring": True,
            "current_state": current_state,
            "previous_state": previous_state,
            "changed_fields": changes_dict.get("changed_fields", []),
            "diff": changes_dict.get("diff", {}),
            "is_first_check": changes_dict.get("is_first", False),
            "rule_filters": rule.filters,
            "notification_threshold": rule.notification_threshold,
        }

        # Derive result_type from monitoring intent type per plan §10
        result_type = derive_result_type(intent_type="monitoring", project_slug=rule.project_slug)

        # Write result with intent_id=NULL (system-originated, no utterance behind it)
        result_id = await self._store.create_result(
            intent_id=None,  # NULL for monitoring-originated results
            topic_id=topic_id,
            session_id=session_id,
            summary=self._generate_summary(rule, current_state, previous_state, changes_dict),
            data=result_data,
            urgency=rule.urgency,
            result_type=result_type,
        )

        # Render monitoring card via hot-path selector (deterministic, no LLM)
        renderer = get_renderer()
        summary_text = self._generate_summary(rule, current_state, previous_state, changes_dict)
        render_outcome = renderer.render(
            result_id=result_id,
            result_type=result_type,
            result_data=result_data,
            summary=summary_text,
            urgency=rule.urgency,
        )

        # Update result's card_fallback flag
        await self._store.update_result_card_fallback(result_id, render_outcome.card_fallback)

        logger.info(f"Created monitoring result {result_id} for topic {rule.topic_id} (intent_id=NULL)")

        # Fire SSE event for canvas update
        # Build result dict for broadcast
        result_for_broadcast = {
            "id": result_id,
            "intent_id": None,
            "topic_id": topic_id,
            "session_id": session_id,
            "summary": summary_text,
            "data": result_data,
            "urgency": rule.urgency,
            "result_type": result_type,
            "card_fallback": render_outcome.card_fallback,
            "rendered_html": render_outcome.rendered_html,
            "component_id": render_outcome.component_id,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }

        # Broadcast to all surfaces in the session
        await broadcast_result(
            result=result_for_broadcast,
            session_id=session_id,
        )

        logger.info(f"Broadcast SSE event for monitoring result {result_id}")

        # Update topic context cache with current state
        await self._update_topic_context_cache(rule.topic_id, current_state)

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
        changes_dict: dict,
    ) -> str:
        """Generate a summary for the monitoring result."""
        if changes_dict.get("is_first"):
            return f"Initial state check for {rule.topic_id}"

        changed_fields = changes_dict.get("changed_fields", [])
        diff = changes_dict.get("diff", {})

        # Check for specific state changes
        if "phase" in diff:
            prev_phase = diff["phase"].get("from")
            curr_phase = diff["phase"].get("to")
            return f"{rule.topic_id} phase changed from {prev_phase} to {curr_phase}"

        if "sync_status" in diff:
            prev_sync = diff["sync_status"].get("from")
            curr_sync = diff["sync_status"].get("to")
            return f"{rule.topic_id} sync status changed from {prev_sync} to {curr_sync}"

        if "health_status" in diff:
            prev_health = diff["health_status"].get("from")
            curr_health = diff["health_status"].get("to")
            return f"{rule.topic_id} health status changed from {prev_health} to {curr_health}"

        if changed_fields:
            return f"{rule.topic_id} changed: {', '.join(changed_fields[:3])}" + ("..." if len(changed_fields) > 3 else "")

        return f"{rule.topic_id} state updated"

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
                # Check current state (uses fetch command matrix)
                current_state = await self.check_topic_state(rule)

                if current_state:
                    # Detect change and get changes dict
                    has_change, changes_dict = await self.detect_state_change(rule, current_state)

                    if has_change:
                        logger.info(f"State change detected for {rule.topic_id}: {changes_dict.get('changed_fields', [])}")
                        await self.push_monitoring_result(rule, current_state, changes_dict, session_id)
                    else:
                        # Update cache even if no change (keeps it fresh)
                        await self._update_topic_context_cache(rule.topic_id, current_state)

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

        # Start the ticker task for config hot-reload
        self._ticker_task = asyncio.create_task(self._config_ticker())
        self.tasks.append(self._ticker_task)

        logger.info(f"Started {len(self.tasks)} topic monitors (including config ticker)")

    async def _config_ticker(self) -> None:
        """
        Config hot-reload ticker.

        Periodically checks if the config file has changed (via mtime) and reloads if needed.
        Runs on the tick_interval_seconds from the config.
        """
        logger.info("Config ticker started")

        while self.running:
            try:
                # Get current tick interval (may have changed from config)
                tick_interval = await self._config_loader.get_tick_interval_seconds()
                logger.debug(f"Config ticker: checking for changes (interval: {tick_interval}s)")

                # Get current config (auto-reloads if mtime changed)
                current_config = await self._config_loader.get_config()

                # Create a simple hash of the active topics to detect structural changes
                import json
                current_hash = hash(json.dumps(current_config.get("monitoring", {}).get("active_topics", []), sort_keys=True))

                if self._last_tick_config_hash != current_hash:
                    logger.info("Config structure changed, reloading monitors")
                    await self.reload_config()
                    self._last_tick_config_hash = current_hash
                else:
                    logger.debug("Config structure unchanged, no reload needed")

                # Wait for next tick
                await asyncio.sleep(tick_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in config ticker: {e}", exc_info=True)
                await asyncio.sleep(tick_interval)

        logger.info("Config ticker stopped")

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
        self._ticker_task = None

        # Close HTTP client
        if self._http_client:
            await self._http_client.close()

        logger.info("Ambient monitoring stopped")

    async def reload_config(self) -> None:
        """Reload monitoring configuration and restart topic monitors."""
        logger.info("Reloading monitoring configuration")

        # Separate ticker task from monitor tasks
        monitor_tasks = [t for t in self.tasks if t != self._ticker_task]
        self.tasks = [self._ticker_task] if self._ticker_task else []

        # Cancel old monitor tasks (but not the ticker)
        for task in monitor_tasks:
            task.cancel()
        await asyncio.gather(*monitor_tasks, return_exceptions=True)

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
