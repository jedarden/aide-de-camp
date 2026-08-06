"""
Action registry - load workflow definitions from project registry.

This module provides functions for loading and validating workflow definitions
from project registry entries. Workflows are defined in project registry
configurations as sequences of step names.

Example workflow definition in registry.yaml:
```yaml
projects:
  my-app:
    workflows:
      deploy:
        description: "Deploy application to production"
        steps:
          - ci_status
          - image_tag
          - gitops_commit
          - argocd_sync_status
          - pod_status
```

The registry validates workflow definitions and provides lookup functions
for the ActionExecutor.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from ..registry import get_registry


logger = logging.getLogger(__name__)


# Path to registry configuration
REGISTRY_PATH = Path(__file__).parent.parent.parent / "config" / "registry.yaml"


class WorkflowValidationError(Exception):
    """Raised when a workflow definition is invalid."""
    def __init__(self, project_slug: str, workflow_name: str, errors: list[str]):
        self.project_slug = project_slug
        self.workflow_name = workflow_name
        self.errors = errors
        message = (
            f"Workflow validation failed for '{project_slug}/{workflow_name}':\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
        super().__init__(message)


def _validate_workflow_steps(
    project_slug: str,
    workflow_name: str,
    steps: list[Any],
) -> list[str]:
    """
    Validate workflow step definitions.

    Args:
        project_slug: Project slug for error reporting
        workflow_name: Workflow name for error reporting
        steps: List of step definitions from registry

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Known step types
    known_steps = {
        "ci_status",
        "image_tag",
        "gitops_commit",
        "argocd_sync_status",
        "pod_status",
        "deployment_info",
        "git_log",
        "argocd_apps",
        "open_beads",
    }

    if not isinstance(steps, list):
        errors.append(f"steps must be a list, got {type(steps).__name__}")
        return errors

    if len(steps) == 0:
        errors.append("workflow must have at least one step")

    for i, step in enumerate(steps):
        if not isinstance(step, str):
            errors.append(f"step[{i}] must be a string, got {type(step).__name__}")
            continue

        if step not in known_steps:
            errors.append(
                f"step[{i}] '{step}' is not a known step type. "
                f"Known types: {', '.join(sorted(known_steps))}"
            )

    return errors


def _validate_workflow_definition(
    project_slug: str,
    workflow_name: str,
    workflow_config: dict[str, Any],
) -> list[str]:
    """
    Validate a single workflow definition.

    Args:
        project_slug: Project slug for error reporting
        workflow_name: Workflow name for error reporting
        workflow_config: Workflow configuration from registry

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not isinstance(workflow_config, dict):
        errors.append(
            f"workflow '{workflow_name}' must be a dict, got {type(workflow_config).__name__}"
        )
        return errors

    # Check required fields
    if "steps" not in workflow_config:
        errors.append(f"workflow '{workflow_name}' missing required field 'steps'")
    else:
        steps = workflow_config["steps"]
        step_errors = _validate_workflow_steps(project_slug, workflow_name, steps)
        errors.extend(step_errors)

    # Optional fields
    if "description" in workflow_config:
        description = workflow_config["description"]
        if not isinstance(description, str):
            errors.append(
                f"workflow '{workflow_name}' description must be a string, "
                f"got {type(description).__name__}"
            )

    return errors


def get_workflow_definition(
    project_slug: str,
    workflow_name: str,
) -> dict[str, Any]:
    """
    Get workflow definition from project registry.

    Args:
        project_slug: Project slug to lookup
        workflow_name: Workflow name to retrieve

    Returns:
        Workflow definition dictionary

    Raises:
        WorkflowValidationError: If workflow definition is invalid
        ValueError: If project or workflow not found
    """
    registry = get_registry()

    # Get project entry
    projects = registry.get("projects", {})
    project_cfg = projects.get(project_slug)

    if not project_cfg:
        raise ValueError(f"Project '{project_slug}' not found in registry")

    # Get workflow definition
    workflows = project_cfg.get("workflows", {})
    workflow_config = workflows.get(workflow_name)

    if not workflow_config:
        raise ValueError(
            f"Workflow '{workflow_name}' not found for project '{project_slug}'. "
            f"Available workflows: {', '.join(workflows.keys()) or '(none)'}"
        )

    # Validate workflow definition
    errors = _validate_workflow_definition(project_slug, workflow_name, workflow_config)
    if errors:
        raise WorkflowValidationError(project_slug, workflow_name, errors)

    return workflow_config


def list_workflows(project_slug: str) -> dict[str, dict[str, Any]]:
    """
    List all workflows for a project.

    Args:
        project_slug: Project slug to lookup

    Returns:
        Dictionary mapping workflow names to their definitions

    Raises:
        ValueError: If project not found
    """
    registry = get_registry()

    projects = registry.get("projects", {})
    project_cfg = projects.get(project_slug)

    if not project_cfg:
        raise ValueError(f"Project '{project_slug}' not found in registry")

    return project_cfg.get("workflows", {})


def validate_all_workflows() -> list[dict[str, Any]]:
    """
    Validate all workflow definitions across all projects.

    Returns:
        List of validation error dictionaries. Each dict has:
        - project_slug: str
        - workflow_name: str
        - errors: list[str]

    Returns empty list if all workflows are valid.
    """
    registry = get_registry()
    all_errors = []

    projects = registry.get("projects", {})

    for project_slug, project_cfg in projects.items():
        workflows = project_cfg.get("workflows", {})

        for workflow_name, workflow_config in workflows.items():
            errors = _validate_workflow_definition(
                project_slug,
                workflow_name,
                workflow_config,
            )

            if errors:
                all_errors.append({
                    "project_slug": project_slug,
                    "workflow_name": workflow_name,
                    "errors": errors,
                })

    return all_errors


def reload_registry() -> None:
    """
    Force reload the project registry cache.

    This bypasses the TTL cache and forces a fresh read from disk.
    Useful after registry.yaml has been updated.
    """
    get_registry(force=True)
    logger.info("Registry cache reloaded")


# Alias functions for compatibility with acceptance criteria naming
def load_workflow_definition(
    project_slug: str,
    workflow_name: str,
) -> dict[str, Any]:
    """
    Alias for get_workflow_definition().

    Args:
        project_slug: Project slug to lookup
        workflow_name: Workflow name to retrieve

    Returns:
        Workflow definition dictionary

    Raises:
        WorkflowValidationError: If workflow definition is invalid
        ValueError: If project or workflow not found
    """
    return get_workflow_definition(project_slug, workflow_name)


def list_available_workflows(project_slug: str) -> dict[str, dict[str, Any]]:
    """
    Alias for list_workflows().

    Args:
        project_slug: Project slug to lookup

    Returns:
        Dictionary mapping workflow names to their definitions

    Raises:
        ValueError: If project not found
    """
    return list_workflows(project_slug)
