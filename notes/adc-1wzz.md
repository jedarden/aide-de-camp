# adc-1wzz: Escalate Generated-Bead Safety

## Summary

Implemented comprehensive deterministic (non-LLM) validation and approval gates for escalate-generated beads, addressing the historical incident where an unscoped 'kubectl delete pod' bead caused NEEDLE workers to refuse in a loop (2026-07-21/22).

## Changes Made

### 1. Fixed Dataclass Field Order (src/bead_validation/models.py)
- Reordered `ValidationResult` dataclass fields to comply with Python dataclass rules
- Made `approval_requirement` field have a default value of `None`

### 2. Fixed Module Exports (src/bead_validation/__init__.py)
- Updated imports to correctly export `ValidationResult` and `ApprovalRequirement` from models module
- Added `get_validator` to exports

### 3. Enhanced Validator Logic (src/bead_validation/validator.py)
- **Lines 176-187**: Added exemption for `SELF_MODIFICATION` and `MONITORING_CONFIG` bead types from GitOps mutation checks
- These bead types are supposed to modify prompts/configs directly, not through GitOps infrastructure workflow
- This allows self-modification and monitoring-config beads to be valid (while still requiring approval)

### 4. Created Comprehensive Test Suite (test/test_bead_validation.py)
- **11 tests** covering all acceptance criteria:
  1. ✅ Historical 'kubectl delete pod' unscoped body is rejected
  2. ✅ GitOps-phrased scoped mutation passes validation but requires approval
  3. ✅ Informational bead passes without approval
  4. ✅ Unscoped mutation is rejected
  5. ✅ Self-modification bead requires approval
  6. ✅ Monitoring-config bead requires approval
  7. ✅ Multiple kubectl violations detected
  8. ✅ All required forbidden verbs present
  9. ✅ Informational patterns correctly identified
  10. ✅ Reformulation hint generated correctly
  11. ✅ Validator singleton works correctly

## Acceptance Criteria Met

All acceptance criteria from the task are satisfied:

### ✅ Tests: Historical 'kubectl delete pod' rejected
The literal historical bead body with unscoped `kubectl delete pod` is correctly rejected with 3 violations:
- `no_direct_kubectl_mutation` - Direct kubectl command detected
- `gitops_required_for_mutations` - No GitOps pattern found
- `scoping_required` - No cluster/namespace/resource scoping

### ✅ GitOps-phrased scoped mutation passes with approval
A properly scoped mutation using GitOps approach passes validation but requires approval for action-type beads.

### ✅ Informational bead passes without approval
Purely informational beads (research, lookups) pass validation and skip the approval gate.

### ✅ Re-formulation happens exactly once
The escalation handler's `_validate_and_prepare_approval()` method (handler.py:736-818):
1. Initial validation (line 760)
2. If failed → ONE re-formulation attempt with failure reason (lines 782-787)
3. If re-formulation still fails → raise `ValidationRetryExhaustedError` (lines 792-798)
4. No loop - exactly one retry

## Validation Rules Enforced

### 1. No Direct kubectl Mutation
Deny-list of forbidden verbs:
- apply, create, delete, scale, patch, edit, annotate, rollout, replace, cordon, uncordon, drain, taint

### 2. GitOps Required for Mutations
Mutations must use declarative-config approach:
- Edit `jedarden/declarative-config/k8s/` files
- Commit and push changes
- ArgoCD syncs automatically

### 3. Scoping Required
Commands must include:
- Cluster (e.g., `cluster: ardenone-manager`)
- Namespace (e.g., `namespace: production`)
- Resource (e.g., `pod:`, `deployment:`)

### 4. Approval Gate
Action-derived beads require explicit user approval:
- ACTION beads
- SELF_MODIFICATION beads
- MONITORING_CONFIG beads
- Informational beads skip approval

## Files Changed

1. `src/bead_validation/models.py` - Fixed dataclass field order
2. `src/bead_validation/__init__.py` - Fixed module exports
3. `src/bead_validation/validator.py` - Added GitOps exemption for self-modification/monitoring types
4. `test/test_bead_validation.py` - Created comprehensive test suite (NEW)

## Test Results

```
RESULTS: 11/11 tests passed
✅ ALL TESTS PASSED
```

## Integration Points

The validation is integrated into the escalate flow at:
- `src/escalate/handler.py:_validate_and_prepare_approval()` (lines 736-818)
- Called from `escalate_intent()` before bead creation (line 994)

## Historical Context

**Motivating incident**: An escalate-authored bead containing unscoped `kubectl delete pod` was created 2026-07-21/22. NEEDLE workers correctly refused it, but without a circuit breaker, the system re-dispatched it in a loop. This validation prevents such beads from being created in the first place.

## Date Completed

2026-07-23
