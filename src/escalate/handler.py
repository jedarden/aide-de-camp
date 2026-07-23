"""
Escalate handler - handles task-profile intents requiring bead escalation.

For intents that need durable async handling:
1. Formulate bead body via LLM (sonnet-class via ZAI proxy)
2. Create bead using bf CLI
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

import aiosqlite
import httpx

from ..components.hot_reload import get_reload_manager
from ..render.hot_path import derive_result_type
from ..session.store import get_store
from .llm import get_zai_client, LLMRequest, ModelClass
from .commands import get_kubectl_executor, CommandExecutionError


logger = getLogger(__name__)

# Project workspace for beads (where bf CLI operates)
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
    1. Check auto-approve rules from exceptions.yaml
    2. Either execute directly (auto-approved) OR create bead (manual approval)
    3. Return pending-card spec (if bead created) or execution result
    """

    def __init__(self, store=None):
        self.store = store
        self._zai_client = None
        self._reload_manager = None

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

    def _get_reload_manager(self):
        """Get or create hot-reload manager."""
        if self._reload_manager is None:
            self._reload_manager = get_reload_manager()
        return self._reload_manager

    def _evaluate_auto_approve(self, request: EscalateRequest, exceptions_config: dict) -> tuple[bool, str | None]:
        """
        Evaluate if an intent should be auto-approved based on exceptions.yaml.

        Args:
            request: The escalate request
            exceptions_config: The loaded exceptions.yaml config

        Returns:
            (auto_approve: bool, reason: str | None)
        """
        auto_approve_rules = exceptions_config.get("auto_approve", {})

        # Extract context for rule evaluation
        context = {
            "environment": request.metadata.get("environment"),
            "project_slug": request.project_slug,
            "branch": request.metadata.get("branch"),
            "action": request.metadata.get("action"),
            "risk_level": request.metadata.get("risk_level", "normal"),
        }

        # Check read-only operations (always auto-approved)
        read_only_actions = auto_approve_rules.get("read_only", [])
        action = context.get("action")
        if action in read_only_actions:
            return True, f"Read-only operation: {action}"

        # Check safe mutations with conditions
        safe_mutations = auto_approve_rules.get("safe_mutations", [])
        for rule in safe_mutations:
            condition = rule.get("condition", "")
            actions = rule.get("actions", [])

            # Simple condition evaluation (supports basic comparisons)
            if self._evaluate_condition(condition, context) and action in actions:
                return True, f"Safe mutation in {condition}: {action}"

        # Check manual approval rules (never auto-approve)
        manual_rules = exceptions_config.get("manual_approval", [])
        for rule in manual_rules:
            condition = rule.get("condition", "")
            actions = rule.get("actions", [])

            # Check if the action is in this rule's actions
            if action not in actions:
                continue

            # Evaluate the condition
            if self._evaluate_condition(condition, context):
                if rule.get("always_approve") is False:
                    return False, f"Manual approval required: {condition}"

        # Check approval workflow rules
        approval_config = exceptions_config.get("approval", {})
        never_auto_approve = approval_config.get("never_auto_approve", [])
        for condition_str in never_auto_approve:
            if self._evaluate_condition(condition_str, context):
                return False, f"Never auto-approve: {condition_str}"

        # Default: require manual approval for unknown actions
        return False, "Unknown action - requires manual approval"

    def _evaluate_condition(self, condition: str, context: dict) -> bool:
        """
        Evaluate a condition string against context.

        Supports simple conditions like:
        - "environment == 'staging'"
        - "branch == 'main' || branch == 'master'"  (using || for OR)
        - "action == 'kubectl_delete_namespace'"
        - "environment == 'staging' && action == 'restart'"  (using && for AND)

        Note: Supports both shell-style operators (||, &&) and Python-style (or, and).

        Args:
            condition: The condition string
            context: Dict of available variables

        Returns:
            True if condition evaluates to True, False otherwise
        """
        try:
            # Translate shell-style operators to Python syntax
            # (People are more familiar with || and && from bash/js)
            python_condition = condition.replace(" || ", " or ").replace(" && ", " and ")

            # Create a safe evaluation environment
            safe_globals = {"__builtins__": {}}
            safe_locals = {
                "environment": context.get("environment"),
                "project_slug": context.get("project_slug"),
                "branch": context.get("branch"),
                "action": context.get("action"),
                "risk_level": context.get("risk_level"),
            }

            # Evaluate condition
            result = eval(python_condition, safe_globals, safe_locals)
            return bool(result)
        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return False

    def _get_bead_type_from_targets(self, intent_type: str, exceptions_config: dict) -> str:
        """
        Get the bead type from escalation_targets config.

        Args:
            intent_type: The intent type from IntentRouter (e.g., 'action', 'task-profile', 'self-modification')
            exceptions_config: The loaded exceptions.yaml config

        Returns:
            The bead type to create (default: 'task')
        """
        # Map IntentRouter types to escalation_targets keys
        intent_type_mapping = {
            "action": "action",
            "task-profile": "action",  # Task-profile intents create action-type beads
            "self-modification": "self_modification",
            "monitoring-config": "monitoring_config",
        }

        # Map the intent type to escalation_targets key
        escalation_key = intent_type_mapping.get(intent_type, intent_type)

        escalation_targets = exceptions_config.get("escalation_targets", {})
        target_config = escalation_targets.get(escalation_key, {})
        return target_config.get("bead_type", "task")

    async def _execute_auto_approved(self, request: EscalateRequest) -> dict:
        """
        Execute an auto-approved action directly.

        Executes kubectl and git commands that are auto-approved based on
        exceptions.yaml rules, without creating beads.

        Args:
            request: The escalate request

        Returns:
            Execution result dict
        """
        action = request.metadata.get("action", "")
        logger.info(f"Executing auto-approved action '{action}' for intent {request.intent_id}")

        try:
            # Route to appropriate executor based on action type
            if action == "kubectl_delete_pod":
                return await self._execute_delete_pod(request)
            elif action.startswith("kubectl_"):
                return await self._execute_kubectl_command(request)
            elif action.startswith("git_"):
                return await self._execute_git_command(request)
            else:
                # Unknown action - return placeholder for now
                logger.warning(f"Unknown auto-approved action: {action}")
                return {
                    "status": "pending",
                    "summary": f"Auto-approved action '{action}' not yet implemented",
                    "data": {
                        "action": action,
                        "utterance": request.utterance,
                    },
                    "urgency": "low",
                }

        except CommandExecutionError as e:
            logger.error(f"Command execution failed for intent {request.intent_id}: {e}")
            return {
                "status": "failed",
                "summary": f"Command execution failed: {str(e)}",
                "data": {
                    "action": action,
                    "error": str(e),
                },
                "urgency": "normal",
            }
        except Exception as e:
            logger.error(f"Unexpected error executing auto-approved action: {e}")
            return {
                "status": "failed",
                "summary": f"Unexpected error: {str(e)}",
                "data": {
                    "action": action,
                    "error": str(e),
                },
                "urgency": "normal",
            }

    async def _execute_delete_pod(self, request: EscalateRequest) -> dict:
        """
        Execute kubectl delete pod command.

        Args:
            request: The escalate request

        Returns:
            Execution result dict
        """
        executor = get_kubectl_executor()

        # Parse utterance to extract pod name and namespace
        params = executor.parse_delete_pod_utterance(
            utterance=request.utterance,
            project_slug=request.project_slug,
        )

        # Execute the delete command
        result = await executor.execute_delete_pod(
            pod_name=params["pod_name"],
            namespace=params["namespace"],
            project_slug=request.project_slug,
        )

        return result

    async def _execute_kubectl_command(self, request: EscalateRequest) -> dict:
        """
        Execute other kubectl commands (placeholder for future).

        Args:
            request: The escalate request

        Returns:
            Execution result dict
        """
        # TODO: Implement other kubectl commands
        action = request.metadata.get("action", "")
        return {
            "status": "pending",
            "summary": f"Kubectl command '{action}' not yet implemented",
            "data": {
                "action": action,
                "utterance": request.utterance,
            },
            "urgency": "low",
        }

    async def _execute_git_command(self, request: EscalateRequest) -> dict:
        """
        Execute git commands (placeholder for future).

        Args:
            request: The escalate request

        Returns:
            Execution result dict
        """
        # TODO: Implement git commands
        action = request.metadata.get("action", "")
        return {
            "status": "pending",
            "summary": f"Git command '{action}' not yet implemented",
            "data": {
                "action": action,
                "utterance": request.utterance,
            },
            "urgency": "low",
        }

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
        Create a bead using the bf CLI.

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

        # Build bf create command
        # Using bf CLI to create the bead
        # Note: bf uses --description for the main body content
        try:
            # Build command with description (escape bead body for shell)
            cmd = [
                "bf",
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
                logger.error(f"bf create failed: {error_msg}")
                raise BeadCreationError(f"bf create failed: {error_msg}")

            # Parse bead ID from output
            output = stdout.decode("utf-8", errors="replace")
            bead_id = self._extract_bead_id(output)

            logger.info(f"Created bead {bead_id} for intent {request.intent_id}")
            return bead_id

        except FileNotFoundError:
            logger.error("bf CLI not found")
            raise BeadCreationError("bf CLI not found")
        except Exception as e:
            logger.error(f"Failed to create bead: {e}")
            raise BeadCreationError(f"Failed to create bead: {e}") from e

    async def _create_bead_with_type(
        self,
        request: EscalateRequest,
        bead_body: str,
        bead_type: str,
    ) -> str:
        """
        Create a bead with a specific type using the bf CLI.

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

        # Build bf create command
        try:
            cmd = [
                "bf",
                "create",
                "--title", title,
                "--type", bead_type,
                "--description", bead_body,
            ]

            # Add labels for metadata tracking
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
                logger.error(f"bf create failed: {error_msg}")
                raise BeadCreationError(f"bf create failed: {error_msg}")

            # Parse bead ID from output
            output = stdout.decode("utf-8", errors="replace")
            bead_id = self._extract_bead_id(output)

            logger.info(f"Created bead {bead_id} (type: {bead_type}) for intent {request.intent_id}")
            return bead_id

        except FileNotFoundError:
            logger.error("bf CLI not found")
            raise BeadCreationError("bf CLI not found")
        except Exception as e:
            logger.error(f"Failed to create bead: {e}")
            raise BeadCreationError(f"Failed to create bead: {e}") from e

    async def _create_bead_watch(
        self,
        bead_ref: str,
        project_slug: str | None,
        intent_type: str,
    ) -> None:
        """Create bead_watch row for circuit breaker tracking.

        Plan §10 The Async Path: watcher tracks open beads for refusals/SLA.
        SLA defaults by intent_type, with per-project sla_hours override.

        Args:
            bead_ref: The bead ID to watch
            project_slug: Project slug for SLA override lookup
            intent_type: Intent type for default SLA lookup
        """
        from ..registry import get_project

        sla_hours = None

        # Check for per-project SLA override
        if project_slug:
            project = get_project(project_slug)
            if project:
                sla_hours = project.get("sla_hours")
                if sla_hours is not None:
                    logger.info(
                        f"Using per-project SLA override for {project_slug}: "
                        f"{sla_hours} hours"
                    )

        store = await self._get_store()
        await store.create_bead_watch(
            bead_ref=bead_ref,
            sla_hours=sla_hours,
            intent_type=intent_type,
        )
        logger.debug(f"Created bead_watch row for {bead_ref}")

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
        """Extract bead ID from bf create output.

        bf create outputs just the bead ID (e.g., "abc-123").
        May include prefix text like "Created bead abc-123" in some versions.
        """
        import re

        # Strip whitespace first
        output = output.strip()

        if not output:
            logger.warning(f"Empty bf create output")
            return str(uuid.uuid4())

        # Try to extract bead ID pattern: lowercase letters, dash, alphanumeric
        # Bead IDs typically include numbers like: abc-123, xyz-789, adc-2fs
        # We prioritize matches with digits over letter-only matches
        patterns = [
            r"[a-z]+-[a-z]+-[a-z0-9]*[0-9]+[a-z0-9]*",  # Three components with digit: test-bead-456
            r"[a-z]+-[a-z0-9]*[0-9]+[a-z0-9]*",          # Two components with digit: abc-123
            r"[a-z]+-[a-z]+-[a-z0-9]+",                  # Three components letter-only: test-bead-xyz
            r"[a-z]{3,}-[a-z0-9]{2,}",                   # Fallback: any 3+ char prefix, dash, 2+ char suffix
        ]

        for pattern in patterns:
            matches = re.findall(pattern, output)
            if matches:
                # Return the longest match (prefer more specific patterns)
                bead_id = max(matches, key=len)
                logger.debug(f"Extracted bead ID '{bead_id}' from output")
                return bead_id

        # Fallback: if output already looks like a bead ID, return as-is
        # Basic validation: should contain a dash and be reasonable length
        if "-" in output and len(output) >= 3:
            logger.warning(f"Using output as bead ID despite non-standard format: {output}")
            return output

        # Last resort: return the whole output (bf might have changed format)
        logger.warning(f"Unexpected bf create output format: {output}")
        return output

    def build_pending_card(
        self,
        request: EscalateRequest,
        bead_id: str,
        bead_type: str = "task",
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
                "bead_type": bead_type,
            },
        }

    async def escalate_intent(self, request: EscalateRequest) -> EscalateResult:
        """
        Escalate an intent to a bead.

        Full flow:
        1. Load exceptions.yaml to determine bead type from escalation_targets
        2. Evaluate auto-approve rules from exceptions.yaml
        3. If auto-approved: execute directly and return result
        4. Otherwise: formulate bead body via LLM, create bead, return pending-card spec

        Args:
            request: The escalate request

        Returns:
            EscalateResult with bead ID and pending card (if bead created)
            or execution result (if auto-approved)
        """
        logger.info(f"Escalating intent {request.intent_id}")

        try:
            # Step 1: Load exceptions.yaml
            reload_mgr = self._get_reload_manager()
            exceptions_config = reload_mgr.get_config("exceptions")

            # Step 2: Evaluate auto-approve rules
            auto_approve, reason = self._evaluate_auto_approve(request, exceptions_config)

            if auto_approve:
                logger.info(f"Auto-approved intent {request.intent_id}: {reason}")

                # Execute directly without bead creation
                execution_result = await self._execute_auto_approved(request)

                # Update intent in store
                store = await self._get_store()
                await store.update_intent_status(
                    intent_id=request.intent_id,
                    status="resolved",
                )

                # Return result with empty pending_card (auto-approved, no bead created)
                return EscalateResult(
                    bead_id="",  # No bead created
                    intent_id=request.intent_id,
                    pending_card=execution_result,  # Return execution result directly
                    status="completed",
                )

            # Step 3: Determine bead type from escalation_targets
            bead_type = self._get_bead_type_from_targets(request.intent_type, exceptions_config)
            logger.info(f"Creating bead type '{bead_type}' for intent {request.intent_id} (not auto-approved: {reason})")

            # Step 4: Formulate bead body
            bead_body = await self.formulate_bead_body(request)

            # Step 5: Create bead with determined type
            bead_id = await self._create_bead_with_type(request, bead_body, bead_type)

            # Step 5.5: Create bead_watch row for circuit breaker tracking
            # (plan §10 The Async Path: watcher tracks open beads for refusals/SLA)
            await self._create_bead_watch(
                bead_ref=bead_id,
                project_slug=request.project_slug,
                intent_type=request.intent_type,
            )

            # Step 6: Build pending card
            pending_card = self.build_pending_card(request, bead_id, bead_type)

            # Update intent in store with bead reference
            store = await self._get_store()
            await store.update_intent_status(
                intent_id=request.intent_id,
                status="dispatched",
            )

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


async def handle_terminal_failure(
    intent_id: str,
    session_id: str,
    topic_id: str | None,
    failure_reason: str,
    error_type: str = "unknown",
    bead_ref: str | None = None,
) -> None:
    """
    Handle a terminal failure for an intent.

    Plan §10 The Async Path: terminal failure handling.
    - Sets intents.status = 'failed'
    - Stores failure reason in bead_watch.last_refusal_reason (if bead exists)
    - Creates failed card in session store
    - Broadcasts task_failed SSE event

    Args:
        intent_id: The intent that failed
        session_id: The session ID
        topic_id: The topic ID (optional)
        failure_reason: Human-readable failure reason
        error_type: Type of error (e.g., "worker_crash", "invalid_input")
        bead_ref: Associated bead reference (optional)
    """
    from ..session.store import get_store as get_session_store
    from ..sse.broadcaster import get_broadcaster, SSEEvent, EventType

    store = get_session_store()

    logger.info(f"Handling terminal failure for intent {intent_id}: {failure_reason}")

    # Step 1: Update intent status to 'failed'
    await store.update_intent_status(intent_id, "failed")
    logger.info(f"Set intent {intent_id} to failed status")

    # Step 2: Store failure reason in bead_watch if bead exists
    if bead_ref:
        try:
            await store.update_bead_watch_refusal(
                bead_ref=bead_ref,
                refusal_reason=failure_reason,
                comment_index=-1,  # No comment index for terminal failures
                refusal_count_add=1,
            )
            logger.info(f"Stored failure reason for bead {bead_ref}")
        except Exception as e:
            logger.warning(f"Failed to update bead_watch for {bead_ref}: {e}")

    # Step 3: Create or find topic for failed card
    # Fetch intent once for both topic creation and result_type derivation
    intent = None
    try:
        intent = await store.get_intent(intent_id)
    except Exception as e:
        logger.warning(f"Failed to fetch intent for result_type derivation: {e}")

    final_topic_id = topic_id
    if not final_topic_id and intent:
        utterance_id = intent.get("utterance_id")
        if utterance_id:
            # Get utterance to create label
            try:
                async with aiosqlite.connect(store.db_path) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        "SELECT raw_text FROM utterances WHERE id = ?",
                        (utterance_id,)
                    ) as cursor:
                        utterance_row = await cursor.fetchone()
                        if utterance_row:
                            utterance_text = utterance_row["raw_text"][:80]
                            final_topic_id, _ = await store.find_or_create_topic(
                                label=f"Failed: {utterance_text}",
                                session_id=session_id,
                                topic_type="exception",
                            )
            except Exception as e:
                logger.warning(f"Failed to create topic for failed card: {e}")

    # Step 4: Link intent to topic and create failed card
    if final_topic_id:
        try:
            # Link intent to topic (many-to-many)
            await store.link_intent_to_topic(intent_id, final_topic_id)

            # Update intent's primary topic_id field
            await store.update_intent_topic(intent_id, final_topic_id)

            # Create failed result card
            summary = f"Task Failed: {error_type.replace('_', ' ').title()}"
            data = {
                "bead_ref": bead_ref,
                "failure_reason": failure_reason,
                "error_type": error_type,
                "message": f"Task failed: {failure_reason}",
                "action_hint": "This task encountered a terminal error and cannot proceed. Review the error details and retry if applicable.",
            }

            # Derive result_type from intent data
            result_type = derive_result_type(
                intent_type=intent.get("intent_type") if intent else None,
                project_slug=intent.get("project_slug") if intent else None,
                lookup_kind=intent.get("lookup_kind") if intent else None,
            )

            result_id = await store.create_result(
                intent_id=intent_id,
                topic_id=final_topic_id,
                session_id=session_id,
                summary=summary,
                data=data,
                urgency="high",
                result_type=result_type,
            )

            logger.info(f"Created failed card {result_id} for intent {intent_id}")
        except Exception as e:
            logger.warning(f"Failed to create failed card for intent {intent_id}: {e}")

    # Step 5: Broadcast task_failed event via SSE
    broadcaster = get_broadcaster()
    await broadcaster.broadcast(
        SSEEvent(
            event_type=EventType.TASK_FAILED,
            data={
                "bead_id": bead_ref,
                "intent_id": intent_id,
                "session_id": session_id,
                "topic_id": final_topic_id,
                "failure_reason": failure_reason,
                "error_type": error_type,
                "message": f"Task failed: {failure_reason}",
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
            },
            target_session_id=session_id,
        )
    )

    logger.info(f"Broadcast task_failed event for intent {intent_id}")
