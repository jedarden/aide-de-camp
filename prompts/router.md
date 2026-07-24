# Intent Router

Segment utterances into intent threads. Return ONLY a JSON array (no markdown):

```json
[
  {
    "intent_type": "status|action|brainstorm|lookup|reminder|task-profile",
    "project_slug": "project-id or null",
    "utterance_fragment": "fragment for this intent",
    "lookup_kind": "logs|config|docs",
    "confidence": 0.0-1.0
  }
]
```

## Intent Types
- **status**: Query state (pods, pipelines, deployments, beads)
- **action**: Execute commands (deploy, restart, create)
- **brainstorm**: Explore options/design/architecture
- **lookup**: Find info (requires lookup_kind: logs/config/docs)
- **reminder**: Set/query reminders (→ clarification)
- **task-profile**: Multi-step work ("implement", "add", "fix", "investigate", "refactor")

## Segmentation
Split: different projects, different intent types, independent questions
Keep together: same intent + same target, simple elaboration

## Project Routing
Map to projects using: name/alias, session context, or default

## Confidence
- >= 0.9: dispatch immediately
- < 0.7: intent_type "clarification"

Return ONLY the JSON array.
