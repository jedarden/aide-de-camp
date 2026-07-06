"""
TTS/Narration Test Module

Provides test endpoints for:
- Capturing narration events without actual audio output
- Verifying narration content, timing, and urgency
- Mock TTS output for programmatic verification
- Testing narration state transitions and urgency handling
"""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger
from typing import Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .router import router


logger = getLogger(__name__)


class UrgencyLevel(str, Enum):
    """Urgency levels for narration."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class NarrationEvent:
    """A captured narration event."""
    event_id: str
    timestamp: float
    event_type: str
    results: list[dict] = field(default_factory=list)
    grouped_by_topic: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "results": self.results,
            "grouped_by_topic": self.grouped_by_topic,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat(),
        }


@dataclass
class TTSCapture:
    """Captured TTS output for verification."""
    utterance_id: str
    text: str
    voice: str
    duration_seconds: float
    sample_rate: int
    file_size: int
    timestamp: float

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "utterance_id": self.utterance_id,
            "text": self.text,
            "voice": self.voice,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
            "file_size": self.file_size,
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat(),
        }


class NarrationSession:
    """
    Mock voice session for testing narration without audio output.

    Captures narration events and TTS output for programmatic verification.
    """

    def __init__(self, session_id: str, voice: str = "alloy"):
        self.session_id = session_id
        self.voice = voice
        self.narration_events: list[NarrationEvent] = []
        self.tts_captures: list[TTSCapture] = []
        self._is_speaking = False
        self._user_last_spoke = 0.0
        self._last_narration_time = 0.0
        self.created_at = time.time()

    def capture_narration_event(self, event_data: dict) -> NarrationEvent:
        """Capture a narration event for testing."""
        event = NarrationEvent(
            event_id=str(uuid.uuid4()),
            timestamp=time.time(),
            event_type=event_data.get("type", "narration"),
            results=event_data.get("results", []),
            grouped_by_topic=event_data.get("grouped_by_topic", {}),
        )
        self.narration_events.append(event)
        logger.info(f"[NARRATION_TEST] Captured event: {event.event_id}")
        return event

    def capture_tts_output(
        self,
        text: str,
        duration_seconds: float,
        sample_rate: int = 24000,
        file_size: int = 0,
    ) -> TTSCapture:
        """Capture TTS output for testing."""
        capture = TTSCapture(
            utterance_id=str(uuid.uuid4()),
            text=text,
            voice=self.voice,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            file_size=file_size,
            timestamp=time.time(),
        )
        self.tts_captures.append(capture)
        logger.info(f"[NARRATION_TEST] Captured TTS: {text[:50]}...")
        return capture

    def get_narration_summary(self) -> dict:
        """Get summary of captured narration events."""
        if not self.narration_events:
            return {
                "session_id": self.session_id,
                "total_events": 0,
                "total_results": 0,
                "urgencies": [],
                "topics": [],
            }

        all_results = []
        urgencies = []
        topics = set()

        for event in self.narration_events:
            all_results.extend(event.results)
            for result in event.results:
                urgency = result.get("urgency", "normal")
                urgencies.append(urgency)
                topic_id = result.get("topic_id", "general")
                topics.add(topic_id)

        return {
            "session_id": self.session_id,
            "total_events": len(self.narration_events),
            "total_results": len(all_results),
            "urgencies": urgencies,
            "topics": list(topics),
            "duration_seconds": time.time() - self.created_at,
        }

    def get_tts_summary(self) -> dict:
        """Get summary of captured TTS output."""
        if not self.tts_captures:
            return {
                "session_id": self.session_id,
                "total_captures": 0,
                "total_duration": 0.0,
                "total_size": 0,
            }

        total_duration = sum(c.duration_seconds for c in self.tts_captures)
        total_size = sum(c.file_size for c in self.tts_captures)

        return {
            "session_id": self.session_id,
            "total_captures": len(self.tts_captures),
            "total_duration": total_duration,
            "average_duration": total_duration / len(self.tts_captures),
            "total_size": total_size,
            "voice": self.voice,
        }

    def verify_timing(self, expected_window_seconds: float = 5.0) -> dict:
        """
        Verify narration timing matches expected batching window.

        Returns verification results with timing analysis.
        """
        if len(self.narration_events) < 2:
            return {
                "session_id": self.session_id,
                "verified": True,
                "message": "Insufficient events for timing verification",
                "event_count": len(self.narration_events),
            }

        timestamps = [e.timestamp for e in self.narration_events]
        intervals = [
            timestamps[i] - timestamps[i-1]
            for i in range(1, len(timestamps))
        ]

        within_window = all(i <= expected_window_seconds for i in intervals)

        return {
            "session_id": self.session_id,
            "verified": within_window,
            "expected_window_seconds": expected_window_seconds,
            "intervals": intervals,
            "average_interval": sum(intervals) / len(intervals) if intervals else 0,
            "max_interval": max(intervals) if intervals else 0,
            "event_count": len(self.narration_events),
        }

    def verify_urgency_order(self) -> dict:
        """
        Verify that results are narrated in correct urgency order.

        Critical should come before high, which should come before normal/low.
        """
        urgency_priority = {
            "critical": 0,
            "high": 1,
            "normal": 2,
            "low": 3,
        }

        all_urgencies = []
        for event in self.narration_events:
            for result in event.results:
                urgency = result.get("urgency", "normal")
                all_urgencies.append(urgency)

        priorities = [urgency_priority.get(u, 99) for u in all_urgencies]

        # Check if priorities are non-decreasing
        is_correct_order = all(
            priorities[i] <= priorities[i+1]
            for i in range(len(priorities) - 1)
        )

        return {
            "session_id": self.session_id,
            "verified": is_correct_order,
            "urgency_sequence": all_urgencies,
            "priority_sequence": priorities,
            "total_checked": len(all_urgencies),
        }

    def verify_tts_properties(self) -> dict:
        """Verify TTS output has expected properties."""
        if not self.tts_captures:
            return {
                "session_id": self.session_id,
                "verified": False,
                "message": "No TTS captures to verify",
            }

        # Check all captures have valid properties
        all_valid = all(
            c.duration_seconds > 0
            and c.sample_rate > 0
            and c.file_size > 0
            and len(c.text) > 0
            for c in self.tts_captures
        )

        return {
            "session_id": self.session_id,
            "verified": all_valid,
            "total_captures": len(self.tts_captures),
            "invalid_captures": [
                c.utterance_id for c in self.tts_captures
                if not (c.duration_seconds > 0 and c.sample_rate > 0 and c.file_size > 0)
            ],
        }


# Global session registry for testing
_test_sessions: dict[str, NarrationSession] = {}


def get_test_session(session_id: str, voice: str = "alloy") -> NarrationSession:
    """Get or create a test narration session."""
    if session_id not in _test_sessions:
        _test_sessions[session_id] = NarrationSession(session_id, voice)
        logger.info(f"[NARRATION_TEST] Created session: {session_id}")
    return _test_sessions[session_id]


def cleanup_test_session(session_id: str) -> bool:
    """Clean up a test session."""
    if session_id in _test_sessions:
        del _test_sessions[session_id]
        logger.info(f"[NARRATION_TEST] Cleaned up session: {session_id}")
        return True
    return False


# Pydantic models for API requests/responses
class CreateNarrationSessionRequest(BaseModel):
    """Request to create a narration test session."""
    session_id: str = Field(..., description="Test session ID")
    voice: str = Field(default="alloy", description="Voice to use")


class InjectNarrationEventRequest(BaseModel):
    """Request to inject a test narration event."""
    session_id: str = Field(..., description="Test session ID")
    results: list[dict] = Field(..., description="Results to narrate")
    grouped_by_topic: dict = Field(default_factory=dict, description="Topic-grouped results")


class InjectTTSCaptureRequest(BaseModel):
    """Request to inject a test TTS capture."""
    session_id: str = Field(..., description="Test session ID")
    text: str = Field(..., description="Spoken text")
    duration_seconds: float = Field(..., description="Audio duration in seconds")
    sample_rate: int = Field(default=24000, description="Audio sample rate")
    file_size: int = Field(default=1024, description="Audio file size in bytes")


class VerifyNarrationRequest(BaseModel):
    """Request to verify narration properties."""
    session_id: str = Field(..., description="Test session ID")
    expected_window_seconds: float = Field(default=5.0, description="Expected batching window")


@router.post("/test/narration/session")
async def create_narration_session(request: CreateNarrationSessionRequest) -> dict:
    """
    Create a narration test session.

    Creates a mock voice session that captures narration events and TTS output
    for testing without actual audio output.

    Request body:
    {
        "session_id": "test-session-id",
        "voice": "alloy"
    }

    Returns:
    {
        "status": "created",
        "session_id": "...",
        "voice": "alloy",
        "timestamp": "..."
    }
    """
    session = get_test_session(request.session_id, request.voice)

    return {
        "status": "created",
        "session_id": session.session_id,
        "voice": session.voice,
        "created_at": session.created_at,
    }


@router.post("/test/narration/inject")
async def inject_narration_event(request: InjectNarrationEventRequest) -> dict:
    """
    Inject a test narration event.

    Simulates a narration event that would be sent to the client.
    Captures the event for verification.

    Request body:
    {
        "session_id": "test-session-id",
        "results": [
            {
                "intent_id": "...",
                "topic_id": "...",
                "summary": "...",
                "urgency": "critical|high|normal|low"
            }
        ],
        "grouped_by_topic": {
            "topic_id": ["summary1", "summary2"]
        }
    }

    Returns:
    {
        "status": "injected",
        "event_id": "...",
        "timestamp": "..."
    }
    """
    session = get_test_session(request.session_id)

    event = session.capture_narration_event({
        "type": "adc.narrate_results",
        "results": request.results,
        "grouped_by_topic": request.grouped_by_topic,
    })

    return {
        "status": "injected",
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "result_count": len(event.results),
    }


@router.post("/test/narration/tts")
async def inject_tts_capture(request: InjectTTSCaptureRequest) -> dict:
    """
    Inject a test TTS capture.

    Simulates TTS audio output for testing.
    Captures the audio properties for verification.

    Request body:
    {
        "session_id": "test-session-id",
        "text": "The text that was spoken",
        "duration_seconds": 2.5,
        "sample_rate": 24000,
        "file_size": 60000
    }

    Returns:
    {
        "status": "captured",
        "utterance_id": "...",
        "timestamp": "...",
        "duration_seconds": 2.5
    }
    """
    session = get_test_session(request.session_id)

    capture = session.capture_tts_output(
        text=request.text,
        duration_seconds=request.duration_seconds,
        sample_rate=request.sample_rate,
        file_size=request.file_size,
    )

    return {
        "status": "captured",
        "utterance_id": capture.utterance_id,
        "timestamp": capture.timestamp,
        "text": capture.text,
        "duration_seconds": capture.duration_seconds,
    }


@router.get("/test/narration/session/{session_id}")
async def get_narration_session(session_id: str) -> dict:
    """
    Get narration session details.

    Returns detailed information about a test narration session including
    captured events and TTS output.

    Returns:
    {
        "session_id": "...",
        "voice": "alloy",
        "created_at": "...",
        "narration_summary": {...},
        "tts_summary": {...},
        "events": [...],
        "tts_captures": [...]
    }
    """
    if session_id not in _test_sessions:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    session = _test_sessions[session_id]

    return {
        "session_id": session.session_id,
        "voice": session.voice,
        "created_at": session.created_at,
        "narration_summary": session.get_narration_summary(),
        "tts_summary": session.get_tts_summary(),
        "events": [e.to_dict() for e in session.narration_events],
        "tts_captures": [c.to_dict() for c in session.tts_captures],
    }


@router.post("/test/narration/verify")
async def verify_narration(request: VerifyNarrationRequest) -> dict:
    """
    Verify narration properties.

    Verifies that narration meets expected criteria for:
    - Timing (batching windows)
    - Urgency ordering (critical before high before normal/low)
    - TTS output properties (non-zero duration, sample rate, file size)

    Request body:
    {
        "session_id": "test-session-id",
        "expected_window_seconds": 5.0
    }

    Returns:
    {
        "session_id": "...",
        "timing_verified": {...},
        "urgency_order_verified": {...},
        "tts_properties_verified": {...},
        "overall_verified": true
    }
    """
    if request.session_id not in _test_sessions:
        raise HTTPException(status_code=404, detail=f"Session {request.session_id} not found")

    session = _test_sessions[request.session_id]

    timing_result = session.verify_timing(request.expected_window_seconds)
    urgency_result = session.verify_urgency_order()
    tts_result = session.verify_tts_properties()

    overall_verified = (
        timing_result.get("verified", False)
        and urgency_result.get("verified", False)
        and tts_result.get("verified", True)  # TTS can be empty if no audio
    )

    return {
        "session_id": request.session_id,
        "timing_verified": timing_result,
        "urgency_order_verified": urgency_result,
        "tts_properties_verified": tts_result,
        "overall_verified": overall_verified,
    }


@router.delete("/test/narration/session/{session_id}")
async def delete_narration_session(session_id: str) -> dict:
    """
    Clean up a narration test session.

    Deletes the session and all captured events.

    Returns:
    {
        "status": "deleted",
        "session_id": "..."
    }
    """
    if not cleanup_test_session(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return {
        "status": "deleted",
        "session_id": session_id,
    }


@router.get("/test/narration/sessions")
async def list_narration_sessions() -> dict:
    """
    List all active narration test sessions.

    Returns:
    {
        "sessions": ["session-id-1", "session-id-2"],
        "total": 2
    }
    """
    return {
        "sessions": list(_test_sessions.keys()),
        "total": len(_test_sessions),
    }


@router.post("/test/narration/cleanup")
async def cleanup_all_sessions() -> dict:
    """
    Clean up all narration test sessions.

    Deletes all test sessions and captured events.

    Returns:
    {
        "status": "cleaned",
        "deleted_count": 5
    }
    """
    count = len(_test_sessions)
    _test_sessions.clear()

    return {
        "status": "cleaned",
        "deleted_count": count,
    }
