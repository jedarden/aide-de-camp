"""
Escalate handler - handles task-profile intents requiring bead escalation.

For intents that need durable async handling:
1. Formulate bead body via LLM (sonnet-class via ZAI proxy)
2. Create bead using br CLI
3. Return pending-card spec with bead reference

The bead watcher bridges bead closure to result delivery.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from logging import getLogger
from pathlib import Path
from typing import Any, Optional

import httpx

from ..session.store import get_store
from .llm import get_zai_client, LLMRequest, ModelClass


logger = getLogger(__name__)

# Project workspace for beads (where br CLI operates)
BEADS_WORKSPACE = Path.home() / ".beads"

# Escalate prompt path
ESCALATE_PROMPT_PATH = Path("/home/coding/aide-de-camp/prompts/escalate/task-profile.md")

# Default escalate system prompt (fallback if prompt file not found)
ESCALATE_SYSTEM_PROMPT = """You are ADC's escalate handler. Your job is to formulate a clear, actionable NEEDLE bead body from a user's intent.

A NEEDLE bead is a task work item with:
- A clear title describing what needs to be done
- A detailed body with context, requirements, and success criteria
- Proper structure for Claude Code to execute

Given the user's intent and any available context, produce a bead body that:
1. Captures the full scope of the request
2. Includes relevant context (project, cluster, specific resources)
3. Defines clear success criteria
4. Structures the work for Claude Code execution

