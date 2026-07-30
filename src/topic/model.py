"""
Topic model: organizing concerns across utterances.

Topics are persistent concerns that accumulate intents and results.
The canvas shows one card per active topic, updated in place.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from ..session.store import SessionStore


@dataclass
class Topic:
    """A persistent concern."""
    id: str
    label: str
    type: str  # 'project', 'research', 'personal', 'exception', 'compound'
    project_slugs: list[str]
    scope: str  # 'session', 'cross-session', 'global'
    session_id: Optional[str]
    created_at: int
    last_active: int
    archived_at: Optional[int] = None
    result_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "project_slugs": self.project_slugs,
            "scope": self.scope,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "archived_at": self.archived_at,
            "result_count": self.result_count,
        }


@dataclass
class TopicCard:
    """A topic card for the canvas - includes staleness info."""
    topic: Topic
    result_type: str  # Distinct card type within topic (e.g., 'status:ibkr-mcp', 'lookup:logs:options-pipeline')
    latest_result: Optional[dict] = None
    staleness_seconds: int = 0
    staleness_level: str = "fresh"  # 'fresh', 'stale', 'very_stale'

    @property
    def card_id(self) -> str:
        """Unique identifier for this card (topic_id + result_type)."""
        return f"{self.topic.id}::{self.result_type}"

    def to_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "topic": self.topic.to_dict(),
            "result_type": self.result_type,
            "latest_result": self.latest_result,
            "staleness": {
                "seconds": self.staleness_seconds,
                "level": self.staleness_level,
            },
        }


class TopicManager:
    """Manages topics and their relationship to intents and results."""

    # Staleness thresholds (in seconds)
    STALE_THRESHOLD = 600  # 10 minutes
    VERY_STALE_THRESHOLD = 3600  # 1 hour

    def __init__(self, store: SessionStore):
        self.store = store

    async def find_or_create_topic(
        self,
        label: str,
        session_id: str,
        topic_type: str = "adhoc",
        project_slugs: list[str] | None = None,
        scope: str = "session",
    ) -> Topic:
        """
        Find an existing topic or create a new one.

        For cross-session topics (scope='cross-session'), finds by label regardless of session.
        For session-scoped topics (scope='session'), finds by label within the current session.

        Args:
            label: Topic label
            session_id: Current session ID
            topic_type: Topic type ('project', 'research', 'personal', 'exception', 'compound', 'adhoc')
            project_slugs: List of project slugs
            scope: Topic scope ('session', 'cross-session', 'global')

        Returns:
            Topic object
        """
        topic_id, created = await self.store.find_or_create_topic(
            label=label,
            session_id=session_id,
            topic_type=topic_type,
            project_slugs=project_slugs,
            scope=scope,
        )

        # Fetch full topic data - get from active topics
        topics = await self.store.get_active_topics(session_id)
        topic_data = next((t for t in topics if t["id"] == topic_id), None)

        if topic_data:
            return Topic(
                id=topic_data["id"],
                label=topic_data["label"],
                type=topic_data.get("type", "adhoc"),
                project_slugs=json.loads(topic_data.get("project_slugs", "[]")),
                scope=topic_data["scope"],
                session_id=topic_data.get("session_id"),
                created_at=topic_data["created_at"],
                last_active=topic_data["last_active"],
                archived_at=topic_data.get("archived_at"),
                result_count=topic_data.get("result_count", 0),
            )

        # Fallback to basic topic (shouldn't normally reach here)
        return Topic(
            id=topic_id,
            label=label,
            type=topic_type,
            project_slugs=project_slugs or [],
            scope=scope,
            session_id=None if scope == "cross-session" else session_id,
            created_at=int(datetime.now().timestamp()),
            last_active=int(datetime.now().timestamp()),
        )

    async def get_active_topic_cards(self, session_id: str) -> list[TopicCard]:
        """
        Get all active topic cards for a session, with staleness info.

        Returns one card per (topic, result_type) pair, enabling granular
        canvas rendering where different result_types on the same topic
        coexist (e.g., status + brainstorm cards).
        """
        # Get latest result for each (topic_id, result_type) pair
        results_by_type = await self.store.get_latest_results_by_type(session_id)

        # Fetch topics for context
        topics_data = {t["id"]: t for t in await self.store.get_active_topics(session_id)}

        now = int(datetime.now().timestamp())
        cards = []

        for result in results_by_type:
            topic_id = result["topic_id"]
            result_type = result["result_type"]

            # Skip if topic not found (shouldn't happen with FK constraints)
            if topic_id not in topics_data:
                continue

            topic_data = topics_data[topic_id]
            topic = Topic(
                id=topic_data["id"],
                label=topic_data["label"],
                type=topic_data.get("type", "adhoc"),
                project_slugs=json.loads(topic_data.get("project_slugs", "[]")),
                scope=topic_data["scope"],
                session_id=topic_data.get("session_id"),
                created_at=topic_data["created_at"],
                last_active=topic_data["last_active"],
                archived_at=topic_data.get("archived_at"),
                result_count=topic_data.get("result_count", 0),
            )

            # Parse result data
            result["data"] = json.loads(result["data"])

            # Calculate staleness
            staleness_seconds = now - topic.last_active
            staleness_level = self._calculate_staleness(staleness_seconds)

            cards.append(TopicCard(
                topic=topic,
                result_type=result_type,
                latest_result=result,
                staleness_seconds=staleness_seconds,
                staleness_level=staleness_level,
            ))

        return cards

    async def update_topic_activity(self, topic_id: str) -> None:
        """Update a topic's last_active timestamp."""
        await self.store.update_topic_activity(topic_id)

    def _calculate_staleness(self, seconds: int) -> str:
        """Calculate staleness level from seconds since last activity."""
        if seconds < self.STALE_THRESHOLD:
            return "fresh"
        elif seconds < self.VERY_STALE_THRESHOLD:
            return "stale"
        else:
            return "very_stale"

    async def create_topic_from_intent(
        self,
        intent: dict,
        session_id: str,
    ) -> Topic:
        """
        Create or find a topic from an intent.

        Infers topic label from project_slug or creates ad hoc topic.
        Project topics are created as cross-session (scope='cross-session', session_id=NULL).
        Ad hoc topics are session-scoped (scope='session', session_id set).

        Args:
            intent: Intent dict with project_slug and intent_type
            session_id: Current session ID

        Returns:
            Topic object
        """
        project_slug = intent.get("project_slug")
        intent_type = intent.get("intent_type", "unknown")

        if project_slug:
            label = project_slug.replace("-", " ").title()
            topic_type = "project"
            project_slugs = [project_slug]
            scope = "cross-session"  # Project topics are cross-session
        else:
            # Create ad hoc topic from intent type
            label = f"{intent_type.title()} Task"
            topic_type = "adhoc"
            project_slugs = []
            scope = "session"  # Ad hoc topics are session-scoped

        return await self.find_or_create_topic(
            label=label,
            session_id=session_id,
            topic_type=topic_type,
            project_slugs=project_slugs,
            scope=scope,
        )

    async def link_intent_to_topic(
        self,
        intent_id: str,
        topic_id: str,
    ) -> None:
        """Link an intent to a topic."""
        await self.store.link_intent_to_topic(intent_id, topic_id)

    async def archive_topic(self, topic_id: str) -> None:
        """Archive a topic (mark as archived)."""
        # This would need to be added to SessionStore
        pass


