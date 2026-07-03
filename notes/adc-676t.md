# Intent Type Reconciliation (adc-676t)

## Task Completed

Reconciled intent types across all documentation in aide-de-camp.

## Canonical Intent Type List (9 types)

1. **status** - Query current state (pods, pipelines, deployments, beads)
2. **action** - Execute a command (deploy, restart, create)
3. **brainstorm** - Explore options, design, architecture discussion
4. **lookup** - Find specific information (logs, configs, docs)
5. **reminder** - Set or query reminders
6. **self-modification** - Instructions to improve the interface itself
7. **monitoring-config** - Configure ambient monitoring rules
8. **task-profile** - Durable async work items that escalate to NEEDLE beads
9. **clarification** - Low-confidence routing outcome requiring user input (meta-type, not dispatched)

## Files Verified

1. ✅ `docs/plan/plan.md` (section 1, Intent Router) - Lines 87-98
2. ✅ `README.md` (How It Works section) - Line 11
3. ✅ `prompts/router.md` (Intent Types section) - Lines 30-40
4. ✅ `src/intent/router.py` (IntentType enum and ROUTER_SYSTEM_PROMPT) - Lines 27-37, 88-98

## Changes Made

- Fixed `prompts/router.md` line 39: Changed "Complex multi-step work that requires durable async handling via NEEDLE bead" to "Durable async work items that escalate to NEEDLE beads" to match the canonical description in `src/intent/router.py` and `docs/plan/plan.md`

## Integration Verification

- `prompts/escalate/task-profile.md` exists and is properly integrated into the escalate strand code
- The escalate path is referenced in `src/intent/router.py` lines 312-314 (process_intent method routes TASK_PROFILE to escalate)
- `src/escalate/handler.py` and `src/escalate/llm.py` handle the escalate logic using the task-profile.md prompt

## Acceptance Criteria Met

- ✅ Intent type list is identical across plan.md, README.md, prompts/router.md, and src/intent/router.py
- ✅ All intent types have consistent descriptions
- ✅ No orphaned intent types in any file
- ✅ prompts/escalate/task-profile.md is referenced and integrated

## Notes

The intent type list was already consistent across all four files—only the task-profile description needed minor harmonization. The escalate strand properly uses `task-profile` (not `task`) as the intent type, and the escalation prompt at `prompts/escalate/task-profile.md` is correctly wired into the codebase.
