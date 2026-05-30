# Escalate Strand: Task-Profile Intent

This document defines the escalation strategy for `intent_type: task-profile` intents that require durable async handling via NEEDLE beads.

## What We Escalate

Task-profile intents are user requests that:
- Require extended work beyond a single-turn response
- Need durable tracking (survives session restart)
- Benefit from structured Claude Code execution
- May require multiple steps or research

Examples:
- "Add authentication to the Kalshi tape service"
- "Investigate why the pipeline is slow"
- "Set up monitoring for the new deployment"

## Escalation Flow

### 1. Formulate Bead Body (LLM Call)

**Model:** Claude Sonnet 4 (via ZAI proxy)
**Timeout:** 30 seconds

Given the user's intent and available context, produce a well-structured bead body that:

1. **Captures the full scope** of the request
2. **Includes relevant context** (project, cluster, specific resources)
3. **Defines clear success criteria**
4. **Structures the work** for Claude Code execution

**System Prompt:**

```
You are ADC's escalate handler. Your job is to formulate a clear, actionable NEEDLE bead body from a user's intent.

A NEEDLE bead is a task work item with:
- A clear title describing what needs to be done
- A detailed body with context, requirements, and success criteria
- Proper structure for Claude Code to execute

Given the user's intent and any available context, produce a bead body that:
1. Captures the full scope of the request
2. Includes relevant context (project, cluster, specific resources)
3. Defines clear success criteria
4. Structures the work for Claude Code execution

Output ONLY the bead body as markdown. Do not include explanations or meta-commentary.
```

**Input Context:**
- User utterance (verbatim)
- Intent type
- Project slug (if applicable)
- Topic ID (if continuing an existing topic)
- Additional context (git status, cluster state, etc.)

**Output:**

```markdown
## Task
[Clear, actionable description of what needs to be done]

## Context
[Relevant context about the project, cluster, resources]

## Success Criteria
[Specific, measurable criteria for completion]

## Implementation Notes
[Any technical details, constraints, or guidance for Claude Code]
```

### 2. Create Bead (br CLI)

**Command:**

```bash
br create \
  --title "[project-slug] task-verb..." \
  --type task \
  --metadata '{"session_id":"...","intent_id":"...","origin_surface_id":"..."}'
```

**Bead metadata includes:**
- `session_id`: For bead watcher routing
- `intent_id`: Links bead to originating intent
- `origin_surface_id`: Which surface originated the request
- `project_slug`: For project workspace routing
- `topic_id`: If continuing an existing topic

### 3. Return Pending-Card Spec

```json
{
  "type": "pending",
  "id": "pending-{bead_id}",
  "intent_id": "{intent_id}",
  "bead_id": "{bead_id}",
  "title": "[Short title from utterance]",
  "summary": "Working on: {utterance preview}",
  "status": "pending",
  "urgency": "normal|high|critical",
  "created_at": 1234567890,
  "metadata": {
    "project_slug": "...",
    "topic_id": "...",
    "bead_type": "task"
  }
}
```

## Bead Watcher Integration

Once created, the bead watcher monitors for bead closure. When the bead is closed:

1. Bead watcher receives the closure event
2. Reads bead body and extracts completion summary
3. Routes result to the originating session via SSE
4. Surface updates from pending-card to result-card

## Routing Decision

The intent router classifies task-profile intents when:
- Intent requires multi-step work
- User explicitly requests tracking ("make me a bead for...")
- Intent complexity exceeds single-turn synthesis
- Request involves implementation work

**Classification criteria:**
- Action verbs: "implement", "add", "create", "fix", "investigate"
- Scope indicators: "feature", "bug", "refactor", "optimize"
- Time indicators: "when you get a chance", "eventually"

## Fallback Behavior

- **LLM timeout**: Retry once, then escalate with simplified bead body
- **br create failure**: Return error to user, suggest manual bead creation
- **Missing project**: Ask user to specify project context

## Context Sources

For escalation, include these context fields if available:

- **Git status**: Current branch, uncommitted changes
- **Cluster state**: Relevant pod/deployment status
- **CI status**: Recent workflow runs
- **Existing beads**: Related open beads for the project
- **Topic context**: Previous turns in this topic

The escalate strand is the only strand that creates durable work items. All other strands are read-only or transient actions.
