"""Confirmation prompt display and response capture system.

This module provides the user-facing confirmation prompt functionality:
1. Display confirmation questions to users
2. Capture user responses (yes/no or specific input)
3. Store responses in session store for validation
4. Integrate with confirmation templates from confirmations.yaml
"""

import json
import logging
from typing import Any, Optional
from datetime import datetime

from ..session.store import get_store
from . import get_pod_deletion_confirmation, format_confirmation_message

logger = logging.getLogger(__name__)


class ConfirmationPromptError(Exception):
    """Base exception for confirmation prompt errors."""
    pass


class ConfirmationPromptExpired(ConfirmationPromptError):
    """Confirmation prompt has expired."""
    pass


class ConfirmationPromptManager:
    """
    Manager for confirmation prompts.

    Handles creating confirmation prompts, displaying them to users,
    and capturing their responses.
    """

    def __init__(self):
        self.store = None

    async def _get_store(self):
        """Get or create session store."""
        if self.store is None:
            self.store = get_store()
        return self.store

    async def create_pod_deletion_confirmation(
        self,
        intent_id: str,
        session_id: str,
        pod_name: str,
        namespace: str | None = None,
        cluster: str | None = None,
    ) -> dict:
        """
        Create a pod deletion confirmation prompt.

        Uses the templates from adc-46ksu (config/confirmations.yaml) to
        generate a user-friendly confirmation question.

        Args:
            intent_id: The intent that triggered this confirmation
            session_id: The session for this confirmation
            pod_name: Name of the pod to delete
            namespace: Optional namespace (for context)
            cluster: Optional cluster name (for context)

        Returns:
            Dict with:
                - confirmation_id: The confirmation prompt ID
                - question: The formatted confirmation question
                - message: Complete formatted message (with warnings)
                - context: Context information included
        """
        store = await self._get_store()

        # Get the confirmation dialog template
        confirmation = get_pod_deletion_confirmation(
            pod_name=pod_name,
            namespace=namespace,
            cluster=cluster,
        )

        # Format the complete message
        message = format_confirmation_message(confirmation)

        # Build context for storage
        context = {
            "pod_name": pod_name,
            "namespace": namespace,
            "cluster": cluster,
            "owner_kind": confirmation.get("context", {}).get("owner_kind"),
            "owner_name": confirmation.get("context", {}).get("owner_name"),
        }

        # Create the confirmation prompt in the database
        confirmation_id = await store.create_confirmation_prompt(
            intent_id=intent_id,
            session_id=session_id,
            prompt_type="pod_deletion",
            question=confirmation["question"],
            context=context,
        )

        logger.info(
            f"Created pod deletion confirmation {confirmation_id} for pod {pod_name} "
            f"(intent: {intent_id}, session: {session_id})"
        )

        return {
            "confirmation_id": confirmation_id,
            "question": confirmation["question"],
            "message": message,
            "context": context,
            "status": "pending",
        }

    async def display_confirmation_prompt(self, confirmation_id: str) -> str:
        """
        Display a confirmation prompt to the user.

        This method retrieves the confirmation prompt and formats it for display.
        In the current implementation, this returns the formatted message.
        Future implementations could integrate with:
        - Canvas UI (SSE broadcast)
        - Telegram fallback (interactive buttons)
        - CLI prompt (for terminal interactions)

        Args:
            confirmation_id: The confirmation ID to display

        Returns:
            The formatted confirmation message for display

        Raises:
            ConfirmationPromptExpired: If the confirmation has expired
            ConfirmationPromptError: If the confirmation is not found
        """
        store = await self._get_store()

        # Get the confirmation prompt
        prompt = await store.get_confirmation_prompt(confirmation_id)

        if not prompt:
            raise ConfirmationPromptError(f"Confirmation prompt not found: {confirmation_id}")

        if prompt["status"] == "expired":
            raise ConfirmationPromptExpired(f"Confirmation prompt has expired: {confirmation_id}")

        # Build the complete message (re-using the format from confirmation templates)
        question = prompt["question"]

        # Add context if available
        context = {}
        if prompt.get("context"):
            try:
                context = json.loads(prompt["context"]) if isinstance(prompt["context"], str) else prompt["context"]
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse context for confirmation {confirmation_id}")

        # Build warnings from context
        message_parts = [question]

        if context.get("owner_kind"):
            message_parts.append(
                f"\n\n⚠️  This pod is managed by a {context['owner_kind']} and will be automatically recreated after deletion."
            )
            message_parts.append("This is normal Kubernetes behavior.")

        # Add response instructions
        message_parts.append("\n\nPlease respond with:")
        message_parts.append("  • 'yes' to confirm deletion")
        message_parts.append("  • 'no' to cancel")
        message_parts.append(f"  • Or type the pod name '{context.get('pod_name', 'pod-name')}' to confirm")

        return "\n".join(message_parts)

    async def capture_confirmation_response(
        self,
        confirmation_id: str,
        response: str,
    ) -> dict:
        """
        Capture a user's response to a confirmation prompt.

        This method stores the raw user response without validation.
        Validation is handled in the next step (per task requirements).

        Args:
            confirmation_id: The confirmation ID
            response: User's raw response (yes/no/pod name)

        Returns:
            Dict with:
                - success: Whether the response was captured
                - confirmation_id: The confirmation ID
                - response: The captured response
                - responded_at: When the response was captured

        Raises:
            ConfirmationPromptError: If the confirmation is not found or already responded
        """
        store = await self._get_store()

        # Submit the response (stores raw response without validation)
        success = await store.submit_confirmation_response(
            confirmation_id=confirmation_id,
            response=response,
        )

        if not success:
            # Get the prompt to provide better error message
            prompt = await store.get_confirmation_prompt(confirmation_id)
            if not prompt:
                raise ConfirmationPromptError(f"Confirmation prompt not found: {confirmation_id}")
            elif prompt["status"] == "responded":
                raise ConfirmationPromptError(f"Confirmation prompt already responded: {confirmation_id}")
            else:
                raise ConfirmationPromptError(f"Failed to capture response for confirmation: {confirmation_id}")

        # Get updated prompt data
        updated_prompt = await store.get_confirmation_prompt(confirmation_id)

        logger.info(
            f"Captured response for confirmation {confirmation_id}: '{response}' "
            f"(responded_at: {updated_prompt.get('responded_at')})"
        )

        return {
            "success": True,
            "confirmation_id": confirmation_id,
            "response": response,
            "responded_at": updated_prompt.get("responded_at"),
        }

    async def get_confirmation_for_validation(self, confirmation_id: str) -> dict:
        """
        Get confirmation prompt data for validation in the next step.

        This returns all the data needed for validation logic:
        - Original question
        - User response
        - Context
        - Timestamps

        Args:
            confirmation_id: The confirmation ID

        Returns:
            Dict with confirmation data for validation

        Raises:
            ConfirmationPromptError: If the confirmation is not found
        """
        store = await self._get_store()

        prompt = await store.get_confirmation_prompt(confirmation_id)

        if not prompt:
            raise ConfirmationPromptError(f"Confirmation prompt not found: {confirmation_id}")

        # Parse context if it's JSON string
        context = prompt.get("context")
        if context and isinstance(context, str):
            try:
                context = json.loads(context)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse context for confirmation {confirmation_id}")
                context = {}

        return {
            "confirmation_id": prompt["id"],
            "intent_id": prompt["intent_id"],
            "session_id": prompt["session_id"],
            "prompt_type": prompt["prompt_type"],
            "question": prompt["question"],
            "response": prompt.get("response"),
            "context": context,
            "created_at": prompt["created_at"],
            "responded_at": prompt.get("responded_at"),
            "status": prompt["status"],
        }


