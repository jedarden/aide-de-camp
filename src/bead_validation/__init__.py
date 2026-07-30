"""
Bead Validation - Deterministic safety checks for escalate-generated beads.

This module provides deterministic (non-LLM) validation for bead bodies
before creation via bead-forge (bf CLI). The validation enforces:

1. Deny-list of live cluster-mutation verbs (kubectl apply/create/delete/scale/patch/edit/annotate/rollout)
2. Mutations must be phrased as declarative-config edits (GitOps), never direct kubectl
3. Mandatory cluster/namespace/resource scoping - unscoped instructions rejected

Usage:
    from src.bead_validation import BeadValidator, ValidationResult, ValidationError

    validator = BeadValidator()
    result = validator.validate_bead_body(bead_body, bead_type="task")

    if result.requires_approval:
        # Show approval card on canvas
        pass
    elif not result.is_valid:
        # Trigger re-formulation with failure reason
        pass
"""

from .validator import BeadValidator, get_validator
from .models import ValidationResult, ApprovalRequirement, ValidationRule, Violation, BeadType
from .exceptions import ValidationError, ValidationRetryExhaustedError

__all__ = [
    "BeadValidator",
    "ValidationResult",
    "ApprovalRequirement",
    "ValidationRule",
    "Violation",
    "BeadType",
    "ValidationError",
    "ValidationRetryExhaustedError",
]
