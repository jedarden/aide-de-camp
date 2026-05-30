"""
Multi-turn conversation tracker.

Tracks conversation focus so follow-up questions deepen current topic context.
Implements topic focus tracking and disambiguation for ambiguous utterances.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging import getLogger
from typing import Optional
from uuid import uuid4

from ..session.store import get_store


logger = getLogger(__name__)

# How long a topic remains "in focus" after activity
FOCUS_TTL_SECONDS = 300  # 5 minutes


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    turn_id: str
    session_id: str
    utterance: str
    primary_topic_id: Optional[str]
    related_topic_ids: list[str]
    timestamp: int
    was_follow_up: bool = False

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "utterance": self.utterance,
            "primary_topic_id": self.primary_topic_id,
            "related_topic_ids": self.related_topic_ids,
            "timestamp": self.timestamp,
            "was_follow_up": self.was_follow_up,
        }


@dataclass
class TopicFocus:
    """The current topic focus for a session."""
    session_id: str
    primary_topic_id: Optional[str]
    primary_topic_label: Optional[str]
    last_activity: int
    turn_count: int = 0

    def is_valid(self) -> bool:
        """Check if this focus is still valid (not expired)."""
        age = int(datetime.now(timezone.utc).timestamp()) - self.last_activity
        return age < FOCUS_TTL_SECONDS

    def age_seconds(self) -> int:
        """Get age of this focus in seconds."""
        return int(datetime.now(timezone.utc).timestamp()) - self.last_activity


class ConversationTracker:
    """
    Tracks conversation focus for multi-turn topic interactions.

    Maintains:
    - Current topic focus for each session
    - History of conversation turns
    - Disambiguation hints for ambiguous utterances
    """

    def __init__(self):
        # session_id -> TopicFocus
        self._focus: dict[str, TopicFocus] = {}
        # session_id -> list[ConversationTurn]
        self._history: dict[str, list[ConversationTurn]] = {}
        # session_id -> list[str] (recent topic IDs for disambiguation)
        self._recent_topics: dict[str, list[str]] = {}

    async def record_turn(
        self,
        session_id: str,
        utterance: str,
        primary_topic_id: Optional[str],
        related_topic_ids: list[str] = None,
        is_follow_up: bool = False,
    ) -> ConversationTurn:
        """
        Record a conversation turn.

        Updates the current focus and history for the session.
        """
        now = int(datetime.now(timezone.utc).timestamp())
        turn_id = str(uuid4())

        if related_topic_ids is None:
            related_topic_ids = []

        turn = ConversationTurn(
            turn_id=turn_id,
            session_id=session_id,
            utterance=utterance,
            primary_topic_id=primary_topic_id,
            related_topic_ids=related_topic_ids,
            timestamp=now,
            was_follow_up=is_follow_up,
        )

        # Update focus
        if primary_topic_id:
            if session_id not in self._focus or self._focus[session_id].primary_topic_id != primary_topic_id:
                # New or changed focus
                self._focus[session_id] = TopicFocus(
                    session_id=session_id,
                    primary_topic_id=primary_topic_id,
                    primary_topic_label=await self._get_topic_label(primary_topic_id),
                    last_activity=now,
                    turn_count=1,
                )
            else:
                # Same focus, update activity
                self._focus[session_id].last_activity = now
                self._focus[session_id].turn_count += 1

        # Add to history
        if session_id not in self._history:
            self._history[session_id] = []
        self._history[session_id].append(turn)

        # Keep only last 20 turns
        if len(self._history[session_id]) > 20:
            self._history[session_id] = self._history[session_id][-20:]

        # Update recent topics
        self._update_recent_topics(session_id, primary_topic_id, related_topic_ids)

        logger.debug(
            f"Recorded turn {turn_id} for session {session_id}, "
            f"topic: {primary_topic_id}, follow_up: {is_follow_up}"
        )

        return turn

    async def detect_follow_up(
        self,
        session_id: str,
        utterance: str,
        detected_topics: list[str],
    ) -> tuple[bool, Optional[str]]:
        """
        Detect if an utterance is a follow-up to the current topic focus.

        Returns (is_follow_up, suggested_topic_id).
        """
        # Check if we have an active focus
        focus = self._focus.get(session_id)
        if not focus or not focus.is_valid():
            return False, None

        # Check if utterance contains follow-up indicators
        follow_up_indicators = [
            "why", "how long", "since when", "what about", "and", "also",
            "more detail", "tell me more", "what else", "then what",
        ]
        utterance_lower = utterance.lower()
        has_indicator = any(ind in utterance_lower for ind in follow_up_indicators)

        # Check if detected topics include the focus topic
        if focus.primary_topic_id in detected_topics:
            # The utterance relates to the current focus topic
            return True, focus.primary_topic_id

        # Check if utterance is very short (likely follow-up)
        # and no other topics detected
        if len(utterance.split()) < 5 and len(detected_topics) == 0:
            # Assume follow-up to current focus
            return True, focus.primary_topic_id

        # Check for pronouns that refer to "it", "that", "this"
        pronoun_indicators = ["it", "that", "this", "there"]
        if any(pronoun in utterance_lower.split() for pronoun in pronoun_indicators):
            if has_indicator or len(detected_topics) == 0:
                return True, focus.primary_topic_id

        # Not a clear follow-up
        return False, None

    def get_focus(self, session_id: str) -> Optional[TopicFocus]:
        """Get the current topic focus for a session."""
        focus = self._focus.get(session_id)
        if focus and focus.is_valid():
            return focus
        return None

    def get_history(self, session_id: str, limit: int = 10) -> list[ConversationTurn]:
        """Get recent conversation turns for a session."""
        history = self._history.get(session_id, [])
        return history[-limit:] if history else []

    def _update_recent_topics(
        self,
        session_id: str,
        primary_topic_id: Optional[str],
        related_topic_ids: list[str],
    ) -> None:
        """Update the list of recent topics for a session."""
        if session_id not in self._recent_topics:
            self._recent_topics[session_id] = []

        # Add primary topic
        if primary_topic_id:
            if primary_topic_id not in self._recent_topics[session_id]:
                self._recent_topics[session_id].insert(0, primary_topic_id)

        # Add related topics
        for topic_id in related_topic_ids:
            if topic_id not in self._recent_topics[session_id]:
                self._recent_topics[session_id].append(topic_id)

        # Keep only last 10
        self._recent_topics[session_id] = self._recent_topics[session_id][:10]

    async def _get_topic_label(self, topic_id: str) -> Optional[str]:
        """Get the label for a topic."""
        store = get_store()
        # This is a simplified lookup - in practice we'd query the topics table
        # For now, return None
        return None

    def disambiguate(
        self,
        session_id: str,
        utterance: str,
        detected_topics: list[str],
    ) -> Optional[str]:
        """
        Disambiguate an utterance by applying conversation context.

        Returns the most likely topic_id, or None if still ambiguous.
        """
        # If only one topic detected, use it
        if len(detected_topics) == 1:
            return detected_topics[0]

        # If no topics detected, check current focus
        if not detected_topics:
            focus = self.get_focus(session_id)
            if focus:
                return focus.primary_topic_id
            return None

        # Multiple topics detected - prefer current focus if it's in the list
        focus = self.get_focus(session_id)
        if focus and focus.primary_topic_id in detected_topics:
            return focus.primary_topic_id

        # Prefer most recently mentioned topic
        recent = self._recent_topics.get(session_id, [])
        for topic_id in recent:
            if topic_id in detected_topics:
                return topic_id

        # Still ambiguous - return None to trigger clarification
        return None

    def clear_session(self, session_id: str) -> None:
        """Clear conversation state for a session."""
        self._focus.pop(session_id, None)
        self._history.pop(session_id, None)
        self._recent_topics.pop(session_id, None)
        logger.debug(f"Cleared conversation state for session {session_id}")

    def get_stats(self, session_id: str) -> dict:
        """Get conversation statistics for a session."""
        focus = self.get_focus(session_id)
        history = self.get_history(session_id)

        return {
            "has_focus": focus is not None,
            "focus_topic_id": focus.primary_topic_id if focus else None,
            "focus_topic_label": focus.primary_topic_label if focus else None,
            "focus_age_seconds": focus.age_seconds() if focus else None,
            "focus_turn_count": focus.turn_count if focus else 0,
            "total_turns": len(history),
            "follow_up_count": sum(1 for t in history if t.was_follow_up),
        }


# Global conversation tracker instance
_conversation_tracker: Optional[ConversationTracker] = None


def get_conversation_tracker() -> ConversationTracker:
    """Get or create the global conversation tracker instance."""
    global _conversation_tracker
    if _conversation_tracker is None:
        _conversation_tracker = ConversationTracker()
    return _conversation_tracker
