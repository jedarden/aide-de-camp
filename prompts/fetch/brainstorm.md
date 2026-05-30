# Fetch Strand: Brainstorm Intent

This document defines the fetch strategy for `intent_type: brainstorm` queries.

## What We Fetch

For a brainstorm query, we want context for exploratory discussion:

1. **Component inventory**: What components exist in the project
2. **Recent git history**: What's been changing lately
3. **Topic context**: Previous related discussion
4. **Related topics**: What else has been discussed

## Command Matrix

```bash
# Component inventory (if project has component library)
components list --project ${PROJECT_SLUG}

# Recent git commits
git -C ${REPO_PATH} log -10 --oneline --pretty=format:'{"hash":"%h","message":"%s","author":"%an","date":"%ar"}'

# Topic context (if continuation of previous discussion)
topic context --topic ${TOPIC_ID}
```

## Parallel Execution

All fetch sources run concurrently. Partial results are passed to the Synthesize strand as they arrive.

Timeout per source: 3 seconds

## Result Structure

```json
{
  "components": {
    "status": "success|timeout|error",
    "data": [ /* component objects */ ],
    "cached_at": null
  },
  "git": {
    "status": "success|timeout|error",
    "data": {
      "commits": [ /* commit objects */ ],
      "branch": "current-branch"
    }
  },
  "topic_context": {
    "status": "success|timeout|error",
    "data": {
      "previous_discussion": [ /* related topics/intents */ ]
    }
  },
  "coverage": {
    "components": true,
    "git": true,
    "topic_context": false
  }
}
```

## Context Expansion

For brainstorm queries, include these context fields if available:

- **Project components**: List of services, modules, dependencies
- **Recent changes**: Git commits from last week
- **Previous discussion**: Related topics in the session

The fetch layer is deterministic. No LLM calls here — just execute the command matrix and return structured data.
