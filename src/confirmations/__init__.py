"""Confirmation dialog utilities for aide-de-camp.

This package provides confirmation prompt functionality for dangerous actions:
- Template-based confirmation questions (from config/confirmations.yaml)
- User response capture and storage
- Integration with session store for persistence
"""

from .confirmations import (
    get_pod_deletion_confirmation,
    format_confirmation_message,
)
from .prompts import (
    ConfirmationPromptManager,
    ConfirmationPromptError,
    ConfirmationPromptExpired,
    get_confirmation_manager,
    create_pod_deletion_confirmation,
    display_confirmation_prompt,
    capture_confirmation_response,
    get_confirmation_for_validation,
    validate_confirmation_response,
)
from .confirmed_deletions import (
    document_confirmed_deletion,
    get_latest_confirmed_deletion,
    get_confirmed_deletion_by_confirmation_id,
    list_all_confirmed_deletions,
    get_deletion_count,
)

__all__ = [
    # Template functions (from adc-46ksu)
    "get_pod_deletion_confirmation",
    "format_confirmation_message",
    # Confirmation prompt manager (from adc-2tw9h)
    "ConfirmationPromptManager",
    "ConfirmationPromptError",
    "ConfirmationPromptExpired",
    "get_confirmation_manager",
    # Convenience functions
    "create_pod_deletion_confirmation",
    "display_confirmation_prompt",
    "capture_confirmation_response",
    "get_confirmation_for_validation",
    # Validation functions (from adc-2os76)
    "validate_confirmation_response",
    # Confirmed deletions storage (from adc-zkdjq)
    "document_confirmed_deletion",
    "get_latest_confirmed_deletion",
    "get_confirmed_deletion_by_confirmation_id",
    "list_all_confirmed_deletions",
    "get_deletion_count",
]
