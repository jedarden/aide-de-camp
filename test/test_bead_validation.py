#!/usr/bin/env python3
"""
Test suite for bead validation.

Tests the deterministic (non-LLM) validation for escalate-generated beads:
- Deny-list of live cluster-mutation verbs
- GitOps requirement for mutations
- Mandatory scoping (cluster/namespace/resource)
- Approval gate for action-derived beads
- Informational beads skip approval but pass validation

Historical incident: Unscoped 'kubectl delete pod' bead (adc-*kubectl-delete*)
created 2026-07-21/22 that NEEDLE workers refused in a loop.
"""

import sys
from pathlib import Path

# Ensure the project root is in the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.bead_validation.validator import BeadValidator, get_validator
from src.bead_validation.models import (
    BeadType,
    ValidationResult,
    Severity,
    Violation,
)


def test_historical_kubectl_delete_pod_rejected():
    """
    Test 1: Historical 'kubectl delete pod' unscoped body is rejected.

    The literal historical bead body from 2026-07-21/22 should be rejected
    because it contains a direct kubectl delete command without proper scoping
    or GitOps approach.
    """
    print("Testing historical 'kubectl delete pod' rejection...")

    validator = get_validator()

    # The literal historical bead body (unscoped, direct kubectl)
    historical_body = """# Task: Delete Pod

Delete the pod using kubectl.

## Steps
1. kubectl delete pod <pod_name>

No namespace or cluster specified - this is the bug.
"""

    result = validator.validate_bead_body(historical_body, bead_type="task")

    # Should be invalid (blocked)
    assert result.is_valid is False, "Historical kubectl delete pod should be invalid"
    assert result.requires_approval is False, "Invalid beads should not require approval"
    assert len(result.violations) > 0, "Should have violations"

    # Check that violations include the right rules
    violation_rule_ids = [v.rule_id for v in result.violations]
    assert "no_direct_kubectl_mutation" in violation_rule_ids, "Should forbid direct kubectl"

    # Should have a reformulation hint
    assert result.reformulation_hint is not None, "Should provide reformulation hint"

    print("  ✅ Historical 'kubectl delete pod' correctly rejected")
    print(f"      Violations: {len(result.violations)}")
    print(f"      Hint: {result.reformulation_hint[:60]}...")
    return True


def test_gitops_phased_mutation_passes_with_approval():
    """
    Test 2: GitOps-phrased scoped mutation passes validation but requires approval.

    A properly scoped mutation that uses GitOps approach should pass validation
    but still require approval for action-type beads.
    """
    print("Testing GitOps-phrased scoped mutation...")

    validator = get_validator()

    # Proper GitOps-phrased mutation with full scoping
    gitops_body = """# Task: Restart Pod on Production

## Overview
Restart the pod in the production namespace using GitOps workflow.

## Scope
- Cluster: ardenone-cluster
- Namespace: production
- Deployment: web-app

## Steps
1. Edit the manifest in jedarden/declarative-config/k8s/ardenone-cluster/production/web-app.yaml
2. Add or modify an annotation to trigger rollout
3. Commit the change: git commit -m 'Trigger rollout for web-app'
4. Push to main branch
5. ArgoCD will sync automatically

## Success Criteria
- ArgoCD reports Synced and Healthy
- New pod is Running
"""

    result = validator.validate_bead_body(gitops_body, bead_type="action")

    # Should be valid (passes safety checks)
    assert result.is_valid is True, "GitOps-phrased mutation should be valid"

    # But requires approval for action-type beads
    assert result.requires_approval is True, "Action beads require approval"
    assert result.approval_requirement is not None, "Should have approval requirement"
    assert result.approval_requirement.bead_type == BeadType.ACTION, "Should be ACTION type"

    # Should have no ERROR-level violations
    error_violations = [v for v in result.violations if v.severity == Severity.ERROR]
    assert len(error_violations) == 0, "Should have no ERROR violations"

    print("  ✅ GitOps-phrased mutation passes with approval requirement")
    print(f"      Approval reason: {result.approval_requirement.reason}")
    return True


