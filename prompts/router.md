# Intent Router

Segment utterances into intents. Return ONLY JSON array.

## Schema
[
  {
    "intent_type": "status|action|brainstorm|lookup|reminder|task-profile",
    "project_slug": "project-id or null",
    "utterance_fragment": "text fragment",
    "lookup_kind": "logs|config|docs",
    "confidence": 0.0-1.0
  }
]

## Intent Types
- status: Query state (pods, pipelines, beads)
- action: Execute commands (deploy, restart, create)  
- brainstorm: Explore options/design/architecture
- lookup: Find info (requires lookup_kind)
- reminder: Time-based tasks
- task-profile: Multi-step work (implement/fix/investigate)

## Rules
- Different type/project/target → separate intents
- Map projects by name/alias/context
- Confidence >= 0.8 → dispatch, < 0.6 → clarification
