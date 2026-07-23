# GitOps and Scoping Validation Implementation

## Task (adc-52ptl)
Add GitOps and scoping validation rules to bead validation.

## Status: ✅ COMPLETE

All acceptance criteria are already implemented in the existing bead validation system:

### Acceptance Criteria Verification

#### ✅ 1. validate_bead_body checks for GitOps phrasing patterns
**Location:** `src/bead_validation/validator.py:_check_gitops_requirement()`

**GitOps-approved patterns detected:**
- `edit.*declarative-config`
- `edit.*k8s/`
- `git commit.*k8s/`
- `jedarden/declarative-config`
- `argocd app\s+`
- `git push.*declarative`
- `pull request.*declarative`

#### ✅ 2. Unscoped mutations are rejected
**Location:** `src/bead_validation/validator.py:_check_scoping_requirement()`

**Scoping patterns detected:**
- `cluster:\s*\S+`
- `namespace:\s*\S+`
- `-n\s+['\"][\w-]+['\"]`
- `pod:\s*\S+`
- `deployment:\s*\S+`
- `service:\s*\S+`

#### ✅ 3. Returns specific reason messages
**Error messages:**
- `'must be declarative-config edit'` → "Mutations must use GitOps (declarative-config) approach"
- `'missing cluster/namespace scoping'` → "Command lacks proper scoping. Must include cluster, namespace, and/or resource scoping (e.g., 'namespace: production', 'cluster: ardenone-manager')"

#### ✅ 4. Valid scoped GitOps mutation passes
**Test result:** Valid GitOps-phrased mutations with proper scoping pass validation but require approval for action-type beads.

### Test Coverage

All 11 bead validation tests pass:
- ✅ Historical kubectl delete pod rejected
- ✅ GitOps-phrased mutation passes with approval
- ✅ Informational bead passes without approval
- ✅ Unscoped mutation rejected
- ✅ Self-modification requires approval
- ✅ Monitoring-config requires approval
- ✅ Multiple kubectl violations detected
- ✅ Forbidden verbs list complete
- ✅ Informational patterns identified
- ✅ Reformulation hint generation
- ✅ Validator singleton

All 15 safety validation pipeline tests pass:
- ✅ Historical rejection integration test
- ✅ GitOps scoped mutation with approval
- ✅ Informational bead no approval
- ✅ Re-formulation happens exactly once
- ✅ Re-formulation count management
- ✅ Re-formulation limit enforced
- ✅ Clarification card generation
- ✅ Complete validation → approval pipeline
- ✅ Complete validation failure → clarification pipeline
- ✅ Edge cases (unknown type, empty body, long body)
- ✅ Pattern detection accuracy (kubectl, GitOps, scoping)

### Implementation Details

**Key Components:**
1. **BeadValidator** (`src/bead_validation/validator.py`) - Main validation logic
2. **Validation Rules** (`src/bead_validation/models.py`) - Rule definitions
3. **Exceptions** (`src/bead_validation/exceptions.py`) - Error handling

**Validation Flow:**
```
validate_bead_body(bead_body, bead_type)
  ├─→ Check informational patterns (skip approval if found)
  ├─→ Check forbidden kubectl verbs (no_direct_kubectl_mutation)
  ├─→ Check GitOps requirement for mutations (gitops_required_for_mutations)
  ├─→ Check scoping requirements (scoping_required)
  └─→ Return ValidationResult (valid/approval_required/invalid)
```

**Historical Context:**
This validation addresses the historical incident from 2026-07-21/22 where an unscoped 'kubectl delete pod' bead (adc-*kubectl-delete*) was created and caused NEEDLE workers to refuse in a loop.
