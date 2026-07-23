"""
Deterministic bead validator - safety checks before bead creation.

Implements deterministic (non-LLM) validation for escalate-generated beads:
- Deny-list of live cluster-mutation verbs
- GitOps requirement for mutations
- Mandatory scoping (cluster/namespace/resource)

Historical incident: Unscoped 'kubectl delete pod' bead (adc-*kubectl-delete*)
created 2026-07-21/22 that NEEDLE workers refused in a loop.
"""
import re
from logging import getLogger
from typing import Optional

from .models import (
    BeadType,
    ValidationResult,
    ValidationRule,
    Severity,
    Violation,
)


logger = getLogger(__name__)


# Deny-list: kubectl verbs that mutate cluster state directly
FORBIDDEN_KUBECTL_VERBS = [
    "apply",
    "create",
    "delete",
    "scale",
    "patch",
    "edit",
    "annotate",
    "rollout",
    "replace",
    "cordon",
    "uncordon",
    "drain",
    "taint",
]

# Patterns that indicate direct kubectl usage
KUBECTL_DIRECT_PATTERNS = [
    r"\bkubectl\s+(apply|create|delete|scale|patch|edit|annotate|rollout|replace|cordon|uncordon|drain|taint)\b",
    r"\bkubectl\s+[--]",
]

# GitOps-approved patterns (declarative-config edits)
GITOPS_APPROVED_PATTERNS = [
    r"edit.*declarative-config",
    r"edit.*k8s/",
    r"git commit.*k8s/",
    r"jedarden/declarative-config",
    r"argocd app\s+",
    r"git push.*declarative",
    r"pull request.*declarative",
]

# Scoping requirements - must include at least one of these
SCOPING_PATTERNS = [
    r"cluster:\s*\S+",
    r"namespace:\s*\S+",
    r"namespace\s*=\s*['\"][\w-]+['\"]",
    r"-n\s+['\"][\w-]+['\"]",
    r"\s-n\s+\w+",
    r"pod:\s*\S+",
    r"pod\s*=\s*['\"][\w-]+['\"]",
    r"deployment:\s*\S+",
    r"deployment\s*=\s*['\"][\w-]+['\"]",
    r"service:\s*\S+",
    r"service\s*=\s*['\"][\w-]+['\"]",
]

# Informational bead patterns - these don't need approval
INFORMATIONAL_PATTERNS = [
    r"\blook( up| at| into)?\b",
    r"\bcheck\b",
    r"\bshow\b",
    r"\bdisplay\b",
    r"\blist\b",
    r"\bdescribe\b",
    r"\bget\b",
    r"\bstatus\b",
    r"\bhealth\b",
    r"\bverify\b",
    r"\bconfirm\b",
    r"\bcompare\b",
    r"\bmonitor\b",
    r"\bobserv(e|ation)\b",
]


