# Fetch Strand: Reminder Intent

This document defines the fetch strategy for `intent_type: reminder` queries.

## What We Fetch

For a reminder query, we need:

1. **Existing reminders**: What reminders are already set
2. **Session context**: Current session, topics in scope
3. **Time context**: Current time, timezone

## Command Matrix

```bash
# List reminders for session
reminders list --session ${SESSION_ID}

# Get session state
session state --session ${SESSION_ID}
```

## Parallel Execution

Both sources run concurrently.

Timeout per source: 3 seconds

## Result Structure

```json
{
  "reminders": {
    "status": "success|timeout|error",
    "data": {
      "reminders": [
        {
          "id": "reminder-id",
          "message": "what to remind",
          "trigger_time": "2025-01-15T10:00:00Z",
          "status": "pending|completed|cancelled"
        }
      ],
      "count": 5
    }
  },
  "session_state": {
    "status": "success|timeout|error",
    "data": {
      "session_id": "session-id",
      "current_surface": "audio",
      "active_topics": [ /* topic IDs */ ]
    }
  },
  "coverage": {
    "reminders": true,
    "session_state": true
  }
}
```

## Reminder Types

- **Time-based**: Remind at specific time
- **Interval-based**: Remind every N minutes/hours
- **Event-based**: Remind when condition met (e.g., "tell me when deployment finishes")

## Context Expansion

For reminder queries, include these context fields if available:

- **User preferences**: How they want to be reminded (audio, telegram, canvas)
- **Current timezone**: For time-based reminders
- **Active topics**: What they're working on (for context-aware reminders)

The fetch layer is deterministic. No LLM calls here — just execute the command matrix and return structured data.
