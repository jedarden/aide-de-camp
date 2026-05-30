"""
Implicit Feedback Signal Collection for aide-de-camp.

Tracks user behavior and generates implicit feedback signals
for the background analysis bead to process.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from logging import getLogger
from typing import Any, Optional
from uuid import uuid4

from ..session.store import get_store


logger = getLogger(__name__)


class SignalType(Enum):
    """Types of implicit feedback signals."""
    ACK_SPEED = "ack_speed"  # How quickly user acknowledged a result
    FOLLOW_UP_PATTERN = "follow_up_pattern"  # Follow-up question patterns
    SURFACE_SWITCH = "surface_switch"  # Audio-to-canvas switches
    RESULT_REQUERY = "result_requery"  # User asked same question again
    RESULT_SKIPPED = "result_skipped"  # User didn't acknowledge result
    TOPIC_CONTINUATION = "topic_continuation"  # User continued same topic
    TOPIC_SWITCH = "topic_switch"  # User switched topics


@dataclass
class FeedbackSignal:
    """A single implicit feedback signal."""
    signal_id: str
    signal_type: SignalType
    session_id: str
    result_id: Optional[str]
    topic_id: Optional[str]
    timestamp: int
    data: dict[str, Any]
    surface_type: Optional[str] = None


class ImplicitFeedbackTracker:
    """
    Tracks implicit user feedback signals.

    Monitors:
    - Result acknowledgment speed (fast = positive, slow = negative)
    - Follow-up question patterns (indicates what was missing)
    - Surface switch timing (audio-to-canvas indicates poor narration)
    - Result re-queries (indicates inadequate result)
    - Topic continuation vs switch
    """

    def __init__(self):
        # Track result creation times for ack speed calculation
        self._result_created_at: dict[str, int] = {}  # result_id -> created_at
        # Track recent utterances per topic for pattern detection
        self._recent_utterances: dict[str, list[dict]] = {}  # session_id -> [{utterance, topic_id, timestamp}]
        # Track re-query attempts
        self._query_attempts: dict[str, list[str]] = {}  # normalized_query -> [result_ids]
        # Track surface switches
        self._surface_switches: dict[str, list[dict]] = {}  # session_id -> [{from_surface, to_surface, timestamp, result_id}]

    async def track_result_created(self, result_id: str, session_id: str, topic_id: Optional[str]) -> None:
        """Track when a result was created for ack speed calculation."""
        now = int(datetime.now(timezone.utc).timestamp())
        self._result_created_at[result_id] = now
        logger.debug(f"Tracked result creation: {result_id} at {now}")

    async def track_result_acknowledged(
        self,
        result_id: str,
        session_id: str,
        surface_type: str,
    ) -> Optional[FeedbackSignal]:
        """
        Track when a user acknowledged a result.

        Generates an ack_speed signal.
        """
        if result_id not in self._result_created_at:
            logger.warning(f"Result {result_id} not tracked for creation time")
            return None

        created_at = self._result_created_at[result_id]
        now = int(datetime.now(timezone.utc).timestamp())
        ack_delay_seconds = now - created_at

        # Clean up old entries
        del self._result_created_at[result_id]

        # Determine signal quality
        # Fast ack (< 10s) = positive signal
        # Medium ack (10-60s) = neutral
        # Slow ack (> 60s) = negative signal
        # Very slow ack (> 300s) = strongly negative (may have been ignored)
        if ack_delay_seconds < 10:
            quality = "positive"
        elif ack_delay_seconds < 60:
            quality = "neutral"
        elif ack_delay_seconds < 300:
            quality = "negative"
        else:
            quality = "strongly_negative"

        signal = FeedbackSignal(
            signal_id=str(uuid4()),
            signal_type=SignalType.ACK_SPEED,
            session_id=session_id,
            result_id=result_id,
            topic_id=None,  # We don't track topic for ack speed
            timestamp=now,
            data={
                "ack_delay_seconds": ack_delay_seconds,
                "quality": quality,
                "surface_type": surface_type,
            },
            surface_type=surface_type,
        )

        await self._store_signal(signal)
        logger.info(f"Tracked ack_speed signal: {ack_delay_seconds}s ({quality})")

        return signal

    async def track_utterance(
        self,
        session_id: str,
        utterance: str,
        topic_id: Optional[str],
        is_follow_up: bool,
    ) -> None:
        """
        Track an utterance for pattern detection.

        Generates follow_up_pattern and topic_switch/continuation signals.
        """
        now = int(datetime.now(timezone.utc).timestamp())

        # Store utterance
        if session_id not in self._recent_utterances:
            self._recent_utterances[session_id] = []

        self._recent_utterances[session_id].append({
            "utterance": utterance,
            "topic_id": topic_id,
            "timestamp": now,
            "is_follow_up": is_follow_up,
        })

        # Keep only last 50 utterances
        if len(self._recent_utterances[session_id]) > 50:
            self._recent_utterances[session_id] = self._recent_utterances[session_id][-50:]

        # Check for follow-up pattern
        if is_follow_up and topic_id:
            await self._analyze_follow_up_pattern(session_id, utterance, topic_id, now)

        # Check for topic switch vs continuation
        await self._analyze_topic_switch(session_id, topic_id, now)

    async def _analyze_follow_up_pattern(
        self,
        session_id: str,
        utterance: str,
        topic_id: str,
        timestamp: int,
    ) -> None:
        """Analyze follow-up patterns to detect what was missing from previous result."""
        utterances = self._recent_utterances.get(session_id, [])

        # Look for the previous utterance on the same topic
        prev_utterance = None
        for u in reversed(utterances[:-1]):  # Exclude current utterance
            if u["topic_id"] == topic_id:
                prev_utterance = u
                break

        if not prev_utterance:
            return

        # Analyze follow-up type
        utterance_lower = utterance.lower()

        follow_up_type = None
        if any(word in utterance_lower for word in ["why", "how come", "reason"]):
            follow_up_type = "why_question"  # Previous result lacked explanation
        elif any(word in utterance_lower for word in ["how long", "when", "time"]):
            follow_up_type = "temporal_question"  # Previous result lacked timing info
        elif any(word in utterance_lower for word in ["what else", "more detail", "tell me more"]):
            follow_up_type = "more_detail"  # Previous result was insufficient
        elif any(word in utterance_lower for word in ["status", "current state", "what's happening"]):
            follow_up_type = "status_check"  # User checking if state changed
        elif any(word in utterance_lower for word in ["fix", "solve", "resolve"]):
            follow_up_type = "action_request"  # User wants to take action

        if follow_up_type:
            signal = FeedbackSignal(
                signal_id=str(uuid4()),
                signal_type=SignalType.FOLLOW_UP_PATTERN,
                session_id=session_id,
                result_id=None,
                topic_id=topic_id,
                timestamp=timestamp,
                data={
                    "follow_up_type": follow_up_type,
                    "utterance": utterance,
                    "prev_utterance": prev_utterance["utterance"],
                    "time_since_prev": timestamp - prev_utterance["timestamp"],
                },
            )

            await self._store_signal(signal)
            logger.info(f"Tracked follow_up_pattern: {follow_up_type}")

    async def _analyze_topic_switch(
        self,
        session_id: str,
        topic_id: Optional[str],
        timestamp: int,
    ) -> None:
        """Analyze whether user switched topics or continued."""
        utterances = self._recent_utterances.get(session_id, [])

        if len(utterances) < 2:
            return

        # Compare with previous utterance
        prev_utterance = utterances[-2]
        prev_topic_id = prev_utterance.get("topic_id")

        if prev_topic_id == topic_id and topic_id is not None:
            # Topic continuation
            signal = FeedbackSignal(
                signal_id=str(uuid4()),
                signal_type=SignalType.TOPIC_CONTINUATION,
                session_id=session_id,
                result_id=None,
                topic_id=topic_id,
                timestamp=timestamp,
                data={
                    "turn_count": sum(1 for u in utterances if u.get("topic_id") == topic_id),
                    "time_in_topic": timestamp - min(
                        u["timestamp"] for u in utterances if u.get("topic_id") == topic_id
                    ) if any(u.get("topic_id") == topic_id for u in utterances) else 0,
                },
            )

            await self._store_signal(signal)

        elif prev_topic_id != topic_id and prev_topic_id and topic_id:
            # Topic switch
            signal = FeedbackSignal(
                signal_id=str(uuid4()),
                signal_type=SignalType.TOPIC_SWITCH,
                session_id=session_id,
                result_id=None,
                topic_id=topic_id,
                timestamp=timestamp,
                data={
                    "from_topic_id": prev_topic_id,
                    "to_topic_id": topic_id,
                },
            )

            await self._store_signal(signal)
            logger.info(f"Tracked topic_switch: {prev_topic_id} -> {topic_id}")

    async def track_surface_switch(
        self,
        session_id: str,
        from_surface: str,
        to_surface: str,
        pending_result_count: int,
    ) -> None:
        """
        Track a surface switch event.

        Generates surface_switch signal. Audio-to-canvas with pending results
        indicates poor narration or complex data.
        """
        now = int(datetime.now(timezone.utc).timestamp())

        if session_id not in self._surface_switches:
            self._surface_switches[session_id] = []

        switch_data = {
            "from_surface": from_surface,
            "to_surface": to_surface,
            "timestamp": now,
            "pending_result_count": pending_result_count,
        }

        self._surface_switches[session_id].append(switch_data)

        # Keep only last 20 switches
        if len(self._surface_switches[session_id]) > 20:
            self._surface_switches[session_id] = self._surface_switches[session_id][-20:]

        # If switching from audio to canvas with pending results, signal
        if from_surface == "audio" and to_surface == "canvas" and pending_result_count > 0:
            signal = FeedbackSignal(
                signal_id=str(uuid4()),
                signal_type=SignalType.SURFACE_SWITCH,
                session_id=session_id,
                result_id=None,
                topic_id=None,
                timestamp=now,
                data={
                    "from_surface": from_surface,
                    "to_surface": to_surface,
                    "pending_result_count": pending_result_count,
                    "reason": "audio_to_canvas_with_pending",
                },
            )

            await self._store_signal(signal)
            logger.info(f"Tracked surface_switch: audio->canvas with {pending_result_count} pending results")

    async def track_requery(
        self,
        session_id: str,
        utterance: str,
        previous_result_ids: list[str],
    ) -> None:
        """
        Track a re-query (user asked same/similar question again).

        Indicates previous result was inadequate.
        """
        now = int(datetime.now(timezone.utc).timestamp())

        # Normalize utterance for comparison
        normalized = self._normalize_utterance(utterance)

        if normalized not in self._query_attempts:
            self._query_attempts[normalized] = []

        self._query_attempts[normalized].extend(previous_result_ids)

        # If we've seen this query before, signal re-query
        if len(self._query_attempts[normalized]) > len(previous_result_ids):
            signal = FeedbackSignal(
                signal_id=str(uuid4()),
                signal_type=SignalType.RESULT_REQUERY,
                session_id=session_id,
                result_id=previous_result_ids[-1] if previous_result_ids else None,
                topic_id=None,
                timestamp=now,
                data={
                    "utterance": utterance,
                    "normalized": normalized,
                    "previous_result_ids": previous_result_ids,
                    "attempt_count": len(self._query_attempts[normalized]),
                },
            )

            await self._store_signal(signal)
            logger.info(f"Tracked result_requery: attempt {len(self._query_attempts[normalized])}")

    async def track_result_skipped(
        self,
        result_id: str,
        session_id: str,
        time_until_skip: int,
    ) -> None:
        """
        Track when a result was skipped (not acknowledged before surface disconnect).

        Indicates low interest or poor delivery.
        """
        now = int(datetime.now(timezone.utc).timestamp())

        signal = FeedbackSignal(
            signal_id=str(uuid4()),
            signal_type=SignalType.RESULT_SKIPPED,
            session_id=session_id,
            result_id=result_id,
            topic_id=None,
            timestamp=now,
            data={
                "time_until_skip_seconds": time_until_skip,
            },
        )

        await self._store_signal(signal)
        logger.info(f"Tracked result_skipped: {result_id} after {time_until_skip}s")

    async def _store_signal(self, signal: FeedbackSignal) -> None:
        """Store a signal in the session store."""
        store = get_store()
        await store.create_feedback_signal(
            signal_id=signal.signal_id,
            signal_type=signal.signal_type.value,
            session_id=signal.session_id,
            result_id=signal.result_id,
            topic_id=signal.topic_id,
            timestamp=signal.timestamp,
            data=signal.data,
        )

    def _normalize_utterance(self, utterance: str) -> str:
        """Normalize utterance for comparison."""
        return utterance.lower().strip()

    def get_session_signals(
        self,
        session_id: str,
        signal_type: Optional[SignalType] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get recent signals for a session (for background analysis)."""
        # This would query the session store in production
        # For now, return empty list
        return []

    def clear_session(self, session_id: str) -> None:
        """Clear tracking data for a session."""
        self._recent_utterances.pop(session_id, None)
        self._surface_switches.pop(session_id, None)
        logger.debug(f"Cleared feedback tracking for session {session_id}")


# Global feedback tracker instance
_feedback_tracker: Optional[ImplicitFeedbackTracker] = None


def get_feedback_tracker() -> ImplicitFeedbackTracker:
    """Get or create the global feedback tracker instance."""
    global _feedback_tracker
    if _feedback_tracker is None:
        _feedback_tracker = ImplicitFeedbackTracker()
    return _feedback_tracker
