"""
Background analysis processor for implicit feedback signals.

Reads feedback signals from the session store and proposes artifact updates
as canvas cards for the self-modification agent to process.
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
from ..agents.self_modification import SelfModificationAgent, get_self_modification_agent
from ..sse.broadcaster import get_broadcaster, SSEEvent


logger = getLogger(__name__)


class AnalysisTrigger(Enum):
    """Triggers for background analysis."""
    SIGNAL_COUNT_THRESHOLD = "signal_count_threshold"  # Process after N signals
    TIME_INTERVAL = "time_interval"  # Process every N seconds
    HIGH_URGENCY_SIGNAL = "high_urgency_signal"  # Process immediately for critical signals
    MANUAL = "manual"  # Triggered by user command


@dataclass
class AnalysisProposal:
    """A proposal for artifact update based on signal analysis."""
    proposal_id: str
    signal_type: str
    artifact_type: str  # 'prompt', 'config', 'component'
    artifact_name: str
    change_summary: str
    confidence: float
    signals_consulted: int
    generated_at: int
    session_ids: set[str] = field(default_factory=set)
    data: dict = field(default_factory=dict)

    def to_canvas_card(self) -> dict:
        """Convert to canvas card format for surfacing to user."""
        return {
            "id": self.proposal_id,
            "type": "artifact_update_proposal",
            "title": f"Update {self.artifact_type}: {self.artifact_name}",
            "summary": self.change_summary,
            "urgency": "normal" if self.confidence < 0.8 else "high",
            "data": {
                "artifact_type": self.artifact_type,
                "artifact_name": self.artifact_name,
                "change_summary": self.change_summary,
                "confidence": self.confidence,
                "signals_consulted": self.signals_consulted,
            },
            "actions": [
                {"id": "approve", "label": "Approve", "type": "primary"},
                {"id": "reject", "label": "Reject", "type": "secondary"},
                {"id": "defer", "label": "Defer", "type": "tertiary"},
            ],
            "created_at": self.generated_at,
        }


class BackgroundAnalysisProcessor:
    """
    Processes implicit feedback signals and proposes artifact updates.

    Runs as a background task that:
    1. Reads unprocessed feedback signals from the session store
    2. Analyzes patterns in the signals
    3. Proposes artifact updates via self-modification agent
    4. Surfaces proposals as canvas cards
    """

    def __init__(
        self,
        signal_threshold: int = 10,
        check_interval: int = 60,
    ):
        self.signal_threshold = signal_threshold
        self.check_interval = check_interval
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.store = get_store()
        self.self_mod_agent = get_self_modification_agent()

    async def analyze_signals(self, limit: int = 100) -> list[AnalysisProposal]:
        """
        Analyze unprocessed feedback signals and generate proposals.

        Args:
            limit: Maximum number of signals to process in one batch

        Returns:
            List of proposals for artifact updates
        """
        # Get unprocessed signals
        signals = await self.store.get_unprocessed_signals(limit=limit)

        if not signals:
            logger.debug("No unprocessed signals to analyze")
            return []

        logger.info(f"Analyzing {len(signals)} feedback signals")

        # Group signals by type
        signals_by_type = self._group_by_type(signals)

        # Generate proposals for each signal type
        proposals = []

        for signal_type, type_signals in signals_by_type.items():
            type_proposals = await self._analyze_signal_type(signal_type, type_signals)
            proposals.extend(type_proposals)

        # Mark processed signals
        signal_ids = [s["id"] for s in signals]
        await self.store.mark_signals_processed(signal_ids)

        logger.info(f"Generated {len(proposals)} proposals from {len(signals)} signals")

        return proposals

    def _group_by_type(self, signals: list[dict]) -> dict[str, list[dict]]:
        """Group signals by type."""
        grouped = {}
        for signal in signals:
            signal_type = signal["signal_type"]
            if signal_type not in grouped:
                grouped[signal_type] = []
            grouped[signal_type].append(signal)
        return grouped

    async def _analyze_signal_type(
        self,
        signal_type: str,
        signals: list[dict],
    ) -> list[AnalysisProposal]:
        """Analyze signals of a specific type and generate proposals."""
        proposals = []

        # Extract unique session_ids from these signals
        session_ids = set(s.get("session_id") for s in signals if s.get("session_id"))

        if signal_type == "ack_speed":
            proposals.extend(await self._analyze_ack_speed(signals, session_ids))
        elif signal_type == "follow_up_pattern":
            proposals.extend(await self._analyze_follow_up_patterns(signals, session_ids))
        elif signal_type == "surface_switch":
            proposals.extend(await self._analyze_surface_switches(signals, session_ids))
        elif signal_type == "result_requery":
            proposals.extend(await self._analyze_requeries(signals, session_ids))
        elif signal_type == "result_skipped":
            proposals.extend(await self._analyze_skipped_results(signals, session_ids))
        elif signal_type == "topic_continuation":
            # Topic continuation signals are informational, don't generate proposals
            pass
        elif signal_type == "topic_switch":
            # Topic switches are informational, don't generate proposals
            pass

        return proposals

    async def _analyze_ack_speed(self, signals: list[dict], session_ids: set[str]) -> list[AnalysisProposal]:
        """
        Analyze acknowledgment speed signals.

        Slow acks may indicate:
        - Poor narration quality (for audio)
        - Unclear result formatting
        - Wrong delivery surface
        """
        proposals = []

        # Calculate average ack delay
        delays = []
        for signal in signals:
            data = json.loads(signal.get("data", "{}"))
            delay = data.get("ack_delay_seconds", 0)
            delays.append(delay)

        if not delays:
            return proposals

        avg_delay = sum(delays) / len(delays)

        # If average ack delay is high, propose improvements
        if avg_delay > 60:  # More than 1 minute average
            # Check which surface type has the slowest acks
            surface_delays = {}
            for signal in signals:
                data = json.loads(signal.get("data", "{}"))
                surface = data.get("surface_type", "unknown")
                delay = data.get("ack_delay_seconds", 0)
                if surface not in surface_delays:
                    surface_delays[surface] = []
                surface_delays[surface].append(delay)

            # Find worst surface
            worst_surface = None
            worst_avg = 0
            for surface, s_delays in surface_delays.items():
                s_avg = sum(s_delays) / len(s_delays)
                if s_avg > worst_avg:
                    worst_avg = s_avg
                    worst_surface = surface

            if worst_surface == "audio":
                # Propose improving narration prompts
                proposals.append(AnalysisProposal(
                    proposal_id=str(uuid4()),
                    signal_type="ack_speed",
                    artifact_type="prompt",
                    artifact_name="audio_narration",
                    change_summary=f"Improve audio narration: average ack delay is {avg_delay:.0f}s (target: <30s). Consider shorter, more concise summaries.",
                    confidence=0.7,
                    signals_consulted=len(signals),
                    generated_at=int(datetime.now(timezone.utc).timestamp()),
                    session_ids=session_ids,
                    data={"avg_delay_seconds": avg_delay, "worst_surface": worst_surface},
                ))
            elif worst_surface == "canvas":
                # Propose improving result formatting
                proposals.append(AnalysisProposal(
                    proposal_id=str(uuid4()),
                    signal_type="ack_speed",
                    artifact_type="component",
                    artifact_name="result_card",
                    change_summary=f"Improve result card formatting: average ack delay is {avg_delay:.0f}s. Consider more prominent summaries and clearer action buttons.",
                    confidence=0.65,
                    signals_consulted=len(signals),
                    generated_at=int(datetime.now(timezone.utc).timestamp()),
                    session_ids=session_ids,
                    data={"avg_delay_seconds": avg_delay, "worst_surface": worst_surface},
                ))

        return proposals

    async def _analyze_follow_up_patterns(self, signals: list[dict], session_ids: set[str]) -> list[AnalysisProposal]:
        """
        Analyze follow-up pattern signals.

        Follow-up patterns indicate what was missing from previous results.
        """
        proposals = []

        # Count follow-up types
        follow_up_types = {}
        for signal in signals:
            data = json.loads(signal.get("data", "{}"))
            f_type = data.get("follow_up_type", "unknown")
            if f_type not in follow_up_types:
                follow_up_types[f_type] = 0
            follow_up_types[f_type] += 1

        # Generate proposals for common follow-up types
        for f_type, count in follow_up_types.items():
            if count >= 3:  # Need at least 3 similar follow-ups to propose change
                if f_type == "why_question":
                    proposals.append(AnalysisProposal(
                        proposal_id=str(uuid4()),
                        signal_type="follow_up_pattern",
                        artifact_type="prompt",
                        artifact_name="synthesize_explainatory",
                        change_summary=f"Add more 'why' explanations to results. {count} users asked 'why' follow-up questions recently.",
                        confidence=0.8,
                        signals_consulted=len(signals),
                        generated_at=int(datetime.now(timezone.utc).timestamp()),
                        session_ids=session_ids,
                        data={"follow_up_type": f_type, "count": count},
                    ))
                elif f_type == "temporal_question":
                    proposals.append(AnalysisProposal(
                        proposal_id=str(uuid4()),
                        signal_type="follow_up_pattern",
                        artifact_type="prompt",
                        artifact_name="synthesize_timing",
                        change_summary=f"Add timing information to results. {count} users asked 'how long/when' follow-up questions recently.",
                        confidence=0.75,
                        signals_consulted=len(signals),
                        generated_at=int(datetime.now(timezone.utc).timestamp()),
                        session_ids=session_ids,
                        data={"follow_up_type": f_type, "count": count},
                    ))
                elif f_type == "more_detail":
                    proposals.append(AnalysisProposal(
                        proposal_id=str(uuid4()),
                        signal_type="follow_up_pattern",
                        artifact_type="prompt",
                        artifact_name="synthesize_verbose",
                        change_summary=f"Provide more detailed results by default. {count} users asked for more detail recently.",
                        confidence=0.7,
                        signals_consulted=len(signals),
                        generated_at=int(datetime.now(timezone.utc).timestamp()),
                        session_ids=session_ids,
                        data={"follow_up_type": f_type, "count": count},
                    ))

        return proposals

    async def _analyze_surface_switches(self, signals: list[dict], session_ids: set[str]) -> list[AnalysisProposal]:
        """
        Analyze surface switch signals.

        Audio-to-canvas switches with pending results indicate poor narration.
        """
        proposals = []

        # Count audio-to-canvas switches with pending results
        audio_to_canvas_count = 0
        for signal in signals:
            data = json.loads(signal.get("data", "{}"))
            if data.get("reason") == "audio_to_canvas_with_pending":
                audio_to_canvas_count += 1

        if audio_to_canvas_count >= 5:
            proposals.append(AnalysisProposal(
                proposal_id=str(uuid4()),
                signal_type="surface_switch",
                artifact_type="prompt",
                artifact_name="audio_narration",
                change_summary=f"Improve audio narration quality. {audio_to_canvas_count} users switched to canvas with pending results, indicating narration was insufficient.",
                confidence=0.85,
                signals_consulted=len(signals),
                generated_at=int(datetime.now(timezone.utc).timestamp()),
                session_ids=session_ids,
                data={"audio_to_canvas_count": audio_to_canvas_count},
            ))

        return proposals

    async def _analyze_requeries(self, signals: list[dict], session_ids: set[str]) -> list[AnalysisProposal]:
        """
        Analyze re-query signals.

        Re-queries indicate inadequate results.
        """
        proposals = []

        # Group by utterance to find frequently re-queried items
        requeries = {}
        for signal in signals:
            data = json.loads(signal.get("data", "{}"))
            utterance = data.get("utterance", "")
            attempt_count = data.get("attempt_count", 0)
            if utterance and attempt_count > 1:
                if utterance not in requeries:
                    requeries[utterance] = 0
                requeries[utterance] = max(requeries[utterance], attempt_count)

        # Find queries with 3+ attempts
        for utterance, max_attempts in requeries.items():
            if max_attempts >= 3:
                proposals.append(AnalysisProposal(
                    proposal_id=str(uuid4()),
                    signal_type="result_requery",
                    artifact_type="prompt",
                    artifact_name="synthesize_completeness",
                    change_summary=f"Improve result completeness for query type: '{utterance[:50]}...'. Users re-queried {max_attempts} times.",
                    confidence=0.75,
                    signals_consulted=len(signals),
                    generated_at=int(datetime.now(timezone.utc).timestamp()),
                    session_ids=session_ids,
                    data={"utterance": utterance, "max_attempts": max_attempts},
                ))

        return proposals

    async def _analyze_skipped_results(self, signals: list[dict], session_ids: set[str]) -> list[AnalysisProposal]:
        """
        Analyze skipped result signals.

        Skipped results indicate low interest or poor delivery.
        """
        proposals = []

        # Count skipped results
        skipped_count = len(signals)

        if skipped_count >= 10:
            proposals.append(AnalysisProposal(
                proposal_id=str(uuid4()),
                signal_type="result_skipped",
                artifact_type="config",
                artifact_name="monitoring",
                change_summary=f"Reduce monitoring verbosity. {skipped_count} results were skipped (not acknowledged) before surface disconnect.",
                confidence=0.6,
                signals_consulted=len(signals),
                generated_at=int(datetime.now(timezone.utc).timestamp()),
                session_ids=session_ids,
                data={"skipped_count": skipped_count},
            ))

        return proposals

    async def run(self) -> None:
        """Main loop: periodically analyze signals and generate proposals."""
        logger.info(f"Starting background analysis processor (interval: {self.check_interval}s)")

        while self.running:
            try:
                # Analyze signals
                proposals = await self.analyze_signals()

                if proposals:
                    # Surface proposals as canvas cards via SSE
                    broadcaster = get_broadcaster()
                    for proposal in proposals:
                        card = proposal.to_canvas_card()

                        # Broadcast to each relevant session
                        for session_id in proposal.session_ids:
                            event = SSEEvent(
                                event_type="artifact_proposal",
                                data=card,
                                target_session_id=session_id,
                            )
                            sent_count = await broadcaster.broadcast(event)
                            logger.info(
                                f"Broadcast proposal {proposal.proposal_id} to session {session_id}: "
                                f"{proposal.change_summary} (sent to {sent_count} connections)"
                            )

                # Wait for next cycle
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background analysis loop: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)

        logger.info("Background analysis processor stopped")

    async def start(self) -> None:
        """Start the background analysis processor."""
        if self.task is not None and not self.task.done():
            logger.warning("Background analysis processor already running")
            return

        self.running = True
        self.task = asyncio.create_task(self.run())
        logger.info("Background analysis processor started")

    async def stop(self) -> None:
        """Stop the background analysis processor."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Background analysis processor stopped")


# Global background analysis processor instance
_background_processor: Optional[BackgroundAnalysisProcessor] = None


def get_background_processor(
    signal_threshold: int = 10,
    check_interval: int = 60,
) -> BackgroundAnalysisProcessor:
    """Get or create the global background analysis processor instance."""
    global _background_processor
    if _background_processor is None:
        _background_processor = BackgroundAnalysisProcessor(
            signal_threshold=signal_threshold,
            check_interval=check_interval,
        )
    return _background_processor