class TopicRegistry:
    """
    Registry of known topics for cross-session resolution.

    Helps resolve vague references like "the pipeline" by maintaining
    a mapping of aliases and references.
    """

    def __init__(self):
        self._aliases: dict[str, str] = {}

    def register_alias(self, alias: str, topic_label: str) -> None:
        """Register an alias for a topic."""
        self._aliases[alias.lower()] = topic_label

    def resolve_alias(self, alias: str) -> str | None:
        """Resolve an alias to a topic label."""
        return self._aliases.get(alias.lower())

    def add_common_aliases(self) -> None:
        """Add common aliases for well-known topics."""
        common_aliases = {
            "pipeline": "options-pipeline",
            "the pipeline": "options-pipeline",
            "feed": "options-aggregator",
            "the feed": "options-aggregator",
            "mcp": "ibkr-mcp",
            "ibkr": "ibkr-mcp",
        }
        for alias, label in common_aliases.items():
            self.register_alias(alias, label)


# Global topic registry
_topic_registry: TopicRegistry | None = None


def get_topic_registry() -> TopicRegistry:
    """Get or create the global topic registry."""
    global _topic_registry
    if _topic_registry is None:
        _topic_registry = TopicRegistry()
        _topic_registry.add_common_aliases()
    return _topic_registry