Output ONLY the bead body as markdown. Do not include explanations or meta-commentary."""


def load_escalate_prompt() -> str:
    """Load the escalate prompt from the prompts directory."""
    try:
        with open(ESCALATE_PROMPT_PATH, "r") as f:
            content = f.read()
            if content.strip():
                return content
            else:
                logger.warning(f"Escalate prompt file is empty: {ESCALATE_PROMPT_PATH}, using default")
                return ESCALATE_SYSTEM_PROMPT
    except FileNotFoundError:
        logger.warning(f"Escalate prompt not found at {ESCALATE_PROMPT_PATH}, using default")
        return ESCALATE_SYSTEM_PROMPT


@dataclass
class EscalateRequest:
    """Request to escalate an intent to a bead."""
    intent_id: str
    session_id: str
    utterance: str
    intent_type: str
    project_slug: str | None = None
    topic_id: str | None = None
    context: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "intent_id": self.intent_id,
            "session_id": self.session_id,
            "utterance": self.utterance,
            "intent_type": self.intent_type,
            "project_slug": self.project_slug,
            "topic_id": self.topic_id,
            "context": self.context,
            "metadata": self.metadata,
        }


@dataclass
class EscalateResult:
    """Result of escalating an intent to a bead."""
    bead_id: str
    intent_id: str
    pending_card: dict
    status: str = "pending"  # pending, created, failed

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "bead_id": self.bead_id,
            "intent_id": self.intent_id,
            "pending_card": self.pending_card,
            "status": self.status,
        }


class EscalateError(Exception):
    """Base exception for escalate errors."""
    pass


class BeadCreationError(EscalateError):
    """Bead creation failed."""
    pass


class EscalateHandler:
    """
    Escalate handler for task-profile intents.

    Handles the full escalate flow:
    1. Formulate bead body via LLM
    2. Create bead via br CLI
    3. Return pending-card spec
    """

    def __init__(self, store=None):
        self.store = store
        self._zai_client = None

    async def _get_zai_client(self):
        """Get or create ZAI client."""
        if self._zai_client is None:
            self._zai_client = get_zai_client()
        return self._zai_client

    async def _get_store(self):
        """Get or create session store."""
        if self.store is None:
            self.store = get_store()
        return self.store

    async def formulate_bead_body(
        self,
        request: EscalateRequest,
    ) -> str:
        """
        Formulate a bead body using the LLM.

        Takes the intent and context, produces a well-structured bead body.
        """
        client = await self._get_zai_client()
        system_prompt = load_escalate_prompt()

        # Build context for the LLM
        context_parts = [
            f"User utterance: {request.utterance}",
            f"Intent type: {request.intent_type}",
        ]

        if request.project_slug:
            context_parts.append(f"Project: {request.project_slug}")

        if request.topic_id:
            context_parts.append(f"Topic ID: {request.topic_id}")

        # Add any additional context
        if request.context:
            context_parts.append(f"\nAdditional context:")
            for key, value in request.context.items():
                context_parts.append(f"  {key}: {value}")

        # Build the user message
        user_message = "\n".join([
            "Formulate a NEEDLE bead body for this intent:",
            "",
            *context_parts,
            "",
            "The bead body should be clear, actionable, and structured for Claude Code execution.",
        ])

        logger.info(f"Formulating bead body for intent {request.intent_id}")

        # Make LLM call
        try:
            bead_body = await client.call_simple(
                system_prompt=system_prompt,
                user_message=user_message,
                model=ModelClass.SONNET.value,
                max_tokens=4096,
                temperature=0.7,
            )

            logger.info(f"Formulated bead body for intent {request.intent_id}: {len(bead_body)} chars")
            return bead_body

        except Exception as e:
            logger.error(f"Failed to formulate bead body: {e}")
            raise EscalateError(f"Failed to formulate bead body: {e}") from e

    async def create_bead(
        self,
        request: EscalateRequest,
        bead_body: str,
    ) -> str:
        """
        Create a bead using the br CLI.

        Returns the bead ID.
        """
        # Generate bead title from intent
        title = self._generate_bead_title(request)

        # Prepare metadata (includes session_id for bead watcher routing)
        metadata = {
            "session_id": request.session_id,
            "intent_id": request.intent_id,
            "intent_type": request.intent_type,
            "origin_surface_id": request.metadata.get("surface_id"),
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }

        if request.project_slug:
            metadata["project_slug"] = request.project_slug

        if request.topic_id:
            metadata["topic_id"] = request.topic_id

        # Build br create command
        # Using br CLI to create the bead
        # Note: br uses --description for the main body content
        try:
            # Build command with description (escape bead body for shell)
            cmd = [
                "br",
                "create",
                "--title", title,
                "--type", "task",  # task-profile intents create task beads
                "--description", bead_body,
            ]

            # Add labels for metadata tracking
            # Labels are simple strings, we'll encode key=value for structured data
            for key, value in metadata.items():
                if value is not None:
                    cmd.extend(["--label", f"{key}={value}"])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.error(f"br create failed: {error_msg}")
                raise BeadCreationError(f"br create failed: {error_msg}")

            # Parse bead ID from output
            output = stdout.decode("utf-8", errors="replace")
            bead_id = self._extract_bead_id(output)

            logger.info(f"Created bead {bead_id} for intent {request.intent_id}")
            return bead_id

        except FileNotFoundError:
            logger.error("br CLI not found")
            raise BeadCreationError("br CLI not found")
        except Exception as e:
            logger.error(f"Failed to create bead: {e}")
            raise BeadCreationError(f"Failed to create bead: {e}") from e

    def _generate_bead_title(self, request: EscalateRequest) -> str:
        """Generate a bead title from the request."""
        # Use utterance prefix as title
        utterance = request.utterance.strip()
        if len(utterance) > 60:
            title = utterance[:57] + "..."
        else:
            title = utterance

        # Add project prefix if available
        if request.project_slug:
            title = f"[{request.project_slug}] {title}"

        return title

    def _extract_bead_id(self, output: str) -> str:
        """Extract bead ID from br create output.

        br create outputs just the bead ID (e.g., "abc-123").
        """
        # br output format: just the bead ID (e.g., "adc-2fs")
        bead_id = output.strip()

        if not bead_id:
            logger.warning(f"Empty br create output")
            return str(uuid.uuid4())

        # Basic validation: should contain a dash and be reasonable length
        if "-" not in bead_id or len(bead_id) < 3:
            logger.warning(f"Unexpected br create output format: {output}")
            # Still return it - br might have changed format

        return bead_id

    def build_pending_card(
        self,
        request: EscalateRequest,
        bead_id: str,
    ) -> dict:
        """
        Build a pending-card spec for the surface.

        The pending card shows the user that work is in progress
        and will be delivered when the bead closes.
        """
        return {
            "type": "pending",
            "id": f"pending-{bead_id}",
            "intent_id": request.intent_id,
            "bead_id": bead_id,
            "title": self._generate_bead_title(request),
            "summary": f"Working on: {request.utterance[:100]}",
            "status": "pending",
            "urgency": request.metadata.get("urgency", "normal"),
            "created_at": int(datetime.now(timezone.utc).timestamp()),
            "metadata": {
                "project_slug": request.project_slug,
                "topic_id": request.topic_id,
                "bead_type": "task",
            },
        }

    async def escalate_intent(self, request: EscalateRequest) -> EscalateResult:
        """
        Escalate an intent to a bead.

        Full flow:
        1. Formulate bead body via LLM
        2. Create bead via br CLI
        3. Return pending-card spec

        Args:
            request: The escalate request

        Returns:
            EscalateResult with bead ID and pending card
        """
        logger.info(f"Escalating intent {request.intent_id} to bead")

        try:
            # Step 1: Formulate bead body
            bead_body = await self.formulate_bead_body(request)

            # Step 2: Create bead
            bead_id = await self.create_bead(request, bead_body)

            # Step 3: Build pending card
            pending_card = self.build_pending_card(request, bead_id)

            # Update intent in store with bead reference
            store = await self._get_store()
            await store.update_intent_status(
                intent_id=request.intent_id,
                status="dispatched",
            )

            # Also update the bead_ref field
            # (This would require a schema update, for now we track via metadata)

            logger.info(f"Escalated intent {request.intent_id} to bead {bead_id}")

            return EscalateResult(
                bead_id=bead_id,
                intent_id=request.intent_id,
                pending_card=pending_card,
                status="created",
            )

        except EscalateError:
            raise
        except Exception as e:
            logger.error(f"Escalate failed for intent {request.intent_id}: {e}")
            raise EscalateError(f"Escalate failed: {e}") from e


# Global escalate handler instance
_handler: Optional[EscalateHandler] = None


def get_escalate_handler(store=None) -> EscalateHandler:
    """Get or create the global escalate handler instance."""
    global _handler
    if _handler is None:
        _handler = EscalateHandler(store=store)
    return _handler


async def escalate_intent(request: EscalateRequest) -> EscalateResult:
    """
    Convenience function to escalate an intent.

    Args:
        request: The escalate request

    Returns:
        EscalateResult with bead ID and pending card
    """
    handler = get_escalate_handler()
    return await handler.escalate_intent(request)
