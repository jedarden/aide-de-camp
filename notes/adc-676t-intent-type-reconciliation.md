# Intent Type Reconciliation (adc-676t)

## Task
Reconcile intent types across all documentation to ensure identical lists and descriptions.

## Changes Made

### Canonical Intent Type List (9 types)
1. **status**: Query current state (pods, pipelines, deployments, beads)
2. **action**: Execute a command (deploy, restart, create)
3. **brainstorm**: Explore options, design, architecture discussion
4. **lookup**: Find specific information (logs, configs, docs)
5. **reminder**: Set or query reminders
6. **self-modification**: Instructions to improve the interface itself
7. **monitoring-config**: Configure ambient monitoring rules
8. **task-profile**: Durable async work items that escalate to NEEDLE beads
9. **clarification**: Low-confidence routing outcome requiring user input (meta-type, not dispatched)

### Files Updated

#### 1. docs/plan/plan.md
- Added intent type descriptions list after the intent type names
- Ensured all 9 types are listed with consistent descriptions

#### 2. README.md
- Added `clarification` to the intent type list (was missing)
- Fixed inconsistent naming: "Task intents (`task` type)" → "task-profile intents"

#### 3. prompts/router.md
- Added `clarification` to the intent type list (was missing)
- Added `clarification` description to Intent Types section

#### 4. src/intent/router.py
- Added `clarification` description to ROUTER_SYSTEM_PROMPT Intent Types section
- Updated JSON schema to include `clarification` in the intent_type enum

## Verification
All four files now contain the identical 9 intent types with consistent descriptions.
The escalate prompt at `prompts/escalate/task-profile.md` already correctly references task-profile intents.

## Result
Intent type list is now identical across plan.md, README.md, prompts/router.md, and src/intent/router.py.
All intent types have consistent descriptions.
No orphaned intent types remain.