def test_informational_bead_passes_without_approval():
    """
    Test 3: Informational bead passes without approval.

    Purely informational beads (research, lookups) should pass validation
    without requiring approval.
    """
    print("Testing informational bead (no approval required)...")

    validator = get_validator()

    # Informational/research bead body
    informational_body = """# Research Task: Investigate Pod Restart Patterns

## Overview
Look up and analyze the last month of pod restart patterns for the web application.

## Scope
- Cluster: ardenone-cluster
- Namespace: production
- Time range: Last 30 days

## Steps
1. Check pod logs from kubectl
2. Look at crash loop back off events
3. Analyze restart patterns
4. Summarize findings

## Success Criteria
- Report includes restart frequency
- Report identifies common failure patterns
- Recommendations provided
"""

    result = validator.validate_bead_body(informational_body, bead_type="task")

    # Should be valid
    assert result.is_valid is True, "Informational bead should be valid"

    # Should NOT require approval (informational)
    assert result.requires_approval is False, "Informational beads should not require approval"

    # Should have no violations
    assert len(result.violations) == 0, "Should have no violations"

    print("  ✅ Informational bead passes without approval")
    return True


def test_unscoped_mutation_rejected():
    """
    Test: Unscoped mutation is rejected.

    Mutations without proper cluster/namespace/resource scoping
    should be rejected.
    """
    print("Testing unscoped mutation rejection...")

    validator = get_validator()

    # Unscoped mutation (no cluster/namespace specified)
    unscoped_body = """# Task: Scale Deployment

Scale up the deployment.

## Steps
1. kubectl scale deployment web-app --replicas=5

No cluster or namespace specified - violates scoping requirement.
"""

    result = validator.validate_bead_body(unscoped_body, bead_type="action")

    # Should be invalid
    assert result.is_valid is False, "Unscoped mutation should be invalid"

    # Check for scoping violation
    violation_rule_ids = [v.rule_id for v in result.violations]
    assert "scoping_required" in violation_rule_ids, "Should require scoping"

    print("  ✅ Unscoped mutation correctly rejected")
    print(f"      Violations: {[v.rule_id for v in result.violations]}")
    return True


def test_self_modification_requires_approval():
    """
    Test: Self-modification beads require approval.

    Beads that modify system prompts or configuration should require approval.
    """
    print("Testing self-modification bead approval requirement...")

    validator = get_validator()

    # Self-modification bead
    self_mod_body = """# Task: Update Router Prompt

Improve the intent router prompt to better handle multi-project utterances.

## Steps
1. Analyze current routing patterns
2. Edit prompts/router.md
3. Test with sample utterances
4. Commit changes
"""

    result = validator.validate_bead_body(self_mod_body, bead_type="self_modification")

    # Should be valid (passes safety checks)
    assert result.is_valid is True, "Self-modification bead should be valid"

    # But requires approval
    assert result.requires_approval is True, "Self-modification beads require approval"
    assert result.approval_requirement.bead_type == BeadType.SELF_MODIFICATION

    print("  ✅ Self-modification bead requires approval")
    return True


def test_monitoring_config_requires_approval():
    """
    Test: Monitoring-config beads require approval.

    Beads that modify monitoring rules should require approval.
    """
    print("Testing monitoring-config bead approval requirement...")

    validator = get_validator()

    # Monitoring config bead
    monitoring_body = """# Task: Add Monitoring Rule

Add a new monitoring rule for pod health checks.

## Steps
1. Edit config/monitoring.yaml
2. Add rule for pod crash loops
3. Test monitoring tick
"""

    result = validator.validate_bead_body(monitoring_body, bead_type="monitoring_config")

    # Should be valid
    assert result.is_valid is True, "Monitoring-config bead should be valid"

    # But requires approval
    assert result.requires_approval is True, "Monitoring-config beads require approval"
    assert result.approval_requirement.bead_type == BeadType.MONITORING_CONFIG

    print("  ✅ Monitoring-config bead requires approval")
    return True


def test_multiple_kubectl_violations_detected():
    """
    Test: Multiple forbidden kubectl verbs are all detected.

    A bead body with multiple different forbidden kubectl commands
    should report violations for each.
    """
    print("Testing multiple kubectl violations detection...")

    validator = get_validator()

    # Bead with multiple forbidden verbs
    multi_violation_body = """# Task: Multi-Step Deployment

## Steps
1. kubectl apply -f deployment.yaml
2. kubectl scale deployment web-app --replicas=3
3. kubectl rollout restart deployment/web-app
4. kubectl delete pod old-pod

Multiple direct kubectl mutations - all should be flagged.
"""

    result = validator.validate_bead_body(multi_violation_body, bead_type="action")

    # Should be invalid
    assert result.is_valid is False, "Multiple violations should make bead invalid"

    # Should detect multiple violations
    kubectl_violations = [v for v in result.violations if v.rule_id == "no_direct_kubectl_mutation"]
    assert len(kubectl_violations) >= 2, "Should detect multiple kubectl violations"

    print(f"  ✅ Multiple violations detected: {len(kubectl_violations)} kubectl violations")
    return True


