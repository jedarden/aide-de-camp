"""
Data models for bead validation.

Defines the structure for validation rules, violations, and bead types.
"""
from dataclasses import dataclass, field
from enum import Enum


class BeadType(Enum):
    """NEEDLE bead types from escalation_targets config."""
    TASK = "task"
    ACTION = "action"
    SELF_MODIFICATION = "self_modification"
    MONITORING_CONFIG = "monitoring_config"
    INFORMATIONAL = "informational"


class Severity(Enum):
    """Severity levels for validation violations."""
    ERROR = "error"  # Blocks bead creation
    WARNING = "warning"  # Requires approval


@dataclass
class Violation:
    """A single validation violation."""
    rule_id: str
    severity: Severity
    message: str
    line_number: int | None = None  # Line in bead body where violation occurs
    context: str | None = None  # Snippet of text that caused the violation

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "line_number": self.line_number,
            "context": self.context,
        }


@dataclass
class ValidationRule:
    """A validation rule definition."""
    rule_id: str
    name: str
    description: str
    severity: Severity
    bead_types: list[BeadType] = field(default_factory=list)  # Empty = all types
    # If True, this rule triggers approval requirement instead of blocking
    requires_approval: bool = False


@dataclass
class ApprovalRequirement:
    """Details about why approval is required."""
    required: bool
    reason: str
    bead_type: BeadType
    violations: list[Violation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "required": self.required,
            "reason": self.reason,
            "bead_type": self.bead_type.value,
            "violations": [v.to_dict() for v in self.violations],
        }


@dataclass
class ValidationResult:
    """Result of bead validation."""
    is_valid: bool
    requires_approval: bool
    violations: list[Violation] = field(default_factory=list)
    approval_requirement: ApprovalRequirement | None = None
    # Re-formulation hint (set when validation fails)
    reformulation_hint: str | None = None

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "requires_approval": self.requires_approval,
            "approval_requirement": self.approval_requirement.to_dict() if self.approval_requirement else None,
            "violations": [v.to_dict() for v in self.violations],
            "reformulation_hint": self.reformulation_hint,
        }

    @classmethod
    def valid(cls, bead_type: BeadType) -> "ValidationResult":
        """Create a valid result (no approval required)."""
        return cls(
            is_valid=True,
            requires_approval=False,
            approval_requirement=ApprovalRequirement(
                required=False,
                reason="Bead passes all validation rules",
                bead_type=bead_type,
            ),
        )

    @classmethod
    def requires_approval(
        cls,
        bead_type: BeadType,
        reason: str,
        violations: list[Violation] | None = None,
    ) -> "ValidationResult":
        """Create a result that requires approval."""
        return cls(
            is_valid=True,
            requires_approval=True,
            approval_requirement=ApprovalRequirement(
                required=True,
                reason=reason,
                bead_type=bead_type,
                violations=violations or [],
            ),
        )

    @classmethod
    def invalid(
        cls,
        violations: list[Violation],
        reformulation_hint: str | None = None,
    ) -> "ValidationResult":
        """Create an invalid result."""
        return cls(
            is_valid=False,
            requires_approval=False,
            approval_requirement=None,
            violations=violations,
            reformulation_hint=reformulation_hint,
        )