# Global confirmation prompt manager instance
_manager: Optional[ConfirmationPromptManager] = None


def get_confirmation_manager() -> ConfirmationPromptManager:
    """Get or create the global confirmation prompt manager instance."""
    global _manager
    if _manager is None:
        _manager = ConfirmationPromptManager()
    return _manager


# Convenience functions for common operations

async def create_pod_deletion_confirmation(
    intent_id: str,
    session_id: str,
    pod_name: str,
    namespace: str | None = None,
    cluster: str | None = None,
) -> dict:
    """
    Create a pod deletion confirmation prompt.

    Convenience wrapper around ConfirmationPromptManager.create_pod_deletion_confirmation()
    """
    manager = get_confirmation_manager()
    return await manager.create_pod_deletion_confirmation(
        intent_id=intent_id,
        session_id=session_id,
        pod_name=pod_name,
        namespace=namespace,
        cluster=cluster,
    )


async def display_confirmation_prompt(confirmation_id: str) -> str:
    """
    Display a confirmation prompt to the user.

    Convenience wrapper around ConfirmationPromptManager.display_confirmation_prompt()
    """
    manager = get_confirmation_manager()
    return await manager.display_confirmation_prompt(confirmation_id)


async def capture_confirmation_response(
    confirmation_id: str,
    response: str,
) -> dict:
    """
    Capture a user's response to a confirmation prompt.

    Convenience wrapper around ConfirmationPromptManager.capture_confirmation_response()
    """
    manager = get_confirmation_manager()
    return await manager.capture_confirmation_response(
        confirmation_id=confirmation_id,
        response=response,
    )


