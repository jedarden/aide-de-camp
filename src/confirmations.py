"""Confirmation dialog utilities for destructive actions.

This module provides functions to load and format confirmation prompts
for destructive operations like pod deletion.
"""

from pathlib import Path
from typing import Any
import yaml


# Path to confirmation templates configuration
CONFIRMATIONS_CONFIG_PATH = Path(__file__).parent.parent / "config" / "confirmations.yaml"


def get_pod_deletion_confirmation(pod_name: str, namespace: str | None = None, cluster: str | None = None) -> dict[str, Any]:
    """
    Get the confirmation dialog for pod deletion.

    Args:
        pod_name: Name of the pod to delete
        namespace: Optional namespace (for context)
        cluster: Optional cluster name (for context)

    Returns:
        Dictionary containing:
        - question: The formatted confirmation question
        - warning: Warning message about consequences
        - required_response: Expected response format ("yes|no")
        - context: Context information included
    """
    try:
        config = yaml.safe_load(CONFIRMATIONS_CONFIG_PATH.read_text())
    except Exception:
        # Fallback if config file not found or invalid
        return {
            "question": f"Do you want to proceed with deleting pod {pod_name}? (yes/no)",
            "warning": "This will permanently delete the pod. The pod will be terminated and cannot be recovered unless recreated by its controller.",
            "required_response": "yes|no",
            "context": {
                "pod_name": pod_name,
                "namespace": namespace,
                "cluster": cluster
            }
        }

    pod_config = config.get("pod_deletion", {})
    template = pod_config.get("template", "Do you want to proceed with deleting pod {pod_name}? (yes/no)")
    warning = pod_config.get("warning", "")
    required_response = pod_config.get("required_response", "yes|no")

    # Format the question with context
    question = template.format(pod_name=pod_name)

    return {
        "question": question,
        "warning": warning,
        "required_response": required_response,
        "context": {
            "pod_name": pod_name,
            "namespace": namespace,
            "cluster": cluster
        },
        "consequences": pod_config.get("consequences", [])
    }


def format_confirmation_message(confirmation: dict[str, Any]) -> str:
    """
    Format a confirmation dictionary into a complete message.

    Args:
        confirmation: Confirmation dictionary from get_pod_deletion_confirmation()

    Returns:
        Formatted message string
    """
    message = confirmation["question"]

    if confirmation.get("warning"):
        message += f"\n\n⚠️  {confirmation['warning']}"

    if confirmation.get("consequences"):
        message += "\n\nConsequences:"
        for consequence in confirmation["consequences"]:
            message += f"\n  • {consequence}"

    return message