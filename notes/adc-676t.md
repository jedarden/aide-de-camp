# Intent Type Reconciliation Verification (adc-676t)

## Task
Reconcile intent types across all documentation files.

## Verification Result: ✅ ALREADY RECONCILED

All four files contain the **identical canonical list of 9 intent types** with matching descriptions.

## Canonical Intent Type List

| Intent Type | Description |
|-------------|-------------|
| `status` | Query current state (pods, pipelines, deployments, beads) |
| `action` | Execute a command (deploy, restart, create) |
| `brainstorm` | Explore options, design, architecture discussion |
| `lookup` | Find specific information (logs, configs, docs) |
| `reminder` | Set or query reminders |
| `self-modification` | Instructions to improve the interface itself |
| `monitoring-config` | Configure ambient monitoring rules |
| `task-profile` | Durable async work items that escalate to NEEDLE beads |
| `clarification` | Low-confidence routing outcome requiring user input (meta-type, not dispatched) |

## File-by-File Verification

### 1. docs/plan/plan.md (line 87)
✅ Lists all 9 types: `status`, `action`, `brainstorm`, `lookup`, `reminder`, `self-modification`, `monitoring-config`, `task-profile`, `clarification`

### 2. README.md (line 11)
✅ Lists all 9 types in the same order with identical formatting

### 3. prompts/router.md (lines 30-40)
✅ Lists all 9 types with full descriptions for each

### 4. src/intent/router.py (lines 27-37, IntentType enum)
✅ Enum contains all 9 types: `STATUS`, `ACTION`, `BRAINSTORM`, `LOOKUP`, `REMINDER`, `SELF_MODIFICATION`, `MONITORING_CONFIG`, `TASK_PROFILE`, `CLARIFICATION`
✅ Inline system prompt (lines 88-98) also documents all 9 types with identical descriptions

## Note on 'task' vs 'task-profile'

The task description mentioned `'task'` being used separately from `'task-profile'`. After review:
- The **intent type** is consistently `'task-profile'` across all files
- `'task'` appears only in `prompts/escalate/task-profile.md` as a **bead type** for the escalate path
- This is correct — `'task'` refers to the br/NEEDLE bead type, not an intent type
- No reconciliation needed

## Conclusion

No file changes required. Intent types were already fully reconciled across all documentation.