async def get_confirmation_for_validation(confirmation_id: str) -> dict:
    """
    Get confirmation prompt data for validation.

    Convenience wrapper around ConfirmationPromptManager.get_confirmation_for_validation()
    """
    manager = get_confirmation_manager()
    return await manager.get_confirmation_for_validation(confirmation_id)


async def validate_confirmation_response(
    confirmation_id: str,
    response: str,
) -> dict:
    """
    Validate a user's confirmation response format.

    This function checks if the user's response is in the correct format:
    - "yes" or "no" (case-insensitive)
    - Or the exact pod name (case-sensitive match)

    Args:
        confirmation_id: The confirmation ID to validate
        response: The user's response to validate

    Returns:
        Dict with:
            - valid: Boolean indicating if response is valid
            - response_type: One of "yes", "no", "pod_name", or None
            - normalized_response: The normalized response ("yes"/"no" lowercase, or pod name)
            - error_message: Clear error message if invalid, None if valid
            - confirmation_id: The confirmation ID

    Raises:
        ConfirmationPromptError: If the confirmation is not found
    """
    manager = get_confirmation_manager()

    # Get the confirmation data to retrieve expected pod name
    confirmation_data = await manager.get_confirmation_for_validation(confirmation_id)

    # Get the pod name from context (handle None case)
    context = confirmation_data.get("context") or {}
    expected_pod_name = context.get("pod_name") if context else None

    # Trim whitespace from response
    response_clean = response.strip()

    # Check for empty response
    if not response_clean:
        return {
            "valid": False,
            "response_type": None,
            "normalized_response": None,
            "error_message": "Empty response. Please respond with 'yes', 'no', or the exact pod name.",
            "confirmation_id": confirmation_id,
        }

    # Check for "yes" (case-insensitive)
    if response_clean.lower() == "yes":
        return {
            "valid": True,
            "response_type": "yes",
            "normalized_response": "yes",
            "error_message": None,
            "confirmation_id": confirmation_id,
        }

    # Check for "no" (case-insensitive)
    if response_clean.lower() == "no":
        return {
            "valid": True,
            "response_type": "no",
            "normalized_response": "no",
            "error_message": None,
            "confirmation_id": confirmation_id,
        }

    # Check for exact pod name match (case-sensitive)
    if expected_pod_name and response_clean == expected_pod_name:
        return {
            "valid": True,
            "response_type": "pod_name",
            "normalized_response": response_clean,
            "error_message": None,
            "confirmation_id": confirmation_id,
        }

    # Response doesn't match any allowed format
    if expected_pod_name:
        error_message = (
            f"Invalid response: '{response}'. "
            f"Please respond with 'yes', 'no', or the exact pod name '{expected_pod_name}'."
        )
    else:
        error_message = (
            f"Invalid response: '{response}'. "
            f"Please respond with 'yes' or 'no'."
        )

    return {
        "valid": False,
        "response_type": None,
        "normalized_response": None,
        "error_message": error_message,
        "confirmation_id": confirmation_id,
    }
