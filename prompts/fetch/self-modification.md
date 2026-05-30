# Fetch Strand: Self-Modification Intent

This document defines the fetch strategy for `intent_type: self-modification` queries.

## What We Fetch

For a self-modification query (instructions to improve the interface itself), we need:

1. **Session state**: Current session configuration
2. **Component list**: Available components/modules
3. **Git history**: Recent changes to the codebase
4. **Error logs**: Recent errors or issues

## Command Matrix

```bash
# Get session state
session state --session ${SESSION_ID}

# List all components
components list --all

# Recent git commits
git -C ${REPO_PATH} log -5 --oneline --pretty=format:'{"hash":"%h","message":"%s","author":"%an","date":"%ar"}'

# Recent error logs (if available)
logs fetch --level error --since "1 hour ago"
```

## Parallel Execution

All sources run concurrently.

Timeout per source: 3 seconds

## Result Structure

```json
{
  "session_state": {
    "status": "success|timeout|error",
    "data": {
      "session_id": "session-id",
      "surfaces": [ /* active surfaces */ ],
      "settings": { /* current settings */ }
    }
  },
  "components": {
    "status": "success|timeout|error",
    "data": [ /* component objects */ ]
  },
  "git": {
    "status": "success|timeout|error",
    "data": {
      "commits": [ /* recent commits */ ]
    }
  },
  "errors": {
    "status": "success|timeout|error",
    "data": [ /* recent error logs */ ]
  },
  "coverage": {
    "session_state": true,
    "components": true,
    "git": true,
    "errors": false
  }
}
```

## Safety Considerations

Self-modification instructions can affect the system behavior. The fetch layer provides:

- **Current state snapshot**: What the system looks like now
- **Change history**: What's been changing lately
- **Error context**: What's been failing

This context is passed to the synthesize strand for safe modification planning.

## Context Expansion

For self-modification queries, include these context fields if available:

- **System health**: Is the system stable
- **User identity**: Who is requesting the modification
- **Session duration**: How long has this session been active

The fetch layer is deterministic. No LLM calls here — just execute the command matrix and return structured data.
