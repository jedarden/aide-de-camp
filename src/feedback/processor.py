"""
Feedback Processor for aide-de-camp.

Handles explicit user feedback and processes it through the self-modification pipeline.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from ..agents.self_modification import (
    SelfModificationAgent,
    ArtifactDiff,
    get_self_modification_agent,
    ArtifactType
)
from ..agents.ui_regen import UIRegenAgent, get_ui_regen_agent
from ..components.hot_reload import get_reload_manager
from ..components.library import get_library
from ..sse.broadcaster import get_broadcaster, SSEEvent, EventType

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    """Types of feedback."""
    SELF_MODIFICATION = "self_modification"
    COMPONENT_ITERATION = "component_iteration"
    ROUTING_CORRECTION = "routing_correction"
    BEHAVIOR_ADJUSTMENT = "behavior_adjustment"


@dataclass
class FeedbackRequest:
    """A user feedback request."""
    feedback: str
    feedback_type: FeedbackType
    context: Optional[Dict[str, Any]]
    session_id: Optional[str]
    require_approval: bool = True


@dataclass
class FeedbackResponse:
    """Response to a feedback request."""
    status: str  # "proposed", "applied", "rejected"
    diff: Optional[ArtifactDiff]
    message: str
    confidence: float
    artifact_name: Optional[str]
    artifact_type: Optional[ArtifactType]


class FeedbackProcessor:
    """
    Processes explicit user feedback through the self-modification pipeline.

    End-to-end flow:
    1. User provides feedback instruction
    2. Identify target artifact
    3. Generate diff
    4. Surface to user for approval
    5. On approval: apply change
    6. Broadcast update via SSE
    7. Hot-reload takes effect
    """

    def __init__(self):
        self.self_mod_agent = get_self_modification_agent()
        self.ui_regen_agent = get_ui_regen_agent()
        self.reload_mgr = get_reload_manager()
        self.library = get_library()
        self.broadcaster = get_broadcaster()
        self._pending_approvals: Dict[str, ArtifactDiff] = {}

    async def process_feedback(self, request: FeedbackRequest) -> FeedbackResponse:
        """
        Process a feedback request.

        Args:
            request: The feedback request

        Returns:
            Response with proposed diff or confirmation of application
        """
        logger.info(f"Processing feedback: {request.feedback_type.value} - {request.feedback[:100]}")

        # Generate the diff
        if request.feedback_type == FeedbackType.COMPONENT_ITERATION:
            return await self._process_component_feedback(request)
        else:
            return await self._process_self_modification_feedback(request)

    async def _process_component_feedback(self, request: FeedbackRequest) -> FeedbackResponse:
        """Process feedback related to component iteration."""
        # Identify component from context
        component_id = request.context.get("component_id") if request.context else None
        result_data = request.context.get("result_data") if request.context else None

        if not component_id:
            return FeedbackResponse(
                status="rejected",
                diff=None,
                message="Component ID required for iteration. Please specify which component to update.",
                confidence=0.0,
                artifact_name=None,
                artifact_type=None
            )

        # Iterate component
        updated_component = self.ui_regen_agent.iterate_component(
            component_id,
            request.feedback,
            result_data
        )

        if not updated_component:
            return FeedbackResponse(
                status="rejected",
                diff=None,
                message=f"Component {component_id} not found.",
                confidence=0.0,
                artifact_name=component_id,
                artifact_type=ArtifactType.COMPONENT
            )

        # Broadcast component update via SSE
        # Note: Component updates are handled by the library, no additional broadcast needed

        return FeedbackResponse(
            status="applied",
            diff=None,
            message=f"Component '{updated_component.name}' updated to version {updated_component.version}. Canvas will re-render affected cards.",
            confidence=0.9,
            artifact_name=updated_component.name,
            artifact_type=ArtifactType.COMPONENT
        )

    async def _process_self_modification_feedback(
        self,
        request: FeedbackRequest
    ) -> FeedbackResponse:
        """Process feedback for artifact modification."""
        # Generate diff
        diff = self.self_mod_agent.process_instruction(request.feedback)

        # If confidence is high and auto-approve is allowed, apply immediately
        if not request.require_approval and diff.confidence >= 0.9:
            success = self.self_mod_agent.apply_diff(diff)
            if success:
                await self._broadcast_artifact_update(diff)
                return FeedbackResponse(
                    status="applied",
                    diff=diff,
                    message=f"Applied change to {diff.artifact_name}: {diff.change_summary}",
                    confidence=diff.confidence,
                    artifact_name=diff.artifact_name,
                    artifact_type=diff.artifact_type
                )

        # Otherwise, propose for approval
        approval_id = self._generate_approval_id()
        self._pending_approvals[approval_id] = diff

        return FeedbackResponse(
            status="proposed",
            diff=diff,
            message=self._format_diff_message(diff, approval_id),
            confidence=diff.confidence,
            artifact_name=diff.artifact_name,
            artifact_type=diff.artifact_type
        )

    async def approve_change(self, approval_id: str) -> FeedbackResponse:
        """
        Approve and apply a pending change.

        Args:
            approval_id: The approval ID from the proposed change

        Returns:
            Response confirming application
        """
        diff = self._pending_approvals.get(approval_id)
        if not diff:
            return FeedbackResponse(
                status="rejected",
                diff=None,
                message="Approval ID not found or already processed.",
                confidence=0.0,
                artifact_name=None,
                artifact_type=None
            )

        # Apply the diff
        success = self.self_mod_agent.apply_diff(diff)

        if success:
            del self._pending_approvals[approval_id]
            await self._broadcast_artifact_update(diff)

            return FeedbackResponse(
                status="applied",
                diff=diff,
                message=f"Change applied to {diff.artifact_name}: {diff.change_summary}",
                confidence=diff.confidence,
                artifact_name=diff.artifact_name,
                artifact_type=diff.artifact_type
            )
        else:
            return FeedbackResponse(
                status="rejected",
                diff=diff,
                message=f"Failed to apply change to {diff.artifact_name}",
                confidence=diff.confidence,
                artifact_name=diff.artifact_name,
                artifact_type=diff.artifact_type
            )

    async def reject_change(self, approval_id: str, reason: Optional[str] = None) -> FeedbackResponse:
        """
        Reject a pending change.

        Args:
            approval_id: The approval ID to reject
            reason: Optional reason for rejection

        Returns:
            Response confirming rejection
        """
        diff = self._pending_approvals.get(approval_id)
        if not diff:
            return FeedbackResponse(
                status="rejected",
                diff=None,
                message="Approval ID not found.",
                confidence=0.0,
                artifact_name=None,
                artifact_type=None
            )

        self.self_mod_agent.reject_diff(diff)
        del self._pending_approvals[approval_id]

        return FeedbackResponse(
            status="rejected",
            diff=diff,
            message=f"Change rejected: {reason or 'No reason provided'}",
            confidence=diff.confidence,
            artifact_name=diff.artifact_name,
            artifact_type=diff.artifact_type
        )

    async def _broadcast_artifact_update(self, diff: ArtifactDiff):
        """Broadcast that an artifact was updated."""
        if diff.artifact_type == ArtifactType.COMPONENT:
            # Component updates are broadcast by the library
            pass
        else:
            # For prompts/configs, broadcast a generic update event
            event = SSEEvent(
                type=EventType.COMPONENT_UPDATED,  # Reuse event type
                data={
                    "artifact_type": diff.artifact_type.value,
                    "artifact_name": diff.artifact_name,
                    "change_summary": diff.change_summary,
                    "timestamp": int(asyncio.get_event_loop().time())
                }
            )
            await self.sse_manager.broadcast_to_all(event)

    def _generate_approval_id(self) -> str:
        """Generate a unique approval ID."""
        import uuid
        return f"apr-{uuid.uuid4().hex[:12]}"

    def _format_diff_message(self, diff: ArtifactDiff, approval_id: str) -> str:
        """Format a user-friendly diff message."""
        lines = [
            f"Proposed change to {diff.artifact_type.value} '{diff.artifact_name}':",
            "",
            diff.change_summary,
            "",
            "---",
            "",
            "To approve this change, respond with:",
            f"  approve {approval_id}",
            "",
            "To reject this change, respond with:",
            f"  reject {approval_id} [optional reason]",
            "",
            f"Confidence: {diff.confidence:.0%}"
        ]
        return "\n".join(lines)

    def list_pending_approvals(self) -> List[Dict[str, Any]]:
        """List all pending approvals."""
        return [
            {
                "approval_id": apr_id,
                "artifact_name": diff.artifact_name,
                "artifact_type": diff.artifact_type.value,
                "change_summary": diff.change_summary,
                "confidence": diff.confidence
            }
            for apr_id, diff in self._pending_approvals.items()
        ]

    async def rollback(self, artifact_name: str, artifact_type: ArtifactType) -> FeedbackResponse:
        """
        Rollback an artifact to its previous version.

        Args:
            artifact_name: The artifact to rollback
            artifact_type: The type of artifact

        Returns:
            Response confirming rollback
        """
        success = self.self_mod_agent.rollback(artifact_name, artifact_type)

        if success:
            return FeedbackResponse(
                status="applied",
                diff=None,
                message=f"Rolled back {artifact_type.value} '{artifact_name}' to previous version.",
                confidence=1.0,
                artifact_name=artifact_name,
                artifact_type=artifact_type
            )
        else:
            return FeedbackResponse(
                status="rejected",
                diff=None,
                message=f"Rollback failed for {artifact_type.value} '{artifact_name}'.",
                confidence=0.0,
                artifact_name=artifact_name,
                artifact_type=artifact_type
            )


# Singleton instance
_processor: Optional[FeedbackProcessor] = None


def get_feedback_processor() -> FeedbackProcessor:
    """Get or create the feedback processor singleton."""
    global _processor
    if _processor is None:
        _processor = FeedbackProcessor()
    return _processor