class BeadValidator:
    """
    Deterministic validator for escalate-generated bead bodies.

    Enforces safety rules before bead creation via bead-forge CLI.
    """

    def __init__(self):
        self.rules = self._build_rules()

    def _build_rules(self) -> list[ValidationRule]:
        """Build validation rules."""
        return [
            ValidationRule(
                rule_id="no_direct_kubectl_mutation",
                name="No Direct kubectl Mutation",
                description="Mutations must use GitOps (declarative-config), not direct kubectl",
                severity=Severity.ERROR,
            ),
            ValidationRule(
                rule_id="gitops_required_for_mutations",
                name="GitOps Required for Mutations",
                description="Cluster changes must go through declarative-config (GitOps)",
                severity=Severity.ERROR,
            ),
            ValidationRule(
                rule_id="scoping_required",
                name="Scoping Required",
                description="Commands must include cluster/namespace/resource scoping",
                severity=Severity.ERROR,
            ),
            ValidationRule(
                rule_id="action_bead_requires_approval",
                name="Action Bead Requires Approval",
                description="Action-type beads require explicit user approval",
                severity=Severity.WARNING,
                requires_approval=True,
            ),
        ]

    def validate_bead_body(
        self,
        bead_body: str,
        bead_type: str = "task",
    ) -> ValidationResult:
        """
        Validate a bead body deterministically.

        Args:
            bead_body: The bead body markdown text
            bead_type: The bead type (task, action, self_modification, etc.)

        Returns:
            ValidationResult with is_valid, requires_approval, violations
        """
        logger.info(f"Validating bead body (type={bead_type}, length={len(bead_body)})")

        # Normalize bead type
        try:
            bead_type_enum = BeadType(bead_type)
        except ValueError:
            # Default to TASK if unknown type
            bead_type_enum = BeadType.TASK
            logger.warning(f"Unknown bead_type '{bead_type}', defaulting to TASK")

        # Lowercase for pattern matching
        body_lower = bead_body.lower()

        # Check for information beads (no approval needed)
        is_informational = self._is_informational_bead(bead_body, body_lower)
        if is_informational and bead_type_enum == BeadType.TASK:
            logger.info("Bead appears to be informational - no approval required")
            return ValidationResult.valid(BeadType.INFORMATIONAL)

        violations = []

        # Rule 1: Check for forbidden kubectl verbs
        kubectl_violations = self._check_forbidden_kubectl_verbs(bead_body, body_lower)
        violations.extend(kubectl_violations)

        # Rule 2: If it's a mutation, check GitOps requirement
        # Exception: self_modification and monitoring_config beads are supposed to
        # modify prompts/configs directly, not through GitOps infrastructure workflow
        if self._is_mutation_bead(body_lower) and bead_type_enum not in (
            BeadType.SELF_MODIFICATION,
            BeadType.MONITORING_CONFIG,
        ):
            gitops_violations = self._check_gitops_requirement(bead_body, body_lower)
            violations.extend(gitops_violations)

        # Rule 3: Check scoping requirements
        scoping_violations = self._check_scoping_requirement(bead_body, body_lower)
        violations.extend(scoping_violations)

        # If there are ERROR-level violations, bead is invalid
        error_violations = [v for v in violations if v.severity == Severity.ERROR]
        if error_violations:
            hint = self._generate_reformulation_hint(error_violations)
            logger.warning(f"Bead validation failed with {len(error_violations)} errors")
            return ValidationResult.invalid(error_violations, reformulation_hint=hint)

        # Rule 4: Action beads require approval
        if bead_type_enum == BeadType.ACTION:
            warning_violations = [v for v in violations if v.severity == Severity.WARNING]
            logger.info(f"Action bead requires approval ({len(warning_violations)} warnings)")
            return ValidationResult.requires_approval(
                bead_type=bead_type_enum,
                reason="Action-type beads require explicit user approval",
                violations=warning_violations,
            )

        # Self-modification and monitoring-config also require approval
        if bead_type_enum in (BeadType.SELF_MODIFICATION, BeadType.MONITORING_CONFIG):
            logger.info(f"{bead_type_enum.value} bead requires approval")
            return ValidationResult.requires_approval(
                bead_type=bead_type_enum,
                reason=f"{bead_type_enum.value.replace('_', ' ').title()} beads require explicit user approval",
            )

        # Valid task/informational bead
        logger.info("Bead validation passed")
        return ValidationResult.valid(bead_type_enum)

    def _is_informational_bead(self, bead_body: str, body_lower: str) -> bool:
        """Check if bead is informational (read-only operations)."""
        # Look for informational keywords in title/summary
        lines = bead_body.split("\n")
        first_few_lines = "\n".join(lines[:5])

        # Check for informational patterns
        for pattern in INFORMATIONAL_PATTERNS:
            if re.search(pattern, body_lower):
                # But make sure it's not a mutation in disguise
                if not any(verb in body_lower for verb in FORBIDDEN_KUBECTL_VERBS):
                    return True

        return False

    def _is_mutation_bead(self, body_lower: str) -> bool:
        """Check if bead describes a mutation operation."""
        # Check for any forbidden kubectl verb
        for verb in FORBIDDEN_KUBECTL_VERBS:
            if verb in body_lower:
                return True

        # Check for mutation keywords
        mutation_keywords = ["restart", "deploy", "scale", "delete", "update", "patch"]
        for keyword in mutation_keywords:
            if keyword in body_lower:
                return True

        return False

    def _check_forbidden_kubectl_verbs(
        self,
        bead_body: str,
        body_lower: str,
    ) -> list[Violation]:
        """Check for forbidden direct kubectl mutation commands."""
        violations = []

        for verb in FORBIDDEN_KUBECTL_VERBS:
            # Look for kubectl followed by forbidden verb
            pattern = rf"\bkubectl\s+{re.escape(verb)}\b"
            matches = list(re.finditer(pattern, body_lower, re.MULTILINE))

            for match in matches:
                # Extract line number
                line_num = body_lower[:match.start()].count("\n") + 1
                line_text = self._get_line_context(bead_body, line_num)

                violations.append(Violation(
                    rule_id="no_direct_kubectl_mutation",
                    severity=Severity.ERROR,
                    message=f"Direct kubectl '{verb}' command detected. Mutations must use GitOps (declarative-config) approach.",
                    line_number=line_num,
                    context=line_text.strip(),
                ))

        return violations

    def _check_gitops_requirement(
        self,
        bead_body: str,
        body_lower: str,
    ) -> list[Violation]:
        """Check that mutations use GitOps (declarative-config) approach."""
        violations = []

        # If it's a mutation, check for GitOps patterns
        has_gitops = False
        for pattern in GITOPS_APPROVED_PATTERNS:
            if re.search(pattern, body_lower, re.IGNORECASE):
                has_gitops = True
                break

        if not has_gitops:
            violations.append(Violation(
                rule_id="gitops_required_for_mutations",
                severity=Severity.ERROR,
                message="Mutation operation detected but no GitOps pattern found. Cluster changes must go through declarative-config (jedarden/declarative-config), not direct kubectl.",
            ))

        return violations

    def _check_scoping_requirement(
        self,
        bead_body: str,
        body_lower: str,
    ) -> list[Violation]:
        """Check that commands include proper scoping."""
        violations = []

        has_scoping = False
        for pattern in SCOPING_PATTERNS:
            if re.search(pattern, body_lower, re.IGNORECASE):
                has_scoping = True
                break

        # Only enforce scoping if it mentions kubectl or cluster operations
        if "kubectl" in body_lower or "namespace" in body_lower or "cluster" in body_lower:
            if not has_scoping:
                violations.append(Violation(
                    rule_id="scoping_required",
                    severity=Severity.ERROR,
                    message="Command lacks proper scoping. Must include cluster, namespace, and/or resource scoping (e.g., 'namespace: production', 'cluster: ardenone-manager').",
                ))

        return violations

    def _get_line_context(self, text: str, line_number: int, context_lines: int = 1) -> str:
        """Get the context around a specific line."""
        lines = text.split("\n")
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)
        return "\n".join(lines[start:end])

    def _generate_reformulation_hint(self, violations: list[Violation]) -> str:
        """Generate a hint for re-formulating the bead body."""
        hints = []

        for violation in violations:
            if violation.rule_id == "no_direct_kubectl_mutation":
                hints.append("Replace direct kubectl commands with GitOps approach: edit jedarden/declarative-config k8s/ files instead")
            elif violation.rule_id == "gitops_required_for_mutations":
                hints.append("Use GitOps workflow: edit declarative-config → git commit → create/merge PR → ArgoCD sync")
            elif violation.rule_id == "scoping_required":
                hints.append("Add explicit scoping: specify cluster (e.g., 'cluster: ardenone-manager'), namespace (e.g., 'namespace: production'), and target resources")

        if hints:
            return "Re-formulation hint: " + "; ".join(hints)
        return "Re-formulate the bead body to address the validation errors above."


# Global validator instance
_validator: Optional[BeadValidator] = None


def get_validator() -> BeadValidator:
    """Get or create the global validator instance."""
    global _validator
    if _validator is None:
        _validator = BeadValidator()
    return _validator