def test_forbidden_verbs_list_completeness():
    """
    Test: All forbidden kubectl verbs are checked.

    Verify that the FORBIDDEN_KUBECTL_VERBS list includes all
    the dangerous verbs from the requirements.
    """
    print("Testing forbidden verbs list completeness...")

    from src.bead_validation.validator import FORBIDDEN_KUBECTL_VERBS

    # Required forbidden verbs from requirements
    required_verbs = [
        "apply",
        "create",
        "delete",
        "scale",
        "patch",
        "edit",
        "annotate",
        "rollout",
    ]

    for verb in required_verbs:
        assert verb in FORBIDDEN_KUBECTL_VERBS, f"Missing required verb: {verb}"

    print(f"  ✅ All required forbidden verbs present ({len(required_verbs)})")
    return True


def test_informational_patterns_correctly_identified():
    """
    Test: Informational beads are correctly identified by patterns.

    Verify that beads with informational keywords are classified
    as informational and don't require approval.
    """
    print("Testing informational pattern identification...")

    validator = get_validator()

    # Various informational patterns
    informational_bodies = [
        ("Look up the pod logs", "lookup"),
        ("Check the deployment status", "check"),
        ("Show the recent errors", "show"),
        ("List all running pods", "list"),
        ("Describe the service endpoints", "describe"),
        ("Get the current configuration", "get"),
        ("Verify the health checks", "verify"),
        ("Monitor the application metrics", "monitor"),
    ]

    for body, keyword in informational_bodies:
        result = validator.validate_bead_body(f"# Task\n\n{body}", bead_type="task")
        assert result.is_valid is True, f"'{keyword}' should be valid"
        assert result.requires_approval is False, f"'{keyword}' should not require approval"

    print(f"  ✅ All {len(informational_bodies)} informational patterns correctly identified")
    return True


def test_reformulation_hint_generation():
    """
    Test: Reformulation hints are generated correctly.

    Verify that validation failures produce helpful reformulation hints.
    """
    print("Testing reformulation hint generation...")

    validator = get_validator()

    # Bead that fails with specific violations
    bad_body = """# Task
kubectl delete pod xyz
No scoping here.
"""

    result = validator.validate_bead_body(bad_body, bead_type="action")

    # Should be invalid with hint
    assert result.is_valid is False
    assert result.reformulation_hint is not None

    # Hint should mention GitOps
    assert "GitOps" in result.reformulation_hint or "declarative-config" in result.reformulation_hint

    print("  ✅ Reformulation hint generated correctly")
    print(f"      Hint: {result.reformulation_hint}")
    return True


def test_validator_singleton():
    """
    Test: Validator singleton works correctly.

    Verify that get_validator() returns the same instance.
    """
    print("Testing validator singleton...")

    validator1 = get_validator()
    validator2 = get_validator()

    assert validator1 is validator2, "Should return same instance"

    print("  ✅ Validator singleton works correctly")
    return True


def main():
    """Run all bead validation tests."""
    print("="*60)
    print("BEAD VALIDATION TEST SUITE")
    print("="*60)
    print()

    tests = [
        # Core acceptance criteria tests
        test_historical_kubectl_delete_pod_rejected,
        test_gitops_phased_mutation_passes_with_approval,
        test_informational_bead_passes_without_approval,

        # Additional safety tests
        test_unscoped_mutation_rejected,
        test_self_modification_requires_approval,
        test_monitoring_config_requires_approval,
        test_multiple_kubectl_violations_detected,

        # Infrastructure tests
        test_forbidden_verbs_list_completeness,
        test_informational_patterns_correctly_identified,
        test_reformulation_hint_generation,
        test_validator_singleton,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
            print()
        except AssertionError as e:
            print(f"  ❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
            print()
        except Exception as e:
            print(f"  ❌ Test error: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
            print()

    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("="*60)

    if all(results):
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
